#!/usr/bin/env python3
"""OPENHTPC Plugin Framework P2: declarative registry foundation."""
from __future__ import annotations

import importlib.util,json,os,pathlib,re,tempfile
from typing import Any

SCHEMA="openhtpc-plugin-v2"
PLUGIN_API=2
PLUGIN_STATES={"INSTALLED","NOT_INSTALLED","DISABLED","AVAILABLE","INCOMPATIBLE","BROKEN",
               "DEPENDENCY_MISSING","DEPENDENCY_UNKNOWN","DEPENDENCY_INVALID","DEPENDENCY_CYCLE"}
DEPENDENCY_STATES={"SATISFIED","MISSING","UNKNOWN","INVALID","CYCLE"}
DEPENDENCY_FACTS_SCHEMA="openhtpc-plugin-dependency-facts-v1"
DEPENDENCY_FACT_STATUSES={"AVAILABLE","NOT_AVAILABLE","UNKNOWN"}
FIELDS={"schema","id","name","version","plugin_api","openhtpc","category","entrypoint","capabilities",
        "dependencies","system_dependencies","enabled_by_default","doctor","resources"}
CATEGORIES={"optical","media","service","presentation","system"}
HOOKS={"capability","doctor","ui_menu","media_handler","dispatcher"}
ID_RE=re.compile(r"^plugin\.[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_RE=re.compile(r"^[^\W_][\w .+()-]{0,79}$")
VERSION_RE=re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$")
TOKEN_RE=re.compile(r"^[a-z][a-z0-9-]{0,63}$")
RESOURCE_KEYS={"BLURAY","UHD_BLURAY"}

class PluginError(ValueError):pass

def paths(home:pathlib.Path,install:pathlib.Path)->dict[str,Any]:
 return {"available":[install/"plugins/available",home/".local/share/openhtpc/plugins/available"],
         "enabled":home/".config/openhtpc/plugins-enabled-v2.json",
         "data":home/".local/share/openhtpc/plugin-data","cache":home/".cache/openhtpc/plugins",
         "runtime":home/".local/state/openhtpc/plugins","snapshot":home/".local/state/openhtpc/plugin-registry-v2.json"}

def _read_json(path:pathlib.Path)->Any:
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError,UnicodeError):return None

def _atomic_json(path:pathlib.Path,value:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
 try:
  with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(value,stream,ensure_ascii=False,indent=2,sort_keys=True);stream.write("\n");stream.flush();os.fsync(stream.fileno())
  os.chmod(name,0o600);os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)

def _version(value:str)->tuple[int,int,int]|None:
 match=VERSION_RE.fullmatch(value) if isinstance(value,str) else None
 return tuple(map(int,match.groups()[:3])) if match else None

def _unique_strings(value:Any,pattern:re.Pattern[str]|None=None)->bool:
 return (isinstance(value,list) and all(isinstance(item,str) and (pattern is None or pattern.fullmatch(item)) for item in value)
         and len(value)==len(set(value)))

def validate_dependency_facts(value:Any)->tuple[bool,str]:
 if not isinstance(value,dict) or set(value)!={"schema","capabilities","system"}:return False,"DEPENDENCY_FACTS_SCHEMA_INVALID"
 if value.get("schema")!=DEPENDENCY_FACTS_SCHEMA:return False,"DEPENDENCY_FACTS_SCHEMA_INVALID"
 for kind in ("capabilities","system"):
  facts=value.get(kind)
  if not isinstance(facts,dict):return False,"DEPENDENCY_FACTS_SCHEMA_INVALID"
  for name,fact in facts.items():
   if not isinstance(name,str) or not TOKEN_RE.fullmatch(name):return False,"DEPENDENCY_FACT_INVALID"
   if (not isinstance(fact,dict) or set(fact)!={"status","source"} or not isinstance(fact.get("status"),str) or
       fact["status"] not in DEPENDENCY_FACT_STATUSES or
       not isinstance(fact.get("source"),str) or not fact["source"]):return False,"DEPENDENCY_FACT_INVALID"
 return True,"PASS"

def _dependency_item(kind:str,name:str,status:str,reason:str,source:str|None=None)->dict[str,Any]:
 result={"kind":kind,"id":name,"status":status,"reason":reason}
 if source is not None:result["source"]=source
 return result

