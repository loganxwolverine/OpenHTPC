"""Unit tests for the deterministic OPENHTPC Autopilot policy layer."""
from __future__ import annotations
import contextlib,importlib.util,io,json,os,pathlib,sys,tempfile,time,unittest
from unittest import mock

MODULE_PATH=pathlib.Path(__file__).resolve().parents[1]/"openhtpc_autopilot.py"
SPEC=importlib.util.spec_from_file_location("openhtpc_autopilot_tested",MODULE_PATH);A=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(A)

def plan(**updates):
 value={"schema_version":1,"run_id":"run-1","title":"Bounded docs","objective":"Update one document","rationale":"Current audit",
        "expected_branch":"feature/test","expected_head":"a"*40,"scope_in":["docs"],"scope_out":["runtime"],"allowed_paths":["docs/"],
        "risk_class":"DOCS_ONLY","human_gate_stage":"NONE","gate_reason":"NONE","physical_validation_required":False,
        "default_behavior_change":False,"security_boundary_change":False,"hardware_io_ownership_change":False,
        "required_tests":["python3 -m unittest test_docs"],"commit_message":"docs: update bounded audit","next_step_policy":"CONTINUE"}
 value.update(updates);return value

def report(**updates):
 value={"schema_version":1,"status":"PASS","summary":"done","files_changed":["docs/a.md"],"tests":[{"command":"python3 -m unittest test_docs","return_code":0,"result":"PASS"}],
        "git_status":" M docs/a.md","head_before":"a"*40,"head_after":"a"*40,"scope_compliance":True,"policy_violations":[],"physical_validation_required":False,"recommended_next_action":"review"}
 value.update(updates);return value

def review(**updates):
 value={"schema_version":1,"verdict":"ACCEPT","summary":"ok","plan_compliance":True,"architecture_compliance":True,"test_evidence_accepted":True,
        "scope_compliance":True,"security_findings":[],"physical_validation_required":False,"human_gate_stage":"NONE","gate_reason":"NONE","blocking_findings":[],"recommended_next_action":"commit"}
 value.update(updates);return value

class Contracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=MODULE_PATH.parents[2]
  cls.executor_schema=A.load_json(A.schema_path(cls.root,"executor-report.schema.json"))
 def test_01_valid_plan_parsing(self):A.validate_document(self.root,plan(),"plan.schema.json")
 def test_02_invalid_plan_rejected(self):
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,{"schema_version":1},"plan.schema.json")
 def test_03_unknown_risk_rejected(self):
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,plan(risk_class="MAGIC"),"plan.schema.json")
 def test_04_malformed_executor_report_rejected(self):
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,{"status":"PASS"},"executor-report.schema.json")
 def test_05_malformed_review_rejected(self):
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,{"verdict":"ACCEPT"},"review.schema.json")
 def test_06_malformed_antigravity_outer_rejected(self):
  for value in ("not-json",'{}','{"status":"SUCCESS"}'):
   with self.assertRaises(A.AutopilotError):A.parse_antigravity_outer(value)
 def test_07_antigravity_status_and_structured_output(self):
  value={"status":"SUCCESS","response":"ok","structured_output":plan()};self.assertEqual(A.parse_antigravity_outer(json.dumps(value)),plan())
  for status in ("ERROR","WAITING","CANCELED","INTERRUPTED","INVALID"):
   with self.assertRaisesRegex(A.AutopilotError,"STATUS"):A.parse_antigravity_outer(json.dumps({"status":status,"structured_output":plan()}))
 def test_08_executor_schema_is_codex_compatible_and_strict(self):
  schema=self.executor_schema
  self.assertEqual(schema["properties"]["schema_version"]["type"],"integer")
  def audit(node):
   if not isinstance(node,dict):return
   if "const" in node or "enum" in node:self.assertIn("type",node)
   if node.get("type")=="object":
    self.assertIsInstance(node.get("properties"),dict);self.assertEqual(set(node["required"]),set(node["properties"]));self.assertIs(node.get("additionalProperties"),False)
   for value in node.values():
    if isinstance(value,dict):audit(value)
    elif isinstance(value,list):
     for item in value:audit(item)
  audit(schema)
 def test_09_executor_test_evidence_contract_is_required(self):
  tests=self.executor_schema["properties"]["tests"]
  self.assertEqual(tests["type"],"array");self.assertEqual(tests["items"]["type"],"object")
  self.assertEqual(set(tests["items"]["required"]),{"command","return_code","result"})
 def test_10_valid_executor_report_passes_local_validation(self):
  self.assertEqual(A.validate_document(self.root,report(),"executor-report.schema.json"),report())
 def test_11_invalid_executor_schema_version_is_rejected(self):
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,report(schema_version=2),"executor-report.schema.json")
 def test_12_malformed_executor_test_evidence_is_rejected(self):
  for evidence in ([{"command":"test","return_code":0}],[{"command":"test","return_code":"0","result":"PASS"}],[{"command":"test","return_code":0,"result":"UNKNOWN"}]):
   with self.subTest(evidence=evidence):
    with self.assertRaises(A.AutopilotError):A.validate_document(self.root,report(tests=evidence),"executor-report.schema.json")

