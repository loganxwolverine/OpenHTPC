#!/usr/bin/env python3
"""OPENHTPC 1.1 Phase C3 CINÉMA AUTO Selection Engine.

Read-only consumer of the Performance Map produced by openhtpc-calibrate.py.

Given a content_scope and output_signature, returns the Highest quality_priority candidate that is technically stable on this hardware. Falls back to PURE
unconditionally when the map is absent, stale, or yields no stable result.

Wired into normal playback in C4 Dev1 for DVD_PAL_FILM scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

STATE_DIR = pathlib.Path(os.environ.get("OPENHTPC_STATE_DIR", pathlib.Path.home() / ".local/state/openhtpc"))
PERFORMANCE_MAP_PATH = STATE_DIR / "performance_map.json"
ROOT_DIR = pathlib.Path(__file__).resolve().parent
CATALOG_PATH = ROOT_DIR / "assets" / "c3_calibration_catalog.json"

SCHEMA_VERSION = 2
BENCHMARK_METHOD_VERSION = 1
FALLBACK_RECIPE = "RECIPE_0_PURE"


def _sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_map() -> dict | None:
    if not PERFORMANCE_MAP_PATH.exists():
        return None
    try:
        data = json.loads(PERFORMANCE_MAP_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            return None
        return data
    except Exception:
        return None


def _load_catalog() -> dict:
    if CATALOG_PATH.exists():
        try:
            return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scopes": {}}


def _build_current_output_sig() -> str:
    """Compute the current output_signature hash for staleness comparison."""
    try:
        import subprocess, re
        res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            m = re.search(r"(\d+)x(\d+)@([0-9.]+)\*", res.stdout)
            bpc = re.search(r"Color resolution:.*\((\d+)\)", res.stdout)
            conn = re.search(r"Output:\s*\d+\s+([A-Za-z0-9-]+)", res.stdout)
            if m:
                w, h, hz = m.group(1), m.group(2), m.group(3)
                b = bpc.group(1) if bpc else "?"
                c = conn.group(1) if conn else "UNKNOWN"
                wayland = os.environ.get("WAYLAND_DISPLAY", "UNKNOWN")
                sig_str = f"{w}x{h}@{float(hz):.2f}Hz_{b}bit_{c}_{wayland}"
                return _sha256_str(sig_str)
    except Exception:
        pass
    return ""


def is_map_stale(perf_map: dict) -> tuple[bool, str]:
    """Check if the saved performance map is stale against current system."""
    saved_sigs = perf_map.get("calibration_metadata", {}).get("signatures", {})

    # Method version must match
    if saved_sigs.get("benchmark_method_version") != BENCHMARK_METHOD_VERSION:
        return True, "STALE_METHOD_VERSION"

    # Output signature must match
    current_output_sig = _build_current_output_sig()
    if current_output_sig and saved_sigs.get("output_signature") != current_output_sig:
        return True, "STALE_OUTPUT_SIGNATURE"

    return False, "CURRENT"


def select_recipe(content_scope: str, perf_map: dict, catalog: dict) -> tuple[str, str]:
    """
    Return (recipe_id, reason) for the given content_scope.

    Quality ranking comes from the catalogue (fixed by Phase C2 qualification).
    Hardware calibration only provides technically_usable boolean.
    Candidates are evaluated in ascending quality_priority order (1 = best).
    """
    stale, stale_reason = is_map_stale(perf_map)
    if stale:
        return FALLBACK_RECIPE, f"FALLBACK_MAP_STALE:{stale_reason}"

    entries_by_scope: dict = perf_map.get("entries", {})
    scope_entries_list: list = entries_by_scope.get(content_scope, [])
    if not scope_entries_list:
        return FALLBACK_RECIPE, "FALLBACK_NO_ENTRIES_FOR_SCOPE"

    # Index entries by recipe_id
    entries_by_recipe: dict[str, dict] = {e["recipe_id"]: e for e in scope_entries_list}

    # Load candidates from catalogue in quality_priority order (ascending = best first)
    scope_def = catalog.get("scopes", {}).get(content_scope, {})
    candidates = sorted(
        scope_def.get("candidates", []),
        key=lambda c: c["quality_priority"],
    )

    if not candidates:
        return FALLBACK_RECIPE, "FALLBACK_NO_CANDIDATES_IN_CATALOG"

    for candidate in candidates:
        recipe_id = candidate["recipe_id"]
        entry = entries_by_recipe.get(recipe_id)
        if entry and entry.get("technically_usable"):
            return recipe_id, f"SELECTED_PRIORITY_{candidate['quality_priority']}"

    return FALLBACK_RECIPE, "FALLBACK_NO_STABLE_CANDIDATE"


def query(content_scope: str) -> dict:
    """Full query: load map, check staleness, select recipe."""
    perf_map = _load_map()
    if perf_map is None:
        return {
            "recipe_id": FALLBACK_RECIPE,
            "reason": "FALLBACK_MAP_ABSENT",
            "content_scope": content_scope,
            "map_status": "ABSENT",
        }

    catalog = _load_catalog()
    recipe_id, reason = select_recipe(content_scope, perf_map, catalog)
    stale_check, stale_reason = is_map_stale(perf_map)
    return {
        "recipe_id": recipe_id,
        "reason": reason,
        "content_scope": content_scope,
        "map_status": f"STALE:{stale_reason}" if stale_check else "CURRENT",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OPENHTPC C3 CINÉMA AUTO Selection Engine"
    )
    parser.add_argument(
        "--scope", default="DVD_PAL_FILM",
        help="Content scope to query (default: DVD_PAL_FILM)"
    )
    parser.add_argument(
        "--source-class", dest="scope",
        help="Alias for --scope (content scope to query)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON"
    )
    args = parser.parse_args()

    result = query(args.scope)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"CINÉMA AUTO: scope={result['content_scope']} → {result['recipe_id']} ({result['reason']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
