#!/usr/bin/env python3
"""Canonical, read-only physical optical-media detection.

Detection is deliberately independent from playback and decryption.  The
legacy ``state`` field remains for qualified DVD/UI consumers; new code must
use ``canonical_state``.
"""
import argparse, fcntl, hashlib, importlib.util, json, os, pathlib, re, subprocess, tempfile

PRESENTATION = {
    "DVD_VIDEO": {"media_label":"DVD","home_prefix":"DVD","poster_label":"DVD","icon":"optical-dvd.png","fallback_artwork":"dvd-media.png","message":"DVD DÉTECTÉ","provider_message":None},
    "BLURAY_VIDEO": {"media_label":"BLU-RAY","home_prefix":"Blu-ray","poster_label":"BLU-RAY","icon":"optical-bluray.png","fallback_artwork":"bluray-media.png","message":"BLU-RAY DÉTECTÉ","provider_message":"Plugin Blu-ray requis"},
    "UHD_BLURAY_VIDEO": {"media_label":"ULTRA HD BLU-RAY","home_prefix":"UHD Blu-ray","poster_label":"ULTRA HD BLU-RAY","icon":"optical-uhd.png","fallback_artwork":"uhd-bluray-media.png","message":"ULTRA HD BLU-RAY DÉTECTÉ","provider_message":"Plugin UHD requis"},
    "BLURAY_FAMILY": {"media_label":"BLU-RAY / UHD","home_prefix":"Blu-ray / UHD","poster_label":"BLU-RAY / UHD","icon":"optical-empty.png","fallback_artwork":"optical-empty.png","message":"DISQUE BLU-RAY DÉTECTÉ","provider_message":"Type exact Blu-ray / UHD non déterminé"},
    "UNKNOWN_OPTICAL_MEDIA": {"media_label":"MÉDIA OPTIQUE","home_prefix":"Disque optique","poster_label":"MÉDIA OPTIQUE","icon":"optical-empty.png","fallback_artwork":"optical-empty.png","message":"MÉDIA OPTIQUE DÉTECTÉ","provider_message":"Format non déterminé"},
}

def canonical_state(value):
    """Return canonical identity; legacy is consulted only when none exists."""
    canonical=value.get("canonical_state") if isinstance(value,dict) else None
    if canonical: return canonical
    return {"DVD":"DVD_VIDEO","BLURAY":"BLURAY_VIDEO","UHD":"UHD_BLURAY_VIDEO",
            "EMPTY":"DRIVE_PRESENT_NO_MEDIA","NO_DRIVE":"NO_OPTICAL_DRIVE",
            "UNKNOWN_DISC":"UNKNOWN_OPTICAL_MEDIA"}.get(value.get("state") if isinstance(value,dict) else None,"DETECTION_INDETERMINATE")

def presentation(value):
    canonical=canonical_state(value)
    return {"canonical_state":canonical,**PRESENTATION.get(canonical,{"media_label":"MÉDIA OPTIQUE","home_prefix":"Disque optique","poster_label":"MÉDIA OPTIQUE","icon":"optical-empty.png","fallback_artwork":"optical-empty.png","message":"ÉTAT OPTIQUE INDÉTERMINÉ","provider_message":None})}

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

def _properties(text):
    return {key:value for line in text.splitlines() if "=" in line for key,value in [line.split("=",1)]}

def _mountpoints(block):
    values=block.get("mountpoints")
    if not isinstance(values,list): values=[block.get("mountpoint")]
    return [pathlib.Path(value) for value in values if isinstance(value,str) and value]

def _bdmv_header(block):
    """Read only the unencrypted BDMV index signature from a mounted disc."""
    for root in _mountpoints(block):
        for relative in ("BDMV/index.bdmv","BDMV/INDEX.BDMV","bdmv/index.bdmv"):
            try:
                header=(root/relative).open("rb").read(8)
                if len(header)==8: return header.decode("ascii","replace"),relative
            except OSError: pass
    return None,None

def _playback_fields(canonical):
    if canonical=="DVD_VIDEO":
        return {"detected":True,"playback_provider":"core","playable":True,"playback_status":"AVAILABLE"}
    if canonical=="BLURAY_VIDEO":
        return {"detected":True,"playback_provider":"plugin:bluray","playable":False,"playback_status":"PLUGIN_REQUIRED"}
    if canonical=="UHD_BLURAY_VIDEO":
        return {"detected":True,"playback_provider":"plugin:uhd","playable":False,"playback_status":"PLUGIN_REQUIRED"}
    if canonical=="BLURAY_FAMILY":
        return {"detected":True,"playback_provider":None,"playable":False,"playback_status":"MEDIA_TYPE_INDETERMINATE"}
    return {"detected":False,"playback_provider":None,"playable":False,"playback_status":"UNAVAILABLE"}

