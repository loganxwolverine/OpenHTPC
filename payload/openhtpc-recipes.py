#!/usr/bin/env python3
"""OPENHTPC Phase C2 Video Enhancement Recipe Qualification Engine."""
from __future__ import annotations
import argparse
import copy
import datetime
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

INSTALL_DIR = pathlib.Path(__file__).resolve().parent
SHADERS_DIR = INSTALL_DIR / "assets" / "shaders"
BENCHMARK_DIR = INSTALL_DIR / "assets" / "benchmark"
STATE_DIR = pathlib.Path.home() / ".local" / "state" / "openhtpc"
RECIPES_STATE_PATH = STATE_DIR / "video_recipes.json"

UPSTREAM_COMMIT = "e2bfe0ccd7eb7b404f9262365bed88771f69a291"

DVD_PAL_RECIPES = [
    {
        "recipe_id": "RECIPE_0_PURE",
        "recipe_version": "1.0",
        "name": "PURE Baseline",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": [],
        "runtime_options": {},
        "description": "Immutable PURE comparison baseline (gpu-next native scaling + dithering)",
        "license_status": "N/A (Built-in)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_CFL_LITE",
        "recipe_version": "1.0",
        "name": "CfL Prediction Lite",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["CfL_Prediction_Lite.glsl"],
        "runtime_options": {},
        "description": "Chroma-from-Luma prediction for DVD 4:2:0 color reconstruction",
        "license_status": "MIT (João Chrisóstomo)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_KRIG_BILATERAL",
        "recipe_version": "1.0",
        "name": "KrigBilateral Chroma",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["KrigBilateral.glsl"],
        "runtime_options": {},
        "description": "Luma-guided bilateral filter chroma upsampler",
        "license_status": "GNU LGPL v3+ (Shiandow)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_RAVU_LITE",
        "recipe_version": "1.0",
        "name": "RAVU Lite AR r4",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["ravu-lite-ar-r4.hook"],
        "runtime_options": {},
        "description": "Fast 2x neural luma prescaler with anti-ringing heuristics",
        "license_status": "GNU LGPL v3+ (bjin)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_FSRCNNX_8",
        "recipe_version": "1.0",
        "name": "FSRCNNX 8-0-4-1",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["FSRCNNX_x2_8-0-4-1.glsl"],
        "runtime_options": {},
        "description": "8-feature convolutional neural network 2x prescaler",
        "license_status": "GNU LGPL v3+ (igv)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_ARTCNN_C4F16",
        "recipe_version": "1.0",
        "name": "ArtCNN C4F16",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["ArtCNN_C4F16.glsl"],
        "runtime_options": {},
        "description": "Modern 4-layer 16-feature CNN upscaler for natural edge restoration",
        "license_status": "MIT (Joao Chrisostomo, Kacper Michajlow)"
    },
    {
        "recipe_id": "RECIPE_C2_DVD_FSRCNNX_16",
        "recipe_version": "1.0",
        "name": "FSRCNNX 16-0-4-1",
        "source_class": "DVD_PAL_CLASS",
        "output_class": "UHD_4K60",
        "ordered_shaders": ["FSRCNNX_x2_16-0-4-1.glsl"],
        "runtime_options": {},
        "description": "Heavy 16-feature CNN 2x prescaler (computational ceiling stress-test)",
        "license_status": "GNU LGPL v3+ (igv)"
    }
]


def load_shader_catalog() -> dict:
    catalog_path = SHADERS_DIR / "catalog.json"
    if catalog_path.exists():
        try:
            return json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"shaders": {}}


class RecipeIPCClient:
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
    sorted_s = sorted(samples)
    n = len(sorted_s)
    
    def percentile(p):
        k = (n - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, n - 1)
        d = k - f
        return round(sorted_s[f] + (sorted_s[c] - sorted_s[f]) * d, 3)

    return {
        "p50": percentile(50),
        "p95": percentile(95),
        "p99": percentile(99),
        "max": round(sorted_s[-1], 3),
        "avg": round(sum(sorted_s) / n, 3)
    }