class Policy(unittest.TestCase):
 def test_08_before_execution_gate_stops(self):self.assertEqual(A.policy_evaluate(plan(human_gate_stage="BEFORE_EXECUTION",gate_reason="OTHER"))["stage"],"BEFORE_EXECUTION")
 def test_09_after_implementation_physical_gate(self):
  value=A.policy_evaluate(plan(risk_class="SOFTWARE_PHYSICAL_GATE",physical_validation_required=True,human_gate_stage="AFTER_IMPLEMENTATION",gate_reason="PHYSICAL_VALIDATION"));self.assertEqual((value["decision"],value["stage"]),("EXECUTE","AFTER_IMPLEMENTATION"))
 def test_10_forbidden_operation_rejected(self):self.assertEqual(A.policy_evaluate(plan(objective="Run git push origin main"))["decision"],"FORBIDDEN")
 def test_11_hardware_and_security_boundaries_gate(self):
  self.assertEqual(A.policy_evaluate(plan(hardware_io_ownership_change=True))["reason"],"HARDWARE_IO_OWNERSHIP");self.assertEqual(A.policy_evaluate(plan(security_boundary_change=True))["reason"],"SECURITY_BOUNDARY")
 def test_12_inside_scope_accepted(self):self.assertTrue(A.path_allowed("docs/a.md",["docs/"]))
 def test_13_outside_scope_rejected(self):self.assertEqual(A.scope_violations(["payload/a.py"],["docs/"]),["payload/a.py"])
 def test_14_head_mutation_detected(self):self.assertFalse(A.head_unchanged("a"*40,"b"*40))
 def test_15_commit_message_sanitization(self):
  self.assertEqual(A.sanitize_commit_message("docs: safe local change"),"docs: safe local change")
  for value in ("-m bad","docs: first\nsecond","git push"):
   with self.assertRaises(A.AutopilotError):A.sanitize_commit_message(value)
 def test_16_max_steps_guard(self):
  self.assertEqual(A.bounded_steps(5),5)
  for value in (0,6):
   with self.assertRaises(A.AutopilotError):A.bounded_steps(value)