def _state(canonical,device,legacy,**fields):
    value={"state":legacy,"canonical_state":canonical,"device":str(device) if device else None,
           "identity_status":"UNAVAILABLE"}
    value.update(_playback_fields(canonical)); value.update(fields); return value

def probe_device(device,runner=run,header_reader=_bdmv_header):
    result=runner(["lsblk","-J","-o","NAME,TYPE,FSTYPE,LABEL,MOUNTPOINTS",str(device)])
    if result.returncode!=0:
        return _state("DETECTION_INDETERMINATE",device,"UNKNOWN_DISC",detection_reason="LSBLK_FAILED")
    try: block=json.loads(result.stdout)["blockdevices"][0]
    except (json.JSONDecodeError,KeyError,IndexError,TypeError):
        return _state("DETECTION_INDETERMINATE",device,"UNKNOWN_DISC",detection_reason="LSBLK_INVALID")
    udev=runner(["udevadm","info","--query=property","--name",str(device)])
    props=_properties(udev.stdout) if udev.returncode==0 else {}
    fstype=(block.get("fstype") or "").lower(); label=block.get("label") or None
    if udev.returncode!=0 and not fstype:
        return _state("DETECTION_INDETERMINATE",device,"UNKNOWN_DISC",detection_reason="MEDIA_PRESENCE_UNAVAILABLE")
    media_present=props.get("ID_CDROM_MEDIA")=="1" or bool(fstype)
    if not media_present:
        return _state("DRIVE_PRESENT_NO_MEDIA",device,"EMPTY",detection_reason="NO_MEDIA_EVIDENCE")
    info=runner(["lsdvd","-x","-Ox",str(device)]); text=info.stdout if info.returncode==0 else ""
    dvd_video=info.returncode==0 and ("<lsdvd" in text.lower() or "discinfo" in text.lower())
    bd_medium=any(props.get(key)=="1" for key in ("ID_CDROM_MEDIA_BD","ID_CDROM_MEDIA_BD_R","ID_CDROM_MEDIA_BD_RE"))
    header,header_path=header_reader(block)
    evidence=[]
    if bd_medium: evidence.append("UDEV_MMC_BD_MEDIA")
    if header and header.startswith("INDX"): evidence.append("BDMV_INDEX_HEADER")
    if dvd_video:
        canonical,legacy,uhd_status="DVD_VIDEO","DVD","NOT_APPLICABLE"
        evidence.append("LSDVD_DVD_VIDEO")
    elif bd_medium and header=="INDX0300": canonical,legacy,uhd_status="UHD_BLURAY_VIDEO","UHD","CONFIRMED"
    elif bd_medium and header in {"INDX0100","INDX0200"}: canonical,legacy,uhd_status="BLURAY_VIDEO","BLURAY","NOT_UHD"
    elif bd_medium and header and header.startswith("INDX"):
        canonical,legacy,uhd_status="BLURAY_FAMILY","BLURAY","UNKNOWN"
    elif bd_medium:
        canonical,legacy,uhd_status="BLURAY_FAMILY","BLURAY","UNKNOWN"
    elif fstype not in {"iso9660","udf"}:
        canonical,legacy,uhd_status="UNKNOWN_OPTICAL_MEDIA","UNKNOWN_DISC","NOT_APPLICABLE"
    else:
        canonical,legacy,uhd_status="UNKNOWN_OPTICAL_MEDIA","UNKNOWN_DISC","UNKNOWN"
    value=_state(canonical,device,legacy,volume_label=label,disc_title=None,
                 uhd_status=uhd_status,detection_evidence=evidence)
    if header: value["bdmv_index_version"]=header[4:] if header.startswith("INDX") else "UNRECOGNIZED"
    if header_path: value["bdmv_index_path"]=header_path
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
    if not drives: return _state("NO_OPTICAL_DRIVE",None,"NO_DRIVE",drives=[])
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
            states.append(_state("DRIVE_PRESENT_NO_MEDIA",device,"EMPTY")); continue
        if not guard.get("empty_observed"):
            states.append(_state("DRIVE_PRESENT_NO_MEDIA",device,"EMPTY",identity_status="EJECTING")); continue
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
    keys=("state","canonical_state","device","volume_label","disc_title","disc_id","playable","playback_status","uhd_status")
    return {key:value.get(key) for key in keys if value.get(key) is not None}

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
        if fstype: return {**_state("DETECTION_INDETERMINATE",device,"INITIALIZING",identity_status="PENDING"),
                           "volume_label":block.get("label") or None,"drives":[str(item) for item in drives]}
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