def resolve_dependencies(value:dict[str,Any],facts:Any)->dict[str,Any]:
 """Resolve declarations against explicit Core facts without collecting or executing anything."""
 valid_facts,facts_reason=validate_dependency_facts(facts)
 plugins=value.get("plugins",[]) if isinstance(value,dict) and isinstance(value.get("plugins"),list) else []
 by_id={item["id"]:item for item in plugins if isinstance(item,dict) and isinstance(item.get("id"),str)}
 errors=value.get("errors",[]) if isinstance(value,dict) and isinstance(value.get("errors"),list) else []
 invalid_ids={item.get("id") for item in errors if isinstance(item,dict) and isinstance(item.get("id"),str)}
 cycle_nodes:set[str]=set();visiting:list[str]=[];visited:set[str]=set()
 def find_cycles(plugin_id:str)->None:
  if plugin_id in visiting:
   cycle_nodes.update(visiting[visiting.index(plugin_id):]);return
  if plugin_id in visited:return
  visiting.append(plugin_id)
  item=by_id.get(plugin_id,{})
  dependencies=item.get("dependencies",{}).get("plugins",[]) if isinstance(item.get("dependencies"),dict) else []
  for dependency in dependencies:
   if dependency in by_id:find_cycles(dependency)
  visiting.pop();visited.add(plugin_id)
 for plugin_id in sorted(by_id):find_cycles(plugin_id)
 cache:dict[str,dict[str,Any]]={};resolving:set[str]=set()
 def resolve(plugin_id:str)->dict[str,Any]:
  if plugin_id in cache:return cache[plugin_id]
  item=by_id[plugin_id];rows=[]
  if not valid_facts:
   rows.append(_dependency_item("facts",DEPENDENCY_FACTS_SCHEMA,"INVALID",facts_reason))
   for kind,key in (("capability","capabilities"),("system","system_dependencies")):
    names=item.get("dependencies",{}).get(key,[]) if kind=="capability" else item.get(key,[])
    rows.extend(_dependency_item(kind,name,"INVALID",facts_reason) for name in names)
  else:
   for kind,key in (("capability","capabilities"),("system","system_dependencies")):
    names=item.get("dependencies",{}).get(key,[]) if kind=="capability" else item.get(key,[])
    fact_map=facts["capabilities" if kind=="capability" else "system"]
    for name in names:
     fact=fact_map.get(name)
     if fact is None:rows.append(_dependency_item(kind,name,"UNKNOWN",f"{kind.upper()}_DEPENDENCY_UNKNOWN"));continue
     status={"AVAILABLE":"SATISFIED","NOT_AVAILABLE":"MISSING","UNKNOWN":"UNKNOWN"}[fact["status"]]
     reason="PASS" if status=="SATISFIED" else f"{kind.upper()}_DEPENDENCY_{status}"
     rows.append(_dependency_item(kind,name,status,reason,fact["source"]))
  resolving.add(plugin_id)
  plugin_dependencies=item.get("dependencies",{}).get("plugins",[])
  for name in plugin_dependencies:
   target=by_id.get(name)
   if name in cycle_nodes:rows.append(_dependency_item("plugin",name,"CYCLE","PLUGIN_DEPENDENCY_CYCLE"))
   elif target is None:
    status="INVALID" if name in invalid_ids else "MISSING"
    rows.append(_dependency_item("plugin",name,status,"PLUGIN_DEPENDENCY_INVALID" if status=="INVALID" else "PLUGIN_DEPENDENCY_NOT_INSTALLED"))
   elif target.get("state")=="DISABLED":rows.append(_dependency_item("plugin",name,"MISSING","PLUGIN_DEPENDENCY_DISABLED"))
   elif target.get("state")=="INCOMPATIBLE":rows.append(_dependency_item("plugin",name,"MISSING","PLUGIN_DEPENDENCY_INCOMPATIBLE"))
   elif name in resolving:rows.append(_dependency_item("plugin",name,"CYCLE","PLUGIN_DEPENDENCY_CYCLE"))
   else:
    target_resolution=resolve(name);status=target_resolution["status"]
    rows.append(_dependency_item("plugin",name,status,"PASS" if status=="SATISFIED" else "PLUGIN_DEPENDENCY_"+status))
  resolving.discard(plugin_id)
  priority=("INVALID","CYCLE","MISSING","UNKNOWN")
  status=next((candidate for candidate in priority if any(row["status"]==candidate for row in rows)),"SATISFIED")
  reason=next((row["reason"] for candidate in priority for row in rows if row["status"]==candidate),"PASS")
  cache[plugin_id]={"status":status,"reason":reason,"dependencies":rows};return cache[plugin_id]
 for plugin_id,item in by_id.items():
  resolution=resolve(plugin_id);item["dependency_resolution"]=resolution
  if item.get("state")=="AVAILABLE" and resolution["status"]!="SATISFIED":item["state"]="DEPENDENCY_"+resolution["status"]
 return value

