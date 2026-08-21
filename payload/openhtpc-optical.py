#!/usr/bin/env python3
"""Minimal read-only optical state and local DVD identity."""
import argparse, fcntl, hashlib, importlib.util, json, os, pathlib, re, subprocess, tempfile

def run(command):
    try: return subprocess.run(command,text=True,capture_output=True,timeout=8)
    except (OSError,subprocess.TimeoutExpired): return subprocess.CompletedProcess(command,127,"","")

def optical_devices(sys_block=pathlib.Path("/sys/class/block")):
    try: entries=sorted(sys_block.iterdir(),key=lambda p:p.name)
    except OSError: return []
    found=[]
    for entry in entries:
        try:
            if (entry/"device/type").read_text().strip()=="5": found.append(pathlib.Path("/dev")/entry.name)
        except OSError: pass
    return found

def _fmt_audio_codec(fmt):
    """Map lsdvd audio format codes to display strings."""
    return {"ac3":"Dolby Digital","dts":"DTS","mp2":"MPEG Audio","lpcm":"PCM","mp3":"MP3","vorbis":"Vorbis"}.get((fmt or "").lower(),(fmt or "").upper())

def _fmt_channels(n):
    """Map channel count to display label."""
    return {1:"Mono",2:"Stéréo",6:"5.1",8:"7.1"}.get(n,f"{n} ch") if n else ""

def _fmt_lang(track):
    """Best available language label from a track dict."""
    v = (track.get("language") or track.get("langcode") or "").strip()
    return v[:1].upper() + v[1:] if v else ""

