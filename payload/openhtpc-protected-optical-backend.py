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


def _load_playback_policy():
    path = pathlib.Path(__file__).with_name("openhtpc-playback-policy.py")
    try:
        spec = importlib.util.spec_from_file_location("openhtpc_playback_policy", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, AttributeError, ImportError, TypeError, ValueError):
        return None


_POLICY_MODULE = _load_playback_policy()

REQUIRED_BITSTREAM_CODECS = getattr(_POLICY_MODULE, "REQUIRED_BITSTREAM_CODECS", ("PCM", "DTS", "AC3", "EAC3", "TrueHD", "DTS-HD"))
CANONICAL_CODECS_MAP = getattr(_POLICY_MODULE, "CANONICAL_CODECS_MAP", {
    "pcm": "PCM", "dts": "DTS", "ac3": "AC3", "eac3": "EAC3", "truehd": "TrueHD", "dts-hd": "DTS-HD", "dtshd": "DTS-HD"
})
parse_wpctl_sink = getattr(_POLICY_MODULE, "parse_wpctl_sink", None)
inspect_sink = getattr(_POLICY_MODULE, "inspect_sink", None)
parse_spa_codecs = getattr(_POLICY_MODULE, "parse_spa_codecs", None)
get_effective_spa_codecs = getattr(_POLICY_MODULE, "get_effective_spa_codecs", None)
prepare_pipewire_hdmi_bitstream = getattr(_POLICY_MODULE, "prepare_pipewire_hdmi_bitstream", None)


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
    policy = _POLICY_MODULE or _load_playback_policy()
    if policy is not None:
        try:
            decision = policy.resolve(home, None, "bluray")
            return (policy, decision)
        except (OSError, AttributeError, ImportError, TypeError, ValueError):
            pass
    return (None, {"mpv_args": []})


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
    target_info = decision.get("audio_target") or {}
    data={"schema":1,"argv":command,"device":request.get("device"),"generation":request.get("generation"),
          "requested_audio_mode":(decision.get("audio_output") or {}).get("requested","PCM"),
          "gpu_render_binding":decision.get("gpu_render_binding") or decision.get("gpu_binding") or {},
          "gpu_binding":decision.get("gpu_render_binding") or decision.get("gpu_binding") or {},
          "target_configured":target_info.get("configured","SYSTEM"),
          "target_configured_label":target_info.get("configured_label","SYSTEM"),
          "target_available":target_info.get("available",True),
          "target_effective":target_info.get("effective","SYSTEM"),
          "target_fallback":target_info.get("fallback",False),
          "selected_audio":selected,"selected_decoder":decoder,"effective_audio_output":output,
          "audio_sink_id":pw.get("audio_sink_id"),
          "audio_sink_name":pw.get("audio_sink_name"),
          "audio_sink_description":pw.get("audio_sink_description"),
          "audio_sink_profile":pw.get("audio_sink_profile"),
          "audio_sink_media_class":pw.get("audio_sink_media_class"),
          "audio_sink_is_hdmi":pw.get("audio_sink_is_hdmi"),
          "iec958_property_codecs":pw.get("iec958_property_codecs"),
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
        if hasattr(policy, "prepare_audio_target_bitstream"):
            pw_diag=policy.prepare_audio_target_bitstream(decision,runner=effective_pw_runner,finder=finder)
        else:
            target_info = decision.get("audio_target") or {}
            sink_target = target_info.get("sink_target") or "@DEFAULT_AUDIO_SINK@"
            target_desc = target_info.get("descriptor")
            pw_diag=prepare_pipewire_hdmi_bitstream(requested_mode,sink_target=sink_target,target_descriptor=target_desc,runner=effective_pw_runner,finder=finder)
    except Exception:
        pw_diag={"audio_sink_id":None,"audio_sink_is_hdmi":False,"iec958_prepare_attempted":False,"iec958_prepare_status":"FAILED","iec958_prepare_reason":"PREPARATION_EXCEPTION"}
    command=[mpv,"--no-config",f"--include={runtime}","--fullscreen=yes","--force-window=immediate","--border=no","--terminal=no",
             "--cache=yes","--demuxer-readahead-secs=12.0","--demuxer-max-bytes=268435456","--demuxer-max-back-bytes=67108864",
             f"--log-file={attempt}",*policy_args,f"--bluray-device={request['device']}","--","bd://"]
    gpu_binding = decision.get("gpu_render_binding") or decision.get("gpu_binding") or {}
    if gpu_binding:
        runtime_helper = home / ".local/lib/openhtpc/openhtpc-runtime.py"
        if not runtime_helper.is_file():
            runtime_helper = pathlib.Path(__file__).with_name("openhtpc-runtime.py")
        if runtime_helper.is_file():
            try:
                subprocess.run(
                    [
                        str(runtime_helper), "log", "--component", "playback", "--event", "GPU_RENDER_BINDING",
                        "--field", f"status={gpu_binding.get('status')}",
                        "--field", f"pci_address={gpu_binding.get('pci_address') or ''}",
                        "--field", f"drm_render_path={gpu_binding.get('drm_render_path') or ''}",
                        "--field", f"vulkan_uuid={gpu_binding.get('vulkan_uuid') or ''}",
                        "--field", f"reason={gpu_binding.get('reason') or ''}",
                    ],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=2, check=False,
                )
            except Exception:
                pass
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
