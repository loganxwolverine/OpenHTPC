#!/usr/bin/env python3
"""Safe local Antigravity-planner / Codex-executor orchestration for OPENHTPC.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import argparse, datetime, fnmatch, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid
from typing import Any

SCHEMA_VERSION=1
RISK_CLASSES={"DOCS_ONLY","SOFTWARE_NO_PHYSICAL","SOFTWARE_PHYSICAL_GATE","HUMAN_APPROVAL_BEFORE_EXECUTION","FORBIDDEN"}
GATE_STAGES={"NONE","BEFORE_EXECUTION","AFTER_IMPLEMENTATION"}
GATE_REASONS={"NONE","PHYSICAL_VALIDATION","PUSH","TAG","RELEASE","MERGE","REBASE","DESTRUCTIVE_GIT","SECURITY_BOUNDARY","HARDWARE_IO_OWNERSHIP","CREDENTIAL_OR_SECRET","SYSTEM_CONFIGURATION","OTHER"}
VERDICTS={"ACCEPT","REJECT","HUMAN_GATE"}
STATUSES={"PASS","FAIL","BLOCKED"}
FORBIDDEN_PATTERNS=(
 r"\bgit\s+push\b",r"\bgit\s+tag\b",r"\b(?:gh|github)\s+release\b",r"\bgit\s+merge\b",r"\bgit\s+rebase\b",
 r"\bgit\s+branch\s+-[dD]\b",r"\bgit\s+reset\s+--hard\b",r"\bgit\s+checkout\s+-f\b",r"\bgit\s+update-ref\b",
 r"\bsudo\b",r"\b(?:dnf|apt|yum|pacman|zypper)\s+(?:install|remove|upgrade)\b",r"(?:^|\s)/(?:etc|usr|dev|sys|proc)(?:/|\s|$)",
 r"~/(?:\.codex|\.gemini)(?:/|\s|$)",r"\b(?:OPENAI|GEMINI|CODEX)_API_KEY\b"
)
SECRET_PATTERNS=(
 ("API_KEY_ASSIGNMENT",re.compile(r"(?i)\b(?:GEMINI|OPENAI|CODEX)_API_KEY\s*=\s*[^\s'\"<>]{8,}")),
 ("GOOGLE_API_KEY",re.compile(r"\bAIza[0-9A-Za-z_-]{20,}")),
 ("OPENAI_STYLE_KEY",re.compile(r"\bsk-[0-9A-Za-z_-]{16,}")),
 ("PRIVATE_KEY",re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
 ("OAUTH_SECRET",re.compile(r'(?i)"(?:client_secret|refresh_token|access_token)"\s*:\s*"(?!REDACTED|EXAMPLE)[^"]{8,}"')),
)

class AutopilotError(RuntimeError):pass

def now()->str:return datetime.datetime.now(datetime.timezone.utc).isoformat()
def root_from_file()->pathlib.Path:return pathlib.Path(__file__).resolve().parents[2]

def run_command(command:list[str],cwd:pathlib.Path,timeout:int,input_text:str|None=None)->subprocess.CompletedProcess[str]:
 try:return subprocess.run(command,cwd=cwd,text=True,input=input_text,capture_output=True,timeout=timeout,check=False)
 except subprocess.TimeoutExpired as exc:raise AutopilotError(f"TIMEOUT:{command[0]}") from exc
 except OSError as exc:raise AutopilotError(f"EXECUTABLE_FAILED:{command[0]}") from exc

def git(root:pathlib.Path,*args:str,timeout:int=30)->str:
 result=run_command(["git",*args],root,timeout)
 if result.returncode:raise AutopilotError(f"GIT_FAILED:{' '.join(args)}")
 return result.stdout.strip()

def git_context(root:pathlib.Path,require_clean:bool=True)->dict[str,Any]:
 if git(root,"rev-parse","--show-toplevel")!=str(root.resolve()):raise AutopilotError("REPOSITORY_ROOT_INVALID")
 status=git(root,"status","--porcelain")
 if require_clean and status:raise AutopilotError("DIRTY_PREFLIGHT")
 return {"root":str(root),"branch":git(root,"branch","--show-current"),"head":git(root,"rev-parse","HEAD"),"status":status,
         "log":git(root,"log","-5","--oneline","--decorate")}

def load_json(path:pathlib.Path)->Any:
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError,UnicodeError) as exc:raise AutopilotError(f"JSON_INVALID:{path.name}") from exc

def _type_ok(value:Any,kind:str)->bool:
 return {"object":isinstance(value,dict),"array":isinstance(value,list),"string":isinstance(value,str),"boolean":type(value) is bool,
         "integer":isinstance(value,int) and not isinstance(value,bool)}.get(kind,True)

def validate_schema(value:Any,schema:dict[str,Any],where:str="$")->None:
 if "const" in schema and value!=schema["const"]:raise AutopilotError(f"SCHEMA_INVALID:{where}:const")
 if "enum" in schema and value not in schema["enum"]:raise AutopilotError(f"SCHEMA_INVALID:{where}:enum")
 kind=schema.get("type")
 if kind and not _type_ok(value,kind):raise AutopilotError(f"SCHEMA_INVALID:{where}:type")
 if isinstance(value,dict):
  required=set(schema.get("required",[]));missing=required-set(value)
  if missing:raise AutopilotError(f"SCHEMA_INVALID:{where}:missing:{','.join(sorted(missing))}")
  properties=schema.get("properties",{})
  if schema.get("additionalProperties") is False and set(value)-set(properties):raise AutopilotError(f"SCHEMA_INVALID:{where}:additional")
  for key,item in value.items():
   if key in properties:validate_schema(item,properties[key],f"{where}.{key}")
 if isinstance(value,list):
  if len(value)<schema.get("minItems",0):raise AutopilotError(f"SCHEMA_INVALID:{where}:minItems")
  for index,item in enumerate(value):validate_schema(item,schema.get("items",{}),f"{where}[{index}]")
 if isinstance(value,str):
  if "pattern" in schema and not re.fullmatch(schema["pattern"],value):raise AutopilotError(f"SCHEMA_INVALID:{where}:pattern")

def schema_path(root:pathlib.Path,name:str)->pathlib.Path:return root/"tools/autopilot/schemas"/name
def validate_document(root:pathlib.Path,value:Any,name:str)->Any:validate_schema(value,load_json(schema_path(root,name)));return value

def load_canonical_state(root:pathlib.Path)->dict[str,Any]:
 value=load_json(root/"OPENHTPC_CURRENT_STATE.json")
 return validate_document(root,value,"project-state.schema.json")

def validate_plan_against_state(state:dict[str,Any],plan:dict[str,Any])->None:
 expected={"default_behavior_change":state["default_behavior_change_expected"],
           "hardware_io_ownership_change":state["hardware_io_ownership_change"],
           "security_boundary_change":state["security_boundary_change"]}
 if any(plan.get(key)!=value for key,value in expected.items()):raise AutopilotError("PLAN_CONTRADICTS_CANONICAL_STATE")
 if state["software_implementation_allowed"] and state["physical_validation_required_after_implementation"]:
  required={"risk_class":"SOFTWARE_PHYSICAL_GATE","human_gate_stage":state["required_human_gate_stage"],
            "gate_reason":state["required_gate_reason"],"physical_validation_required":True,"next_step_policy":"STOP"}
  if any(plan.get(key)!=value for key,value in required.items()):raise AutopilotError("PLAN_CONTRADICTS_CANONICAL_STATE")

def plan_has_executable_step(plan:dict[str,Any])->bool:
 return plan["next_step_policy"]!="STOP" or (plan["risk_class"]=="SOFTWARE_PHYSICAL_GATE" and plan["human_gate_stage"]=="AFTER_IMPLEMENTATION")

def parse_antigravity_outer(text:str,require_structured:bool=True)->dict[str,Any]:
 try:outer=json.loads(text)
 except json.JSONDecodeError as exc:raise AutopilotError("ANTIGRAVITY_OUTER_JSON_INVALID") from exc
 if not isinstance(outer,dict) or outer.get("status")!="SUCCESS":raise AutopilotError("ANTIGRAVITY_STATUS_INVALID")
 if require_structured:
  value=outer.get("structured_output")
  if not isinstance(value,dict):raise AutopilotError("ANTIGRAVITY_STRUCTURED_OUTPUT_INVALID")
  return value
 return outer

def sanitize_commit_message(value:str)->str:
 if not isinstance(value,str) or "\n" in value or "\r" in value or len(value)>120 or len(value)<5 or value.startswith("-"):raise AutopilotError("COMMIT_MESSAGE_INVALID")
 if not re.fullmatch(r"[a-z][a-z0-9-]*(?:\([a-z0-9._-]+\))?!?: [ -~]+",value):raise AutopilotError("COMMIT_MESSAGE_INVALID")
 return value

def validate_allowed_path(value:str)->str:
 if not isinstance(value,str) or not value or "\\" in value:raise AutopilotError("ALLOWED_PATH_INVALID")
 path=pathlib.PurePosixPath(value)
 if path.is_absolute() or ".." in path.parts or path.parts[0] in {".git",".openhtpc-autopilot"}:raise AutopilotError("ALLOWED_PATH_INVALID")
 return path.as_posix()

def path_allowed(path:str,allowed:list[str])->bool:
 candidate=pathlib.PurePosixPath(path).as_posix()
 for raw in allowed:
  rule=validate_allowed_path(raw);prefix=rule.rstrip("/")
  if candidate==prefix or candidate.startswith(prefix+"/") or fnmatch.fnmatchcase(candidate,rule):return True
 return False

def policy_evaluate(plan:dict[str,Any])->dict[str,str]:
 if plan.get("risk_class") not in RISK_CLASSES or plan.get("human_gate_stage") not in GATE_STAGES or plan.get("gate_reason") not in GATE_REASONS:raise AutopilotError("POLICY_ENUM_INVALID")
 sanitize_commit_message(plan.get("commit_message",""))
 for path in plan.get("allowed_paths",[]):validate_allowed_path(path)
 haystack=json.dumps(plan,sort_keys=True)
 if plan["risk_class"]=="FORBIDDEN" or any(re.search(pattern,haystack,re.I|re.M) for pattern in FORBIDDEN_PATTERNS):return {"decision":"FORBIDDEN","stage":"BEFORE_EXECUTION","reason":"OTHER"}
 if plan["hardware_io_ownership_change"]:return {"decision":"HUMAN_GATE","stage":"BEFORE_EXECUTION","reason":"HARDWARE_IO_OWNERSHIP"}
 if plan["security_boundary_change"]:return {"decision":"HUMAN_GATE","stage":"BEFORE_EXECUTION","reason":"SECURITY_BOUNDARY"}
 if plan["risk_class"]=="HUMAN_APPROVAL_BEFORE_EXECUTION" or plan["human_gate_stage"]=="BEFORE_EXECUTION":return {"decision":"HUMAN_GATE","stage":"BEFORE_EXECUTION","reason":plan["gate_reason"]}
 if plan["physical_validation_required"] or plan["risk_class"]=="SOFTWARE_PHYSICAL_GATE":return {"decision":"EXECUTE","stage":"AFTER_IMPLEMENTATION","reason":"PHYSICAL_VALIDATION"}
 return {"decision":"EXECUTE","stage":plan["human_gate_stage"],"reason":plan["gate_reason"]}

def changed_paths(root:pathlib.Path)->list[str]:
 values=set(filter(None,git(root,"diff","--name-only").splitlines()))
 values.update(filter(None,git(root,"ls-files","--others","--exclude-standard").splitlines()))
 return sorted(values)

def scope_violations(paths:list[str],allowed:list[str])->list[str]:return [path for path in paths if not path_allowed(path,allowed)]
def head_unchanged(before:str,after:str)->bool:return bool(before==after)

def workspace_fingerprint(root:pathlib.Path)->dict[str,Any]:
 status=git(root,"status","--porcelain");paths=changed_paths(root);digest=hashlib.sha256()
 for value in (git(root,"rev-parse","HEAD"),status,git(root,"diff","--binary"),git(root,"diff","--cached","--binary")):
  digest.update(value.encode("utf-8",errors="surrogateescape"));digest.update(b"\0")
 untracked=set(filter(None,git(root,"ls-files","--others","--exclude-standard").splitlines()))
 for relative in sorted(untracked):
  path=root/relative;digest.update(relative.encode());digest.update(b"\0")
  try:
   metadata=path.lstat();digest.update(f"{metadata.st_mode}:{metadata.st_size}".encode());digest.update(b"\0")
   if path.is_symlink():digest.update(b"SYMLINK\0"+os.readlink(path).encode())
   elif path.is_file():
    with path.open("rb") as stream:
     for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
   else:digest.update(b"NONREGULAR")
  except OSError:digest.update(b"UNREADABLE")
 return {"head":git(root,"rev-parse","HEAD"),"status":status,"paths":paths,"digest":digest.hexdigest()}

def require_workspace_unchanged(before:dict[str,Any],after:dict[str,Any],error:str="ANTIGRAVITY_MUTATED_WORKSPACE")->None:
 if before!=after:raise AutopilotError(error)

def codex_doctor_success(result:subprocess.CompletedProcess[str],output:pathlib.Path)->bool:
 if result.returncode!=0 or not output.is_file():return False
 try:return output.read_text(encoding="utf-8").strip()=="CODEX_OK"
 except (OSError,UnicodeError):return False

def _installed_runtime_name(argv:list[str],home:pathlib.Path)->str|None:
 if not argv:return None
 runtime_root=home/".local/lib/openhtpc";bin_root=home/".local/bin"
 for index,raw in enumerate(argv):
  if not raw:continue
  path=pathlib.Path(raw);name=path.name
  in_runtime=path.is_absolute() and (path==runtime_root or runtime_root in path.parents)
  in_bin=path.is_absolute() and path.parent==bin_root
  if name in {"openhtpc-home.py","openhtpc-optical-monitor"} and in_runtime:return name
  if name=="openhtpc-session-start" and (in_runtime or in_bin or index==0):return name
  if name=="flex-launcher" and in_runtime:return name
 return None

def local_openhtpc_runtime_processes(proc_root:pathlib.Path=pathlib.Path("/proc"),home:pathlib.Path|None=None,limit:int=16)->list[dict[str,Any]]:
 home=(home or pathlib.Path.home()).resolve();found=[];uid=os.getuid()
 try:entries=sorted((entry for entry in proc_root.iterdir() if entry.name.isdigit()),key=lambda entry:int(entry.name))
 except OSError:return []
 for entry in entries:
  if len(found)>=limit:break
  try:
   if entry.stat().st_uid!=uid:continue
   raw=(entry/"cmdline").read_bytes()[:65536]
  except OSError:continue
  argv=[item.decode("utf-8",errors="replace") for item in raw.split(b"\0") if item]
  name=_installed_runtime_name(argv,home)
  if name:found.append({"pid":int(entry.name),"name":name})
 return found

def print_local_runtime_stop(processes:list[dict[str,Any]])->None:
 print("LOCAL_OPENHTPC_RUNTIME_ACTIVE")
 for process in processes:print(f"process={process['name']} pid={process['pid']}")

def secret_findings(text:str)->list[dict[str,str]]:
 findings=[]
 for label,pattern in SECRET_PATTERNS:
  for match in pattern.finditer(text):findings.append({"kind":label,"redacted":match.group(0)[:4]+"…REDACTED"})
 return findings

def redact_text(text:str)->str:
 for _,pattern in SECRET_PATTERNS:text=pattern.sub("[REDACTED_SECRET]",text)
 return text

def diff_for_scan(root:pathlib.Path,paths:list[str])->str:
 result=run_command(["git","diff","--no-ext-diff","--no-color","--",*paths],root,60);content=result.stdout
 tracked=set(filter(None,git(root,"ls-files","--others","--exclude-standard").splitlines()))
 for path in paths:
  if path not in tracked:continue
  candidate=root/path
  try:
   if candidate.is_file() and candidate.stat().st_size<=1_000_000:content+="\n"+candidate.read_text(encoding="utf-8")
  except (OSError,UnicodeError):pass
 return content

def test_evidence_satisfies(plan:dict[str,Any],report:dict[str,Any])->bool:
 evidence={item["command"]:item for item in report.get("tests",[])}
 return all(command in evidence and evidence[command]["return_code"]==0 and evidence[command]["result"]=="PASS" for command in plan["required_tests"])

def acceptance_ready(plan:dict[str,Any],report:dict[str,Any],review:dict[str,Any],checks:dict[str,bool])->bool:
 return all(checks.values()) and report["status"]=="PASS" and not report["policy_violations"] and report["scope_compliance"] and test_evidence_satisfies(plan,report) and review["verdict"]=="ACCEPT" and all((review["plan_compliance"],review["architecture_compliance"],review["test_evidence_accepted"],review["scope_compliance"])) and not review["blocking_findings"]

def safe_state(value:dict[str,Any])->dict[str,Any]:
 allowed={"schema_version","status","last_run_id","branch","head","last_accepted_commit","current_gate","gate_reason","created_at","updated_at"}
 result={key:value[key] for key in allowed if key in value}
 if secret_findings(json.dumps(result)):raise AutopilotError("STATE_CONTAINS_SECRET")
 return result

class Autopilot:
 def __init__(self,root:pathlib.Path):
  self.root=root.resolve();self.runtime=self.root/".openhtpc-autopilot";self.runs=self.runtime/"runs"
  self.planner_timeout=max(300,int(os.environ.get("OPENHTPC_AUTOPILOT_PLANNER_TIMEOUT","300")))
  self.reviewer_timeout=max(300,int(os.environ.get("OPENHTPC_AUTOPILOT_REVIEWER_TIMEOUT","300")))
  self.executor_timeout=int(os.environ.get("OPENHTPC_AUTOPILOT_EXECUTOR_TIMEOUT","1800"))
  self.antigravity_doctor_timeout=int(os.environ.get("OPENHTPC_AUTOPILOT_ANTIGRAVITY_DOCTOR_TIMEOUT","90"))
  self.codex_doctor_timeout=int(os.environ.get("OPENHTPC_AUTOPILOT_CODEX_DOCTOR_TIMEOUT","90"))
 def ensure_runtime(self)->None:self.runs.mkdir(parents=True,exist_ok=True)
 def write_json(self,path:pathlib.Path,value:Any)->None:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 def update_state(self,**fields:Any)->None:
  self.ensure_runtime();path=self.runtime/"state.json"
  try:value=load_json(path)
  except AutopilotError:value={"schema_version":1,"created_at":now()}
  value.update(fields,updated_at=now());self.write_json(path,safe_state(value))
 def context(self)->dict[str,Any]:
  context=git_context(self.root);context["architecture_documents"]=["AGENTS.md","PLUGIN_FRAMEWORK_P2_ARCHITECTURE.md","PLUGIN_FRAMEWORK_P2_PROTECTED_OPTICAL_BOUNDARY_FREEZE.md","OPENHTPC-PROTECTED-OPTICAL-ROADMAP.md"]
  context["canonical_project_state"]=load_canonical_state(self.root)
  state=self.runtime/"state.json";context["previous_state"]=load_json(state) if state.is_file() else None
  return context
 def _agy_command(self,prompt:str,schema:pathlib.Path|None,timeout:int)->list[str]:
  command=["agy","--mode=plan","-p",prompt,"--output-format","json","--print-timeout",f"{timeout}s"]
  if schema is not None:
   resolved=schema.resolve(strict=True);expected=(self.root/"tools/autopilot/schemas").resolve()
   if not resolved.is_file() or resolved.parent!=expected:raise AutopilotError("ANTIGRAVITY_SCHEMA_PATH_INVALID")
   command.extend(["--json-schema",str(resolved)])
  model=os.environ.get("OPENHTPC_AGY_MODEL")
  if model:
   if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}",model):raise AutopilotError("ANTIGRAVITY_MODEL_INVALID")
   command.extend(["--model",model])
  effort=os.environ.get("OPENHTPC_AGY_EFFORT")
  if effort:
   if effort not in {"low","medium","high"}:raise AutopilotError("ANTIGRAVITY_EFFORT_INVALID")
   command.extend(["--effort",effort])
  return command
 def _agy(self,prompt:str,schema:pathlib.Path|None,timeout:int)->subprocess.CompletedProcess[str]:
  return run_command(self._agy_command(prompt,schema,timeout),self.root,timeout+15)
 def _codex_doctor_command(self,output:pathlib.Path)->list[str]:
  return ["codex","exec","--sandbox","read-only","--ephemeral","-C",str(self.root),"-o",str(output),"Réponds exactement et uniquement : CODEX_OK"]
 def _codex_executor_command(self,report_path:pathlib.Path)->list[str]:
  command=["codex","exec","--approve-for-me","--ephemeral","-C",str(self.root),"--output-schema",str(schema_path(self.root,"executor-report.schema.json")),"-o",str(report_path),"-"]
  model=os.environ.get("OPENHTPC_CODEX_MODEL");command[2:2]=["--model",model] if model else []
  return command
 def plan(self,run_id:str|None=None)->tuple[pathlib.Path,dict[str,Any],dict[str,Any]]:
  self.ensure_runtime();context=self.context();run_id=run_id or datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8];run_dir=self.runs/run_id;run_dir.mkdir()
  context["run_id"]=run_id;self.write_json(run_dir/"context.json",context)
  prompt=(self.root/"tools/autopilot/prompts/planner.md").read_text()+"\n\nCANONICAL_PROJECT_STATE:\n"+json.dumps(context["canonical_project_state"],indent=2)+"\n\nCONTEXT:\n"+json.dumps(context,indent=2)
  before=workspace_fingerprint(self.root);result=self._agy(prompt,schema_path(self.root,"plan.schema.json"),self.planner_timeout)
  (run_dir/"antigravity-planner.raw.json").write_text(redact_text(result.stdout),encoding="utf-8");(run_dir/"antigravity-planner.stderr.log").write_text(redact_text(result.stderr),encoding="utf-8")
  require_workspace_unchanged(before,workspace_fingerprint(self.root))
  if result.returncode:raise AutopilotError("PLANNER_FAILED")
  plan=validate_document(self.root,parse_antigravity_outer(result.stdout),"plan.schema.json")
  if plan["run_id"]!=run_id or plan["expected_branch"]!=context["branch"] or plan["expected_head"]!=context["head"]:raise AutopilotError("PLAN_CONTEXT_MISMATCH")
  validate_plan_against_state(context["canonical_project_state"],plan)
  policy=policy_evaluate(plan);self.write_json(run_dir/"plan.json",plan);self.write_json(run_dir/"policy.json",policy)
  (run_dir/"summary.txt").write_text(f"PLAN: {plan['title']}\nRISK: {plan['risk_class']}\nPOLICY: {policy['decision']}\n",encoding="utf-8")
  self.update_state(status="PLANNED",last_run_id=run_id,branch=context["branch"],head=context["head"],current_gate=policy["stage"],gate_reason=policy["reason"])
  return run_dir,plan,policy
 def execute(self,run_dir:pathlib.Path,plan:dict[str,Any])->dict[str,Any]:
  before=git(self.root,"rev-parse","HEAD");prompt=(self.root/"tools/autopilot/prompts/executor.md").read_text()+"\n\nAGENTS:\n"+(self.root/"AGENTS.md").read_text()+"\n\nVALIDATED PLAN:\n"+json.dumps(plan,indent=2)+"\nHEAD BEFORE: "+before+"\nDO NOT COMMIT\nDO NOT PUSH\n"
  report_path=run_dir/"executor-report.json";command=self._codex_executor_command(report_path)
  result=run_command(command,self.root,self.executor_timeout,prompt);(run_dir/"codex.stderr.log").write_text(redact_text(result.stderr),encoding="utf-8")
  if result.returncode:raise AutopilotError("EXECUTOR_FAILED")
  report=validate_document(self.root,load_json(report_path),"executor-report.schema.json");after=git(self.root,"rev-parse","HEAD")
  if not head_unchanged(before,after) or report["head_before"]!=before or report["head_after"]!=after:raise AutopilotError("EXECUTOR_MUTATED_GIT_HISTORY")
  paths=changed_paths(self.root);offending=scope_violations(paths,plan["allowed_paths"])
  if offending:raise AutopilotError("PATH_SCOPE_VIOLATION:"+",".join(offending))
  check=run_command(["git","diff","--check"],self.root,60)
  if check.returncode:raise AutopilotError("GIT_DIFF_CHECK_FAILED")
  diff=diff_for_scan(self.root,paths);(run_dir/"git-diff.patch").write_text(redact_text(diff),encoding="utf-8")
  if secret_findings(diff):raise AutopilotError("SECRET_GATE")
  if sorted(report["files_changed"])!=paths:raise AutopilotError("EXECUTOR_REPORT_PATH_MISMATCH")
  if not test_evidence_satisfies(plan,report):raise AutopilotError("REQUIRED_TEST_EVIDENCE_MISSING")
  return report
 def reviewer(self,run_dir:pathlib.Path,plan:dict[str,Any],report:dict[str,Any])->dict[str,Any]:
  payload={"plan":plan,"executor_report":report,"branch":git(self.root,"branch","--show-current"),"head":git(self.root,"rev-parse","HEAD"),"git_status":git(self.root,"status","--porcelain"),"changed_paths":changed_paths(self.root),"diff_check":"PASS"}
  prompt=(self.root/"tools/autopilot/prompts/reviewer.md").read_text()+"\n\nREVIEW INPUT:\n"+json.dumps(payload,indent=2)
  before=workspace_fingerprint(self.root);result=self._agy(prompt,schema_path(self.root,"review.schema.json"),self.reviewer_timeout);(run_dir/"antigravity-reviewer.raw.json").write_text(redact_text(result.stdout),encoding="utf-8");(run_dir/"antigravity-reviewer.stderr.log").write_text(redact_text(result.stderr),encoding="utf-8")
  require_workspace_unchanged(before,workspace_fingerprint(self.root))
  if result.returncode:raise AutopilotError("REVIEWER_FAILED")
  review=validate_document(self.root,parse_antigravity_outer(result.stdout),"review.schema.json");self.write_json(run_dir/"review.json",review);return review
 def review_saved(self)->dict[str,Any]:
  state=load_json(self.runtime/"state.json");run_id=state.get("last_run_id")
  if not isinstance(run_id,str):raise AutopilotError("NO_ACTIVE_RUN")
  run_dir=self.runs/run_id;plan=validate_document(self.root,load_json(run_dir/"plan.json"),"plan.schema.json");report=validate_document(self.root,load_json(run_dir/"executor-report.json"),"executor-report.schema.json")
  review=self.reviewer(run_dir,plan,report);print(f"REVIEW: {review['verdict']}");return review
 def commit(self,plan:dict[str,Any],paths:list[str])->str:
  if not paths:raise AutopilotError("NO_CHANGES_TO_COMMIT")
  message=sanitize_commit_message(plan["commit_message"]);add=run_command(["git","add","--",*paths],self.root,60)
  if add.returncode:raise AutopilotError("GIT_ADD_FAILED")
  result=run_command(["git","commit","-m",message],self.root,120)
  if result.returncode:raise AutopilotError("LOCAL_COMMIT_FAILED")
  if git(self.root,"status","--porcelain"):raise AutopilotError("POST_COMMIT_DIRTY")
  return git(self.root,"rev-parse","HEAD")
 def run_once(self)->str:
  run_dir,plan,policy=self.plan()
  if not plan_has_executable_step(plan):self.update_state(status="NO_USEFUL_WORK",current_gate="NONE",gate_reason="NONE");return "NO_USEFUL_WORK"
  if policy["decision"] in {"FORBIDDEN","HUMAN_GATE"}:self.update_state(status="AWAITING_HUMAN_GATE",current_gate=policy["stage"],gate_reason=policy["reason"]);return "AWAITING_HUMAN_GATE"
  processes=local_openhtpc_runtime_processes()
  if processes:
   print_local_runtime_stop(processes);self.update_state(status="AWAITING_LOCAL_RUNTIME_STOP",current_gate="BEFORE_EXECUTION",gate_reason="LOCAL_RUNTIME_ACTIVE");return "AWAITING_LOCAL_RUNTIME_STOP"
  report=self.execute(run_dir,plan);review=self.reviewer(run_dir,plan,report)
  if review["verdict"]=="REJECT":self.update_state(status="REVIEW_REJECTED",current_gate="NONE",gate_reason="NONE");return "REVIEW_REJECTED"
  if review["verdict"]=="HUMAN_GATE" and review["human_gate_stage"]=="BEFORE_EXECUTION":self.update_state(status="AWAITING_HUMAN_GATE",current_gate="BEFORE_EXECUTION",gate_reason=review["gate_reason"]);return "AWAITING_HUMAN_GATE"
  checks={"repository_began_clean":True,"expected_context":True,"executor_exit":True,"head_immutable":True,"scope":True,"diff_check":True,"secret_scan":True}
  if not acceptance_ready(plan,report,review,checks):self.update_state(status="ACCEPTANCE_FAILED",current_gate="NONE",gate_reason="OTHER");return "ACCEPTANCE_FAILED"
  commit=self.commit(plan,changed_paths(self.root));after_gate=policy["stage"]=="AFTER_IMPLEMENTATION" or review["human_gate_stage"]=="AFTER_IMPLEMENTATION"
  status="AWAITING_PHYSICAL_VALIDATION" if after_gate and (policy["reason"]=="PHYSICAL_VALIDATION" or review["gate_reason"]=="PHYSICAL_VALIDATION") else "AWAITING_HUMAN_GATE" if after_gate else "ACCEPTED"
  self.update_state(status=status,last_accepted_commit=commit,head=commit,current_gate="AFTER_IMPLEMENTATION" if after_gate else "NONE",gate_reason=policy["reason"] if after_gate else "NONE");return status
 def doctor(self,online:bool=False)->int:
  checks={"repository_root":self.root.is_dir(),"git_repository":(self.root/".git").exists(),"python":sys.version_info>=(3,10),"antigravity":bool(shutil.which("agy")),"codex":bool(shutil.which("codex")),"agents":(self.root/"AGENTS.md").is_file(),"gemini_md":(self.root/"GEMINI.md").is_file(),"policy":True,"local_openhtpc_runtime_active":bool(local_openhtpc_runtime_processes())}
  try:context=git_context(self.root,require_clean=False);checks["git_status"]="CLEAN" if not context["status"] else "DIRTY";checks["branch"]=context["branch"]
  except AutopilotError:checks["git_status"]="ERROR"
  for folder in ("schemas","prompts"):checks[folder]=all((self.root/f"tools/autopilot/{folder}"/name).is_file() for name in ({"schemas":["plan.schema.json","executor-report.schema.json","review.schema.json","project-state.schema.json"],"prompts":["planner.md","executor.md","reviewer.md"]}[folder]))
  try:load_canonical_state(self.root);checks["canonical_state"]=True
  except AutopilotError:checks["canonical_state"]=False
  try:self.ensure_runtime();probe=self.runtime/".write-test";probe.write_text("ok");probe.unlink();checks["runtime_writable"]=True
  except OSError:checks["runtime_writable"]=False
  for key,executable in (("antigravity","agy"),("codex","codex")):
   if checks[key]:
    result=run_command([executable,"--version"],self.root,30);checks[key+"_version"]=result.stdout.strip() or result.stderr.strip()
  if online:
   before=workspace_fingerprint(self.root);antigravity=self._agy("Return exactly ANTIGRAVITY_OK and do nothing else.",None,self.antigravity_doctor_timeout);after=workspace_fingerprint(self.root)
   require_workspace_unchanged(before,after)
   try:envelope=parse_antigravity_outer(antigravity.stdout,require_structured=False)
   except AutopilotError:envelope={}
   checks["antigravity_online"]=antigravity.returncode==0 and str(envelope.get("response","")).strip()=="ANTIGRAVITY_OK"
   with tempfile.TemporaryDirectory() as raw:
    output=pathlib.Path(raw)/"out.txt";command=self._codex_doctor_command(output);before=workspace_fingerprint(self.root)
    codex=run_command(command,self.root,self.codex_doctor_timeout);require_workspace_unchanged(before,workspace_fingerprint(self.root),"CODEX_DOCTOR_MUTATED_WORKSPACE");checks["codex_online"]=codex_doctor_success(codex,output)
  print("OPENHTPC AUTOPILOT DOCTOR");[print(f"{key}={value}") for key,value in checks.items()]
  required={key:value for key,value in checks.items() if key!="local_openhtpc_runtime_active"}
  return 0 if all(value not in {False,"ERROR"} for value in required.values()) else 1

def bounded_steps(value:int)->int:
 if value<1 or value>5:raise AutopilotError("MAX_STEPS_INVALID")
 return value

def cli(argv:list[str]|None=None)->int:
 parser=argparse.ArgumentParser(prog="openhtpc-autopilot");sub=parser.add_subparsers(dest="command",required=True)
 doctor=sub.add_parser("doctor");doctor.add_argument("--online",action="store_true");sub.add_parser("status");sub.add_parser("plan");run=sub.add_parser("run");run.add_argument("--until-gate",action="store_true");run.add_argument("--max-steps",type=int,default=1);sub.add_parser("review")
 args=parser.parse_args(argv);pilot=Autopilot(root_from_file())
 try:
  if args.command=="doctor":return pilot.doctor(args.online)
  if args.command=="status":
   path=pilot.runtime/"state.json";print(json.dumps(load_json(path),indent=2) if path.is_file() else "AUTOPILOT_NOT_STARTED");return 0
  if args.command=="plan":
   run_dir,plan,policy=pilot.plan();print(f"OPENHTPC AUTOPILOT\nRun: {run_dir.name}\nPLAN: {plan['title']}\nRISK: {plan['risk_class']}\nPOLICY: {policy['decision']}");return 0
  if args.command=="review":pilot.review_saved();return 0
  steps=bounded_steps(args.max_steps);steps=steps if args.until_gate else 1
  for _ in range(steps):
   result=pilot.run_once();print(f"STATE: {result}")
   if result!="ACCEPTED":break
  return 0
 except AutopilotError as exc:print(f"AUTOPILOT_STOP: {exc}",file=sys.stderr);return 2

if __name__=="__main__":raise SystemExit(cli())