def _parse_duration_seconds(text: str | None) -> float | None:
    if not text: return None
    s = str(text).strip()
    m = re.match(r"^(\d+):(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        h, mn, sec = m.groups()
        return int(h) * 3600 + int(mn) * 60 + float(sec)
    m = re.match(r"^(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        mn, sec = m.groups()
        return int(mn) * 60 + float(sec)
    try:
        val = float(s)
        if val > 0: return val
    except ValueError:
        pass
    return None

def parse_lsdvd_xml(text):
    """Parse lsdvd -Ox XML into a physical-edition dict.
    Only includes keys with reliable data; never fabricates values.
    Returns {} on any parse error so callers can safely ignore failures."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception:
        return {}
    result = {"media_type": "DVD-VIDEO", "lsdvd_ok": True}

    tracks = root.findall("track")
    if not tracks:
        return result

    # Identify main feature track: prefer <longest_track> index, else longest by duration
    longest_ix = None
    el = root.find("longest_track")
    if el is not None:
        try: longest_ix = int(el.text)
        except (ValueError, TypeError): pass

    def _track_len(t):
        el = t.find("length")
        if el is None or not el.text: return 0.0
        return _parse_duration_seconds(el.text) or 0.0

    main = None
    if longest_ix is not None:
        for t in tracks:
            ix = t.find("ix")
            try:
                if ix is not None and int(ix.text) == longest_ix:
                    main = t; break
            except (ValueError, TypeError): pass
    if main is None:
        main = max(tracks, key=_track_len)

    # Duration of main track in seconds
    el = main.find("length")
    if el is not None and el.text:
        dur = _parse_duration_seconds(el.text)
        if dur and dur > 0: result["duration"] = dur

    # Video properties
    vid = {}
    for field, cast in [("format", str), ("fps", str), ("width", int), ("height", int), ("aspect", str)]:
        el = main.find(field)
        if el is not None and el.text:
            try: vid[field] = cast(el.text.strip())
            except (ValueError, TypeError): pass
    if vid:
        vid["codec"] = "MPEG-2"   # DVD-Video standard; always reliable
        result["video"] = vid

    # Audio tracks on main feature
    audio_tracks = []
    for ael in main.findall("audio"):
        track = {}
        for field, cast in [("langcode", str), ("language", str), ("format", str), ("channels", int), ("frequency", int)]:
            el = ael.find(field)
            if el is not None and el.text:
                try: track[field] = cast(el.text.strip())
                except (ValueError, TypeError): pass
        # Normalise display values
        if "format" in track: track["display_codec"] = _fmt_audio_codec(track["format"])
        if "channels" in track: track["display_channels"] = _fmt_channels(track["channels"])
        if "language" in track or "langcode" in track: track["display_lang"] = _fmt_lang(track)
        if track: audio_tracks.append(track)
    if audio_tracks: result["audio"] = audio_tracks

    # Subtitle tracks on main feature
    sub_tracks = []
    for sel in main.findall("subp"):
        track = {}
        for field in ("langcode", "language", "content"):
            el = sel.find(field)
            if el is not None and el.text:
                track[field] = el.text.strip()
        if "language" in track or "langcode" in track:
            track["display_lang"] = _fmt_lang(track)
        if track: sub_tracks.append(track)
    if sub_tracks: result["subtitles"] = sub_tracks

    # Chapter count
    chapters = main.findall("chapter")
    if chapters: result["chapters"] = len(chapters)

    return result

def probe_device(device,runner=run):
    result=runner(["lsblk","-J","-o","NAME,TYPE,FSTYPE,LABEL",str(device)])
    if result.returncode!=0: return {"state":"EMPTY","device":str(device),"identity_status":"UNAVAILABLE"}
    try: block=json.loads(result.stdout)["blockdevices"][0]
    except (json.JSONDecodeError,KeyError,IndexError,TypeError): return {"state":"UNKNOWN_DISC","device":str(device),"identity_status":"UNAVAILABLE"}
    fstype=(block.get("fstype") or "").lower(); label=block.get("label") or None
    if not fstype: return {"state":"EMPTY","device":str(device),"identity_status":"UNAVAILABLE"}
    if fstype not in {"iso9660","udf"}: return {"state":"UNKNOWN_DISC","device":str(device),"volume_label":label,"identity_status":"UNAVAILABLE"}
    info=runner(["lsdvd","-x","-Ox",str(device)]); text=info.stdout if info.returncode==0 else ""; upper=(text+" "+(label or "")).upper()
    if any(word in upper for word in ("ULTRA HD","ULTRA_HD","UHD","4K UHD","BDXL")): state="UHD"
    elif any(word in upper for word in ("BLU-RAY","BLURAY","BDMV")): state="BLURAY"
    elif info.returncode==0 and ("<lsdvd" in text.lower() or "discinfo" in text.lower()): state="DVD"
    else: state="UNKNOWN_DISC"
    value={"state":state,"device":str(device),"volume_label":label,"disc_title":None,"identity_status":"UNAVAILABLE"}
    if info.returncode==0 and text.strip():
        value.update(disc_id=hashlib.sha256(text.encode()).hexdigest(),identity_status="FINGERPRINT")
        # Parse physical-edition data from the same lsdvd output (no extra disc access needed)
        phys = parse_lsdvd_xml(text)
        if phys:
            value["physical_edition"] = phys
            if phys.get("duration") and not value.get("duration"):
                value["duration"] = phys["duration"]
    return value

def eject_guard(home):
    try:
        data=json.loads((home/".local/state/openhtpc/optical-ejecting.json").read_text())
        return data if isinstance(data.get("device"),str) else None
    except (OSError,json.JSONDecodeError,AttributeError): return None

def write_eject_guard(home,data): atomic_json(home/".local/state/openhtpc/optical-ejecting.json",data)

def current_state(runner=run,sys_block=pathlib.Path("/sys/class/block"),home=None):
    drives=optical_devices(sys_block)
    if not drives: return {"state":"NO_DRIVE","device":None,"identity_status":"UNAVAILABLE","drives":[]}
    guard=eject_guard(home) if home else None; states=[]
    for device in drives:
        if not guard or str(device)!=guard.get("device"):
            states.append(probe_device(device,runner)); continue
        basic=runner(["lsblk","-J","-o","NAME,TYPE,FSTYPE,LABEL",str(device)])
        try: fstype=(json.loads(basic.stdout)["blockdevices"][0].get("fstype") or "").lower()
        except (json.JSONDecodeError,KeyError,IndexError,TypeError): fstype=""
        if not fstype:
            if not guard.get("empty_observed"):
                guard["empty_observed"]=True; write_eject_guard(home,guard)
            states.append({"state":"EMPTY","device":str(device),"identity_status":"UNAVAILABLE"}); continue
        if not guard.get("empty_observed"):
            states.append({"state":"EMPTY","device":str(device),"identity_status":"EJECTING"}); continue
        try: (home/".local/state/openhtpc/optical-ejecting.json").unlink()
        except OSError: pass
        states.append(probe_device(device,runner))
    priority={"DVD":0,"BLURAY":1,"UHD":1,"UNSUPPORTED_IN_V1":2,"UNKNOWN_DISC":3,"EMPTY":4}
    chosen=min(states,key=lambda x:(priority[x["state"]],x["device"])); chosen["drives"]=[str(d) for d in drives]; return chosen

def atomic_json(target,data):
    target.parent.mkdir(parents=True,exist_ok=True); fd,name=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w") as stream: json.dump(data,stream,ensure_ascii=False,sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name,0o600); os.replace(name,target)
        directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)

def cached_state(home):
    try:
        value=json.loads((home/".local/state/openhtpc/optical-current.json").read_text())
        return value if isinstance(value,dict) else None
    except (OSError,json.JSONDecodeError): return None

def ui_state(value):
    """Return only fields whose change is meaningful to the couch UI."""
    return {key:value.get(key) for key in ("state","device","volume_label","disc_title","disc_id") if value.get(key) is not None}

def ui_state_hash(value):
    return hashlib.sha256(json.dumps(ui_state(value),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def initializing_state(home,runner=run,sys_block=pathlib.Path("/sys/class/block")):
    previous=cached_state(home) or {}; drives=optical_devices(sys_block)
    if previous.get("state") not in {"EMPTY","NO_DRIVE","UNKNOWN_DISC","UNSUPPORTED_IN_V1",None}: return None
    for device in drives:
        result=runner(["lsblk","-J","-o","NAME,TYPE,FSTYPE,LABEL",str(device)])
        try:
            block=json.loads(result.stdout)["blockdevices"][0]; fstype=(block.get("fstype") or "").lower()
        except (json.JSONDecodeError,KeyError,IndexError,TypeError): continue
        if fstype: return {"state":"INITIALIZING","device":str(device),"volume_label":block.get("label") or None,"identity_status":"PENDING","drives":[str(item) for item in drives]}
    return None

def next_generation(home):
    target=home/".local/state/openhtpc/optical-generation"; target.parent.mkdir(parents=True,exist_ok=True)
    with open(target,"a+") as stream:
        fcntl.flock(stream,fcntl.LOCK_EX); stream.seek(0)
        try: value=int(stream.read().strip() or "0")+1
        except ValueError: value=1
        stream.seek(0); stream.truncate(); stream.write(str(value)); stream.flush(); os.fsync(stream.fileno()); return value

def publish(home,state,generation=None):
    previous=cached_state(home) or {}; candidate=dict(state); candidate.pop("generation",None)
    if previous and ui_state_hash(previous)==ui_state_hash(candidate): return previous
    generation=next_generation(home) if generation is None else generation
    value=candidate; value["generation"]=generation; value["ui_state_hash"]=ui_state_hash(value)
    atomic_json(home/".local/state/openhtpc/optical-current.json",value)
    runtime=pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR",pathlib.Path(__file__).parent))/"openhtpc-runtime.py"
    if runtime.is_file():
        try:
            spec=importlib.util.spec_from_file_location("openhtpc_runtime_optical",runtime); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.log(home,"optical","STATE_TRANSITION",optical_generation=generation,old_state=previous.get("state"),new_state=value.get("state"))
        except (OSError,AttributeError,TypeError): pass
    return value

def refresh_state(home,runner=run,sys_block=pathlib.Path("/sys/class/block")):
    lock_path=home/".local/state/openhtpc/optical-refresh.lock"; lock_path.parent.mkdir(parents=True,exist_ok=True)
    with open(lock_path,"w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        pending=initializing_state(home,runner,sys_block)
        if pending: return publish(home,pending)
        return publish(home,current_state(runner,sys_block,home))

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--refresh",action="store_true"); parser.add_argument("--print",action="store_true"); args=parser.parse_args()
    home=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home()))
    state=refresh_state(home) if args.refresh else publish(home,current_state(home=home))
    if args.print: print(json.dumps(state,ensure_ascii=False,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
