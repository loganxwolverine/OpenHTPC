#!/usr/bin/env python3
"""OPENHTPC Adaptive Read-Ahead & Playback Cache Policy Engine.

Evaluates host memory headroom and media source characteristics at playback launch
to synthesize generic, deterministic, hardware-agnostic read-ahead parameters for MPV.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

POLICY_VERSION = "1.1-c0-dev1"

VALID_SOURCES = ("OPTICAL", "NETWORK", "LOCAL_ROTATIONAL", "LOCAL_FAST", "UNKNOWN")

SOURCE_DEFAULTS = {
    "OPTICAL": {
        "target_seconds": 12.0,
        "max_ceiling": 256 * 1024 * 1024,  # 256 MiB
        "min_floor": 64 * 1024 * 1024,     # 64 MiB
        "cache_fraction": 0.05,            # 5% of safe pool
        "backward_ratio": 0.25,
    },
    "NETWORK": {
        "target_seconds": 30.0,
        "max_ceiling": 512 * 1024 * 1024,  # 512 MiB
        "min_floor": 64 * 1024 * 1024,     # 64 MiB
        "cache_fraction": 0.08,
        "backward_ratio": 0.25,
    },
    "LOCAL_ROTATIONAL": {
        "target_seconds": 8.0,
        "max_ceiling": 128 * 1024 * 1024,  # 128 MiB
        "min_floor": 32 * 1024 * 1024,     # 32 MiB
        "cache_fraction": 0.03,
        "backward_ratio": 0.25,
    },
    "LOCAL_FAST": {
        "target_seconds": 2.0,
        "max_ceiling": 64 * 1024 * 1024,   # 64 MiB
        "min_floor": 16 * 1024 * 1024,     # 16 MiB
        "cache_fraction": 0.02,
        "backward_ratio": 0.25,
    },
    "UNKNOWN": {
        "target_seconds": 5.0,
        "max_ceiling": 64 * 1024 * 1024,   # 64 MiB
        "min_floor": 32 * 1024 * 1024,     # 32 MiB
        "cache_fraction": 0.03,
        "backward_ratio": 0.25,
    },
}


def read_system_memory() -> tuple[int | None, int | None]:
    """Safely and lightweightly read (MemTotal, MemAvailable) in bytes from /proc/meminfo."""
    mem_total: int | None = None
    mem_available: int | None = None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        mem_total = int(parts[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        mem_available = int(parts[1]) * 1024
                if mem_total is not None and mem_available is not None:
                    break
    except OSError:
        pass
    return mem_total, mem_available


PROBE_DEFAULT = object()


def compute_readahead_policy(
    source_class: str = "OPTICAL",
    total_ram_bytes: Any = PROBE_DEFAULT,
    available_ram_bytes: Any = PROBE_DEFAULT,
) -> dict[str, Any]:
    """Calculate deterministic, generic read-ahead and cache configuration for MPV."""
    norm_source = str(source_class).strip().upper()
    if norm_source not in VALID_SOURCES:
        norm_source = "UNKNOWN"

    sys_total, sys_avail = read_system_memory()
    if total_ram_bytes is PROBE_DEFAULT:
        total_ram_bytes = sys_total
    if available_ram_bytes is PROBE_DEFAULT:
        available_ram_bytes = sys_avail


    cfg = SOURCE_DEFAULTS[norm_source]
    base_target = cfg["target_seconds"]
    max_ceiling = cfg["max_ceiling"]
    min_floor = cfg["min_floor"]
    cache_fraction = cfg["cache_fraction"]
    backward_ratio = cfg["backward_ratio"]

    # Minimum system reserve: at least 2 GiB or 25% of total RAM
    if total_ram_bytes is not None and total_ram_bytes > 0:
        system_reserve = max(2 * 1024 * 1024 * 1024, int(total_ram_bytes * 0.25))
    else:
        system_reserve = 2 * 1024 * 1024 * 1024

    memory_pressure = False
    safe_pool = 0

    if available_ram_bytes is None:
        memory_pressure = True
        reason = "UNKNOWN_AVAILABLE_MEMORY_FALLBACK"
        max_bytes = min(max_ceiling, 64 * 1024 * 1024)
        back_bytes = min(max_bytes // 4, 16 * 1024 * 1024)
        target_seconds = min(base_target, 5.0)
    elif available_ram_bytes < 512 * 1024 * 1024:
        memory_pressure = True
        reason = "CRITICAL_LOW_MEMORY_FALLBACK"
        max_bytes = 32 * 1024 * 1024
        back_bytes = 8 * 1024 * 1024
        target_seconds = 2.0
    elif available_ram_bytes < system_reserve:
        memory_pressure = True
        reason = "CONSERVATIVE_MEMORY_PRESSURE_BUDGET"
        safe_pool = max(0, available_ram_bytes - 512 * 1024 * 1024)
        budget = int(safe_pool * 0.10)
        max_bytes = max(32 * 1024 * 1024, min(64 * 1024 * 1024, budget))
        back_bytes = max(8 * 1024 * 1024, max_bytes // 4)
        target_seconds = min(base_target, 4.0)
    else:
        reason = "ADAPTIVE_MEMORY_BUDGET_PASS"
        safe_pool = available_ram_bytes - system_reserve
        budget = int(safe_pool * cache_fraction)
        max_bytes = max(min_floor, min(max_ceiling, budget))
        back_bytes = max(8 * 1024 * 1024, int(max_bytes * backward_ratio))
        target_seconds = base_target

    startup_prefill = {
        "mode": "NONE",
        "pause_initial": False,
        "pause_wait_seconds": 1.0,
    }

    mpv_options = [
        "--cache=yes",
        f"--demuxer-readahead-secs={target_seconds:.1f}",
        f"--demuxer-max-bytes={max_bytes}",
        f"--demuxer-max-back-bytes={back_bytes}",
        "--demuxer-thread=yes",
        "--cache-pause=yes",
        "--cache-pause-initial=no",
        "--cache-pause-wait=1",
        "--cache-on-disk=no",
    ]

    return {
        "schema": 1,
        "status": "PASS",
        "policy_version": POLICY_VERSION,
        "source_class": norm_source,
        "enabled": True,
        "target_readahead_seconds": target_seconds,
        "maximum_cache_bytes": max_bytes,
        "backward_cache_bytes": back_bytes,
        "startup_prefill": startup_prefill,
        "system_reserve_bytes": system_reserve,
        "memory_pressure": memory_pressure,
        "reason": reason,
        "memory_budget": {
            "installed_ram_bytes": total_ram_bytes,
            "available_ram_bytes": available_ram_bytes,
            "system_reserve_bytes": system_reserve,
            "safe_available_bytes": safe_pool,
            "cache_fraction": cache_fraction,
            "pressure_detected": memory_pressure,
        },
        "mpv_options": mpv_options,
        "metrics": {
            "demuxer_thread": True,
            "forward_cache_target_secs": target_seconds,
            "max_cache_mb": round(max_bytes / (1024 * 1024), 2),
            "back_cache_mb": round(back_bytes / (1024 * 1024), 2),
        },
    }


def format_human(report: dict[str, Any]) -> str:
    """Format read-ahead policy report into human-readable text."""
    mb = report["memory_budget"]
    tot_str = f"{mb['installed_ram_bytes'] // (1024 * 1024)} MiB" if mb["installed_ram_bytes"] else "Inconnue"
    avail_str = f"{mb['available_ram_bytes'] // (1024 * 1024)} MiB" if mb["available_ram_bytes"] else "Inconnue"
    res_str = f"{mb['system_reserve_bytes'] // (1024 * 1024)} MiB"
    max_mb = report["maximum_cache_bytes"] // (1024 * 1024)
    back_mb = report["backward_cache_bytes"] // (1024 * 1024)
    prefill = report["startup_prefill"]
    prefill_str = f"{prefill['mode']} (pause_initial={prefill['pause_initial']})"

    lines = [
        f"=== OPENHTPC Adaptive Read-Ahead Engine ({report['policy_version']}) ===",
        f"État :              {'ACTIF' if report['enabled'] else 'INACTIF'}",
        f"Source :            {report['source_class']}",
        f"Cible tampon :      {report['target_readahead_seconds']:.1f} s",
        f"Plafond cache :     {max_mb} MiB (avant: {max_mb} MiB, arrière: {back_mb} MiB)",
        f"Mémoire système :   Totale: {tot_str} | Disponible: {avail_str} | Réserve: {res_str}",
        f"Pression mémoire :  {'OUI' if report['memory_pressure'] else 'NON'}",
        f"Pré-remplissage :   {prefill_str}",
        f"Motif :             {report['reason']}",
        "",
        "Options MPV générées :",
        "  " + " ".join(report["mpv_options"]),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPENHTPC Adaptive Read-Ahead Policy Engine")
    parser.add_argument("--source", default="OPTICAL", choices=VALID_SOURCES, help="Media source classification")
    parser.add_argument("--json", action="store_true", help="Emit technical JSON representation")
    parser.add_argument("--args-only", action="store_true", help="Emit space-separated MPV CLI arguments")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    policy = compute_readahead_policy(source_class=args.source)

    if args.json:
        print(json.dumps(policy, ensure_ascii=False, indent=2))
    elif args.args_only:
        print(" ".join(policy["mpv_options"]))
    else:
        print(format_human(policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