def _safe_entrypoint(plugin_dir:pathlib.Path,value:Any)->bool:
 if value is None:return True
 if not isinstance(value,str) or not value or "\\" in value:return False
 relative=pathlib.PurePosixPath(value)
 if relative.is_absolute() or ".." in relative.parts or relative.name in {"",".",".."}:return False
 try:
  root=plugin_dir.resolve(strict=True);candidate=(plugin_dir/pathlib.Path(*relative.parts)).resolve(strict=True)
  return candidate.is_relative_to(root) and candidate.is_file() and not (plugin_dir/pathlib.Path(*relative.parts)).is_symlink()
 except OSError:return False

def _safe_resource(plugin_dir:pathlib.Path,value:Any)->pathlib.Path|None:
 if not isinstance(value,str) or not value or "\\" in value or "://" in value:return None
 relative=pathlib.PurePosixPath(value)
 if relative.is_absolute() or ".." in relative.parts or len(relative.parts)!=2 or relative.parts[0]!="assets" or relative.suffix.lower()!=".png":return None
 unresolved=plugin_dir/pathlib.Path(*relative.parts)
 try:
  root=plugin_dir.resolve(strict=True);asset_root=(plugin_dir/"assets").resolve(strict=True);candidate=unresolved.resolve(strict=True)
  if unresolved.is_symlink() or (plugin_dir/relative.parts[0]).is_symlink():return None
  return candidate if candidate.is_relative_to(root) and candidate.is_relative_to(asset_root) and candidate.is_file() and not candidate.is_symlink() else None
 except OSError:return None

def validate_manifest(value:Any,plugin_dir:pathlib.Path,core_version:str)->tuple[bool,str,bool]:
 if not isinstance(value,dict) or set(value)!=FIELDS or value.get("schema")!=SCHEMA:return False,"PLUGIN_SCHEMA_INVALID",False
 if not isinstance(value.get("id"),str) or not ID_RE.fullmatch(value["id"]) or plugin_dir.name!=value["id"]:return False,"PLUGIN_ID_INVALID",False
 if not isinstance(value.get("name"),str) or not NAME_RE.fullmatch(value["name"]):return False,"PLUGIN_NAME_INVALID",False
 if _version(value.get("version")) is None:return False,"PLUGIN_VERSION_INVALID",False
 if type(value.get("plugin_api")) is not int or value["plugin_api"]!=PLUGIN_API:return False,"PLUGIN_API_UNSUPPORTED",False
 requirement=value.get("openhtpc")
 if not isinstance(requirement,dict) or set(requirement)!={"minimum","maximum"} or _version(requirement.get("minimum")) is None:return False,"PLUGIN_COMPATIBILITY_INVALID",False
 if requirement.get("maximum") is not None and _version(requirement["maximum"]) is None:return False,"PLUGIN_COMPATIBILITY_INVALID",False
 if value.get("category") not in CATEGORIES:return False,"PLUGIN_CATEGORY_INVALID",False
 if not _safe_entrypoint(plugin_dir,value.get("entrypoint")):return False,"PLUGIN_PATH_INVALID",False
 capabilities=value.get("capabilities")
 if not _unique_strings(capabilities) or any(item not in HOOKS for item in capabilities):return False,"PLUGIN_CAPABILITIES_INVALID",False
 dependencies=value.get("dependencies")
 if not isinstance(dependencies,dict) or set(dependencies)!={"plugins","capabilities"}:return False,"PLUGIN_DEPENDENCIES_INVALID",False
 for key in ("plugins","capabilities"):
  items=dependencies[key]
  pattern=ID_RE if key=="plugins" else TOKEN_RE
  if not _unique_strings(items,pattern):return False,"PLUGIN_DEPENDENCIES_INVALID",False
 system=value.get("system_dependencies")
 if not _unique_strings(system,TOKEN_RE):return False,"PLUGIN_SYSTEM_DEPENDENCIES_INVALID",False
 if not isinstance(value.get("enabled_by_default"),bool):return False,"PLUGIN_ENABLEMENT_INVALID",False
 resources=value.get("resources")
 if not isinstance(resources,dict) or any(key not in RESOURCE_KEYS or _safe_resource(plugin_dir,path) is None for key,path in resources.items()):return False,"PLUGIN_RESOURCES_INVALID",False
 doctor=value.get("doctor")
 if doctor is not None and (not isinstance(doctor,dict) or set(doctor)!={"label","capability"} or
                            not isinstance(doctor.get("label"),str) or not NAME_RE.fullmatch(doctor["label"]) or
                            not isinstance(doctor.get("capability"),str) or not TOKEN_RE.fullmatch(doctor["capability"])):return False,"PLUGIN_DOCTOR_INVALID",False
 current=_version(core_version)
 compatible=bool(current and current>=_version(requirement["minimum"]) and (requirement["maximum"] is None or current<=_version(requirement["maximum"])))
 return True,"PASS",compatible

