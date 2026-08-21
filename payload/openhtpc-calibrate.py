#!/usr/bin/env python3
"""OPENHTPC 1.1 Phase C3 Auto Calibration Engine.

Determines which visually-qualified presentation recipe is technically stable
on the current hardware/output combination.  Writes a persistent Performance Map
consumed by the CINÉMA AUTO selection engine.

Calibration methodology:
  - Uses real fullscreen Wayland rendering (not null/headless).
  - Audio is intentionally absent from benchmark assets; --ao=null applies to
    the calibration harness only and does NOT affect normal playback audio.
  - Stability verdict is derived exclusively from observed VO drops, decoder
    drops, delayed frames, starvation events, and process exit code.
  - No timing thresholds or invented headroom percentages are used.
  - Candidates are tested in ascending quality_priority order (1 = best).
  - Calibration stops as soon as the first stable candidate is found.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = pathlib.Path(__file__).resolve().parent
INSTALL_DIR = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", pathlib.Path.home() / ".local/lib/openhtpc"))
STATE_DIR = pathlib.Path(os.environ.get("OPENHTPC_STATE_DIR", pathlib.Path.home() / ".local/state/openhtpc"))
PERFORMANCE_MAP_PATH = STATE_DIR / "performance_map.json"
CALIBRATION_LOG_PATH = STATE_DIR / "calibration.log"
ASSETS_DIR = ROOT_DIR / "assets" / "benchmark"
SHADERS_DIR = ROOT_DIR / "assets" / "shaders"
CATALOG_PATH = ROOT_DIR / "assets" / "c3_calibration_catalog.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2
BENCHMARK_METHOD_VERSION = 1
WARMUP_SECONDS = 3.0
MEASUREMENT_SECONDS = 30.0
SAMPLE_INTERVAL = 0.25   # seconds between IPC polls (4 Hz)
IPC_CONNECT_TIMEOUT = 8.0
MPV_QUIT_TIMEOUT = 4.0

# ---------------------------------------------------------------------------
# Stability verdict constants
# ---------------------------------------------------------------------------

VERDICT_STABLE = "STABLE"
VERDICT_UNSTABLE_DROPS = "UNSTABLE_DROPS"
VERDICT_UNSTABLE_DELAYED = "UNSTABLE_DELAYED"
VERDICT_UNSTABLE_STARVATION = "UNSTABLE_STARVATION"
VERDICT_FAILED_PROCESS = "FAILED_PROCESS"
VERDICT_FAILED_MISSING_SHADER = "FAILED_MISSING_SHADER"
VERDICT_FAILED_TELEMETRY = "FAILED_TELEMETRY"

# Per-scope calibration abort codes (environment / infrastructure failure)
ABORT_NO_WAYLAND = "CALIBRATION_INVALID_ENVIRONMENT_NO_WAYLAND"
ABORT_NO_ASSET = "CALIBRATION_INVALID_ASSET"
ABORT_NO_PURE_CONF = "CALIBRATION_INVALID_ENVIRONMENT_NO_PURE_CONF"
ABORT_STARVATION = "CALIBRATION_INVALID_SOURCE_DELIVERY"
ABORT_INFRA = "CALIBRATION_INVALID_ENVIRONMENT"
ABORT_TELEMETRY = "CALIBRATION_TELEMETRY_INCOMPLETE"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_lines: list[str] = []


def _log(msg: str) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"{ts}  {msg}"
    _log_lines.append(line)
    print(line, flush=True)


def _flush_log() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with CALIBRATION_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(_log_lines) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# MPV IPC client (mirrors existing benchmark engine)
# ---------------------------------------------------------------------------

class MPVIPCClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock: socket.socket | None = None
        self.req_id = 0
        self._buffer = b""

    def connect(self, timeout: float = IPC_CONNECT_TIMEOUT) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(self.socket_path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.socket_path)
                    s.settimeout(2.0)
                    self.sock = s
                    return True
                except OSError:
                    pass
            time.sleep(0.1)
        return False

    def _readline(self) -> dict | None:
        while b"\n" not in self._buffer:
            try:
                chunk = self.sock.recv(4096)  # type: ignore[union-attr]
                if not chunk:
                    return None
                self._buffer += chunk
            except OSError:
                return None
        line, self._buffer = self._buffer.split(b"\n", 1)
        try:
            return json.loads(line.decode("utf-8"))
        except Exception:
            return None

    def command(self, cmd: list) -> dict:
        if not self.sock:
            return {"error": "not connected"}
        self.req_id += 1
        current_id = self.req_id
        payload = json.dumps({"command": cmd, "request_id": current_id}) + "\n"
        try:
            self.sock.sendall(payload.encode("utf-8"))
            start = time.time()
            while time.time() - start < 3.0:
                msg = self._readline()
                if not msg:
                    break
                if msg.get("request_id") == current_id:
                    return msg
        except OSError as exc:
            return {"error": str(exc)}
        return {"error": "timeout or disconnect"}

    def get_property(self, name: str):
        res = self.command(["get_property", name])
        if isinstance(res, dict) and res.get("error") == "success":
            return res.get("data")
        return None

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(val, default: int = 0) -> int:
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _compute_percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50": None, "p95": None, "p99": None, "max": None, "median": None, "avg": None}
    s = sorted(samples)
    n = len(s)

    def p(pct: float) -> float:
        k = (n - 1) * pct
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(s[int(k)], 3)
        return round(s[f] * (c - k) + s[c] * (k - f), 3)

    return {
        "p50": p(0.50),
        "p95": p(0.95),
        "p99": p(0.99),
        "max": round(max(s), 3),
        "median": p(0.50),
        "avg": round(sum(s) / n, 3),
    }


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Signature builders
# ---------------------------------------------------------------------------

def _get_gpu_pci_info() -> str:
    """Best-effort GPU PCI vendor:device string."""
    try:
        result = subprocess.run(
            ["lspci", "-mm", "-nn"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "VGA" in line or "Display" in line or "3D" in line:
                # Extract [vendor:device] from brackets
                import re
                m = re.search(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line)
                if m:
                    return f"{m.group(1)}:{m.group(2)}"
    except Exception:
        pass
    return "UNKNOWN:UNKNOWN"


def _get_driver_version() -> str:
    """Best-effort Intel iHD driver version."""
    for path in pathlib.Path("/usr/lib64").glob("dri/iHD_drv_video.so*"):
        try:
            res = subprocess.run(
                ["strings", str(path)],
                capture_output=True, text=True, timeout=3
            )
            import re
            m = re.search(r"(\d+\.\d+\.\d+)", res.stdout)
            if m:
                return m.group(1)
        except Exception:
            pass
    # Try vulkaninfo path
    try:
        res = subprocess.run(
            ["vulkaninfo", "--summary"],
            capture_output=True, text=True, timeout=5, env={**os.environ, "VULKAN_DEVICE": ""}
        )
        import re
        m = re.search(r"driverVersion\s*[:=]\s*([^\s\n]+)", res.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "UNKNOWN"


def _get_mpv_version() -> str:
    try:
        res = subprocess.run(["mpv", "--version"], capture_output=True, text=True, timeout=3)
        import re
        m = re.search(r"mpv\s+([^\s]+)", res.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "UNKNOWN"


def _get_display_signature() -> dict:
    """Query the active Wayland display and return a human-readable signature string."""
    sig = {
        "connector": "UNKNOWN",
        "width": None,
        "height": None,
        "refresh_hz": None,
        "bit_depth": None,
        "compositor": os.environ.get("WAYLAND_DISPLAY", "UNKNOWN"),
    }
    try:
        res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout:
            import re
            m_conn = re.search(r"Output:\s*\d+\s+([A-Za-z0-9-]+)", res.stdout)
            if m_conn:
                sig["connector"] = m_conn.group(1)
            m_mode = re.search(r"(\d+)x(\d+)@([0-9.]+)\*", res.stdout)
            if m_mode:
                sig["width"] = int(m_mode.group(1))
                sig["height"] = int(m_mode.group(2))
                sig["refresh_hz"] = float(m_mode.group(3))
            m_bpc = re.search(r"Color resolution:.*\((\d+)\)", res.stdout)
            if m_bpc:
                sig["bit_depth"] = int(m_bpc.group(1))
    except Exception:
        pass
    return sig


def build_signatures(catalog_version: int, asset_hashes: dict[str, str]) -> dict:
    """Assemble all 6 calibration signatures from live system."""
    pci = _get_gpu_pci_info()
    drv = _get_driver_version()
    mpv = _get_mpv_version()

    disp = _get_display_signature()
    w = disp.get("width") or 0
    h = disp.get("height") or 0
    hz = disp.get("refresh_hz") or 0
    bpc = disp.get("bit_depth") or 0
    connector = disp.get("connector", "UNKNOWN")
    compositor = disp.get("compositor", "UNKNOWN")

    hw_sig = _sha256_str(f"{pci}|{drv}")
    renderer_sig = _sha256_str(f"{mpv}|gpu-next|Vulkan|vaapi")
    output_sig_str = f"{w}x{h}@{hz:.2f}Hz_{bpc}bit_{connector}_{compositor}"
    output_sig = _sha256_str(output_sig_str)

    return {
        "hardware_signature": hw_sig,
        "renderer_signature": renderer_sig,
        "output_signature": output_sig,
        "output_signature_human": output_sig_str,
        "benchmark_method_version": BENCHMARK_METHOD_VERSION,
        "benchmark_asset_version": asset_hashes,
        "recipe_catalog_version": catalog_version,
    }


# ---------------------------------------------------------------------------
# Calibration catalogue
# ---------------------------------------------------------------------------

def _load_catalog() -> dict:
    """Load the C3 calibration catalogue from disk."""
    if CATALOG_PATH.exists():
        try:
            return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Embedded fallback (bootstrap): Phase C2 qualification result
    return {
        "schema_version": 1,
        "recipe_catalog_version": 1,
        "scopes": {
            "DVD_PAL_FILM": {
                "benchmark_asset_id": "C1_DVD_PAL",
                "benchmark_asset_filename": "c1_dvd_pal.mpg",
                "description": "PAL DVD 25fps film content (Phase C2 visual qualification)",
                "candidates": [
                    {
                        "quality_priority": 1,
                        "recipe_id": "RECIPE_0_PURE",
                        "shader_ids": [],
                        "qualification_verdict": "PROJECT_QUALIFIED/PREFERRED",
                        "phase": "C2",
                    },
                    {
                        "quality_priority": 2,
                        "recipe_id": "RECIPE_C2_DVD_KRIG_BILATERAL",
                        "shader_ids": ["KrigBilateral.glsl"],
                        "qualification_verdict": "PROJECT_QUALIFIED/QUALIFIED_ALTERNATIVE",
                        "phase": "C2",
                    },
                    {
                        "quality_priority": 3,
                        "recipe_id": "RECIPE_C2_DVD_FSRCNNX_8",
                        "shader_ids": ["FSRCNNX_x2_8-0-4-1.glsl"],
                        "qualification_verdict": "PROJECT_QUALIFIED/HIGH_GPU_WORKLOAD",
                        "phase": "C2",
                    },
                ],
            }
        },
    }


# ---------------------------------------------------------------------------
# Asset hash helpers
# ---------------------------------------------------------------------------

def _compute_asset_hashes(catalog: dict) -> dict[str, str]:
    result = {}
    for scope_id, scope in catalog.get("scopes", {}).items():
        filename = scope.get("benchmark_asset_filename", "")
        asset_path = ASSETS_DIR / filename
        if asset_path.exists():
            result[scope_id] = _sha256_file(asset_path)
        else:
            result[scope_id] = "MISSING"
    return result


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def _stale_scopes(saved_map: dict | None, current_sigs: dict) -> set[str]:
    """Return set of scope IDs that need re-calibration."""
    if saved_map is None:
        return set()  # caller handles absent map as full re-calibration

    saved_meta = saved_map.get("calibration_metadata", {})
    saved_sigs = saved_meta.get("signatures", {})
    all_scopes: set[str] = set(saved_map.get("entries", {}).keys())

    stale: set[str] = set()

    # Hardware / renderer / method / catalog version: full stale
    for key in ("hardware_signature", "renderer_signature",
                "benchmark_method_version", "recipe_catalog_version"):
        if saved_sigs.get(key) != current_sigs.get(key):
            _log(f"STALE: {key} changed ({saved_sigs.get(key)!r} → {current_sigs.get(key)!r})")
            return all_scopes  # full re-calibration

    # Output signature: stale all scopes (render target changed)
    if saved_sigs.get("output_signature") != current_sigs.get("output_signature"):
        _log(f"STALE: output_signature changed → full re-calibration")
        return all_scopes

    # Per-scope asset hashes
    saved_asset_versions = saved_sigs.get("benchmark_asset_version", {})
    current_asset_versions = current_sigs.get("benchmark_asset_version", {})
    for scope_id in all_scopes:
        if saved_asset_versions.get(scope_id) != current_asset_versions.get(scope_id):
            _log(f"STALE: benchmark_asset_version changed for scope {scope_id}")
            stale.add(scope_id)

    return stale


def check_staleness(saved_map: dict | None, current_sigs: dict, scopes: list[str]) -> dict[str, bool]:
    """Return {scope_id: needs_calibration} mapping."""
    if saved_map is None:
        return {s: True for s in scopes}

    stale = _stale_scopes(saved_map, current_sigs)
    result = {}
    saved_entries = saved_map.get("entries", {})
    for scope_id in scopes:
        if scope_id in stale or scope_id not in saved_entries:
            result[scope_id] = True
        else:
            result[scope_id] = False
    return result


# ---------------------------------------------------------------------------
# Wayland environment check
# ---------------------------------------------------------------------------

def _wayland_available() -> bool:
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not wayland_display or not xdg_runtime:
        return False
    sock = pathlib.Path(xdg_runtime) / wayland_display
    return sock.exists()


def _find_pure_conf() -> pathlib.Path | None:
    candidates = [
        pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf",
        INSTALL_DIR / "pure.conf",
        ROOT_DIR / "pure.conf",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Stability verdict derivation
# ---------------------------------------------------------------------------

def derive_stability_verdict(evidence: dict) -> tuple[str, bool]:
    """Return (verdict, technically_usable)."""
    exit_code = evidence.get("mpv_exit_code", -1)

    # Infrastructure failure — always abort scope, not candidate failure
    starvation = evidence.get("starvation_events", 0)
    if starvation > 0:
        return VERDICT_UNSTABLE_STARVATION, False

    # Process failure
    if exit_code not in (0, None):
        return VERDICT_FAILED_PROCESS, False

    # Insufficient telemetry
    if evidence.get("samples_collected", 0) < 5:
        return VERDICT_FAILED_TELEMETRY, False

    vo_drops = evidence.get("vo_drops", 0)
    decoder_drops = evidence.get("decoder_drops", 0)
    delayed = evidence.get("delayed_frames", 0)

    if vo_drops > 0 or decoder_drops > 0:
        return VERDICT_UNSTABLE_DROPS, False
    if delayed > 0:
        return VERDICT_UNSTABLE_DELAYED, False

    return VERDICT_STABLE, True


def _is_candidate_failure(verdict: str) -> bool:
    """True if this failure is attributable to the candidate (may try next)."""
    return verdict in (
        VERDICT_UNSTABLE_DROPS,
        VERDICT_UNSTABLE_DELAYED,
        VERDICT_FAILED_MISSING_SHADER,
        VERDICT_FAILED_PROCESS,
    )


def _is_environment_failure(verdict: str) -> bool:
    """True if this failure indicates environment contamination (abort scope)."""
    return verdict in (
        VERDICT_UNSTABLE_STARVATION,
        VERDICT_FAILED_TELEMETRY,
    )


# ---------------------------------------------------------------------------
# GPU frequency sampling (sysfs, best-effort)
# ---------------------------------------------------------------------------

def _read_gpu_freq_mhz() -> int | None:
    for path in [
        "/sys/class/drm/card1/gt_act_freq_mhz",
        "/sys/class/drm/card0/gt_act_freq_mhz",
    ]:
        try:
            return int(pathlib.Path(path).read_text().strip())
        except (OSError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------------
# Single recipe calibration run
# ---------------------------------------------------------------------------

def run_calibration_pass(
    scope_id: str,
    candidate: dict,
    asset_path: pathlib.Path,
    pure_conf: pathlib.Path,
) -> dict:
    """
    Execute one fullscreen MPV calibration pass.

    Returns an evidence dict.  Never raises — all errors are captured.

    Abort codes are returned in evidence["abort_code"] when environment
    contamination is detected (caller must stop the scope).
    """
    recipe_id = candidate["recipe_id"]
    shader_ids = candidate.get("shader_ids", [])

    _log(f"  [RUN] {scope_id}/{recipe_id} — shaders={shader_ids}")

    # --- Shader presence check (candidate failure, not environment)
    shader_paths: list[str] = []
    for sid in shader_ids:
        sp = SHADERS_DIR / sid
        if not sp.exists():
            _log(f"    FAILED_MISSING_SHADER: {sid}")
            return {
                "stability_verdict": VERDICT_FAILED_MISSING_SHADER,
                "technically_usable": False,
                "abort_code": None,
                "error": f"Shader missing: {sid}",
                "samples_collected": 0,
            }
        shader_paths.append(str(sp))

    # --- Wayland environment (environment failure → abort scope)
    if not _wayland_available():
        _log("    ABORT: No Wayland session available")
        return {
            "stability_verdict": "FAILED_PROCESS",
            "technically_usable": False,
            "abort_code": ABORT_NO_WAYLAND,
            "error": "No active Wayland session",
            "samples_collected": 0,
        }

    # --- Asset hash verification (environment failure → abort scope)
    if not asset_path.exists():
        _log(f"    ABORT: Asset missing: {asset_path}")
        return {
            "stability_verdict": "FAILED_PROCESS",
            "technically_usable": False,
            "abort_code": ABORT_NO_ASSET,
            "error": f"Asset missing: {asset_path}",
            "samples_collected": 0,
        }

    ipc_sock = f"/tmp/openhtpc_cal_{os.getpid()}_{recipe_id}.sock"
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    # Phase C0 read-ahead args — import the frozen module
    readahead_args: list[str] = []
    try:
        import importlib.util as ilu
        ra_spec = ilu.spec_from_file_location("openhtpc_readahead", ROOT_DIR / "openhtpc-readahead.py")
        ra_mod = ilu.module_from_spec(ra_spec)   # type: ignore[arg-type]
        ra_spec.loader.exec_module(ra_mod)        # type: ignore[union-attr]
        policy = ra_mod.compute_readahead_policy(source_class="LOCAL_FAST")
        readahead_args = policy.get("mpv_options", [])
    except Exception as exc:
        _log(f"    WARNING: read-ahead policy unavailable: {exc}")

    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-0"

    cmd = [
        "mpv",
        f"--include={pure_conf}",
        f"--input-ipc-server={ipc_sock}",
        # Audio: absent from benchmark assets; null output for calibration harness only
        "--ao=null",
        # Real fullscreen on active Wayland output — NOT null/headless
        "--fs",
        "--force-window=immediate",
        "--border=no",
        "--no-terminal",
        "--keep-open=no",
        "--osd-font=Open Sans",
        "--osd-font-size=28",
        "--osd-color=#F4F8FF",
        "--osd-back-color=#80050B13",
        "--osd-align-x=center",
        "--osd-align-y=center",
        *readahead_args,
        *(["--glsl-shaders=" + ":".join(shader_paths)] if shader_paths else []),
        str(asset_path),
    ]

    wall_start = time.time()
    proc: subprocess.Popen | None = None

    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError as exc:
        _log(f"    ABORT: MPV launch failed: {exc}")
        return {
            "stability_verdict": VERDICT_FAILED_PROCESS,
            "technically_usable": False,
            "abort_code": ABORT_INFRA,
            "error": f"MPV launch failed: {exc}",
            "samples_collected": 0,
        }

    ipc = MPVIPCClient(ipc_sock)
    if not ipc.connect(timeout=IPC_CONNECT_TIMEOUT):
        proc.kill()
        proc.wait()
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)
        _log("    ABORT: IPC connect timeout")
        return {
            "stability_verdict": VERDICT_FAILED_PROCESS,
            "technically_usable": False,
            "abort_code": ABORT_INFRA,
            "error": "MPV IPC connect timeout",
            "samples_collected": 0,
        }

    def _show_calibration_osd(elapsed_secs: float) -> None:
        mm = int(elapsed_secs // 60)
        ss = int(elapsed_secs % 60)
        osd_msg = (
            "OPENHTPC\n\n"
            "ANALYSE DU MATÉRIEL\n"
            "Optimisation du rendu vidéo…\n\n"
            "Aucune action requise.\n"
            f"Temps écoulé : {mm:02d}:{ss:02d}"
        )
        try:
            ipc.command(["show-text", osd_msg, 2000])
        except Exception:
            pass

    # --- Warmup window
    _log(f"    Warmup {WARMUP_SECONDS:.0f}s …")
    warmup_start = time.time()
    last_osd = 0.0
    while time.time() - warmup_start < WARMUP_SECONDS:
        if proc.poll() is not None:
            break
        now = time.time()
        if now - last_osd >= 1.0:
            _show_calibration_osd(now - wall_start)
            last_osd = now
        time.sleep(0.1)

    # Snapshot baseline counters (delta measurement)
    base_vo_drops = ipc.get_property("frame-drop-count") or 0
    base_dec_drops = ipc.get_property("decoder-frame-drop-count") or 0
    base_delayed = ipc.get_property("vo-delayed-frame-count") or 0

    # --- Measurement window
    _log(f"    Measurement {MEASUREMENT_SECONDS:.0f}s …")
    pass_samples: list[float] = []
    freq_samples: list[int] = []
    starvation_events = 0

    measure_start = time.time()
    while time.time() - measure_start < MEASUREMENT_SECONDS:
        if proc.poll() is not None:
            break

        now = time.time()
        if now - last_osd >= 1.0:
            _show_calibration_osd(now - wall_start)
            last_osd = now

        # vo-passes telemetry
        passes_data = ipc.get_property("vo-passes")
        if passes_data and isinstance(passes_data, dict):
            fresh = passes_data.get("fresh", [])
            total_ns = 0
            for p in fresh:
                last = p.get("last")
                if isinstance(last, (int, float)):
                    total_ns += last
            if total_ns > 0:
                pass_samples.append(total_ns / 1_000_000.0)

        # GPU frequency (sysfs, best-effort)
        freq = _read_gpu_freq_mhz()
        if freq is not None:
            freq_samples.append(freq)

        # Demuxer starvation detection
        cache_state = ipc.get_property("demuxer-cache-state")
        if isinstance(cache_state, dict):
            if cache_state.get("underrun"):
                starvation_events += 1

        time.sleep(SAMPLE_INTERVAL)

    # Collect final counters
    end_vo_drops = ipc.get_property("frame-drop-count") or 0
    end_dec_drops = ipc.get_property("decoder-frame-drop-count") or 0
    end_delayed = ipc.get_property("vo-delayed-frame-count") or 0

    ipc.command(["quit"])
    try:
        proc.wait(timeout=MPV_QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    ipc.close()
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    exit_code = proc.returncode
    wall_duration = time.time() - wall_start

    steady_vo = max(0, _to_int(end_vo_drops) - _to_int(base_vo_drops))
    steady_dec = max(0, _to_int(end_dec_drops) - _to_int(base_dec_drops))
    steady_delayed = max(0, _to_int(end_delayed) - _to_int(base_delayed))

    stats = _compute_percentiles(pass_samples)
    freq_avg = round(sum(freq_samples) / len(freq_samples)) if freq_samples else None
    freq_max = max(freq_samples) if freq_samples else None

    evidence = {
        "run_duration_s": round(wall_duration, 1),
        "samples_collected": len(pass_samples),
        "gpu_pass_sum_p95_ms": stats["p95"],
        "gpu_pass_sum_median_ms": stats["median"],
        "gpu_pass_sum_max_ms": stats["max"],
        "gpu_pass_sum_avg_ms": stats["avg"],
        "gpu_freq_avg_mhz": freq_avg,
        "gpu_freq_max_mhz": freq_max,
        "vo_drops": steady_vo,
        "decoder_drops": steady_dec,
        "delayed_frames": steady_delayed,
        "starvation_events": starvation_events,
        "mpv_exit_code": exit_code,
    }

    verdict, usable = derive_stability_verdict(evidence)

    # Starvation is environment failure → abort scope
    abort_code = None
    if verdict == VERDICT_UNSTABLE_STARVATION:
        abort_code = ABORT_STARVATION
    elif verdict == VERDICT_FAILED_TELEMETRY:
        abort_code = ABORT_TELEMETRY

    evidence["stability_verdict"] = verdict
    evidence["technically_usable"] = usable
    evidence["abort_code"] = abort_code

    _log(
        f"    verdict={verdict} usable={usable} "
        f"vo={steady_vo} dec={steady_dec} delayed={steady_delayed} "
        f"starvation={starvation_events} samples={len(pass_samples)} "
        f"p95={stats['p95']}"
    )
    return evidence


# ---------------------------------------------------------------------------
# Per-scope calibration state machine
# ---------------------------------------------------------------------------

def calibrate_scope(
    scope_id: str,
    scope_def: dict,
    current_sigs: dict,
) -> dict:
    """
    Run the adaptive calibration state machine for one content scope.

    Returns a scope result dict with:
      - "decision": recipe_id selected (or "RECIPE_0_PURE" on fail-safe)
      - "abort_code": set if environment contamination detected
      - "entries": list of measured entries
      - "candidates_tested": count
    """
    candidates = sorted(
        scope_def.get("candidates", []),
        key=lambda c: c["quality_priority"],
    )
    asset_filename = scope_def.get("benchmark_asset_filename", "")
    asset_path = ASSETS_DIR / asset_filename

    entries: list[dict] = []
    selected: str | None = None
    abort_code: str | None = None
    candidates_tested = 0

    _log(f"[SCOPE] {scope_id} — {len(candidates)} candidate(s) ordered by quality_priority")
    _log(f"  asset: {asset_path}")

    # Validate asset (environment failure → abort immediately)
    if not asset_path.exists():
        _log(f"  ABORT: benchmark asset missing: {asset_path}")
        return {
            "decision": "RECIPE_0_PURE",
            "abort_code": ABORT_NO_ASSET,
            "entries": [],
            "candidates_tested": 0,
        }

    pure_conf = _find_pure_conf()
    if pure_conf is None:
        _log("  ABORT: pure.conf not found")
        return {
            "decision": "RECIPE_0_PURE",
            "abort_code": ABORT_NO_PURE_CONF,
            "entries": [],
            "candidates_tested": 0,
        }

    if not _wayland_available():
        _log("  DEFERRED: no Wayland session")
        return {
            "decision": "RECIPE_0_PURE",
            "abort_code": ABORT_NO_WAYLAND,
            "entries": [],
            "candidates_tested": 0,
        }

    # Reference p95 of PURE for relative workload computation
    pure_p95: float | None = None

    for candidate in candidates:
        recipe_id = candidate["recipe_id"]
        quality_priority = candidate["quality_priority"]
        candidates_tested += 1

        evidence = run_calibration_pass(scope_id, candidate, asset_path, pure_conf)

        # Store relative GPU workload vs PURE (raw informational only)
        relative_workload: float | None = None
        candidate_p95 = evidence.get("gpu_pass_sum_p95_ms")
        if recipe_id == "RECIPE_0_PURE":
            pure_p95 = candidate_p95
            relative_workload = None  # null for PURE entry itself
        elif pure_p95 is not None and candidate_p95 is not None:
            try:
                relative_workload = round(candidate_p95 / pure_p95, 3)
            except ZeroDivisionError:
                relative_workload = None

        entry = {
            "content_scope": scope_id,
            "recipe_id": recipe_id,
            "shader_ids": candidate.get("shader_ids", []),
            "quality_priority": quality_priority,
            **evidence,
            "relative_gpu_workload_vs_pure": relative_workload,
        }
        entries.append(entry)

        ac = evidence.get("abort_code")
        if ac:
            # Environment contamination: abort the whole scope
            _log(f"  SCOPE ABORTED: {ac}")
            abort_code = ac
            break

        if evidence.get("technically_usable") and selected is None:
            selected = recipe_id
            _log(f"  SELECTED: {recipe_id} (quality_priority={quality_priority}) — stopping")
            break
        # else: candidate failed, try next

    if selected is None and abort_code is None:
        _log(f"  All candidates exhausted — fail-safe: RECIPE_0_PURE")

    decision = selected or "RECIPE_0_PURE"

    return {
        "decision": decision,
        "abort_code": abort_code,
        "entries": entries,
        "candidates_tested": candidates_tested,
    }


# ---------------------------------------------------------------------------
# Performance Map I/O
# ---------------------------------------------------------------------------

def _load_performance_map() -> dict | None:
    if not PERFORMANCE_MAP_PATH.exists():
        return None
    try:
        data = json.loads(PERFORMANCE_MAP_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            _log("Performance map schema mismatch — treating as absent")
            return None
        return data
    except Exception as exc:
        _log(f"Performance map unreadable: {exc} — treating as absent")
        return None


def _write_performance_map(data: dict) -> None:
    """Atomic write via temp file + rename."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mktemp(dir=STATE_DIR, prefix=".perf_map_", suffix=".json.tmp"))
    try:
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(PERFORMANCE_MAP_PATH)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# CINÉMA AUTO decision helper
# ---------------------------------------------------------------------------

