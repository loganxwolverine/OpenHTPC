#!/usr/bin/env python3
"""Bounded MPV/libbluray backend for already-authorized optical requests."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

OPEN_MARKERS=("VO:","AO:","Video:","Audio:","Starting playback")
MEDIA_TYPES={"BLURAY","UHD_BLURAY"}


def runtime_config(home:pathlib.Path)->pathlib.Path:
    try:
        profile=json.loads((home/".config/openhtpc/profile.json").read_text(encoding="utf-8"))
        pure=profile["runtime_profiles"]["profiles"]["PURE"]
        candidate=pathlib.Path(pure["config_path"])
        if profile["runtime"]["status"]!="ready" or pure["generation_status"]!="generated" or not candidate.is_file():raise ValueError
        return candidate.resolve(strict=True)
    except (OSError,KeyError,TypeError,json.JSONDecodeError,ValueError) as error:
        raise ValueError("PLAYBACK_RUNTIME_NOT_READY") from error


def open_disc(home:pathlib.Path,request:dict[str,Any],*,runner:Callable[...,Any]=subprocess.run,
              finder:Callable[[str],str|None]=shutil.which,clock:Callable[[],float]=time.monotonic)->dict[str,Any]:
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
    command=[mpv,"--no-config",f"--include={runtime}","--fullscreen=yes","--force-window=immediate","--border=no","--terminal=no",
             "--cache=yes","--demuxer-readahead-secs=12.0","--demuxer-max-bytes=268435456","--demuxer-max-back-bytes=67108864",
             f"--log-file={attempt}",f"--bluray-device={request['device']}","--","bd://"]
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
    if not opened:reason="DISC_OPEN_REFUSED" if exit_code!=127 else reason
    elif elapsed<0.75:reason="MPV_EXITED_IMMEDIATELY"
    status="OPEN_SUCCESS" if opened and elapsed>=0.75 else "OPEN_FAILED"
    return {"status":status,"process_started":exit_code!=127,"media_opened":opened,"exit_code":exit_code,
            "elapsed_seconds":round(elapsed,3),"reason":reason,"media_type":media_type,"protection":protection}
