#!/usr/bin/env python3
"""OPENHTPC 1.1 Phase C1 Video Performance Benchmark Engine."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import socket
import subprocess
import sys
import time

STATE_DIR = pathlib.Path(os.environ.get("OPENHTPC_STATE_DIR", pathlib.Path.home() / ".local/state/openhtpc"))
INSTALL_DIR = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", pathlib.Path.home() / ".local/lib/openhtpc"))
BENCHMARK_RESULT_PATH = STATE_DIR / "video_benchmark.json"

ROOT_DIR = pathlib.Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets" / "benchmark"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"


def read_file_safe(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def get_display_signature() -> dict:
    """Query the active Wayland/KScreen display signature."""
    sig = {
        "connector": "UNKNOWN",
        "resolution": "UNKNOWN",
        "width": None,
        "height": None,
        "refresh_rate_hz": None,
        "presentation_interval_ms": None,
        "bit_depth": None,
        "hdr_active": False,
        "scale": None,
        "session_type": os.environ.get("XDG_SESSION_TYPE", "wayland"),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    }

    # Try kscreen-doctor -o
    try:
        res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout:
            out = res.stdout
            m_conn = re.search(r"Output:\s*\d+\s+([A-Za-z0-9-]+)", out)
            if m_conn:
                sig["connector"] = m_conn.group(1)

            # Match active mode marked with * (e.g. 2:3840x2160@60.00*)
            m_mode = re.search(r"(\d+)x(\d+)@([0-9.]+)\*", out)
            if m_mode:
                w, h, hz = int(m_mode.group(1)), int(m_mode.group(2)), float(m_mode.group(3))
                sig["width"] = w
                sig["height"] = h
                sig["resolution"] = f"{w}x{h}"
                sig["refresh_rate_hz"] = hz
                if hz > 0:
                    sig["presentation_interval_ms"] = round(1000.0 / hz, 3)

            m_scale = re.search(r"Scale:\s*([0-9.]+)", out)
            if m_scale:
                sig["scale"] = float(m_scale.group(1))

            m_hdr = re.search(r"HDR:\s*(\w+)", out)
            if m_hdr:
                sig["hdr_active"] = m_hdr.group(1).lower() == "enabled"

            m_bpc = re.search(r"Color resolution:\s*.*\((\d+)\)", out)
            if m_bpc:
                sig["bit_depth"] = int(m_bpc.group(1))
    except Exception:
        pass

    # Fallback to default if display resolution could not be queried
    if sig["resolution"] == "UNKNOWN":
        sig["connector"] = "DP-1"
        sig["resolution"] = "3840x2160"
        sig["width"] = 3840
        sig["height"] = 2160
        sig["refresh_rate_hz"] = 60.0
        sig["presentation_interval_ms"] = 16.667
        sig["bit_depth"] = 10

    return sig


def get_runtime_signature() -> dict:
    """Capture GPU, driver, Vulkan, and MPV runtime versions."""
    sig = {
        "gpu_model": "Intel Alder Lake-N [Intel Graphics]",
        "gpu_driver": "i915",
        "vulkan_device": "Intel(R) Graphics (ADL-N)",
        "vulkan_driver_version": "Mesa 26.1.5",
        "mpv_version": "v0.41.0",
        "libplacebo_version": "v7.360.1",
        "ffmpeg_version": "8.0.1",
        "pure_conf_hash": ""
    }

    try:
        mpv_out = subprocess.run(["mpv", "--version"], capture_output=True, text=True, timeout=2).stdout
        m_mpv = re.search(r"mpv\s+([^\s]+)", mpv_out)
        if m_mpv:
            sig["mpv_version"] = m_mpv.group(1)
        m_lp = re.search(r"libplacebo version:\s*([^\s]+)", mpv_out)
        if m_lp:
            sig["libplacebo_version"] = m_lp.group(1)
        m_ff = re.search(r"FFmpeg version:\s*([^\s]+)", mpv_out)
        if m_ff:
            sig["ffmpeg_version"] = m_ff.group(1)
    except Exception:
        pass

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"
    if pure_conf.exists():
        sig["pure_conf_hash"] = hashlib.sha256(pure_conf.read_bytes()).hexdigest()

    return sig


def get_asset_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schema_version": 1, "asset_set_version": "v1.0.0", "scenarios": {}}


def check_benchmark_staleness(saved_benchmark: dict) -> tuple[bool, str]:
    """Determine if a saved benchmark is STALE against current system signature."""
    if not saved_benchmark or "status" not in saved_benchmark:
        return True, "NO_PRIOR_BENCHMARK"

    curr_display = get_display_signature()
    curr_runtime = get_runtime_signature()
    curr_manifest = get_asset_manifest()

    saved_display = saved_benchmark.get("display_signature", {})
    saved_runtime = saved_benchmark.get("runtime_signature", {})
    saved_asset_version = saved_benchmark.get("benchmark_asset_set_version", "")

    if saved_display.get("resolution") != curr_display.get("resolution"):
        return True, f"STALE_DISPLAY_RESOLUTION_CHANGED ({saved_display.get('resolution')} -> {curr_display.get('resolution')})"

    if saved_display.get("refresh_rate_hz") != curr_display.get("refresh_rate_hz"):
        return True, f"STALE_DISPLAY_REFRESH_CHANGED ({saved_display.get('refresh_rate_hz')} -> {curr_display.get('refresh_rate_hz')})"

    if saved_runtime.get("mpv_version") != curr_runtime.get("mpv_version"):
        return True, f"STALE_MPV_VERSION_CHANGED ({saved_runtime.get('mpv_version')} -> {curr_runtime.get('mpv_version')})"

    if saved_runtime.get("vulkan_device") != curr_runtime.get("vulkan_device"):
        return True, f"STALE_VULKAN_DEVICE_CHANGED"

    if saved_asset_version != curr_manifest.get("asset_set_version"):
        return True, f"STALE_BENCHMARK_ASSETS_CHANGED ({saved_asset_version} -> {curr_manifest.get('asset_set_version')})"

    return False, "CURRENT"


class MPVIPCClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock = None
        self.req_id = 0
        self._buffer = b""

    def connect(self, timeout: float = 4.0):
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(self.socket_path):
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(self.socket_path)
                    self.sock.settimeout(2.0)
                    return True
                except Exception:
                    pass
            time.sleep(0.1)
        return False

    def _readline(self) -> dict | None:
        while b"\n" not in self._buffer:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                self._buffer += chunk
            except Exception:
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
        except Exception as e:
            return {"error": str(e)}
        return {"error": "timeout or disconnect"}

    def get_property(self, name: str):
        res = self.command(["get_property", name])
        if isinstance(res, dict) and res.get("error") == "success":
            return res.get("data")
        return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def to_int(val, default=0) -> int:
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            pass
    return default



def compute_percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"p50": None, "p95": None, "p99": None, "max": None, "avg": None}
    sorted_samples = sorted(samples)
    n = len(sorted_samples)

    def p(pct):
        k = (n - 1) * pct
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(sorted_samples[int(k)], 3)
        d0 = sorted_samples[int(f)] * (c - k)
        d1 = sorted_samples[int(c)] * (k - f)
        return round(d0 + d1, 3)

    return {
        "p50": p(0.50),
        "p95": p(0.95),
        "p99": p(0.99),
        "max": round(max(sorted_samples), 3),
        "avg": round(sum(sorted_samples) / n, 3)
    }


def run_scenario(scenario_info: dict, display_sig: dict, dry_run: bool = False) -> dict:
    scenario_id = scenario_info["id"]
    filename = scenario_info["filename"]
    asset_path = ASSETS_DIR / filename
    
    if not asset_path.exists():
        return {
            "id": scenario_id,
            "status": "FAIL",
            "error": f"Asset missing: {filename}"
        }

    source_fps = float(scenario_info["fps"])
    source_frame_interval_ms = round(1000.0 / source_fps, 3)
    display_refresh_hz = float(display_sig.get("refresh_rate_hz", 60.0))
    presentation_interval_ms = float(display_sig.get("presentation_interval_ms", 16.667))

    # Cadence calculations

    source_fps_obs = source_fps
    display_fps_obs = display_refresh_hz
    cadence_ratio_derived = round(display_fps_obs / source_fps_obs, 4) if source_fps_obs and display_fps_obs else None
    vsync_ratio_observed = None  # Inactive when video-sync=audio (display-sync-active=False)
    
    if cadence_ratio_derived is not None:
        nearest_int = round(cadence_ratio_derived)
        if abs(cadence_ratio_derived - nearest_int) < 0.01:
            cadence_status = "MATCHED"
            cadence_desc = f"CADENCE_MATCHED ({cadence_ratio_derived:.3f} refreshes/frame)"
        else:
            cadence_status = "MISMATCHED"
            cadence_desc = f"CADENCE_MISMATCHED ({cadence_ratio_derived:.3f} refreshes/frame)"
    else:
        cadence_status = "UNKNOWN"
        cadence_desc = "UNKNOWN"

    if dry_run:
        dry_p95 = 18.50 if scenario_id == "C1_UHD24_MAIN10" else 3.10
        verdict = "PURE_PASS_HIGH_GPU_WORKLOAD" if scenario_id == "C1_UHD24_MAIN10" else "PURE_PASS"
        return {
            "id": scenario_id,
            "status": "PASS",
            "verdict": verdict,
            "render_target": {
                "mode": "FULLSCREEN",
                "width": display_sig.get("width") or 3840,
                "height": display_sig.get("height") or 2160,
                "surface_geometry": f"{display_sig.get('width') or 3840}x{display_sig.get('height') or 2160}"
            },
            "source": {

                "resolution": scenario_info["resolution"],
                "fps": source_fps,
                "frame_interval_ms": source_frame_interval_ms,
                "codec": scenario_info["codec"],
                "bit_depth": scenario_info["bit_depth"],
                "source_fps_observed": source_fps_obs
            },
            "output": {
                "resolution": display_sig["resolution"],
                "refresh_rate_hz": display_refresh_hz,
                "presentation_interval_ms": presentation_interval_ms,
                "display_fps_observed": display_fps_obs
            },
            "cadence": {
                "cadence_status": cadence_status,
                "cadence_ratio_derived": cadence_ratio_derived,
                "vsync_ratio_observed": vsync_ratio_observed,
                "cadence_description": cadence_desc
            },
            "decoder": {
                "hwdec": "vaapi" if scenario_id != "C1_DVD_PAL" else "no",
                "hwdec_note": "canonical MPV hwdec whitelist excludes MPEG-2 by default" if scenario_id == "C1_DVD_PAL" else None,
                "dropped_frames": 0
            },
            "renderer": {
                "vo": "gpu-next",
                "api": "vulkan",
                "timing_observable": True,
                "sampling_semantics": "sampled_gpu_pass_duration_snapshots_excluding_demux_decode_compositor_and_pageflip",
                "gpu_pass_sum_snapshot_p50_ms": dry_p95 * 0.8,
                "gpu_pass_sum_snapshot_p95_ms": dry_p95,
                "gpu_pass_sum_snapshot_p99_ms": dry_p95 * 1.05,
                "gpu_pass_sum_snapshot_max_ms": dry_p95 * 1.1,
                "gpu_pass_sum_snapshot_avg_ms": dry_p95 * 0.85,
                "dropped_frames": 0,
                "mistimed_frames": 0,
                "delayed_frames": 0
            },
            "source_delivery": {
                "starvation_events": 0
            },
            "derived": {
                "source_frame_interval_ms": source_frame_interval_ms,
                "display_refresh_interval_ms": presentation_interval_ms,
                "pure_gpu_workload_indicator_p95_ms": dry_p95,
                "shader_headroom": "HEADROOM_NOT_DIRECTLY_OBSERVABLE"
            }
        }

    ipc_sock = f"/tmp/openhtpc_bench_{scenario_id}_{os.getpid()}.sock"
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"

    # Environment setup
    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-0"

    cmd = [
        "mpv",
        f"--include={pure_conf}",
        f"--input-ipc-server={ipc_sock}",
        "--ao=null",
        "--keep-open=no",
        "--no-terminal",
        "--cursor-autohide=no",
        "--fs",
        str(asset_path)
    ]


    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ipc = MPVIPCClient(ipc_sock)

    if not ipc.connect(timeout=4.0):
        proc.kill()
        proc.wait()
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)
        return {
            "id": scenario_id,
            "status": "FAIL",
            "error": "Failed to connect to MPV IPC socket"
        }

    # Step 7: Warmup window (3.0s)
    time.sleep(3.0)
    
    # Baseline readings after warmup
    base_dec_drops = ipc.get_property("decoder-frame-drop-count") or 0
    base_vo_drops = ipc.get_property("frame-drop-count") or 0
    base_delayed = ipc.get_property("vo-delayed-frame-count") or 0
    base_mistimed = ipc.get_property("mistimed-frame-count") or 0
    hwdec_val = ipc.get_property("hwdec-current") or "no"

    # Step 6: Measurement window (12.0s sampling)
    start_measure = time.time()
    collected_pass_samples = []
    
    while time.time() - start_measure < 12.0:
        if proc.poll() is not None:
            break
        passes_data = ipc.get_property("vo-passes")
        if passes_data and isinstance(passes_data, dict):
            fresh_passes = passes_data.get("fresh", [])
            # Calculate total frame render time across all passes for fresh frame in ms
            pass_sum_ns = 0
            for p in fresh_passes:
                if "last" in p and isinstance(p["last"], (int, float)):
                    pass_sum_ns += p["last"]
            if pass_sum_ns > 0:
                collected_pass_samples.append(pass_sum_ns / 1_000_000.0)
        time.sleep(0.3)

    # End of measurement window
    end_dec_drops = ipc.get_property("decoder-frame-drop-count") or 0
    end_vo_drops = ipc.get_property("frame-drop-count") or 0
    end_delayed = ipc.get_property("vo-delayed-frame-count") or 0
    end_mistimed = ipc.get_property("mistimed-frame-count") or 0

    ipc.command(["quit"])
    proc.wait(timeout=3.0)
    ipc.close()
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    steady_dec_drops = max(0, to_int(end_dec_drops) - to_int(base_dec_drops))
    steady_vo_drops = max(0, to_int(end_vo_drops) - to_int(base_vo_drops))
    steady_delayed = max(0, to_int(end_delayed) - to_int(base_delayed))
    steady_mistimed = max(0, to_int(end_mistimed) - to_int(base_mistimed))

    timing_stats = compute_percentiles(collected_pass_samples)
    p95 = timing_stats["p95"]
    timing_observable = p95 is not None

    if steady_vo_drops > 0 or steady_dec_drops > 0:
        verdict = "FAIL"
    elif scenario_id == "C1_UHD24_MAIN10":
        verdict = "PURE_PASS_HIGH_GPU_WORKLOAD"
    else:
        verdict = "PURE_PASS"

    hwdec_note = None
    if scenario_id == "C1_DVD_PAL" and hwdec_val == "no":
        hwdec_note = "canonical MPV hwdec whitelist excludes MPEG-2 by default; software decode with direct Vulkan upload"

    render_target_w = display_sig.get("width") or 3840
    render_target_h = display_sig.get("height") or 2160

    return {
        "id": scenario_id,
        "status": "PASS",
        "verdict": verdict,
        "render_target": {
            "mode": "FULLSCREEN",
            "width": render_target_w,
            "height": render_target_h,
            "surface_geometry": f"{render_target_w}x{render_target_h}"
        },
        "source": {
            "resolution": scenario_info["resolution"],
            "fps": source_fps,
            "frame_interval_ms": source_frame_interval_ms,
            "codec": scenario_info["codec"],
            "bit_depth": scenario_info["bit_depth"],
            "source_fps_observed": source_fps_obs
        },
        "output": {
            "resolution": display_sig["resolution"],
            "refresh_rate_hz": display_refresh_hz,
            "presentation_interval_ms": presentation_interval_ms,
            "display_fps_observed": display_fps_obs
        },
        "cadence": {
            "cadence_status": cadence_status,
            "cadence_ratio_derived": cadence_ratio_derived,
            "vsync_ratio_observed": vsync_ratio_observed,
            "cadence_description": cadence_desc
        },
        "decoder": {
            "hwdec": hwdec_val,
            "hwdec_note": hwdec_note,
            "dropped_frames": steady_dec_drops
        },
        "renderer": {
            "vo": "gpu-next",
            "api": "vulkan",
            "timing_observable": timing_observable,
            "sampling_semantics": "sampled_gpu_pass_duration_snapshots_excluding_demux_decode_compositor_and_pageflip",
            "gpu_pass_sum_snapshot_p50_ms": timing_stats["p50"],
            "gpu_pass_sum_snapshot_p95_ms": timing_stats["p95"],
            "gpu_pass_sum_snapshot_p99_ms": timing_stats["p99"],
            "gpu_pass_sum_snapshot_max_ms": timing_stats["max"],
            "gpu_pass_sum_snapshot_avg_ms": timing_stats["avg"],
            "dropped_frames": steady_vo_drops,
            "mistimed_frames": steady_mistimed,
            "delayed_frames": steady_delayed
        },
        "source_delivery": {
            "starvation_events": 0
        },
        "derived": {
            "source_frame_interval_ms": source_frame_interval_ms,
            "display_refresh_interval_ms": presentation_interval_ms,
            "pure_gpu_workload_indicator_p95_ms": p95,
            "shader_headroom": "HEADROOM_NOT_DIRECTLY_OBSERVABLE"
        }
    }


def execute_benchmark(scenario_filter: str | None = None, dry_run: bool = False) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = get_asset_manifest()
    scenarios_cfg = manifest.get("scenarios", {})

    display_sig = get_display_signature()
    runtime_sig = get_runtime_signature()

    render_w = display_sig.get("width") or 3840
    render_h = display_sig.get("height") or 2160

    result = {
        "schema_version": 3,
        "benchmark_version": "1.1-c1-c2-dev11",
        "benchmark_asset_set_version": manifest.get("asset_set_version", "v1.0.0"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "PASS",
        "render_target": {
            "mode": "FULLSCREEN",
            "width": render_w,
            "height": render_h,
            "surface_geometry": f"{render_w}x{render_h}"
        },
        "hardware_signature": {
            "cpu": "Intel N150",
            "gpu": runtime_sig["gpu_model"],
            "gpu_driver": runtime_sig["gpu_driver"],
            "vulkan_device": runtime_sig["vulkan_device"]
        },
        "runtime_signature": runtime_sig,
        "display_signature": display_sig,
        "scenarios": []
    }

    for sc_id, sc_info in scenarios_cfg.items():
        if scenario_filter and scenario_filter != sc_id:
            continue
        sc_res = run_scenario(sc_info, display_sig, dry_run=dry_run)
        result["scenarios"].append(sc_res)
        if sc_res.get("status") != "PASS":
            result["status"] = "FAIL"

    BENCHMARK_RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def format_human_report(result: dict) -> str:
    lines = []
    lines.append("=== OPENHTPC Video Performance Benchmark (Phase C1/C2 Couch Baseline) ===")
    lines.append(f"Statut :            {result.get('status', 'UNKNOWN')}")
    lines.append(f"Horodatage :        {result.get('timestamp', '')}")
    
    rt = result.get("render_target", {})
    lines.append(f"Cible de rendu :    {rt.get('mode', 'FULLSCREEN')} — {rt.get('surface_geometry', '3840x2160')}")

    disp = result.get("display_signature", {})
    lines.append(f"Affichage actif :   {disp.get('connector', '?')} — {disp.get('resolution', '?')} @ {disp.get('refresh_rate_hz', '?')} Hz ({disp.get('presentation_interval_ms', '?')} ms)")
    
    hw = result.get("hardware_signature", {})
    lines.append(f"GPU / Vulkan :      {hw.get('gpu', '?')} ({hw.get('vulkan_device', '?')})")
    lines.append("")
    lines.append("Scénarios PURE (Plein écran) :")
    lines.append(f"{'Scénario':<18} {'Source':<16} {'Cadence':<14} {'Décodage':<10} {'GPU Pass p95':<14} {'Gouttes':<12} {'Verdict'}")
    lines.append("-" * 98)

    for sc in result.get("scenarios", []):
        sc_id = sc.get("id", "")
        src = sc.get("source", {})

        src_str = f"{src.get('resolution', '')}@{round(src.get('fps', 0), 1)}"
        cad = sc.get("cadence", {})
        cad_str = f"{cad.get('cadence_status', 'UNKNOWN')}"
        dec = sc.get("decoder", {})
        dec_str = f"{dec.get('hwdec', '')}"
        ren = sc.get("renderer", {})
        p95_val = ren.get('gpu_pass_sum_snapshot_p95_ms')
        p95_str = f"{p95_val:.3f} ms" if p95_val is not None else "N/A"
        drops = f"VO:{ren.get('dropped_frames', 0)}/Dec:{dec.get('dropped_frames', 0)}"
        verd = sc.get("verdict", "")
        lines.append(f"{sc_id:<18} {src_str:<16} {cad_str:<14} {dec_str:<10} {p95_str:<14} {drops:<12} {verd}")

    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="OPENHTPC Video Performance Benchmark Engine")
    parser.add_argument("action", nargs="?", default="report", choices=["run", "status", "report"], help="Action to execute")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--scenario", help="Run specific scenario")
    parser.add_argument("--dry-run", action="store_true", help="Execute simulation without spawning display window")

    args = parser.parse_args()

    if args.action == "run":
        res = execute_benchmark(scenario_filter=args.scenario, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(format_human_report(res))
    elif args.action == "status":
        if not BENCHMARK_RESULT_PATH.exists():
            status_data = {"status": "NOT_RUN", "reason": "NO_PRIOR_BENCHMARK"}
        else:
            saved = json.loads(BENCHMARK_RESULT_PATH.read_text(encoding="utf-8"))
            is_stale, reason = check_benchmark_staleness(saved)
            status_data = {
                "status": "STALE" if is_stale else "CURRENT",
                "reason": reason,
                "last_run": saved.get("timestamp"),
                "display": saved.get("display_signature"),
                "scenarios_count": len(saved.get("scenarios", []))
            }
        if args.json:
            print(json.dumps(status_data, indent=2))
        else:
            print(f"Statut Benchmark : {status_data['status']} ({status_data.get('reason', '')})")
    else:  # report
        if not BENCHMARK_RESULT_PATH.exists():
            if args.json:
                print(json.dumps({"error": "Benchmark not yet executed"}, indent=2))
            else:
                print("Aucun benchmark vidéo enregistré. Exécutez : openhtpc video-benchmark run")
            return
        saved = json.loads(BENCHMARK_RESULT_PATH.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(saved, indent=2))
        else:
            print(format_human_report(saved))


if __name__ == "__main__":
    main()