def cinema_auto_decision(scope_id: str, saved_map: dict) -> str:
    """Read the performance map and return the CINÉMA AUTO selected recipe."""
    if saved_map is None:
        return "RECIPE_0_PURE"
    meta = saved_map.get("calibration_metadata", {})
    decisions = meta.get("cinema_auto_decisions", {})
    return decisions.get(scope_id, "RECIPE_0_PURE")


# ---------------------------------------------------------------------------
# Main calibration orchestrator
# ---------------------------------------------------------------------------

def run_calibration(
    scope_filter: str | None = None,
    force: bool = False,
) -> dict:
    """
    Orchestrate calibration across all requested content scopes.

    Returns a result dict suitable for JSON output.
    """
    _log("=" * 60)
    _log(f"OPENHTPC C3 Auto Calibration Engine  (method_version={BENCHMARK_METHOD_VERSION})")
    _log("=" * 60)

    catalog = _load_catalog()
    catalog_version = catalog.get("recipe_catalog_version", 1)
    scopes_def = catalog.get("scopes", {})

    if scope_filter:
        if scope_filter not in scopes_def:
            raise ValueError(f"Unknown scope: {scope_filter!r}. Available: {list(scopes_def)}")
        scopes_def = {scope_filter: scopes_def[scope_filter]}

    asset_hashes = _compute_asset_hashes(catalog)
    current_sigs = build_signatures(catalog_version, asset_hashes)

    _log(f"output_signature_human: {current_sigs['output_signature_human']}")
    _log(f"hardware_signature: {current_sigs['hardware_signature'][:16]}…")
    _log(f"renderer_signature: {current_sigs['renderer_signature'][:16]}…")

    saved_map = _load_performance_map()

    # Determine which scopes need calibration
    all_scope_ids = list(scopes_def.keys())
    if force or saved_map is None:
        needs_cal = {s: True for s in all_scope_ids}
        reason = "FORCE" if force else "MAP_ABSENT"
        _log(f"Calibration required for all scopes ({reason})")
    else:
        needs_cal = check_staleness(saved_map, current_sigs, all_scope_ids)
        _log(f"Staleness check: {needs_cal}")

    # Build the updated map, preserving existing entries for non-stale scopes
    if saved_map is not None and not force:
        existing_entries = saved_map.get("entries", {})
        existing_decisions = saved_map.get("calibration_metadata", {}).get("cinema_auto_decisions", {})
    else:
        existing_entries = {}
        existing_decisions = {}

    new_entries: dict[str, list[dict]] = {}
    new_decisions: dict[str, str] = {}
    scope_results: list[dict] = []
    overall_duration = 0.0

    for scope_id, scope_def in scopes_def.items():
        if not needs_cal.get(scope_id):
            _log(f"[SCOPE] {scope_id} — CURRENT (no re-calibration needed)")
            new_entries[scope_id] = existing_entries.get(scope_id, [])
            new_decisions[scope_id] = existing_decisions.get(scope_id, "RECIPE_0_PURE")
            scope_results.append({
                "scope_id": scope_id,
                "status": "CURRENT",
                "decision": new_decisions[scope_id],
            })
            continue

        t_start = time.time()
        result = calibrate_scope(scope_id, scope_def, current_sigs)
        elapsed = round(time.time() - t_start, 1)
        overall_duration += elapsed

        new_entries[scope_id] = result["entries"]
        decision = result["decision"]
        new_decisions[scope_id] = decision

        scope_results.append({
            "scope_id": scope_id,
            "status": "ABORT" if result.get("abort_code") else "CALIBRATED",
            "decision": decision,
            "abort_code": result.get("abort_code"),
            "candidates_tested": result["candidates_tested"],
            "duration_s": elapsed,
        })

    # Merge remaining scopes not in scope_filter
    for scope_id in list(scopes_def.keys()):
        pass  # already handled above

    # Write performance map
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    performance_map = {
        "schema_version": SCHEMA_VERSION,
        "calibration_metadata": {
            "timestamp_utc": timestamp,
            "openhtpc_version": _installed_version(),
            "signatures": current_sigs,
            "calibration_result": "CALIBRATION_COMPLETE",
            "cinema_auto_decisions": new_decisions,
        },
        "entries": new_entries,
    }

    try:
        _write_performance_map(performance_map)
        _log(f"Performance map written: {PERFORMANCE_MAP_PATH}")
    except Exception as exc:
        _log(f"ERROR: Failed to write performance map: {exc}")

    return {
        "calibration_result": "CALIBRATION_COMPLETE",
        "timestamp_utc": timestamp,
        "overall_duration_s": round(overall_duration, 1),
        "scopes": scope_results,
        "cinema_auto_decisions": new_decisions,
        "performance_map_path": str(PERFORMANCE_MAP_PATH),
    }


