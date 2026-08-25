#!/usr/bin/env python3
"""Bounded O1 optical forensic collector: read-only, keyless and title-free."""
from __future__ import annotations
import argparse, importlib.util, json, os, pathlib, subprocess

SAFE_UDEV_PREFIXES=("ID_CDROM",)
SAFE_UDEV_KEYS={"ID_BUS","ID_TYPE","ID_MODEL","ID_MODEL_ID","ID_REVISION","ID_VENDOR","ID_VENDOR_ID","DEVNAME","DEVTYPE"}

def run(command):
    try: return subprocess.run(command,text=True,capture_output=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired): return subprocess.CompletedProcess(command,127,"","")

def properties(device):
    result=run(["udevadm","info","--query=property","--name",str(device)])
    values={}
    for line in result.stdout.splitlines():
        if "=" not in line: continue
        key,value=line.split("=",1)
        if key in SAFE_UDEV_KEYS or key.startswith(SAFE_UDEV_PREFIXES): values[key]=value
    return values

def sanitized(state):
    allowed={"canonical_state","state","device","drives","detected","playback_provider","playable",
             "playback_status","uhd_status","detection_evidence","detection_reason","bdmv_index_version"}
    return {key:value for key,value in state.items() if key in allowed}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    home=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home()))
    installed=home/".local/lib/openhtpc/openhtpc-optical.py"
    source=pathlib.Path(__file__).resolve().parents[1]/"payload/openhtpc-optical.py"
    parser.add_argument("--engine",type=pathlib.Path,default=installed if installed.is_file() else source)
    args=parser.parse_args()
    args.engine=args.engine.expanduser().resolve()
    spec=importlib.util.spec_from_file_location("openhtpc_o1_optical",args.engine)
    optical=importlib.util.module_from_spec(spec); spec.loader.exec_module(optical)
    devices=optical.optical_devices(); rows=[]
    for device in devices:
        block=run(["lsblk","-J","-o","NAME,PATH,TYPE,FSTYPE,MOUNTPOINTS,VENDOR,MODEL,REV,RM,HOTPLUG",str(device)])
        try: block_data=json.loads(block.stdout)["blockdevices"][0]
        except (json.JSONDecodeError,KeyError,IndexError,TypeError): block_data={"path":str(device),"probe_status":"INDETERMINATE"}
        rows.append({"device":str(device),"kernel_type":(pathlib.Path("/sys/class/block")/device.name/"device/type").read_text().strip(),
                     "udev":properties(device),"block":block_data})
    output={"schema":1,"collector":"OPENHTPC_OPTICAL_CORE_O1","read_only":True,"decryption_attempted":False,
            "devices":rows,"canonical_optical_state":sanitized(optical.current_state())}
    print(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
