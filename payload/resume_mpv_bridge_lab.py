"""LAB: MPV exact-child IPC bridge for OPENHTPC resume state, no product writes.

This intentionally does not create a Flex instance or launch MPV: Core alone
owns launch. The bridge only follows the actual child while the Core's lifetime
lock is held. End-file event with reason=eof or quit is required to commit a
resume checkpoint. No event, error/crash or stdin-driven termination => no save.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import time

P=Path(__file__).with_name("resume_media_lab.py")
spec=importlib.util.spec_from_file_location("oht_media_resume_state",P)
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class PeerMismatch(Exception):
    pass

class BridgeError(Exception):
    pass

class SessionBridge:
    def __init__(self, home, media, *, previous=None, choice="Lire depuis le début"):
        self.session=core.Session(home,media,previous=previous,choice=choice)
        self.media=Path(media)
        self.end_reason=None
        self.eof_event_seen=False
        self.quit_event_seen=False
        self.error_event_seen=False
        self.properties={}
        self.last_poll_monotonic=None
        self.last_accounted_monotonic=None
        self.start_position=core.start_arg(previous,choice) if previous else "--start=0"
        self.media_key=self.session.key

    def event(self, message, at_clock):
        if not isinstance(message,dict):
            return
        if message.get("event")=="end-file":
            reason=message.get("reason")
            if reason=="eof":
                self.end_reason="eof";self.eof_event_seen=True
            elif reason=="quit":
                self.end_reason="quit";self.quit_event_seen=True
            else:
                self.end_reason=reason if isinstance(reason,str) else "error"
                self.error_event_seen=True
        if message.get("event")=="seek":
            self.properties["seeking"]=True
        if message.get("event")=="playback-restart":
            self.properties["seeking"]=False
        should_sample=False
        if message.get("event")=="property-change":
            name=message.get("name")
            if name in ("time-pos","duration","pause","seeking"):
                self.properties[name]=message.get("data")
                # mpv emits multiple properties at the same clock time.
                # Only sample on position updates, not on every notification.
                should_sample=name=="time-pos"
        # Never treat pause or seek as watched time.
        props=self.properties
        if (should_sample and "duration" in props
            and type(props.get("pause",False)) is bool
            and type(props.get("seeking",False)) is bool
            and (self.last_accounted_monotonic is None
                 or at_clock-self.last_accounted_monotonic>=0.25
                 or at_clock<self.last_accounted_monotonic)):
            # MPV can publish time-pos 25–60 times per second. Every
            # notification is too small for Session's guarded accounting.
            # Sample at a bounded period without resetting the previous
            # time/position baseline on each individual video frame.
            self.session.observe(
                clock=at_clock,
                position=props["time-pos"],
                duration=props["duration"],
                paused=props.get("pause",False),
                seeking=props.get("seeking",False))
            self.last_accounted_monotonic=at_clock
        self.last_poll_monotonic=at_clock

    def snapshot(self, *, clock, position, duration, paused, seeking):
        self.properties.update({
            "time-pos":position,"duration":duration,
            "pause":paused,"seeking":seeking,
        })
        self.session.observe(
            clock=clock,position=position,duration=duration,
            paused=paused,seeking=seeking)
        self.last_poll_monotonic=clock

    def finish(self, exit_code, *, identity_is_current=True):
        # A stale file changed during playback cannot overwrite any marker.
        try:
            same_media=(core.identity(self.media)==self.media_key)
        except (OSError,ValueError):
            same_media=False
        if not identity_is_current or not same_media:
            return "STALE_MEDIA"
        if not core._finite(exit_code):
            return "UNCHANGED"
        if exit_code!=0 or self.error_event_seen:
            return "UNCHANGED"
        if self.eof_event_seen:
            return self.session.finish(voluntary_stop=False,real_end=True)
        if self.quit_event_seen:
            return self.session.finish(voluntary_stop=True,real_end=False)
        # Do not infer voluntary stop from an exit code alone.
        return "UNCHANGED"


def connect_verified(path, *, expected_pid, expected_uid=None):
    """Verified client socket to Core's exact MPV process; not a global server."""
    path=Path(path)
    expected_uid=os.geteuid() if expected_uid is None else expected_uid
    if not path.is_socket() or path.is_symlink():
        raise BridgeError("IPC_NOT_SOCKET")
    if path.stat().st_uid!=expected_uid:
        raise PeerMismatch("IPC_FILE_OWNER_MISMATCH")
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        client.settimeout(2)
        client.connect(str(path))
        raw=client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
        pid,uid,gid=struct.unpack("3i",raw)
        if uid!=expected_uid or pid!=expected_pid:
            raise PeerMismatch("MPV_PEER_ID_MISMATCH")
        return client
    except Exception:
        client.close()
        raise

def launch_plan(home,media,*,choice=None):
    """Pure gate immediately after Core validates the existing media token."""
    saved=core.offer(home,media)
    if saved is None:
        if choice is not None:
            return {"state":"STALE"}
        return {"state":"START","argument":"--start=0","saved":None}
    if choice is None:
        return {"state":"PROMPT","choices":saved["choices"],
                "position_seconds":saved["position_seconds"],
                "saved":saved}
    if choice=="CANCEL":
        return {"state":"CANCEL"}
    arg=core.start_arg(saved,choice)
    return {"state":"START","argument":arg,"saved":saved}

def verified_choice(home,media,*,choice,expected_key):
    """Bind both buttons to the same exact media identity, deny stale actions."""
    if core.identity(media)!=expected_key:
        raise ValueError("STALE_MEDIA")
    p=launch_plan(home,media,choice=choice)
    if p["state"]!="START":
        raise ValueError("CHOICE_NOT_AUTHORIZED")
    return p
