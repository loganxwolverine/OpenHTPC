#!/usr/bin/env python3
"""Universal physical-disc sheet controller with progressive TMDb enrichment."""
import importlib.util,json,os,pathlib,shlex,subprocess,tempfile,time
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def load_theme(install):
 path=install/"openhtpc-theme.py"
 if not path.is_file(): path=pathlib.Path(__file__).with_name("openhtpc-theme.py")
 return load("disc_theme",path)
def duration(device,runner=subprocess.run):
 try:
  p=runner(["lsdvd","-Ox",device],text=True,capture_output=True,timeout=10)
  import re
  values=[float(v) for v in re.findall(r'length="([0-9.]+)"',p.stdout)]
  values += [int(h)*3600+int(m)*60+float(s) for h,m,s in re.findall(r'<length>\s*(\d+):(\d+):(\d+(?:\.\d+)?)\s*</length>',p.stdout)]
  if values:
   minutes=round(max(values)/60); return f"{minutes//60} h {minutes%60:02d}" if minutes>=60 else f"{minutes} min"
 except (OSError,subprocess.TimeoutExpired,ValueError): pass
 return "Durée inconnue"
def identity(state):
 raw=state.get("tmdb_title") or state.get("disc_title") or state.get("volume_label")
 if raw:
  import re
  return re.sub(r"(?i)(?:[ _.-]+)(?:DVD|DISC|DISK)\s*[12]\s*$","",str(raw)).strip() or "Disque identifié"
 return {"DVD":"DVD","BLURAY":"Blu-ray","UHD":"UHD Blu-ray","INITIALIZING":"Initialisation du disque…"}.get(state.get("state"),"Aucun disque détecté")
def model(home,install,state):
 title=identity(state); metadata={"status":"NOT_CONFIGURED"}; artwork={"DVD":"optical-dvd.png","BLURAY":"optical-bluray.png","UHD":"optical-uhd.png"}.get(state.get("state"),"optical-empty.png"); artwork=install/"assets/ui"/artwork
 if state.get("state")=="DVD" and (install/"openhtpc-tmdb.py").is_file():
  tmdb=load("tmdb",install/"openhtpc-tmdb.py"); metadata=tmdb.lookup(home,title); poster=tmdb.poster(home,metadata)
  if metadata.get("status")=="PASS": title=metadata.get("title") or title
  if poster: artwork=poster
 return {"state":state,"title":title,"metadata":metadata,"artwork":artwork,"duration":duration(state["device"]) if state.get("state")=="DVD" else None}
def write_menu(home,install,data):
 state=data["state"]; icon=data["artwork"]; font=install/"flex/assets/fonts/OpenSans-Regular.ttf"; theme=load_theme(install); entries=[]
 if state.get("state")=="DVD":
  meta=data["metadata"]; year=(meta.get("release_date") or "")[:4]
  title=f"{data['title']}{' ('+year+')' if year else ''}"; dev=shlex.quote(state["device"])
  entries.append(("LIRE · "+title,f"env OPENHTPC_FLEX_RETAINED=1 {install/'openhtpc-play-dvd'} {dev}"))
  if meta.get("status")!="PASS": entries.append(("CONFIGURER TMDb",f":replace {install/'openhtpc-configure-tmdb'}"))
  entries.append(("ÉJECTER",f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {dev}"))
 elif state.get("state") in {"BLURAY","UHD"}: entries.append((f"{data['title']} — Lecture disponible via module optionnel.",":fork true"))
 elif state.get("state")=="INITIALIZING": entries.append(("INITIALISATION DU DISQUE…",":fork true"))
 else: entries.append(("AUCUN DISQUE DÉTECTÉ — Insérez un DVD, Blu-ray ou UHD compatible.",":fork true"))
 entries.append(("RETOUR",f":replace {install/'openhtpc-session-start'}"))
 body="\n".join(f"Entry{i}={str(label).replace(';','—')};{icon};{cmd}" for i,(label,cmd) in enumerate(entries,1)); menu=home/".config/openhtpc/disc-sheet.ini"; menu.parent.mkdir(parents=True,exist_ok=True)
 content=f"""[General]\nDefaultMenu=DISQUE\nVSync=true\nOnLaunch=Blank\nWrapEntries=true\nMouseSelect=true\n{theme.background_block(install,58)}\n[Layout]\nMaxButtons=4\nIconSize=250\nIconSpacing=4%\nVCenter=52%\n{theme.title_block(font,48,22)}\n{theme.highlight_block()}\n[Hotkeys]\nHotkey1=#1B;:replace {install/'openhtpc-session-start'}\nHotkey2=#08;:replace {install/'openhtpc-session-start'}\n[DISQUE]\n{body}\n"""
 fd,tmp=tempfile.mkstemp(prefix="disc-sheet.",dir=menu.parent)
 with os.fdopen(fd,"w") as stream: stream.write(content)
 os.chmod(tmp,0o600); os.replace(tmp,menu); return menu
def main():
 home=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home())); install=pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR",home/".local/lib/openhtpc")); optical=load("optical",install/"openhtpc-optical.py")
 while True:
  state=optical.cached_state(home)
  if not state:
   state=optical.current_state(home=home); optical.atomic_json(home/".local/state/openhtpc/optical-current.json",state)
  key=json.dumps(state,sort_keys=True); menu=write_menu(home,install,model(home,install,state))
  try: lock_fd=int(os.environ.get("OPENHTPC_SESSION_LOCK_FD","-1")); pass_fds=(lock_fd,) if lock_fd>=0 else ()
  except ValueError: pass_fds=()
  proc=subprocess.Popen([str(install/"flex/bin/flex-launcher"),"-c",str(menu)],pass_fds=pass_fds)
  changed=False
  while proc.poll() is None:
   time.sleep(0.5); current=optical.cached_state(home) or state
   if json.dumps(current,sort_keys=True)!=key: changed=True; proc.terminate(); proc.wait(timeout=3); break
  if not changed: return proc.returncode
if __name__=="__main__": raise SystemExit(main())