class AcceptanceAndSecrets(unittest.TestCase):
 def checks(self):return {name:True for name in ("repository_began_clean","expected_context","executor_exit","head_immutable","scope","diff_check","secret_scan")}
 def test_17_accept_requirements(self):self.assertTrue(A.acceptance_ready(plan(),report(),review(),self.checks()))
 def test_18_reviewer_reject_blocks_commit(self):self.assertFalse(A.acceptance_ready(plan(),report(),review(verdict="REJECT",blocking_findings=["bad"]),self.checks()))
 def test_19_reviewer_human_gate_blocks_acceptance(self):self.assertFalse(A.acceptance_ready(plan(),report(),review(verdict="HUMAN_GATE",human_gate_stage="AFTER_IMPLEMENTATION",gate_reason="PHYSICAL_VALIDATION"),self.checks()))
 def test_20_missing_test_evidence_rejected(self):self.assertFalse(A.acceptance_ready(plan(),report(tests=[]),review(),self.checks()))
 def test_21_secret_detection_and_redaction(self):
  secret="OPENAI_"+"API_KEY="+"sk-"+"abcdefghijklmnop1234";self.assertTrue(A.secret_findings(secret));self.assertNotIn("abcdefghijklmnop",A.redact_text(secret))
 def test_22_runtime_state_serialization_is_bounded(self):
  value=A.safe_state({"schema_version":1,"status":"OK","created_at":"x","updated_at":"x","raw_agent_response":"hidden"});self.assertNotIn("raw_agent_response",value)
 def test_23_secret_not_stored_in_state(self):
  secret="OPENAI_"+"API_KEY="+"sk-"+"abcdefghijklmnop1234"
  with self.assertRaises(A.AutopilotError):A.safe_state({"schema_version":1,"status":secret})

class ProcessAndPreflight(unittest.TestCase):
 def test_24_timeout_handling(self):
  with self.assertRaisesRegex(A.AutopilotError,"TIMEOUT"):A.run_command([sys.executable,"-c","import time;time.sleep(.2)"],pathlib.Path.cwd(),0.01)
 def test_25_dirty_preflight_rejected(self):
  with mock.patch.object(A,"git",side_effect=[str(pathlib.Path.cwd().resolve())," M file"]):
   with self.assertRaisesRegex(A.AutopilotError,"DIRTY_PREFLIGHT"):A.git_context(pathlib.Path.cwd())
 def test_26_missing_antigravity_executable(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);(root/".git").mkdir();pilot=A.Autopilot(root)
   with mock.patch.object(A.shutil,"which",side_effect=lambda name:None if name=="agy" else "/bin/true"),mock.patch.object(A,"git_context",return_value={"status":"","branch":"x"}),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(pilot.doctor(False),1)
 def test_27_missing_codex_executable(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);(root/".git").mkdir();pilot=A.Autopilot(root)
   with mock.patch.object(A.shutil,"which",side_effect=lambda name:None if name=="codex" else "/bin/true"),mock.patch.object(A,"git_context",return_value={"status":"","branch":"x"}),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(pilot.doctor(False),1)
 def test_28_gemini_executable_is_not_required(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);(root/".git").mkdir();pilot=A.Autopilot(root);calls=[]
   def lookup(name):
    calls.append(name);return "/bin/true"
   with mock.patch.object(A.shutil,"which",side_effect=lookup),mock.patch.object(A,"git_context",return_value={"status":"","branch":"x"}),contextlib.redirect_stdout(io.StringIO()):pilot.doctor(False)
   self.assertNotIn("gemini",calls);self.assertIn("agy",calls)