def run_single_recipe_benchmark(recipe: dict, asset_path: pathlib.Path, dry_run: bool = False) -> dict:
    recipe_id = recipe["recipe_id"]
    ordered_shaders = recipe["ordered_shaders"]

    if dry_run:
        dry_p95_map = {
            "RECIPE_0_PURE": 20.75,
            "RECIPE_C2_DVD_CFL_LITE": 19.48,
            "RECIPE_C2_DVD_KRIG_BILATERAL": 20.14,
            "RECIPE_C2_DVD_RAVU_LITE": 23.87,
            "RECIPE_C2_DVD_FSRCNNX_8": 34.10,
            "RECIPE_C2_DVD_ARTCNN_C4F16": 221.35,
            "RECIPE_C2_DVD_FSRCNNX_16": 67.49
        }
        dry_p95 = dry_p95_map.get(recipe_id, 20.0)
        drops = 90 if dry_p95 > 50.0 else 0
        if drops > 0:
            verdict = "TECH_FAIL_DROPS"
        elif recipe_id == "RECIPE_C2_DVD_FSRCNNX_8" or dry_p95 > 30.0:
            verdict = "TECH_PASS_HIGH_GPU_WORKLOAD"
        else:
            verdict = "TECH_PASS"
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "gpu_pass_sum_snapshot_p50_ms": round(dry_p95 * 0.95, 3),
            "gpu_pass_sum_snapshot_p95_ms": dry_p95,
            "gpu_pass_sum_snapshot_p99_ms": round(dry_p95 * 1.02, 3),
            "gpu_pass_sum_snapshot_max_ms": round(dry_p95 * 1.05, 3),
            "gpu_pass_sum_snapshot_avg_ms": round(dry_p95 * 0.96, 3),
            "decoder_drops": 0,
            "vo_drops": drops,
            "delayed_frames": 0,
            "mistimed_frames": 0,
            "starvation_events": 0,
            "mpv_errors": 0,
            "technical_verdict": verdict
        }


    ipc_sock = f"/tmp/openhtpc_recipe_{recipe_id}_{os.getpid()}_{int(time.time()*1000)%10000}.sock"
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"

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
    ]


    # Append shaders in order
    if ordered_shaders:
        shader_paths = []
        for s_file in ordered_shaders:
            p = SHADERS_DIR / s_file
            if p.exists():
                shader_paths.append(str(p))
        if shader_paths:
            cmd.append(f"--glsl-shaders={':'.join(shader_paths)}")

    cmd.append(str(asset_path))

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ipc = RecipeIPCClient(ipc_sock)

    if not ipc.connect(timeout=4.0):
        proc.kill()
        proc.wait()
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "technical_verdict": "TECH_FAIL_RUNTIME",
            "error": "Failed to connect to MPV IPC socket"
        }

    # Warmup 3.0s
    time.sleep(3.0)

    base_dec_drops = ipc.get_property("decoder-frame-drop-count") or 0
    base_vo_drops = ipc.get_property("frame-drop-count") or 0
    base_delayed = ipc.get_property("vo-delayed-frame-count") or 0
    base_mistimed = ipc.get_property("mistimed-frame-count") or 0

    # 12.0s measurement window
    start_measure = time.time()
    collected_pass_samples = []

    while time.time() - start_measure < 12.0:
        if proc.poll() is not None:
            break
        passes_data = ipc.get_property("vo-passes")
        if passes_data and isinstance(passes_data, dict):
            fresh_passes = passes_data.get("fresh", [])
            pass_sum_ns = 0
            for p in fresh_passes:
                if "last" in p and isinstance(p["last"], (int, float)):
                    pass_sum_ns += p["last"]
            if pass_sum_ns > 0:
                collected_pass_samples.append(pass_sum_ns / 1_000_000.0)
        time.sleep(0.3)

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

    if steady_vo_drops > 0 or steady_dec_drops > 0:
        verdict = "TECH_FAIL_DROPS"
    elif p95 is None:
        verdict = "TECH_FAIL_RUNTIME"
    elif recipe_id in ("RECIPE_C2_DVD_FSRCNNX_8",) or (p95 is not None and p95 > 25.0):
        verdict = "TECH_PASS_HIGH_GPU_WORKLOAD"
    else:
        verdict = "TECH_PASS"

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gpu_pass_sum_snapshot_p50_ms": timing_stats["p50"],
        "gpu_pass_sum_snapshot_p95_ms": timing_stats["p95"],
        "gpu_pass_sum_snapshot_p99_ms": timing_stats["p99"],
        "gpu_pass_sum_snapshot_max_ms": timing_stats["max"],
        "gpu_pass_sum_snapshot_avg_ms": timing_stats["avg"],
        "decoder_drops": steady_dec_drops,
        "vo_drops": steady_vo_drops,
        "delayed_frames": steady_delayed,
        "mistimed_frames": steady_mistimed,
        "starvation_events": 0,
        "mpv_errors": 0,
        "technical_verdict": verdict
    }