def _enabled(home:pathlib.Path)->set[str]:
 value=_read_json(paths(home,pathlib.Path("/"))["enabled"])
 items=value.get("plugins",[]) if isinstance(value,dict) and type(value.get("schema")) is int and value["schema"]==2 and isinstance(value.get("plugins"),list) else []
 return {item for item in items if isinstance(item,str) and ID_RE.fullmatch(item)}

def discover(home:pathlib.Path,install:pathlib.Path)->dict[str,Any]:
 try:core_version=(install/"VERSION").read_text(encoding="utf-8").strip()
 except OSError:core_version="0.0.0"
 enabled=_enabled(home);plugins=[];errors=[];seen={}
 for root_index,root in enumerate(paths(home,install)["available"]):
  try:children=sorted(root.iterdir(),key=lambda item:item.name)
  except OSError:continue
  for plugin_dir in children:
   origin="project" if root_index==0 else "user";identity=plugin_dir.name
   if plugin_dir.is_symlink() or not plugin_dir.is_dir():errors.append({"id":identity,"state":"BROKEN","reason":"PLUGIN_PATH_INVALID","origin":origin});continue
   manifest=plugin_dir/"plugin.json"
   if manifest.is_symlink() or not manifest.is_file():errors.append({"id":identity,"state":"BROKEN","reason":"PLUGIN_MANIFEST_MISSING","origin":origin});continue
   value=_read_json(manifest);valid,reason,compatible=validate_manifest(value,plugin_dir,core_version)
   plugin_id=value.get("id") if isinstance(value,dict) and isinstance(value.get("id"),str) else identity
   if not valid:errors.append({"id":plugin_id,"state":"BROKEN","reason":reason,"origin":origin});continue
   if plugin_id in seen:
    errors.append({"id":plugin_id,"state":"BROKEN","reason":"PLUGIN_DUPLICATE","origin":origin});seen[plugin_id]["state"]="BROKEN";seen[plugin_id]["reason"]="PLUGIN_DUPLICATE";continue
   active=plugin_id in enabled or value["enabled_by_default"]
   item={**value,"origin":origin,"installation_state":"INSTALLED","compatible":compatible,
         "state":"INCOMPATIBLE" if not compatible else "AVAILABLE" if active else "DISABLED"}
   seen[plugin_id]=item;plugins.append(item)
 return {"schema":2,"plugin_api":PLUGIN_API,"core_version":core_version,"plugins":sorted(plugins,key=lambda item:item["id"]),
         "errors":sorted(errors,key=lambda item:(item.get("id",""),item["reason"])),"enabled":sorted(enabled)}

def registry(home:pathlib.Path,install:pathlib.Path,facts:Any=None)->dict[str,Any]:
 value=discover(home,install);providers={hook:[] for hook in sorted(HOOKS)}
 if facts is not None:
  try:value=resolve_dependencies(value,facts)
  except RecursionError:
   for plugin in value["plugins"]:
    plugin["dependency_resolution"]={"status":"INVALID","reason":"PLUGIN_DEPENDENCY_GRAPH_INVALID","dependencies":[]}
    if plugin["state"]=="AVAILABLE":plugin["state"]="DEPENDENCY_INVALID"
 for plugin in value["plugins"]:
  if plugin["state"]!="AVAILABLE":continue
  for hook in plugin["capabilities"]:providers[hook].append({"plugin_id":plugin["id"],"plugin_version":plugin["version"]})
 return {**value,"providers":{key:providers[key] for key in sorted(providers) if providers[key]}}