class LocalRuntimeIsolation(unittest.TestCase):
 def setUp(self):self.home=pathlib.Path("/home/tester")
 def classify(self,*argv):return A._installed_runtime_name(list(argv),self.home)
 def test_29_no_runtime_allows_execution_to_continue(self):
  pilot=A.Autopilot(MODULE_PATH.parents[2]);run_dir=pathlib.Path("/tmp/run");calls=[]
  with mock.patch.object(pilot,"plan",return_value=(run_dir,plan(),A.policy_evaluate(plan()))),mock.patch.object(A,"local_openhtpc_runtime_processes",return_value=[]),mock.patch.object(pilot,"execute",side_effect=lambda *_:calls.append("execute") or report()),mock.patch.object(pilot,"reviewer",return_value=review()),mock.patch.object(pilot,"commit",return_value="b"*40),mock.patch.object(pilot,"update_state"):
   self.assertEqual(pilot.run_once(),"ACCEPTED")
  self.assertEqual(calls,["execute"])
 def test_30_detects_canonical_installed_runtime_forms(self):
  cases=(("python3",str(self.home/".local/lib/openhtpc/openhtpc-home.py"),"openhtpc-home.py"),("bash",str(self.home/".local/lib/openhtpc/openhtpc-optical-monitor"),"openhtpc-optical-monitor"),("systemd-inhibit",str(self.home/".local/bin/openhtpc-session-start"),"openhtpc-session-start"),(str(self.home/".local/lib/openhtpc/flex/bin/flex-launcher"),"flex-launcher"))
  for case in cases:
   with self.subTest(case=case):self.assertEqual(self.classify(*case[:-1]),case[-1])
 def test_31_unrelated_flex_and_prompt_text_do_not_match(self):
  self.assertIsNone(self.classify("/opt/other/flex-launcher"))
  self.assertIsNone(self.classify("rg","openhtpc-home.py",str(self.home/"source/test_openhtpc-optical-monitor.py"),"prompt mentions openhtpc-session-start"))
 def test_32_proc_scan_is_current_user_bounded_and_structured(self):
  with tempfile.TemporaryDirectory() as raw:
   proc=pathlib.Path(raw);entry=proc/"4321";entry.mkdir();(entry/"cmdline").write_bytes(b"python3\0"+str(self.home/".local/lib/openhtpc/openhtpc-home.py").encode()+b"\0")
   self.assertEqual(A.local_openhtpc_runtime_processes(proc,self.home),[{"pid":4321,"name":"openhtpc-home.py"}])
 def test_33_active_runtime_blocks_executor_and_records_gate(self):
  pilot=A.Autopilot(MODULE_PATH.parents[2]);processes=[{"pid":123,"name":"openhtpc-home.py"}]
  with mock.patch.object(pilot,"plan",return_value=(pathlib.Path("/tmp/run"),plan(),A.policy_evaluate(plan()))),mock.patch.object(A,"local_openhtpc_runtime_processes",return_value=processes),mock.patch.object(pilot,"execute") as execute,mock.patch.object(pilot,"update_state") as state,contextlib.redirect_stdout(io.StringIO()) as output:
   self.assertEqual(pilot.run_once(),"AWAITING_LOCAL_RUNTIME_STOP")
  execute.assert_not_called();state.assert_called_once_with(status="AWAITING_LOCAL_RUNTIME_STOP",current_gate="BEFORE_EXECUTION",gate_reason="LOCAL_RUNTIME_ACTIVE");self.assertIn("process=openhtpc-home.py pid=123",output.getvalue())
 def test_34_plan_remains_independent_of_runtime_detection(self):
  import inspect
  self.assertNotIn("local_openhtpc_runtime_processes",inspect.getsource(A.Autopilot.plan))
 def test_35_doctor_reports_runtime_without_making_it_failure(self):
  pilot=A.Autopilot(MODULE_PATH.parents[2])
  with mock.patch.object(A,"local_openhtpc_runtime_processes",return_value=[{"pid":1,"name":"openhtpc-home.py"}]),mock.patch.object(A.shutil,"which",return_value="/bin/true"),contextlib.redirect_stdout(io.StringIO()) as output:
   result=pilot.doctor(False)
  self.assertEqual(result,0);self.assertIn("local_openhtpc_runtime_active=True",output.getvalue())
 def test_36_detection_has_no_process_control(self):
  import inspect
  source=inspect.getsource(A.local_openhtpc_runtime_processes)+inspect.getsource(A.print_local_runtime_stop)
  self.assertNotIn("os.kill(",source);self.assertNotIn("subprocess",source)
 def test_37_existing_human_gate_precedes_runtime_check(self):
  pilot=A.Autopilot(MODULE_PATH.parents[2]);gated=plan(human_gate_stage="BEFORE_EXECUTION",gate_reason="OTHER")
  with mock.patch.object(pilot,"plan",return_value=(pathlib.Path("/tmp/run"),gated,A.policy_evaluate(gated))),mock.patch.object(A,"local_openhtpc_runtime_processes") as detection,mock.patch.object(pilot,"update_state"):
   self.assertEqual(pilot.run_once(),"AWAITING_HUMAN_GATE")
  detection.assert_not_called()

