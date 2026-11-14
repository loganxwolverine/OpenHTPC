#!/usr/bin/env python3
"""Temporary, opt-in refresh matching. Display evidence is owned by T8.4.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime
import fcntl
from fractions import Fraction
import importlib.util
import hashlib
import json
import math
import os
import pathlib
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
import uuid


def read_presentation_telemetry(home: pathlib.Path | str) -> dict | None:
    path = pathlib.Path(home) / '.local/state/openhtpc/presentation-telemetry-last.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and data.get('schema') == 1 else None
    except (OSError, ValueError): return None


def load(name):
    path = pathlib.Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def policy(home):
    return read(home / '.config/openhtpc/user-config.json').get('refresh_matching') == 'AUTO'


def cadence(probe):
    """Conservative declared CFR: one progressive video, agreeing rational rates."""
    try:
        streams = [s for s in probe['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
        if len(streams) != 1: return None
        stream = streams[0]
        if stream.get('field_order') not in ('progressive', 'unknown', None): return None
        a, b = Fraction(stream['avg_frame_rate']), Fraction(stream['r_frame_rate'])
        if not 1 <= a <= 240 or a != b: return None
        return float(a)
    except (KeyError, TypeError, ValueError, ZeroDivisionError): return None


def probe_cadence_evidence(media):
    """Validate 128 decoded frames with 32 frames of lookahead before packet-limit drain.

    ffprobe flushes reordered frames at read_intervals' packet boundary. That
    synthetic tail is not a media cadence discontinuity. Thresholds within the
    validated window stay strict; no late/interior discontinuity is repaired.
    """
    evidence = {'cadence_source': 'FFPROBE_STREAM_AND_TIMESTAMPS',
                'cadence_rational': None, 'cadence_fps': None,
                'cadence_reason': 'MEDIA_UNAVAILABLE'}
    if media is None: return evidence
    path = pathlib.Path(media)
    evidence['media_identity'] = hashlib.sha256(os.fsencode(str(path))).hexdigest()
    evidence['media_exists'] = path.is_file()
    probe = load('openhtpc-playback-policy.py').probe_media(path)
    rate = cadence(probe)
    if rate is None:
        evidence['cadence_reason'] = 'STREAM_CADENCE_UNPROVEN'; return evidence
    stream = next(s for s in probe['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic'))
    evidence.update(avg_frame_rate=stream['avg_frame_rate'], r_frame_rate=stream['r_frame_rate'])
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-read_intervals', '%+#160', '-show_frames',
                                 '-show_entries', 'frame=best_effort_timestamp_time,interlaced_frame',
                                 '-of', 'json', '--', str(path)], capture_output=True, text=True, timeout=10, check=False)
        evidence['ffprobe_exit_code'] = result.returncode
        frames = json.loads(result.stdout)['frames'] if result.returncode == 0 else []
        evidence['frames_observed'] = len(frames)
        if len(frames) < 160:
            evidence['cadence_reason'] = 'INSUFFICIENT_LOOKAHEAD'; return evidence
        frames = frames[:128]
        evidence['frames_validated'] = len(frames)
        if any(f.get('interlaced_frame') != 0 for f in frames):
            evidence['cadence_reason'] = 'INTERLACED_OR_UNKNOWN'; return evidence
        stamps = [float(f['best_effort_timestamp_time']) for f in frames]
        if any(not math.isfinite(t) for t in stamps):
            evidence['cadence_reason'] = 'INVALID_TIMESTAMPS'; return evidence
        if any(abs((b-a) - 1/rate) > .0011 for a,b in zip(stamps, stamps[1:])):
            evidence['cadence_reason'] = 'TIMESTAMP_DISCONTINUITY'; return evidence
        if abs((stamps[-1]-stamps[0])*rate/(len(stamps)-1) - 1) > .002:
            evidence['cadence_reason'] = 'TIMESTAMP_RATE_MISMATCH'; return evidence
        evidence.update(cadence_fps=rate, cadence_rational=str(Fraction(stream['avg_frame_rate'])),
                        cadence_reason='VERIFIED_SAMPLE')
        return evidence
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        evidence['cadence_reason'] = type(error).__name__; return evidence


def probe_cadence(media):
    return probe_cadence_evidence(media)['cadence_fps']


def clean_multiple(refresh, rate):
    if type(refresh) not in (int, float) or type(rate) not in (int, float): return False
    if not math.isfinite(refresh) or not math.isfinite(rate) or rate <= 0: return False
    multiple = round(refresh / rate)
    return 1 <= multiple <= 5 and abs(refresh / multiple - rate) <= .003


def active(snapshot):
    outputs = snapshot.get('outputs', [])
    enabled = [o for o in outputs if o.get('active')]
    if len(enabled) != 1: return None
    chosen = snapshot.get('active_output')
    return chosen if isinstance(chosen, dict) and chosen.get('connector') == enabled[0].get('connector') else None


def identity(output):
    return {k: output.get(k) for k in ('connector', 'output_id', 'display_identity')}


def proven(output):
    return (output and isinstance(output.get('connector'), str) and type(output.get('output_id')) is int
            and output['output_id'] > 0 and isinstance(output.get('display_identity'), str)
            and re.fullmatch(r'[0-9a-f]{64}', output['display_identity'])
            and type(output.get('scale')) in (int, float))


def select(snapshot, rate):
    if len([o for o in snapshot.get('outputs', []) if o.get('active')]) > 1:
        return 'MULTI_DISPLAY_UNSUPPORTED', None
    output = active(snapshot)
    if not proven(output): return 'DISPLAY_UNAVAILABLE', None
    mode = output.get('current_mode') or {}
    modes = output.get('available_modes', [])
    current = [m for m in modes if m.get('id') == output.get('current_mode_id')]
    if (len(current) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+', str(output.get('current_mode_id')))
                or len({m.get('id') for m in modes}) != len(modes)
                or any(current[0].get(k) != mode.get(k) for k in ('width','height','refresh_hz'))):
        return 'MODE_UNAVAILABLE', None
    if rate is None: return 'UNAVAILABLE', None
    if clean_multiple(mode.get('refresh_hz'), rate): return 'ALREADY_MATCHED', None
    candidates = [m for m in modes if all(m.get(k) == mode.get(k) for k in ('width','height'))
                  and isinstance(m.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]+', m['id'])
                  and clean_multiple(m.get('refresh_hz'), rate)]
    if not candidates: return 'NO_CLEAN_MATCH', None

    # For cinema/video cadences up to 30 fps, prefer a clean 2x display cadence
    # when the display exposes one (25 -> 50 Hz, 29.97 -> 59.94 Hz, 30 -> 60 Hz).
    # Native 23.976/24 Hz remains the fallback when no clean 2x mode exists.
    def rank(candidate):
        refresh = candidate['refresh_hz']
        multiple = round(refresh / rate)
        preferred = 0 if rate <= 30 and multiple == 2 else 1
        return (preferred, abs(multiple - 2), refresh, candidate['id'])

    return 'MATCH_AVAILABLE', min(candidates, key=rank)


class Runtime:
    def __init__(self, home):
        self.home = home
        self.install = pathlib.Path(__file__).resolve().parent
        self.caps = load('openhtpc-capabilities.py')

    def snapshot(self):
        return self.caps.collect_display(self.home, self.install)

    def apply(self, output, mode_id):
        # Only a mode ID already reported for this exact KScreen output is accepted.
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(mode_id)): return False
        context = self.caps.resolve_graphical_context(home=self.home, install=self.install)
        if context.get('status') != 'RESOLVED': return False
        resolved_env = context.get('environment', {})
        if hasattr(self.caps, 'is_graphical_context_usable') and not self.caps.is_graphical_context_usable(resolved_env):
            return False
        env = os.environ.copy()
        for key in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        env.update(resolved_env)
        result = subprocess.run(['kscreen-doctor', f"output.{output['output_id']}.mode.{mode_id}"],
                                env=env, capture_output=True, text=True, timeout=8, check=False)
        return result.returncode == 0


POST_MODESET_SETTLE_SECONDS = 2.0


class Transaction:
    def __init__(self, home, runtime=None):
        self.home = pathlib.Path(home)
        self.runtime = runtime
        self.root = self.home / '.local/state/openhtpc'
        self.path = self.root / 'refresh-transaction.json'
        self.diag = self.root / 'refresh-match-last.json'
        self.record = {'schema': 1, 'owner': uuid.uuid4().hex, 'status': 'UNAVAILABLE',
                       'switch_requested': False, 'switch_verified': False,
                       'playback_started': False, 'restore_requested': False, 'restore_verified': False,
                       'settled': False, 'fallback_active': False,
                       'post_modeset_settle_seconds': POST_MODESET_SETTLE_SECONDS}
        self.lock = None

    def settle(self, seconds=POST_MODESET_SETTLE_SECONDS):
        if seconds > 0:
            time.sleep(seconds)

    def note(self, status, **fields):
        self.record.update(status=status, **fields)
        atomic(self.root / 'refresh-attempts' / (self.record['owner'] + '.json'), self.record)
        atomic(self.diag, self.record)

    def record_telemetry(self, telemetry):
        if not isinstance(telemetry, dict): return
        payload = {'schema': 1, 'dispatch_id': self.record.get('dispatch_id'),
                   'owner': self.record.get('owner'),
                   'timestamp': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                   **telemetry}
        atomic(self.root / 'presentation-telemetry-last.json', payload)

    def acquire(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.root / 'refresh-match.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, 'a')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close(); self.lock = None; return False
        return True

    def release(self):
        if self.lock:
            self.lock.close(); self.lock = None

    def snapshot(self):
        if self.runtime is None: self.runtime = Runtime(self.home)
        return self.runtime.snapshot()

    def verify(self, original, mode):
        # Bounded settling period; current truth is reread after every request.
        for _ in range(3):
            now = active(self.snapshot())
            if (now and identity(now) == identity(original)
                    and now.get('current_mode_id') == mode['id']
                    and now.get('scale') == original.get('scale')
                    and now.get('current_hdr_mode') == original.get('current_hdr_mode')
                    and all((now.get('current_mode') or {}).get(k) == mode.get(k) for k in ('width','height','refresh_hz'))):
                return True
            time.sleep(.1)
        return False

    def restore(self):
        tx = read(self.path)
        if not tx:
            if self.path.exists(): self.note('RECOVERY_UNSAFE'); return False
            return True
        original, mode = tx.get('original'), tx.get('original_mode')
        now = active(self.snapshot())
        if (tx.get('schema') != 1 or tx.get('state') not in ('PREPARED','APPLIED','RESTORED')
                or not isinstance(original, dict) or not isinstance(mode, dict) or not proven(now)
                or identity(now) != identity(original)
                or mode not in now.get('available_modes', [])):
            self.note('RECOVERY_UNSAFE'); return False
        # The original exact mode ID must still denote the original timing.
        if tx.get('state') != 'RESTORED' or not self.verify(original, mode):
            self.note('RESTORING', restore_requested=True)
            self.record['restore_request_success'] = self.runtime.apply(now, mode['id'])
        if not self.verify(original, mode):
            self.note('RESTORE_FAILED'); return False
        tx['state'] = 'RESTORED'; atomic(self.path, tx)
        self.note('RESTORED', original=original, original_mode=mode, restore_verified=True,
                  final_mode_id=mode['id'], final_display=active(self.snapshot()),
                  refresh_phase='REFRESH_MATCH_RESTORE')
        self.path.unlink()
        return True

    def begin(self, rate):
        if self.path.exists() and not self.restore(): return
        if not policy(self.home): self.note('DISABLED'); return
        snapshot = self.snapshot()
        status, target = select(snapshot, rate)
        self.note(status, cadence_fps=rate, match_decision=status)
        if not target: return
        original = active(snapshot)
        old = next(m for m in original['available_modes'] if m['id'] == original['current_mode_id'])
        # Revalidate immediately before persisting intent; never reuse changed topology.
        if active(self.snapshot()) != original:
            self.note('DISPLAY_CHANGED'); return
        tx = {'schema':1, 'owner':self.record['owner'], 'state':'PREPARED',
              'original':original, 'original_mode':old, 'target_mode':target}
        atomic(self.path, tx)
        self.record.update(original=original, original_mode=old, target_mode=target)
        self.note('PREPARED', switch_requested=True)
        request_ok = False
        try:
            request_ok = bool(self.runtime.apply(original, target['id']))
        except Exception:
            request_ok = False
        self.record['switch_request_success'] = request_ok

        verified = False
        if request_ok:
            try:
                verified = bool(self.verify(original, target))
            except Exception:
                verified = False

        if not request_ok or not verified:
            # Fallback path: safe restoration/retention of original mode
            self.note('SWITCH_FAILED', switch_status='FAILED', switch_verified=False,
                      fallback_active=True, refresh_phase='REFRESH_MATCH_FALLBACK')
            now = active(self.snapshot())
            at_original = bool(now and identity(now) == identity(original)
                               and now.get('current_mode_id') == old['id']
                               and self.verify(original, old))
            applied_corrective = False
            if not at_original and now:
                try:
                    self.note('RESTORING', restore_requested=True)
                    self.record['restore_request_success'] = bool(self.runtime.apply(now, old['id']))
                    applied_corrective = True
                except Exception:
                    self.record['restore_request_success'] = False

            restore_verified = bool(self.verify(original, old))
            if not restore_verified:
                usable = active(self.snapshot())
                restore_verified = bool(usable and proven(usable))

            if applied_corrective and restore_verified:
                self.settle(POST_MODESET_SETTLE_SECONDS)
                self.record['fallback_settled'] = True
                self.record['settled'] = True

            tx['state'] = 'RESTORED'
            atomic(self.path, tx)
            self.note('RESTORED', original=original, original_mode=old, restore_verified=restore_verified,
                      switch_status='FAILED', switch_verified=False, fallback_active=True,
                      refresh_phase='REFRESH_MATCH_FALLBACK',
                      final_mode_id=old['id'], final_display=active(self.snapshot()))
            if self.path.exists():
                self.path.unlink()
            return

        tx['state'] = 'APPLIED'
        atomic(self.path, tx)
        self.note('APPLIED', switch_verified=True, switch_status='VERIFIED',
                  refresh_phase='REFRESH_MATCH_APPLIED', achieved=active(self.snapshot()))
        self.settle(POST_MODESET_SETTLE_SECONDS)
        self.record['settled'] = True
        self.record['settle_seconds'] = POST_MODESET_SETTLE_SECONDS
        self.note('APPLIED', switch_verified=True, switch_status='VERIFIED', settled=True,
                  settle_seconds=POST_MODESET_SETTLE_SECONDS,
                  refresh_phase='REFRESH_MATCH_SETTLED', achieved=active(self.snapshot()))


@contextlib.contextmanager
def matching(home, media=None, *, runtime=None, rate=None, dispatch_id=None):
    tx = Transaction(home, runtime)
    tx.record['dispatch_id'] = dispatch_id
    owned = False
    handlers = {}
    try:
        try:
            owned = tx.acquire()
            if owned:
                # Catch termination before PREPARED, including the switch window.
                def stop(signum, frame): raise SystemExit(128 + signum)
                for sig in (signal.SIGTERM, signal.SIGHUP):
                    handlers[sig] = signal.signal(sig, stop)
                if rate is None and policy(pathlib.Path(home)):
                    evidence = probe_cadence_evidence(media)
                    tx.record.update(evidence)
                    rate = evidence['cadence_fps']
                tx.begin(rate)
        except Exception as error:
            if owned:
                try:
                    tx.note('UNAVAILABLE', error=type(error).__name__)
                    if tx.path.exists(): tx.restore()
                except Exception: pass
        yield tx if owned else None
    finally:
        if owned:
            try:
                if tx.path.exists(): tx.restore()
            except Exception as error:
                try: tx.note('RESTORE_FAILED', error=type(error).__name__)
                except OSError: pass
        for sig, handler in handlers.items(): signal.signal(sig, handler)
        tx.release()


class TelemetryCollector:
    PROPERTIES = (
        'video-sync',
        'container-fps',
        'estimated-vf-fps',
        'display-fps',
        'estimated-display-fps',
        'vsync-ratio',
        'vsync-jitter',
        'frame-drop-count',
        'decoder-frame-drop-count',
        'mistimed-frame-count',
        'vo-delayed-frame-count',
        'avsync',
        'total-avsync-change',
        'vo-passes',
    )

    def __init__(self, socket_path: pathlib.Path | str, resume_context=None):
        self.path = str(socket_path)
        self.resume_bridge = None
        if isinstance(resume_context,dict):
            try:
                import resume_mpv_bridge_lab
                self.resume_bridge = resume_mpv_bridge_lab.SessionBridge(
                    resume_context["home"],resume_context["media"],
                    previous=resume_context.get("previous"),
                    choice=resume_context.get("choice","Lire depuis le début"))
                self.PROPERTIES = (
                    *type(self).PROPERTIES,"time-pos","duration","pause","seeking")
            except (ImportError,OSError,ValueError,TypeError,KeyError):
                self.resume_bridge = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.lifecycle_thread = (
            threading.Thread(target=self._lifecycle_events,daemon=True)
            if self.resume_bridge is not None else None
        )
        self.lifecycle_done = threading.Event()
        self.resume_lock = threading.RLock()
        self.latest: dict = {}
        self.sample_count = 0
        self.max_frame_drops = 0
        self.max_decoder_frame_drops = 0
        self.max_mistimed = 0
        self.max_delayed = 0
        self.avsync_min: float | None = None
        self.avsync_max: float | None = None

    def start(self):
        if self.lifecycle_thread is not None:
            self.lifecycle_thread.start()
        self.thread.start()

    def _lifecycle_events(self):
        """Drain exact-child MPV lifecycle events on a dedicated IPC client."""
        deadline=time.monotonic()+3.0
        sock=None
        try:
            while not self.stop_event.is_set() and time.monotonic()<deadline:
                if os.path.exists(self.path):
                    break
                self.stop_event.wait(0.05)
            if self.stop_event.is_set() or not os.path.exists(self.path):
                return
            sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            sock.settimeout(0.25)
            sock.connect(self.path)
            import struct
            pid,uid,gid=struct.unpack("3i",sock.getsockopt(
                socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.geteuid():
                return
            try:
                exe=pathlib.Path("/proc")/str(pid)/"exe"
                if exe.resolve().name!="mpv":
                    return
            except OSError:
                return
            buf=b""
            while not self.stop_event.is_set():
                try: chunk=sock.recv(8192)
                except socket.timeout: continue
                except OSError: break
                if not chunk:break
                buf+=chunk
                if len(buf)>65536:
                    break
                while b"\n" in buf:
                    line,buf=buf.split(b"\n",1)
                    if not line:
                        continue
                    try:msg=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if msg.get("event") in ("end-file","seek","playback-restart"):
                        with self.resume_lock:
                            self.resume_bridge.event(msg,at_clock=time.monotonic())
                        if msg.get("event")=="end-file":
                            return
        except (OSError,ValueError):
            return
        finally:
            if sock is not None:
                try:sock.close()
                except OSError:pass
            self.lifecycle_done.set()

    def _run(self):
        deadline = time.time() + 3.0
        while not self.stop_event.is_set() and time.time() < deadline:
            if os.path.exists(self.path):
                break
            self.stop_event.wait(0.05)
        if self.stop_event.is_set() or not os.path.exists(self.path):
            return

        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(self.path)
        except Exception:
            if sock:
                try: sock.close()
                except Exception: pass
            return

        try:
            while not self.stop_event.is_set():
                sample = self._query(sock)
                if sample:
                    self.sample_count += 1
                    self.latest = sample
                    self._record_resume_sample(sample)
                    fd = sample.get('frame-drop-count')
                    if isinstance(fd, int) and fd > self.max_frame_drops:
                        self.max_frame_drops = fd
                    dfd = sample.get('decoder-frame-drop-count')
                    if isinstance(dfd, int) and dfd > self.max_decoder_frame_drops:
                        self.max_decoder_frame_drops = dfd
                    mt = sample.get('mistimed-frame-count')
                    if isinstance(mt, int) and mt > self.max_mistimed:
                        self.max_mistimed = mt
                    dl = sample.get('vo-delayed-frame-count')
                    if isinstance(dl, int) and dl > self.max_delayed:
                        self.max_delayed = dl
                    av = sample.get('avsync')
                    if isinstance(av, (int, float)):
                        if self.avsync_min is None or av < self.avsync_min:
                            self.avsync_min = float(av)
                        if self.avsync_max is None or av > self.avsync_max:
                            self.avsync_max = float(av)
                self.stop_event.wait(0.5)
        finally:
            try: sock.close()
            except Exception: pass

    def _record_resume_sample(self,sample,*,clock=None):
        if self.resume_bridge is None or not isinstance(sample,dict):
            return
        seeking=sample.get("seeking")
        paused=sample.get("pause")
        with self.resume_lock:
            self.resume_bridge.snapshot(
                clock=time.monotonic() if clock is None else clock,
                position=sample.get("time-pos"),
                duration=sample.get("duration"),
                paused=paused if type(paused) is bool else True,
                seeking=seeking if type(seeking) is bool else False)

    def _query(self, sock) -> dict | None:
        try:
            payload = ''.join(
                json.dumps({'command': ['get_property', name], 'request_id': i}) + '\n'
                for i, name in enumerate(self.PROPERTIES, 1)
            )
            sock.sendall(payload.encode('utf-8'))
            results = {}
            buf = b''
            while len(results) < len(self.PROPERTIES):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    if line:
                        msg = json.loads(line.decode('utf-8'))
                        if self.resume_bridge is not None and msg.get('event') in (
                                'end-file','seek','playback-restart'):
                            with self.resume_lock:
                                self.resume_bridge.event(msg,at_clock=time.monotonic())
                        req_id = msg.get('request_id')
                        if req_id is not None and 1 <= req_id <= len(self.PROPERTIES):
                            results[self.PROPERTIES[req_id - 1]] = msg.get('data')
            return results
        except Exception:
            return None

    def stop(self):
        if self.lifecycle_thread is not None and not self.lifecycle_done.is_set():
            self.lifecycle_done.wait(0.65)
        self.stop_event.set()
        self.thread.join(0.5)
        if self.lifecycle_thread is not None:
            self.lifecycle_thread.join(0.5)

    def result(self) -> dict | None:
        if self.sample_count == 0:
            return None
        return {
            'status': 'CAPTURED',
            'samples_count': self.sample_count,
            'effective_video_sync': self.latest.get('video-sync'),
            'container_fps': self.latest.get('container-fps'),
            'estimated_vf_fps': self.latest.get('estimated-vf-fps'),
            'display_fps': self.latest.get('display-fps'),
            'estimated_display_fps': self.latest.get('estimated-display-fps'),
            'vsync_ratio': self.latest.get('vsync-ratio'),
            'vsync_jitter': self.latest.get('vsync-jitter'),
            'frame_drop_count': self.latest.get('frame-drop-count'),
            'decoder_frame_drop_count': self.latest.get('decoder-frame-drop-count'),
            'mistimed_frame_count': self.latest.get('mistimed-frame-count'),
            'vo_delayed_frame_count': self.latest.get('vo-delayed-frame-count'),
            'last_avsync': self.latest.get('avsync'),
            'min_avsync': self.avsync_min,
            'max_avsync': self.avsync_max,
            'total_avsync_change': self.latest.get('total-avsync-change'),
            'max_frame_drop_count': self.max_frame_drops,
            'max_decoder_frame_drop_count': self.max_decoder_frame_drops,
            'max_mistimed_frame_count': self.max_mistimed,
            'max_vo_delayed_frame_count': self.max_delayed,
            'vo_passes': self.latest.get('vo-passes'),
        }


TEARDOWN_EXIT_MARKER = "Exiting... ("
TEARDOWN_GRACE_SECONDS = 1.5


def _log_path_from_command(command):
    if not isinstance(command, (list, tuple)):
        return None
    for item in command:
        if isinstance(item, str) and item.startswith("--log-file="):
            return pathlib.Path(item.split("=", 1)[1])
    return None


def _run_guarded_subprocess(command, **kwargs):
    """Run real MPV and force-release it only after MPV has announced its own exit.

    NVIDIA/Wayland/Vulkan can occasionally hang in gpu-next/libplacebo teardown
    after `Exiting... (Quit)` has already been logged.  At that point playback is
    over from the user's perspective; leaving the process alive pins the final
    frame on screen indefinitely.
    """
    opts = dict(kwargs)
    check = bool(opts.pop("check", False))
    timeout = opts.pop("timeout", None)
    if "input" in opts or "capture_output" in opts or opts.get("stdout") == subprocess.PIPE or opts.get("stderr") == subprocess.PIPE:
        return subprocess.run(command, check=check, timeout=timeout, **opts), False

    process = subprocess.Popen(command, **opts)
    log_path = _log_path_from_command(command)
    offset = 0
    exit_seen_at = None
    started = time.monotonic()
    forced = False
    try:
        while process.poll() is None:
            now = time.monotonic()
            if timeout is not None and now - started >= timeout:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(command, timeout)
            if log_path is not None:
                try:
                    with log_path.open("r", encoding="utf-8", errors="replace") as stream:
                        stream.seek(offset)
                        chunk = stream.read()
                        offset = stream.tell()
                    if exit_seen_at is None and TEARDOWN_EXIT_MARKER in chunk:
                        exit_seen_at = now
                except OSError:
                    pass
            if exit_seen_at is not None and now - exit_seen_at >= TEARDOWN_GRACE_SECONDS:
                forced = True
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
                break
            time.sleep(0.05)
        returncode = 0 if forced else process.returncode
        result = subprocess.CompletedProcess(command, returncode)
        if check and result.returncode:
            raise subprocess.CalledProcessError(result.returncode, command)
        return result, forced
    finally:
        if process.poll() is None:
            process.kill()
            try: process.wait(timeout=1.0)
            except subprocess.TimeoutExpired: pass



def _pin_resolved_bitstream_sink(command, decision, diag):
    """Bind playback to the post-modeset sink and fail safely when passthrough is unproven.

    A stored BITSTREAM preference is not proof that the sink which exists after an
    HDMI modeset accepts encoded audio.  Pin the resolved digital sink so mpv does
    not race a stale PipeWire default.  Preserve passthrough only after the audio
    preparation stage reports SUCCESS; otherwise disable passthrough for this
    launch and let mpv decode to PCM.  The persisted user preference is untouched.
    """
    if not isinstance(command, (list, tuple)):
        return command
    cmd = list(command)
    output = (decision or {}).get('audio_output') or {}
    if output.get('requested') != 'BITSTREAM':
        return cmd
    diag = diag if isinstance(diag, dict) else {}
    sink_name = diag.get('audio_sink_name')
    sink_profile = str(diag.get('audio_sink_profile') or '').lower()
    digital = bool(diag.get('audio_sink_is_hdmi')) or 'iec958' in sink_profile or (isinstance(sink_name, str) and '.iec958-' in sink_name.lower())
    if isinstance(sink_name, str) and sink_name and digital and not any(isinstance(arg, str) and arg.startswith('--audio-device=') for arg in cmd):
        arg = f'--audio-device=pipewire/{sink_name}'
        idx = cmd.index('--') if '--' in cmd else len(cmd)
        cmd.insert(idx, arg)
    if diag.get('iec958_prepare_status') != 'SUCCESS':
        replaced = False
        for index, arg in enumerate(cmd):
            if isinstance(arg, str) and arg.startswith('--audio-spdif='):
                cmd[index] = '--audio-spdif='
                replaced = True
        if not replaced:
            idx = cmd.index('--') if '--' in cmd else len(cmd)
            cmd.insert(idx, '--audio-spdif=')
        if isinstance(output, dict):
            output['effective_resolved'] = 'PCM'
            output['effective_reason'] = 'passthrough_unproven_post_modeset'
    else:
        if isinstance(output, dict):
            output['effective_resolved'] = 'BITSTREAM'
            output['effective_reason'] = 'passthrough_confirmed_post_modeset'
    return cmd


def run_playback(home, command, *, media=None, rate=None, runner=subprocess.run, dispatch_id=None, audio_prep=None, decision=None, resume_context=None, **kwargs):
    with matching(home, media, rate=rate, dispatch_id=dispatch_id) as tx:
        switched = bool(tx and tx.record.get('switch_requested') and tx.record.get('switch_verified') and tx.record.get('status') == 'APPLIED')
        prep_diag = {}
        if audio_prep is not None:
            try:
                value = audio_prep(settle_timeout=1.5 if switched else 0.0)
                if isinstance(value, dict): prep_diag = value
            except TypeError:
                try:
                    value = audio_prep()
                    if isinstance(value, dict): prep_diag = value
                except Exception: pass
            except Exception:
                pass
        elif decision is not None:
            try:
                policy_mod = load("openhtpc-playback-policy.py")
                if hasattr(policy_mod, "prepare_audio_target_bitstream"):
                    value = policy_mod.prepare_audio_target_bitstream(decision, runner=runner, settle_timeout=1.5 if switched else 0.0)
                    if isinstance(value, dict): prep_diag = value
            except Exception:
                pass
        owner = tx.record['owner'] if tx else uuid.uuid4().hex
        sock_path = pathlib.Path(tempfile.gettempdir()) / f"openhtpc-mpv-{owner}.sock"
        if sock_path.exists():
            try: sock_path.unlink()
            except OSError: pass

        mpv_cmd = list(command) if isinstance(command, (list, tuple)) else str(command)
        mpv_cmd = _pin_resolved_bitstream_sink(mpv_cmd, decision, prep_diag)
        if tx and isinstance(mpv_cmd, list):
            pinned = next((arg.split('=', 1)[1] for arg in mpv_cmd if isinstance(arg, str) and arg.startswith('--audio-device=')), None)
            if pinned:
                effective_mode = ((decision or {}).get('audio_output') or {}).get('effective_resolved')
                effective_reason = ((decision or {}).get('audio_output') or {}).get('effective_reason')
                try: tx.note(tx.record['status'], effective_audio_device=pinned,
                             effective_audio_mode=effective_mode,
                             effective_audio_reason=effective_reason)
                except OSError: pass
        ipc_arg = f"--input-ipc-server={sock_path}"
        if isinstance(mpv_cmd, list):
            if not any(isinstance(a, str) and a.startswith("--input-ipc-server=") for a in mpv_cmd):
                idx = mpv_cmd.index("--") if "--" in mpv_cmd else len(mpv_cmd)
                mpv_cmd.insert(idx, ipc_arg)
        elif isinstance(mpv_cmd, str) and "--input-ipc-server=" not in mpv_cmd:
            mpv_cmd = f"{mpv_cmd} {ipc_arg}"

        collector = TelemetryCollector(sock_path,resume_context=resume_context)
        collector.start()
        teardown_forced = False
        try:
            if runner is subprocess.run:
                result, teardown_forced = _run_guarded_subprocess(mpv_cmd, **kwargs)
            else:
                result = runner(mpv_cmd, **kwargs)
        finally:
            collector.stop()
            if sock_path.exists():
                try: sock_path.unlink()
                except OSError: pass

        telemetry = collector.result()
        if collector.resume_bridge is not None:
            try:
                outcome=collector.resume_bridge.finish(
                    getattr(result,"returncode",None))
            except (OSError,ValueError):
                outcome="RESUME_PERSISTENCE_FAILED"
            try:
                setattr(result,"openhtpc_resume_outcome",outcome)
            except Exception:
                pass
        if tx:
            try:
                tx.note(
                    tx.record['status'],
                    playback_started=True,
                    playback_exit_code=getattr(result, 'returncode', None),
                    playback_teardown_forced=teardown_forced,
                    presentation_telemetry=telemetry,
                )
                if telemetry:
                    tx.record_telemetry(telemetry)
            except OSError:
                pass
        elif telemetry:
            target = pathlib.Path(home) / '.local/state/openhtpc/presentation-telemetry-last.json'
            atomic(target, {
                'schema': 1,
                'dispatch_id': dispatch_id,
                'owner': owner,
                'timestamp': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
                **telemetry,
            })
        # Preserve the exact command that reached the runner after refresh/audio
        # resolution (including fail-safe PCM, sink pinning and IPC injection).
        # Higher-level diagnostics may inspect this without changing the return API.
        try:
            setattr(result, 'openhtpc_effective_command', list(mpv_cmd) if isinstance(mpv_cmd, list) else mpv_cmd)
        except Exception:
            pass
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--rate', type=float, default=None, help='Trusted source cadence supplied by the caller')
    parser.add_argument('--decision-json', default=None, help='Resolved playback policy JSON; audio preparation occurs after display settle and before mpv')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.rate is not None and (not math.isfinite(args.rate) or not 1 <= args.rate <= 240):
        parser.error('--rate must be a finite cadence between 1 and 240 fps')
    home = pathlib.Path(os.environ.get('OPENHTPC_HOME', pathlib.Path.home()))
    if args.recover:
        tx = Transaction(home)
        try:
            if tx.acquire() and tx.path.exists(): tx.restore()
        except Exception as error:
            print(f'OPENHTPC refresh recovery: {type(error).__name__}', flush=True)
        finally: tx.release()
        return 0
    decision = None
    if args.decision_json is not None:
        try:
            decision = json.loads(args.decision_json)
        except (TypeError, ValueError):
            parser.error('--decision-json must be valid JSON')
        if not isinstance(decision, dict):
            parser.error('--decision-json must decode to an object')
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    return run_playback(home, command, rate=args.rate, decision=decision, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