def execute_all_dvd_recipes(repeats: int = 3, dry_run: bool = False) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = BENCHMARK_DIR / "c1_dvd_pal.mpg"

    catalog = load_shader_catalog()

    result = {
        "schema_version": 2,
        "catalog_version": "v1.1.0",
        "upstream_repository": "https://github.com/loganxwolverine/shaders",
        "upstream_commit": UPSTREAM_COMMIT,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_class": "DVD_PAL_CLASS",
        "render_target": {
            "mode": "FULLSCREEN",
            "width": 3840,
            "height": 2160,
            "surface_geometry": "3840x2160"
        },
        "output_signature": {
            "resolution": "3840x2160",
            "refresh_rate_hz": 60.0,
            "bit_depth": 10
        },
        "recipes": []
    }

    pure_p95_baseline = None

    for recipe_def in DVD_PAL_RECIPES:
        recipe_record = copy.deepcopy(recipe_def)
        recipe_record["runs"] = []
        recipe_record["visual_status"] = "NOT_REVIEWED"
        recipe_record["cinema_auto_eligible"] = False

        run_verdicts = []
        run_p95s = []

        for r_idx in range(repeats):
            run_data = run_single_recipe_benchmark(recipe_def, asset_path, dry_run=dry_run)
            recipe_record["runs"].append(run_data)
            run_verdicts.append(run_data.get("technical_verdict", "TECH_FAIL_RUNTIME"))
            if run_data.get("gpu_pass_sum_snapshot_p95_ms") is not None:
                run_p95s.append(run_data["gpu_pass_sum_snapshot_p95_ms"])

        # Determine aggregate technical verdict
        if any("TECH_FAIL_DROPS" in v for v in run_verdicts):
            agg_verdict = "TECH_FAIL_DROPS"
        elif any("TECH_FAIL_RUNTIME" in v for v in run_verdicts):
            agg_verdict = "TECH_FAIL_RUNTIME"
        elif any("TECH_PASS_HIGH_GPU_WORKLOAD" in v for v in run_verdicts):
            agg_verdict = "TECH_PASS_HIGH_GPU_WORKLOAD"
        elif any("TECH_PASS_WITH_SPIKES" in v for v in run_verdicts):
            agg_verdict = "TECH_PASS_WITH_SPIKES"
        else:
            agg_verdict = "TECH_PASS"

        avg_p95 = round(sum(run_p95s)/len(run_p95s), 3) if run_p95s else None
        if recipe_def["recipe_id"] == "RECIPE_0_PURE":
            pure_p95_baseline = avg_p95

        recipe_record["technical_verdict"] = agg_verdict
        recipe_record["aggregate_p95_ms"] = avg_p95
        result["recipes"].append(recipe_record)

    # Compute relative GPU workload vs PURE baseline
    for r in result["recipes"]:
        rec_p95 = r.get("aggregate_p95_ms")
        if rec_p95 and pure_p95_baseline and pure_p95_baseline > 0:
            ratio = round(rec_p95 / pure_p95_baseline, 3)
            r["relative_gpu_workload_vs_pure_ratio"] = ratio
            r["relative_gpu_workload_description"] = f"{ratio:.3f}x PURE baseline workload (informational metric, not available headroom)"
        else:
            r["relative_gpu_workload_vs_pure_ratio"] = 1.0 if r["recipe_id"] == "RECIPE_0_PURE" else None
            r["relative_gpu_workload_description"] = "N/A"

    RECIPES_STATE_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result



def capture_recipe_comparison(recipe_id: str, timestamp_s: float = 5.0, output_png: pathlib.Path | None = None) -> pathlib.Path | None:
    recipe_match = next((r for r in DVD_PAL_RECIPES if r["recipe_id"] == recipe_id), None)
    if not recipe_match:
        return None

    asset_path = BENCHMARK_DIR / "c1_dvd_pal.mpg"
    if not output_png:
        output_png = STATE_DIR / f"capture_{recipe_id}.png"
    output_png.parent.mkdir(parents=True, exist_ok=True)
    if output_png.exists():
        output_png.unlink()

    ipc_sock = f"/tmp/openhtpc_cap_{recipe_id}_{os.getpid()}.sock"
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"

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
        f"--start={timestamp_s}",
        "--pause=yes",
    ]

    ordered_shaders = recipe_match["ordered_shaders"]
    if ordered_shaders:
        shader_paths = []
        for s_file in ordered_shaders:
            p = SHADERS_DIR / s_file
            if p.exists():
                shader_paths.append(str(p))
        if shader_paths:
            cmd.append(f"--glsl-shaders={':'.join(shader_paths)}")

    cmd.append(str(asset_path))

    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ipc = RecipeIPCClient(ipc_sock)

    if not ipc.connect(timeout=4.0):
        proc.kill()
        proc.wait()
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)
        return None

    # Wait for frame to be ready and take screenshot
    time.sleep(1.0)
    ipc.command(["screenshot-to-file", str(output_png), "video"])
    time.sleep(0.5)
    ipc.command(["quit"])
    proc.wait(timeout=3.0)
    ipc.close()
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    return output_png if output_png.exists() else None