class AntigravityReadonlyHeadless(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=MODULE_PATH.parents[2];cls.pilot=A.Autopilot(cls.root)
  cls.plan_command=cls.pilot._agy_command("plan",A.schema_path(cls.root,"plan.schema.json"),cls.pilot.planner_timeout)
  cls.review_command=cls.pilot._agy_command("review",A.schema_path(cls.root,"review.schema.json"),cls.pilot.reviewer_timeout)
 def test_29_commands_use_antigravity(self):self.assertEqual(self.plan_command[0],"agy");self.assertEqual(self.review_command[0],"agy")
 def test_30_commands_force_plan_mode(self):self.assertIn("--mode=plan",self.plan_command);self.assertIn("--mode=plan",self.review_command)
 def test_31_commands_exclude_dangerous_modes(self):
  for command in (self.plan_command,self.review_command):self.assertNotIn("--mode=accept-edits",command);self.assertNotIn("--dangerously-skip-permissions",command)
 def test_32_commands_use_json_and_native_schema(self):
  for command,schema in ((self.plan_command,"plan.schema.json"),(self.review_command,"review.schema.json")):
   self.assertEqual(command[command.index("--output-format")+1],"json");self.assertEqual(pathlib.Path(command[command.index("--json-schema")+1]).name,schema)
 def test_33_missing_structured_output_rejected(self):
  with self.assertRaisesRegex(A.AutopilotError,"STRUCTURED_OUTPUT"):A.parse_antigravity_outer(json.dumps({"status":"SUCCESS","response":"text"}))
 def test_34_doctor_envelope_without_schema(self):self.assertEqual(A.parse_antigravity_outer(json.dumps({"status":"SUCCESS","response":"ANTIGRAVITY_OK"}),False)["response"],"ANTIGRAVITY_OK")
 def test_35_doctor_command_uses_antigravity_plan_mode(self):
  command=self.pilot._agy_command("doctor",None,90);self.assertEqual(command[0],"agy");self.assertIn("--mode=plan",command);self.assertNotIn("--json-schema",command)
 def test_36_planner_workspace_mutation_detected(self):
  before={"head":"a","status":"","paths":[],"digest":"1"};after={**before,"digest":"2"}
  with self.assertRaisesRegex(A.AutopilotError,"ANTIGRAVITY_MUTATED_WORKSPACE"):A.require_workspace_unchanged(before,after)
 def test_37_reviewer_workspace_mutation_detected(self):
  before={"head":"a","status":" M x","paths":["x"],"digest":"1"};after={**before,"status":" M y","paths":["y"]}
  with self.assertRaisesRegex(A.AutopilotError,"ANTIGRAVITY_MUTATED_WORKSPACE"):A.require_workspace_unchanged(before,after)
 def test_38_workspace_unchanged_accepted(self):
  value={"head":"a","status":" M x","paths":["x"],"digest":"1"};A.require_workspace_unchanged(value,dict(value))
 def test_39_review_structured_output_is_locally_revalidated(self):
  value=review();parsed=A.parse_antigravity_outer(json.dumps({"status":"SUCCESS","structured_output":value}));self.assertEqual(A.validate_document(self.root,parsed,"review.schema.json"),value)
 def test_40_optional_model_and_effort(self):
  with mock.patch.dict(os.environ,{"OPENHTPC_AGY_MODEL":"model-safe","OPENHTPC_AGY_EFFORT":"high"}):
   command=self.pilot._agy_command("x",None,90);self.assertEqual(command[command.index("--model")+1],"model-safe");self.assertEqual(command[command.index("--effort")+1],"high")
 def test_41_invalid_model_or_effort_rejected(self):
  with mock.patch.dict(os.environ,{"OPENHTPC_AGY_MODEL":"bad value"}):
   with self.assertRaises(A.AutopilotError):self.pilot._agy_command("x",None,90)
  with mock.patch.dict(os.environ,{"OPENHTPC_AGY_EFFORT":"extreme"}):
   with self.assertRaises(A.AutopilotError):self.pilot._agy_command("x",None,90)
 def test_42_gemini_cli_not_in_runtime_command(self):
  self.assertNotIn("gemini",self.plan_command);self.assertNotIn("gemini",self.review_command)
 def test_43_timeout_defaults_are_bounded_and_sane(self):
  self.assertGreaterEqual(self.pilot.planner_timeout,300);self.assertGreaterEqual(self.pilot.reviewer_timeout,300)
  self.assertEqual(self.pilot.antigravity_doctor_timeout,90);self.assertEqual(self.pilot.codex_doctor_timeout,90);self.assertGreater(self.pilot.executor_timeout,self.pilot.planner_timeout)
 def test_44_print_timeout_is_explicit(self):self.assertEqual(self.plan_command[self.plan_command.index("--print-timeout")+1],"300s")
 def test_45_codex_online_doctor_is_read_only_without_approval_routing(self):
  command=self.pilot._codex_doctor_command(pathlib.Path("/tmp/output.txt"))
  self.assertEqual(command[command.index("--sandbox")+1],"read-only");self.assertNotIn("--approve-for-me",command);self.assertNotIn("--ask-for-approval",command);self.assertIn("--ephemeral",command);self.assertIn("-o",command);self.assertNotIn("--output-schema",command)
 def test_46_codex_doctor_exact_success(self):
  with tempfile.TemporaryDirectory() as raw:
   output=pathlib.Path(raw)/"out.txt";output.write_text("CODEX_OK\n");self.assertTrue(A.codex_doctor_success(mock.Mock(returncode=0),output))
 def test_47_codex_doctor_wrong_or_missing_output(self):
  with tempfile.TemporaryDirectory() as raw:
   output=pathlib.Path(raw)/"out.txt";output.write_text("not ok");self.assertFalse(A.codex_doctor_success(mock.Mock(returncode=0),output));output.unlink();self.assertFalse(A.codex_doctor_success(mock.Mock(returncode=0),output))
 def test_48_codex_doctor_nonzero_return(self):
  with tempfile.TemporaryDirectory() as raw:
   output=pathlib.Path(raw)/"out.txt";output.write_text("CODEX_OK");self.assertFalse(A.codex_doctor_success(mock.Mock(returncode=1),output))
 def test_49_codex_doctor_workspace_mutation_detected(self):
  before={"head":"a","status":"","paths":[],"digest":"1"};after={**before,"paths":["changed"],"digest":"2"}
  with self.assertRaisesRegex(A.AutopilotError,"CODEX_DOCTOR_MUTATED_WORKSPACE"):A.require_workspace_unchanged(before,after,"CODEX_DOCTOR_MUTATED_WORKSPACE")
 def test_50_normal_executor_keeps_structured_report_contract(self):
  report_path=pathlib.Path("/tmp/executor-report.json");command=self.pilot._codex_executor_command(report_path)
  self.assertIn("--approve-for-me",command);self.assertNotIn("--sandbox",command);self.assertNotIn("danger-full-access",command)
  self.assertIn("--ephemeral",command);self.assertEqual(pathlib.Path(command[command.index("--output-schema")+1]).name,"executor-report.schema.json")
  self.assertEqual(pathlib.Path(command[command.index("-o")+1]),report_path)
 def test_51_executor_prompt_and_safety_guards_remain(self):
  source=MODULE_PATH.read_text(encoding="utf-8")
  for contract in ('DO NOT COMMIT\\nDO NOT PUSH\\n','head_unchanged(before,after)','scope_violations(paths,plan["allowed_paths"])'):
   self.assertIn(contract,source)

class CanonicalProjectState(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=MODULE_PATH.parents[2];cls.state=A.load_canonical_state(cls.root)
 def cutover_plan(self,**updates):
  value=plan(risk_class="SOFTWARE_PHYSICAL_GATE",human_gate_stage="AFTER_IMPLEMENTATION",gate_reason="PHYSICAL_VALIDATION",
             physical_validation_required=True,default_behavior_change=True,hardware_io_ownership_change=False,
             security_boundary_change=False,next_step_policy="STOP")
  value.update(updates);return value
 def test_51_canonical_state_parses(self):self.assertEqual(self.state["schema_version"],1)
 def test_52_malformed_state_rejected(self):
  value=dict(self.state);value.pop("next_action")
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,value,"project-state.schema.json")
 def test_53_unknown_state_schema_rejected(self):
  value=dict(self.state);value["schema_version"]=2
  with self.assertRaises(A.AutopilotError):A.validate_document(self.root,value,"project-state.schema.json")
 def test_54_planner_context_receives_canonical_state(self):
  with mock.patch.object(A,"git_context",return_value={"root":str(self.root),"branch":"x","head":"a"*40,"status":"","log":""}):
   self.assertEqual(A.Autopilot(self.root).context()["canonical_project_state"],self.state)
 def test_55_architecture_freeze_is_not_development_stop(self):
  prompt=(self.root/"tools/autopilot/prompts/planner.md").read_text(encoding="utf-8")
  self.assertIn("does not mean all protected-optical development is finished",prompt)
  self.assertEqual((self.state["architectural_boundary"],self.state["plugin_cutover_status"]),("FROZEN_AFTER_PHASE11","INCOMPLETE"))
 def test_56_implement_then_gate_policy_executes(self):
  decision=A.policy_evaluate(self.cutover_plan());self.assertEqual((decision["decision"],decision["stage"],decision["reason"]),("EXECUTE","AFTER_IMPLEMENTATION","PHYSICAL_VALIDATION"))
 def test_57_future_physical_validation_is_after_implementation(self):
  value=self.cutover_plan();A.validate_plan_against_state(self.state,value);self.assertTrue(A.plan_has_executable_step(value))
 def test_58_physical_task_can_require_before_execution(self):
  value=plan(risk_class="HUMAN_APPROVAL_BEFORE_EXECUTION",human_gate_stage="BEFORE_EXECUTION",gate_reason="SYSTEM_CONFIGURATION")
  self.assertEqual(A.policy_evaluate(value)["stage"],"BEFORE_EXECUTION")
 def test_59_current_state_rejects_docs_only_stop(self):
  with self.assertRaisesRegex(A.AutopilotError,"PLAN_CONTRADICTS_CANONICAL_STATE"):
   A.validate_plan_against_state(self.state,plan(next_step_policy="STOP",objective="No further automated work"))
 def test_60_current_state_rejects_missing_physical_validation(self):
  with self.assertRaisesRegex(A.AutopilotError,"PLAN_CONTRADICTS_CANONICAL_STATE"):
   A.validate_plan_against_state(self.state,self.cutover_plan(physical_validation_required=False))
 def test_61_current_state_rejects_default_behavior_downgrade(self):
  with self.assertRaisesRegex(A.AutopilotError,"PLAN_CONTRADICTS_CANONICAL_STATE"):
   A.validate_plan_against_state(self.state,self.cutover_plan(default_behavior_change=False))
 def test_62_current_state_rejects_hardware_ownership_change(self):
  with self.assertRaisesRegex(A.AutopilotError,"PLAN_CONTRADICTS_CANONICAL_STATE"):
   A.validate_plan_against_state(self.state,self.cutover_plan(hardware_io_ownership_change=True))
 def test_63_current_state_rejects_security_boundary_change(self):
  with self.assertRaisesRegex(A.AutopilotError,"PLAN_CONTRADICTS_CANONICAL_STATE"):
   A.validate_plan_against_state(self.state,self.cutover_plan(security_boundary_change=True))
 def test_64_current_state_accepts_software_physical_gate(self):A.validate_plan_against_state(self.state,self.cutover_plan())
 def test_65_stop_policy_is_post_implementation(self):self.assertTrue(A.plan_has_executable_step(self.cutover_plan()))
 def test_66_ordinary_stop_plan_has_no_executable_step(self):self.assertFalse(A.plan_has_executable_step(plan(next_step_policy="STOP")))

if __name__=="__main__":unittest.main()