def publish(home:pathlib.Path,install:pathlib.Path,facts:Any=None)->dict[str,Any]:
 value=registry(home,install,facts);_atomic_json(paths(home,install)["snapshot"],value);return value

def set_enabled(home:pathlib.Path,install:pathlib.Path,plugin_id:str,enabled:bool,facts:Any=None)->dict[str,Any]:
 current=discover(home,install);plugin=next((item for item in current["plugins"] if item["id"]==plugin_id),None)
 if plugin is None:raise PluginError("PLUGIN_NOT_FOUND")
 if not plugin["compatible"]:raise PluginError("PLUGIN_INCOMPATIBLE")
 selected=set(current["enabled"])
 if enabled:selected.add(plugin_id)
 else:selected.discard(plugin_id)
 _atomic_json(paths(home,install)["enabled"],{"schema":2,"plugins":sorted(selected)})
 return publish(home,install,facts)

def load_entrypoint(home:pathlib.Path,install:pathlib.Path,plugin_id:str,shadow:bool=False)->dict[str,Any]:
 """Explicitly load one validated entrypoint; discovery remains data-only."""
 value=registry(home,install);plugin=next((item for item in value["plugins"] if item["id"]==plugin_id),None)
 if plugin is None:return {"state":"BROKEN","reason":"PLUGIN_NOT_FOUND"}
 if plugin["state"] in {"BROKEN","INCOMPATIBLE"}:return {"state":"BROKEN","reason":"PLUGIN_NOT_LOADABLE"}
 if plugin["state"]!="AVAILABLE" and not shadow:return {"state":"BROKEN","reason":"PLUGIN_DISABLED"}
 entrypoint=plugin.get("entrypoint")
 if not entrypoint:return {"state":"BROKEN","reason":"PLUGIN_ENTRYPOINT_MISSING"}
 root=paths(home,install)["available"][0 if plugin["origin"]=="project" else 1]/plugin_id
 if not _safe_entrypoint(root,entrypoint):return {"state":"BROKEN","reason":"PLUGIN_PATH_INVALID"}
 try:
  target=(root/entrypoint).resolve(strict=True)
  spec=importlib.util.spec_from_file_location("openhtpc_p2_"+plugin_id.replace(".","_"),target)
  if spec is None or spec.loader is None:return {"state":"BROKEN","reason":"PLUGIN_LOAD_FAILED"}
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  if not callable(getattr(module,"observe",None)):return {"state":"BROKEN","reason":"PLUGIN_CONTRACT_INVALID"}
  return {"state":"SHADOW" if shadow and plugin["state"]=="DISABLED" else "AVAILABLE","plugin":plugin,"module":module}
 except (Exception,SystemExit):return {"state":"BROKEN","reason":"PLUGIN_LOAD_FAILED"}

def resolve_resource(home:pathlib.Path,install:pathlib.Path,plugin_id:str,resource_key:str)->dict[str,Any]:
 """Resolve one allowlisted local resource; callers retain all file-reading authority."""
 if resource_key not in RESOURCE_KEYS:return {"authority":"CORE_FALLBACK","reason":"PLUGIN_RESOURCE_KEY_INVALID"}
 value=registry(home,install);plugin=next((item for item in value["plugins"] if item["id"]==plugin_id),None)
 if not plugin or plugin.get("state")!="AVAILABLE":return {"authority":"PLUGIN_UNAVAILABLE","reason":"PLUGIN_RESOURCE_UNAVAILABLE"}
 relative=(plugin.get("resources") or {}).get(resource_key);root=paths(home,install)["available"][0 if plugin["origin"]=="project" else 1]/plugin_id
 target=_safe_resource(root,relative)
 return ({"authority":"PLUGIN_P2","resource_key":resource_key,"path":target} if target else
         {"authority":"PLUGIN_UNAVAILABLE","reason":"PLUGIN_RESOURCE_INVALID"})