def format_recipes_report(result: dict) -> str:
    lines = []
    lines.append("=== OPENHTPC Video Enhancement Recipe Qualification (Phase C1/C2 Couch Baseline) ===")
    lines.append(f"Source Class :      {result.get('source_class', 'DVD_PAL_CLASS')} (720x576 @ 25.0 fps)")
    rt = result.get("render_target", {})
    lines.append(f"Cible de rendu :    {rt.get('mode', 'FULLSCREEN')} — {rt.get('surface_geometry', '3840x2160')}")
    disp = result.get("output_signature", {})
    lines.append(f"Target Output :     {disp.get('resolution', '3840x2160')} @ {disp.get('refresh_rate_hz', 60.0)} Hz ({disp.get('bit_depth', 10)}-bit)")
    lines.append(f"Upstream Commit :   {result.get('upstream_commit', UPSTREAM_COMMIT)[:12]}")
    lines.append(f"Horodatage :        {result.get('timestamp', '')}")
    lines.append("")
    lines.append("Résultats de qualification des recettes :")
    lines.append(f"{'ID Recette':<30} {'Nom Recette':<24} {'GPU Pass p95':<14} {'Charge Rel.':<12} {'Gouttes':<10} {'Verdict Tech':<28} {'Eligible Auto'}")
    lines.append("-" * 135)

    for r in result.get("recipes", []):
        r_id = r.get("recipe_id", "")
        r_name = r.get("name", "")
        p95 = f"{r.get('aggregate_p95_ms', '?')} ms" if r.get("aggregate_p95_ms") is not None else "N/A"
        ratio = r.get("relative_gpu_workload_vs_pure_ratio")
        ratio_str = f"{ratio:.3f}x" if ratio is not None else "1.000x"
        runs = r.get("runs", [])
        drops = f"VO:{runs[0].get('vo_drops', 0)}/Dec:{runs[0].get('decoder_drops', 0)}" if runs else "N/A"
        verd = r.get("technical_verdict", "")
        elig = "OUI" if r.get("cinema_auto_eligible") else "NON"
        lines.append(f"{r_id:<30} {r_name:<24} {p95:<14} {ratio_str:<12} {drops:<10} {verd:<28} {elig}")

    lines.append("")
    return "\n".join(lines)



def main():
    parser = argparse.ArgumentParser(description="OPENHTPC Phase C2 Recipe Qualification Engine")
    parser.add_argument("action", nargs="?", default="run", choices=["run", "status", "report", "catalog", "compare"])
    parser.add_argument("--repeats", type=int, default=3, help="Number of benchmark repeats per recipe")
    parser.add_argument("--dry-run", action="store_true", help="Run deterministic synthetic test")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--recipe", type=str, default="RECIPE_0_PURE", help="Target recipe ID for compare")
    parser.add_argument("--all", action="store_true", help="Capture comparison frames for all recipes")

    args = parser.parse_args()

    if args.action == "catalog":
        cat = load_shader_catalog()
        if args.json:
            print(json.dumps(cat, indent=2))
        else:
            print(f"=== OPENHTPC Shader Capability Catalog (v1.0.0) ===")
            print(f"Upstream: {cat.get('upstream_repository')} (commit {cat.get('upstream_commit')[:12]})")
            print(f"{'ID':<25} {'Classe':<14} {'Hook':<10} {'Licence':<20} {'Nom'}")
            print("-" * 85)
            for s_id, s_data in cat.get("shaders", {}).items():
                print(f"{s_id:<25} {s_data.get('functional_class', ''):<14} {s_data.get('hook_stage', ''):<10} {s_data.get('license', ''):<20} {s_data.get('name', '')}")
        return

    if args.action == "compare":
        if args.all:
            for r in DVD_PAL_RECIPES:
                cap = capture_recipe_comparison(r["recipe_id"])
                if cap:
                    print(f"[OPENHTPC] Frame comparison capture generated: {cap}")
                else:
                    print(f"[OPENHTPC] Failed to capture comparison frame for {r['recipe_id']}")
        else:
            cap = capture_recipe_comparison(args.recipe)
            if cap:
                print(f"[OPENHTPC] Frame comparison capture generated: {cap}")
            else:
                print(f"[OPENHTPC] Failed to capture comparison frame for {args.recipe}")
        return

    if args.action == "run":
        res = execute_all_dvd_recipes(repeats=args.repeats, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(format_recipes_report(res))
        return

    if args.action in ("status", "report"):
        if not RECIPES_STATE_PATH.exists():
            print("[OPENHTPC] No recipe qualification data recorded. Run 'openhtpc recipe-benchmark run'.")
            sys.exit(1)
        res = json.loads(RECIPES_STATE_PATH.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(format_recipes_report(res))
        return



if __name__ == "__main__":
    main()
