"""OPENHTPC local MEDIA playback resume: isolated candidate, no installed code.

Contract: on first play start from zero. For a genuinely watched, voluntarily
interrupted film (<=90% watched), offer Reprise de lecture / Lire depuis le
début. At >90%, start from zero without prompting. Never trust a seek as
watched time. No optical/disc menu paths here. No MPV daemon or UI takeover.
"""
from __future__ import annotations
import hashlib
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import secrets

MIN_SECONDS=30.0
MAX_DURATION=24*3600.0
WATCHED_THRESHOLD=0.9
SCHEMA=1

def _finite(value):
    return type(value) in (float,int) and math.isfinite(value)

def identity(media:Path):
    path=Path(media).resolve(strict=True)
    s=path.stat()
    if not stat.S_ISREG(s.st_mode):
        raise ValueError("MEDIA_NOT_REGULAR")
    blob=json.dumps([str(path),s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns],
                    ensure_ascii=False,separators=(",",":")).encode()
    return hashlib.sha256(blob).hexdigest()

def _state_path(home:Path,key:str):
    assert len(key)==64 and all(c in "0123456789abcdef" for c in key)
    return Path(home)/".local/state/openhtpc/resume-media"/(key+".json")

def _read(path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size>4096:return None
        with path.open("r",encoding="utf-8") as f:
            return json.load(f)
    except (OSError,ValueError,TypeError):
        return None

def offer(home:Path,media:Path):
    """Return saved seconds and UI choices or None; no file mutations."""
    try:
        key=identity(media)
        state=_read(_state_path(home,key))
    except (OSError,ValueError):
        return None
    if type(state) is not dict or set(state)!={
        "schema","key","duration","position","watched_seconds"}:
        return None
    if state["schema"]!=SCHEMA or state["key"]!=key:
        return None
    duration=state["duration"]
    pos=state["position"]
    watched=state["watched_seconds"]
    if not all(_finite(v) for v in (duration,pos,watched)):
        return None
    if not MIN_SECONDS*2<=duration<=MAX_DURATION:
        return None
    if not MIN_SECONDS<=pos<=duration-MIN_SECONDS:
        return None
    if not MIN_SECONDS<=watched<=WATCHED_THRESHOLD*duration:
        return None
    return {
        "position_seconds":round(float(pos),2),
        "watched_seconds":float(watched),
        "duration_seconds":float(duration),
        "choices":("Reprise de lecture","Lire depuis le début"),
    }

def start_arg(saved,choice):
    """Only from a trusted modal selection; explicit start, not auto-resume."""
    if choice=="Lire depuis le début":
        return "--start=0"
    if choice=="Reprise de lecture" and isinstance(saved,dict):
        pos=saved.get("position_seconds")
        if _finite(pos) and MIN_SECONDS<=pos<=MAX_DURATION:
            return "--start="+format(float(pos),".3f")
    raise ValueError("INVALID_RESUME_CHOICE")

def _commit(home:Path,key:str,position:float,duration:float,watched:float):
    path=_state_path(home,key)
    folder=path.parent
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink() or folder.stat().st_uid!=os.geteuid():
        raise OSError("UNSAFE_RESUME_DIRECTORY")
    if path.is_symlink():
        raise OSError("UNSAFE_RESUME_FILE")
    payload=json.dumps({
        "schema":SCHEMA,"key":key,"duration":round(duration,3),
        "position":round(position,3),"watched_seconds":round(watched,3),
    },sort_keys=True,separators=(",",":")).encode()
    fd,tmp=tempfile.mkstemp(prefix=".resume-",suffix=".tmp",dir=folder)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as f:
            f.write(payload)
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        dirfd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def _clear(home:Path,key:str):
    path=_state_path(home,key)
    if path.is_symlink():raise OSError("UNSAFE_RESUME_FILE")
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False

def refresh_stamp(home:Path):
    """Current-generation signal for the *existing* retained Flex controller."""
    target=Path(home)/".local/state/openhtpc/resume-media/refresh-stamp"
    try:
        if target.is_symlink() or not target.is_file():
            return None
        if target.stat().st_size!=32:
            return None
        value=target.read_text("ascii")
        if len(value)!=32 or any(c not in "0123456789abcdef" for c in value):
            return None
        return value
    except (OSError,UnicodeError):
        return None

def _notify_refresh(home:Path):
    """Publish a unique stamp AFTER a durable checkpoint change.

    The HOME controller, not this player child, owns regeneration.
    A missed stamp is fail-visible by testing and does not invalidate
    the checkpoint. No global process, trigger, or direct Flex edits.
    """
    folder=Path(home)/".local/state/openhtpc/resume-media"
    if folder.is_symlink():
        raise OSError("UNSAFE_RESUME_REFRESH_DIR")
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink() or folder.stat().st_uid!=os.geteuid():
        raise OSError("UNSAFE_RESUME_REFRESH_DIR")
    target=folder/"refresh-stamp"
    if target.is_symlink():
        raise OSError("UNSAFE_RESUME_REFRESH_STAMP")
    fd,tmp=tempfile.mkstemp(prefix=".refresh-",suffix=".tmp",dir=folder)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="ascii") as f:
            f.write(secrets.token_hex(16))
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
        dirfd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dirfd)
        finally:os.close(dirfd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


@lru_cache(maxsize=96)
def _refresh_epoch_cached(folder_text, folder_mtime_ns, stamp):
    """A checkpoint update changes directory metadata even if stamp I/O failed."""
    folder=Path(folder_text)
    items=[]
    try:
        for child in folder.glob("*.json"):
            name=child.name
            if (len(name)!=69 or not name.endswith(".json")
                or any(c not in "0123456789abcdef" for c in name[:-5])
                or child.is_symlink()):
                continue
            st=child.stat()
            if stat.S_ISREG(st.st_mode):
                items.append((name,st.st_ino,st.st_size,st.st_mtime_ns))
    except OSError:
        return None
    # Do not fabricate a valid epoch from an empty folder with an invalid
    # or symlinked stamp. The Core publisher explicitly strips an obsolete
    # suffix when a previously active checkpoint disappears.
    if not items and stamp is None:
        return None
    material=json.dumps([stamp, sorted(items)], separators=(",",":")).encode("ascii")
    return hashlib.blake2s(material,digest_size=16).hexdigest()

def refresh_generation(home:Path):
    """Retained Flex epoch survives missed refresh-stamp writes and EOF deletes.

    Cached by directory mtime, so HOME polls in O(1) while unchanged.
    """
    folder=Path(home)/".local/state/openhtpc/resume-media"
    try:
        if folder.is_symlink() or not folder.is_dir():
            return None
        st=folder.stat()
        return _refresh_epoch_cached(str(folder),st.st_mtime_ns,refresh_stamp(home))
    except OSError:
        return None

def _safe_notify_refresh(home):
    try:
        _notify_refresh(home)
        return True
    except OSError:
        # State is durable. HOME notices its changed directory via the epoch.
        return False

class Session:
    """MPV IPC observer data model (only the independent lab calls observe)."""
    def __init__(self,home:Path,media:Path,previous=None,choice="Lire depuis le début"):
        self.home=Path(home)
        self.key=identity(media)
        self.duration=None
        self.position=None
        self.watched=float(previous["watched_seconds"]) if (
            choice=="Reprise de lecture" and isinstance(previous,dict)
            and _finite(previous.get("watched_seconds"))) else 0.0
        self.prev=None
        self.started=False
        self.invalidated=False

    def observe(self,*,clock,position,duration,paused=False,seeking=False):
        if self.invalidated:
            return
        if not all(_finite(v) for v in (clock,position,duration)):
            return
        if not (MIN_SECONDS*2<=duration<=MAX_DURATION and 0<=position<=duration):
            return
        if self.duration is not None and abs(duration-self.duration)>max(2,duration*.01):
            # Never keep an old checkpoint after file timeline changed.
            self.prev=None;self.started=False;self.invalidated=True
            return
        self.duration=float(duration)
        self.position=float(position)
        self.started=True
        if self.prev:
            prev_clock,prev_pos,prev_pause=self.prev
            wall=clock-prev_clock
            advanced=position-prev_pos
            # Do not turn a seek/pause into watched time. Cap at real time;
            # accumulation is from monotonic samples, not final position.
            if (not paused and not seeking and not prev_pause
                and .05<=wall<=5.0 and 0<advanced<=wall*1.45+.35):
                self.watched+=min(float(advanced),float(wall))
        self.prev=(float(clock),float(position),bool(paused or seeking))

    def finish(self,*,voluntary_stop:bool,real_end:bool=False):
        """Preserve prior state on crash/error/cancel; clear after true EOF."""
        if not self.started or self.duration is None or self.position is None:
            return "UNCHANGED"
        if real_end:
            if _clear(self.home,self.key):
                return "COMPLETED" if _safe_notify_refresh(self.home) else "COMPLETED_REFRESH_FALLBACK"
            return "COMPLETED"
        if not voluntary_stop:
            return "UNCHANGED"
        if not (MIN_SECONDS<=self.position<=self.duration-MIN_SECONDS
                and MIN_SECONDS<=self.watched<=WATCHED_THRESHOLD*self.duration):
            # Distinguish invalid progress from an observed completed watch.
            if self.watched>WATCHED_THRESHOLD*self.duration:
                if _clear(self.home,self.key):
                    _safe_notify_refresh(self.home)
                return "START_NEXT_TIME"
            return "UNCHANGED"
        _commit(self.home,self.key,self.position,self.duration,self.watched)
        return "SAVED" if _safe_notify_refresh(self.home) else "SAVED_REFRESH_FALLBACK"
