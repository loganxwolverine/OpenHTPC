#!/usr/bin/env python3
"""Create a small read-only, sanitized OPENHTPC support archive."""
from __future__ import annotations
import datetime,json,os,pathlib,re,shutil,subprocess,tarfile,tempfile
POLICY="openhtpc-support-v3-capabilities-redacted"
SECRET=re.compile(r"(?i)(authorization|api[_-]?key|password|secret|token)\s*[:=].*")
def sanitize(text:str,home:pathlib.Path)->str:
 text=text.replace(str(home),"~")
 try:
  value=json.loads(text)
  def clean(item):
   if isinstance(item,dict):return {key:("[REDACTED]" if re.search(r"(?i)(authorization|api[_-]?key|password|secret|token)",key) else clean(val)) for key,val in item.items()}
   if isinstance(item,list):return [clean(x) for x in item]
   return item
  return json.dumps(clean(value),ensure_ascii=False,indent=2)+"\n"
 except json.JSONDecodeError:pass
 return "\n".join("[REDACTED]" if SECRET.search(line) else line for line in text.splitlines())+"\n"
def command(argv):
 try:r=subprocess.run(argv,text=True,capture_output=True,timeout=12);return r.stdout+r.stderr
 except (OSError,subprocess.TimeoutExpired) as exc:return f"source unavailable: {exc}\n"
def playback_summary(home:pathlib.Path)->str:
 action=home/".local/state/openhtpc/media-action-last.json";state=home/".local/state/openhtpc/playback-last-private.json"
 try:data=json.loads(action.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError):data={}
 try:private=json.loads(state.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError):private={}
 if not data and not private:return "playback diagnostics unavailable: no MEDIA action has been recorded\n"
 data={**private,**data}
 allowed=("timestamp","media_action_seen","action_payload_valid","action_token_valid","token_present","manifest_present","page_id_match","token_found","generation_valid","item_identity_valid","source_identity_valid","dispatcher_seen","current_page","model_generation","flex_instances","authoritative_flex_pid","kind","source_id","extension","path_resolved","path_absolute","file_exists","runtime","mpv","argv_count","process_started","media_opened","exit_code","elapsed","error_class")
 lines=[f"{key}={data.get(key,'unavailable')}" for key in allowed]
 media=pathlib.Path(str(private.get("media_path","")))
 probe=shutil.which("ffprobe")
 if probe and media.is_absolute() and media.is_file():
  try:
   result=subprocess.run([probe,"-v","error","-show_entries","format=format_name:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(media)],text=True,capture_output=True,timeout=8,check=False)
   value=json.loads(result.stdout) if result.returncode==0 else {}
   fmt=value.get("format",{}).get("format_name")
   if fmt:lines.append(f"container={fmt}")
   for stream in value.get("streams",[]):
    if stream.get("codec_type")=="video":
     lines.extend((f"video_codec={stream.get('codec_name','unknown')}",f"resolution={stream.get('width','?')}x{stream.get('height','?')}",f"frame_rate={stream.get('r_frame_rate','unknown')}"));break
   audio=next((x for x in value.get("streams",[]) if x.get("codec_type")=="audio"),None)
   if audio:lines.append(f"audio_codec={audio.get('codec_name','unknown')}")
  except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):lines.append("ffprobe=unavailable")
 for item in private.get("diagnostic_lines",[])[:20]:
  safe=str(item).replace(str(home),"~")
  if media.is_absolute():safe=safe.replace(str(media),"<media>")
  if media.name:safe=safe.replace(media.name,"<media>")
  lines.append("mpv="+safe)
 return "\n".join(lines)+"\n"
def create(home:pathlib.Path,install:pathlib.Path,output:pathlib.Path|None=None)->pathlib.Path:
 stamp=datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S");output=output or home/f"openhtpc-support-{stamp}.tar.gz"
 with tempfile.TemporaryDirectory(prefix="openhtpc-support-") as raw:
  root=pathlib.Path(raw)/"openhtpc-support";root.mkdir();included=[]
  def add(name,data):
   target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(sanitize(data,home),encoding="utf-8");included.append(name)
  add("doctor.txt",command([str(install/"openhtpc"),"doctor"]))
  add("doctor.json",command([str(install/"openhtpc"),"doctor","--json"]))
  add("playback-summary.txt",playback_summary(home))
  capability=home/".config/openhtpc/runtime/capabilities.json"
  try:add("capabilities.json",capability.read_text(encoding="utf-8"))
  except OSError:add("capabilities.json",'{"status":"NOT_GENERATED"}\n')
  ledger=home/".local/state/openhtpc/capability-validation.json"
  try:add("capability-validation.json",ledger.read_text(encoding="utf-8"))
  except OSError:add("capability-validation.json",'{"status":"NO_VALIDATED_PLAYBACK"}\n')
  for source,name in ((install/"version.json","version.json"),(home/".config/openhtpc/profile.json","hardware-passport.json"),(home/".local/state/openhtpc/runtime.log","runtime.log"),(home/".local/state/openhtpc/optical-current.json","optical-state.json"),(install/"flex/BUILD-METADATA.json","flex-build.json")):
   try:add(name,source.read_text(encoding="utf-8"))
   except OSError:add(name,"source unavailable")
  add("user-services.txt",command(["systemctl","--user","--no-pager","--full","status","plasma-plasmashell.service"]))
  add("journal.txt",command(["journalctl","--user","--since=-2 hours","--no-pager","-n","400","-g","OPENHTPC|flex-launcher|plasmashell"]))
  version=json.loads((install/"version.json").read_text()) if (install/"version.json").is_file() else {"version":"unknown"}
  manifest=f"sanitization_policy={POLICY}\ncreated={datetime.datetime.now().astimezone().isoformat()}\nversion={version.get('version','unknown')}\nfiles="+",".join(sorted(included))+"\n"
  add("MANIFEST.txt",manifest)
  with tarfile.open(output,"w:gz") as archive:archive.add(root,arcname="openhtpc-support",recursive=True)
 os.chmod(output,0o600);return output
def main():
 home=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home()));install=pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR",home/".local/lib/openhtpc"));target=create(home,install);print(f"Support bundle created:\n{target}\nReview the archive before sharing; it contains machine-specific diagnostics.");return 0
if __name__=="__main__":raise SystemExit(main())
