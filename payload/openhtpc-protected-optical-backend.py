#!/usr/bin/env python3
"""Bounded MPV/libbluray backend for already-authorized optical requests."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import json
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

OPEN_MARKERS=("VO:","AO:","Video:","Audio:","Starting playback")
MEDIA_TYPES={"BLURAY","UHD_BLURAY"}
REQUIRED_BITSTREAM_CODECS=("PCM","DTS","AC3","EAC3","TrueHD","DTS-HD")
CANONICAL_CODECS_MAP={
    "pcm":"PCM",
    "dts":"DTS",
    "ac3":"AC3",
    "eac3":"EAC3",
    "truehd":"TrueHD",
    "dts-hd":"DTS-HD",
    "dtshd":"DTS-HD",
}


def parse_wpctl_sink(inspect_text:str)->dict[str,Any]:
    """Parse output from `wpctl inspect <target>` dynamically."""
    if not inspect_text:return {}
    id_match=re.search(r"\bid\s+(\d+)",inspect_text,re.I)
    sink_id=int(id_match.group(1)) if id_match else None
    props:dict[str,str]={}
    for line in inspect_text.splitlines():
        match=re.match(r"^\s*\*?\s*([\w.]+)\s*=\s*(.+)$",line)
        if match:
            props[match.group(1).strip()]=match.group(2).strip()
    media_class=props.get("media.class","").strip('"')
    node_name=props.get("node.name","").strip('"')
    node_desc=props.get("node.description","").strip('"')
    node_nick=props.get("node.nick","").strip('"')
    profile_name=props.get("device.profile.name","").strip('"')
    profile_desc=props.get("device.profile.description","").strip('"')
    alsa_path=props.get("api.alsa.path","").strip('"')
    raw_codecs=props.get("iec958.codecs","")
    codecs_tokens=[c for c in re.findall(r"[A-Za-z0-9_-]+",raw_codecs) if c.lower() not in {"iec958","codecs"}]
    codecs=[CANONICAL_CODECS_MAP.get(c.lower(),c) for c in codecs_tokens]

    combined=f"{profile_name} {node_name} {node_desc} {node_nick} {profile_desc} {alsa_path}".lower()
    is_hdmi=media_class=="Audio/Sink" and bool(re.search(r"\bhdmi\b|hdmi-|\.hdmi|digital surround|displayport",combined))

    return {
        "id":sink_id,
        "name":node_name or None,
        "description":node_desc or node_nick or None,
        "profile":profile_name or None,
        "media_class":media_class or None,
        "alsa_path":alsa_path or None,
        "is_hdmi":is_hdmi,
        "codecs":codecs,
    }


def inspect_sink(target:str="@DEFAULT_AUDIO_SINK@",*,runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    try:
        proc=runner(["wpctl","inspect",target],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        if getattr(proc,"returncode",1)!=0:return {}
        stdout=getattr(proc,"stdout","") or ""
        return parse_wpctl_sink(stdout)
    except (OSError,ValueError,TypeError):
        return {}


def prepare_pipewire_hdmi_bitstream(
    requested_mode:str,
    *,
    sink_target:str="@DEFAULT_AUDIO_SINK@",
    runner:Callable[...,Any]=subprocess.run,
    finder:Callable[[str],str|None]=shutil.which,
)->dict[str,Any]:
    """Inspect and prepare PipeWire HDMI sink for bitstream HD passthrough if required."""
    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    sink=inspect_sink(sink_target,runner=runner)
    sink_id=sink.get("id")
    sink_name=sink.get("name")
    sink_desc=sink.get("description")
    sink_profile=sink.get("profile")
    sink_media_class=sink.get("media_class")
    is_hdmi=bool(sink.get("is_hdmi",False))
    codecs_before=list(sink.get("codecs",[]))
    req_codecs=list(REQUIRED_BITSTREAM_CODECS)

    base_diag={
        "audio_sink_id":sink_id,
        "audio_sink_name":sink_name,
        "audio_sink_description":sink_desc,
        "audio_sink_profile":sink_profile,
        "audio_sink_media_class":sink_media_class,
        "audio_sink_is_hdmi":is_hdmi,
        "iec958_codecs_before":codecs_before,
        "iec958_codecs_requested":req_codecs if requested_mode=="BITSTREAM" else [],
        "iec958_codecs_after":codecs_before,
        "iec958_prepare_attempted":False,
        "iec958_prepare_status":"SKIPPED",
        "iec958_prepare_reason":"PCM_MODE",
        "iec958_prepare_method":None,
        "timestamp":timestamp,
    }

    if requested_mode!="BITSTREAM":
        return base_diag

    if not sink or sink_id is None:
        base_diag.update({
            "iec958_prepare_status":"SKIPPED",
            "iec958_prepare_reason":"SINK_UNRESOLVED",
        })
        return base_diag

    if not is_hdmi:
        base_diag.update({
            "iec958_prepare_status":"SKIPPED",
            "iec958_prepare_reason":"SINK_NOT_HDMI",
        })
        return base_diag

    if all(codec in codecs_before for codec in req_codecs):
        base_diag.update({
            "iec958_prepare_attempted":False,
            "iec958_prepare_status":"SUCCESS",
            "iec958_prepare_reason":"ALREADY_SATISFIED",
            "iec958_prepare_method":"pw-cli",
        })
        return base_diag

    pw_cli=finder("pw-cli")
    if not pw_cli:
        base_diag.update({
            "iec958_prepare_attempted":True,
            "iec958_prepare_status":"FAILED",
            "iec958_prepare_reason":"PW_CLI_UNAVAILABLE",
            "iec958_prepare_method":"pw-cli",
        })
        return base_diag

    target_codecs:list[str]=[]
    seen:set[str]=set()
    for c in codecs_before+req_codecs:
        c_norm=CANONICAL_CODECS_MAP.get(c.lower(),c)
        if c_norm.upper() not in seen:
            seen.add(c_norm.upper())
            target_codecs.append(c_norm)

    codecs_payload=" ".join(target_codecs)
    cmd=[pw_cli,"s",str(sink_id),"Props",f"{{ iec958Codecs : [ {codecs_payload} ] }}"]

    try:
        proc=runner(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        returncode=getattr(proc,"returncode",1)
    except (OSError,ValueError,TypeError):
        returncode=1

    if returncode!=0:
        base_diag.update({
            "iec958_prepare_attempted":True,
            "iec958_prepare_status":"FAILED",
            "iec958_prepare_reason":"PW_CLI_MUTATION_FAILED",
            "iec958_prepare_method":"pw-cli",
        })
        return base_diag

    after_sink=inspect_sink(str(sink_id),runner=runner)
    codecs_after=list(after_sink.get("codecs",[])) if after_sink else []
    base_diag["iec958_codecs_after"]=codecs_after
    base_diag["iec958_prepare_attempted"]=True
    base_diag["iec958_prepare_method"]="pw-cli"

    if all(codec in codecs_after for codec in req_codecs):
        base_diag["iec958_prepare_status"]="SUCCESS"
        base_diag["iec958_prepare_reason"]="CODECS_APPLIED"
    else:
        base_diag["iec958_prepare_status"]="FAILED"
        base_diag["iec958_prepare_reason"]="MUTATION_NOT_EFFECTIVE"

    return base_diag


def runtime_config(home:pathlib.Path)->pathlib.Path:
    try:
        profile=json.loads((home/".config/openhtpc/profile.json").read_text(encoding="utf-8"))
        pure=profile["runtime_profiles"]["profiles"]["PURE"]
        candidate=pathlib.Path(pure["config_path"])
        if profile["runtime"]["status"]!="ready" or pure["generation_status"]!="generated" or not candidate.is_file():raise ValueError
        return candidate.resolve(strict=True)
    except (OSError,KeyError,TypeError,json.JSONDecodeError,ValueError) as error:
        raise ValueError("PLAYBACK_RUNTIME_NOT_READY") from error


def playback_policy(home:pathlib.Path)->tuple[Any,dict[str,Any]]:
    """Resolve the same persistent policy used by local files and DVD."""
    path=pathlib.Path(__file__).with_name("openhtpc-playback-policy.py")
    try:
        spec=importlib.util.spec_from_file_location("openhtpc_protected_optical_policy",path)
        if spec is None or spec.loader is None:raise ImportError
        policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
        decision=policy.resolve(home,None,"bluray")
        return (policy,decision)
    except (OSError,AttributeError,ImportError,TypeError,ValueError):
        return (None,{"mpv_args":[]})


def effective_policy_args(decision:dict[str,Any])->list[str]:
    """Make protected optical audio intent explicit after every included option."""
    args=[value for value in decision.get("mpv_args",[]) if not value.startswith(("--audio-spdif=","--audio-channels=","--aid="))]
    args.append("--aid=auto")
    requested=(decision.get("audio_output") or {}).get("requested","PCM")
    if requested=="BITSTREAM":
        args.extend(("--audio-channels=auto","--audio-spdif=ac3,eac3,dts,dts-hd,truehd"))
    else:
        args.append("--audio-spdif=")
    return args


def atomic_diagnostic(home:pathlib.Path,command:list[str],request:dict[str,Any],decision:dict[str,Any],raw:str,result:dict[str,Any],pipewire_diag:dict[str,Any]|None=None)->None:
    target=home/".local/state/openhtpc/protected-optical-last-command.json";target.parent.mkdir(parents=True,exist_ok=True)
    selected=next((line.strip() for line in raw.splitlines() if re.search(r"(?:Selected audio|^Audio:)",line,re.I)),"UNKNOWN")
    decoder=next((line.strip() for line in raw.splitlines() if "Selected decoder:" in line),"UNKNOWN")
    output=next((line.strip() for line in raw.splitlines() if line.strip().startswith("AO:")),"UNKNOWN")
    pw=pipewire_diag or {}
    data={"schema":1,"argv":command,"device":request.get("device"),"generation":request.get("generation"),
          "requested_audio_mode":(decision.get("audio_output") or {}).get("requested","PCM"),
          "selected_audio":selected,"selected_decoder":decoder,"effective_audio_output":output,
          "audio_sink_id":pw.get("audio_sink_id"),
          "audio_sink_name":pw.get("audio_sink_name"),
          "audio_sink_description":pw.get("audio_sink_description"),
          "audio_sink_profile":pw.get("audio_sink_profile"),
          "audio_sink_media_class":pw.get("audio_sink_media_class"),
          "audio_sink_is_hdmi":pw.get("audio_sink_is_hdmi"),
          "iec958_codecs_before":pw.get("iec958_codecs_before"),
          "iec958_codecs_requested":pw.get("iec958_codecs_requested"),
          "iec958_codecs_after":pw.get("iec958_codecs_after"),
          "iec958_prepare_attempted":pw.get("iec958_prepare_attempted"),
          "iec958_prepare_status":pw.get("iec958_prepare_status"),
          "iec958_prepare_reason":pw.get("iec958_prepare_reason"),
          "iec958_prepare_method":pw.get("iec958_prepare_method"),
          "timestamp":pw.get("timestamp"),
          **result}
    fd,name=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(data,stream,ensure_ascii=False,sort_keys=True);stream.write("\n")
        os.chmod(name,0o600);os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)


def open_disc(home:pathlib.Path,request:dict[str,Any],*,runner:Callable[...,Any]=subprocess.run,
              finder:Callable[[str],str|None]=shutil.which,clock:Callable[[],float]=time.monotonic,
              pw_runner:Callable[...,Any]|None=None)->dict[str,Any]:
    """Ask MPV's normal libbluray integration to open a validated device."""
    media_type=request.get("media_type");protection=request.get("protection")
    if media_type not in MEDIA_TYPES:return {"status":"UNSUPPORTED","process_started":False,"reason":"MEDIA_TYPE_UNSUPPORTED"}
    if protection not in {"UNPROTECTED","PROTECTED"}:return {"status":"UNSUPPORTED","process_started":False,"reason":"PROTECTION_UNKNOWN"}
    if protection=="PROTECTED" and request.get("provider_status")!="AVAILABLE":
        return {"status":"NOT_CONFIGURED","process_started":False,"reason":"PROVIDER_NOT_READY"}
    mpv=finder("mpv")
    if not mpv:return {"status":"OPEN_FAILED","process_started":False,"reason":"MPV_UNAVAILABLE"}
    try:runtime=runtime_config(home)
    except ValueError as error:return {"status":"OPEN_FAILED","process_started":False,"reason":str(error)}
    state_root=home/".local/state/openhtpc";state_root.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix="optical-mpv.",suffix=".log",dir=state_root);os.close(fd);attempt=pathlib.Path(name)
    policy,decision=playback_policy(home);policy_args=effective_policy_args(decision)
    requested_mode=(decision.get("audio_output") or {}).get("requested","PCM")
    pw_diag=None
    try:
        effective_pw_runner=pw_runner if pw_runner is not None else subprocess.run
        pw_diag=prepare_pipewire_hdmi_bitstream(requested_mode,runner=effective_pw_runner,finder=finder)
    except Exception:
        pw_diag={"audio_sink_id":None,"audio_sink_is_hdmi":False,"iec958_prepare_attempted":False,"iec958_prepare_status":"FAILED","iec958_prepare_reason":"PREPARATION_EXCEPTION"}
    command=[mpv,"--no-config",f"--include={runtime}","--fullscreen=yes","--force-window=immediate","--border=no","--terminal=no",
             "--cache=yes","--demuxer-readahead-secs=12.0","--demuxer-max-bytes=268435456","--demuxer-max-back-bytes=67108864",
             f"--log-file={attempt}",*policy_args,f"--bluray-device={request['device']}","--","bd://"]
    started=clock()
    try:
        completed=runner(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,env=os.environ.copy())
        exit_code=int(completed.returncode);reason="NONE"
    except OSError:
        exit_code=127;reason="MPV_NOT_STARTED"
    elapsed=max(0.0,clock()-started)
    try:raw=attempt.read_text(encoding="utf-8",errors="replace")
    except OSError:raw=""
    finally:attempt.unlink(missing_ok=True)
    opened=any(marker in raw for marker in OPEN_MARKERS)
    if policy is not None:
        try:policy.record_audio_observation(home,decision,raw)
        except (OSError,AttributeError,TypeError,ValueError):pass
    if not opened:reason="DISC_OPEN_REFUSED" if exit_code!=127 else reason
    elif elapsed<0.75:reason="MPV_EXITED_IMMEDIATELY"
    status="OPEN_SUCCESS" if opened and elapsed>=0.75 else "OPEN_FAILED"
    result={"status":status,"process_started":exit_code!=127,"media_opened":opened,"exit_code":exit_code,
            "elapsed_seconds":round(elapsed,3),"reason":reason,"media_type":media_type,"protection":protection}
    try:atomic_diagnostic(home,command,request,decision,raw,result,pw_diag)
    except (OSError,TypeError,ValueError):pass
    return result
