#!/usr/bin/env python3
"""Authoritative pre-release gate for the OPENHTPC Magnificence RC.

This gate validates the current Magnificence product contract without weakening
or hiding historical tranche tests whose frozen assumptions intentionally refer
to older OPENHTPC revisions.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
PROFILES = PAYLOAD / "assets/magnificence_profiles.json"
SHADER_CATALOG = PAYLOAD / "assets/shaders/catalog.json"
MANAGED = PAYLOAD / "managed-files.txt"

STABLE_REF = "release/1.2.0-stable-prep"
STABLE_COMMIT = "cae1f8f496dfd71c243bfef4fa199b66d1c7cd30"

EXPECTED_TIERS = {
    "intel_n150_8086_46d4_sd_1080p": "LIGHT",
    "amd_picasso_15d8_vega3_sd_2160p": "LIGHT",
    "intel_arc_a310_8086_56a6_sd_2160p": "MEDIUM",
    "intel_hd630_8086_5912_sd_1080p": "MEDIUM",
    "nvidia_rtx3050_10de_2507_sd_2160p": "HIGH",
    "amd_rx580_1002_67df_sd_2160p": "STRONG",
    "amd_rx5700xt_1002_731f_sd_2160p": "HIGH",
}

ACTIVE_TESTS = [
    "tests/test_dev32_playback_policy.py",
    "tests/test_dev34_playback_ui_persistence_osd.py",
    "tests/test_dev35_playback_ux.py",
    "tests/test_dev36_playback_corrective.py",
    "tests/test_magnificence_policy.py",
    "tests/test_magnificence_static_auto.py",
    "tests/test_rc7_system_model.py",
    "tests/test_refresh_match.py",
    "tests/test_audio_passthrough_p0.py",
    "tests/test_audio_passthrough_rc2.py",
    "tests/test_pipewire_hd_passthrough_rc4.py",
    "tests/test_pipewire_hd_passthrough_rc5.py",
    "tests/test_release_metadata_consistency.py",
    "tests/test_update_runtime_regeneration_dev14.py",
    "tests/test_devctl.py",
]


def run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        list(cmd),
        cwd=ROOT,
        text=True,
        stdin=subprocess.DEVNULL,
        check=check,
    )


def capture(*cmd: str) -> str:
    return subprocess.run(
        list(cmd),
        cwd=ROOT,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=True,
    ).stdout.strip()


def static_contract() -> None:
    profiles_doc = json.loads(PROFILES.read_text(encoding="utf-8"))
    catalog_doc = json.loads(SHADER_CATALOG.read_text(encoding="utf-8"))
    managed = set(MANAGED.read_text(encoding="utf-8").splitlines())

    profiles = profiles_doc.get("profiles", {})
    if set(profiles) != set(EXPECTED_TIERS):
        missing = sorted(set(EXPECTED_TIERS) - set(profiles))
        extra = sorted(set(profiles) - set(EXPECTED_TIERS))
        raise RuntimeError(f"PROFILE_MATRIX_MISMATCH missing={missing} extra={extra}")

    catalog = {
        entry.get("filename"): entry
        for entry in catalog_doc.get("shaders", {}).values()
        if isinstance(entry, dict)
    }

    for profile_id, tier in EXPECTED_TIERS.items():
        profile = profiles[profile_id]
        gpu = profile.get("gpu", {})
        classification = profile.get("classification", {})
        mag = profile.get("magnificence", {})

        if gpu.get("hardware_class") != tier:
            raise RuntimeError(f"{profile_id}:GPU_TIER_MISMATCH")
        if classification.get("gpu_tier") != tier:
            raise RuntimeError(f"{profile_id}:CLASSIFICATION_TIER_MISMATCH")
        if classification.get("runtime_benchmark_required") is not False:
            raise RuntimeError(f"{profile_id}:RUNTIME_BENCHMARK_SELECTION_NOT_DISABLED")
        if mag.get("fallback_recipe") != "RECIPE_0_PURE":
            raise RuntimeError(f"{profile_id}:PURE_FALLBACK_MISSING")

        for shader in mag.get("selected_shaders", []):
            shader_path = PAYLOAD / "assets/shaders" / shader
            entry = catalog.get(shader)
            if not shader_path.is_file():
                raise RuntimeError(f"{profile_id}:SHADER_MISSING:{shader}")
            if not entry:
                raise RuntimeError(f"{profile_id}:SHADER_UNCATALOGED:{shader}")
            if entry.get("redistributable") is not True or not entry.get("license"):
                raise RuntimeError(f"{profile_id}:SHADER_LICENSE_INCOMPLETE:{shader}")
            if f"assets/shaders/{shader}" not in managed:
                raise RuntimeError(f"{profile_id}:SHADER_NOT_MANAGED:{shader}")

    if profiles_doc.get("policy") != "PURE_OR_MAGNIFICENCE":
        raise RuntimeError("PUBLIC_MODE_CONTRACT_CHANGED")

    stable = capture("git", "rev-parse", STABLE_REF)
    if stable != STABLE_COMMIT:
        raise RuntimeError(f"STABLE_REF_MOVED:{stable}")

    print("PASS static Magnificence profile/shader/stable-ref contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow a dirty worktree while developing the candidate",
    )
    args = parser.parse_args()

    static_contract()

    run(sys.executable, "-m", "pytest", "-q", *ACTIVE_TESTS)
    run(str(ROOT / "tools/openhtpc-devctl"), "test", "media-foundation")
    run("git", "diff", "--check")

    if not args.allow_dirty:
        status = capture("git", "status", "--porcelain")
        if status:
            print(status)
            raise RuntimeError("RC_WORKTREE_DIRTY")

    print("PASS OPENHTPC Magnificence RC gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
