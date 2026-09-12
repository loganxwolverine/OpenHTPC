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
    return 'MATCH_AVAILABLE', min(candidates, key=lambda m: (m['refresh_hz'], m['id']))


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


class Transaction:
    def __init__(self, home, runtime=None):
        self.home = pathlib.Path(home)
        self.runtime = runtime
        self.root = self.home / '.local/state/openhtpc'
        self.path = self.root / 'refresh-transaction.json'
        self.diag = self.root / 'refresh-match-last.json'
        self.record = {'schema': 1, 'owner': uuid.uuid4().hex, 'status': 'UNAVAILABLE',
                       'switch_requested': False, 'switch_verified': False,
                       'playback_started': False, 'restore_requested': False, 'restore_verified': False}
        self.lock = None

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
                  final_mode_id=mode['id'], final_display=active(self.snapshot()))
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
        request_ok = self.runtime.apply(original, target['id'])
        self.record['switch_request_success'] = request_ok
        if not request_ok or not self.verify(original, target):
            self.note('SWITCH_FAILED', switch_status='FAILED')
            self.restore(); return
        tx['state'] = 'APPLIED'; atomic(self.path, tx)
        self.note('APPLIED', switch_verified=True, switch_status='VERIFIED', achieved=active(self.snapshot()))


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

    def __init__(self, socket_path: pathlib.Path | str):
        self.path = str(socket_path)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.latest: dict = {}
        self.sample_count = 0
        self.max_frame_drops = 0
        self.max_decoder_frame_drops = 0
        self.max_mistimed = 0
        self.max_delayed = 0
        self.avsync_min: float | None = None
        self.avsync_max: float | None = None

    def start(self):
        self.thread.start()

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
                        req_id = msg.get('request_id')
                        if req_id is not None and 1 <= req_id <= len(self.PROPERTIES):
                            results[self.PROPERTIES[req_id - 1]] = msg.get('data')
            return results
        except Exception:
            return None

    def stop(self):
        self.stop_event.set()
        self.thread.join(0.5)

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


def run_playback(home, command, *, media=None, runner=subprocess.run, dispatch_id=None, audio_prep=None, decision=None, **kwargs):
    with matching(home, media, dispatch_id=dispatch_id) as tx:
        switched = bool(tx and tx.record.get('switch_requested'))
        if audio_prep is not None:
            try:
                audio_prep(settle_timeout=1.5 if switched else 0.0)
            except TypeError:
                try: audio_prep()
                except Exception: pass
            except Exception:
                pass
        elif decision is not None:
            try:
                policy_mod = load("openhtpc-playback-policy.py")
                if hasattr(policy_mod, "prepare_audio_target_bitstream"):
                    policy_mod.prepare_audio_target_bitstream(decision, runner=runner, settle_timeout=1.5 if switched else 0.0)
            except Exception:
                pass
        owner = tx.record['owner'] if tx else uuid.uuid4().hex
        sock_path = pathlib.Path(tempfile.gettempdir()) / f"openhtpc-mpv-{owner}.sock"
        if sock_path.exists():
            try: sock_path.unlink()
            except OSError: pass

        mpv_cmd = list(command) if isinstance(command, (list, tuple)) else str(command)
        ipc_arg = f"--input-ipc-server={sock_path}"
        if isinstance(mpv_cmd, list):
            if not any(isinstance(a, str) and a.startswith("--input-ipc-server=") for a in mpv_cmd):
                idx = mpv_cmd.index("--") if "--" in mpv_cmd else len(mpv_cmd)
                mpv_cmd.insert(idx, ipc_arg)
        elif isinstance(mpv_cmd, str) and "--input-ipc-server=" not in mpv_cmd:
            mpv_cmd = f"{mpv_cmd} {ipc_arg}"

        collector = TelemetryCollector(sock_path)
        collector.start()
        try:
            result = runner(mpv_cmd, **kwargs)
        finally:
            collector.stop()
            if sock_path.exists():
                try: sock_path.unlink()
                except OSError: pass

        telemetry = collector.result()
        if tx:
            try:
                tx.note(
                    tx.record['status'],
                    playback_started=True,
                    playback_exit_code=getattr(result, 'returncode', None),
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
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    home = pathlib.Path(os.environ.get('OPENHTPC_HOME', pathlib.Path.home()))
    if args.recover:
        tx = Transaction(home)
        try:
            if tx.acquire() and tx.path.exists(): tx.restore()
        except Exception as error:
            print(f'OPENHTPC refresh recovery: {type(error).__name__}', flush=True)
        finally: tx.release()
        return 0
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    return run_playback(home, command, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