def _installed_version() -> str:
    vf = ROOT_DIR / "VERSION"
    if vf.exists():
        return vf.read_text(encoding="utf-8").strip()
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Signature-only check (--check mode)
# ---------------------------------------------------------------------------

def check_only() -> dict:
    """Check staleness without running any calibration passes."""
    catalog = _load_catalog()
    catalog_version = catalog.get("recipe_catalog_version", 1)
    asset_hashes = _compute_asset_hashes(catalog)
    current_sigs = build_signatures(catalog_version, asset_hashes)
    saved_map = _load_performance_map()

    if saved_map is None:
        return {
            "status": "CALIBRATION_ABSENT",
            "reason": "No performance map found",
            "current_signatures": current_sigs,
        }

    all_scopes = list(catalog.get("scopes", {}).keys())
    needs = check_staleness(saved_map, current_sigs, all_scopes)
    any_stale = any(needs.values())
    return {
        "status": "CALIBRATION_STALE" if any_stale else "CALIBRATION_OK",
        "stale_scopes": [s for s, v in needs.items() if v],
        "current_signatures": current_sigs,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="OPENHTPC C3 Auto Calibration Engine"
    )
    parser.add_argument(
        "--scope",
        help="Calibrate a specific content scope only (e.g. DVD_PAL_FILM)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-calibration regardless of staleness",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check staleness only — do not run any calibration passes",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON",
    )
    args = parser.parse_args()

    if args.check:
        result = check_only()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Calibration status: {result['status']}")
            stale = result.get("stale_scopes", [])
            if stale:
                print(f"Stale scopes: {', '.join(stale)}")
        _flush_log()
        return 0

    result = run_calibration(scope_filter=args.scope, force=args.force)
    _flush_log()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\nCalibration result: {result['calibration_result']}")
        print(f"Duration: {result['overall_duration_s']:.1f}s")
        for sc in result.get("scopes", []):
            ac = sc.get("abort_code") or ""
            tested = sc.get("candidates_tested", 0)
            status = sc.get("status", "")
            decision = sc.get("decision", "")
            print(
                f"  {sc['scope_id']:<20} {status:<12} decision={decision:<40} "
                f"tested={tested} {ac}"
            )
        print(f"\nCINÉMA AUTO decisions: {result['cinema_auto_decisions']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
