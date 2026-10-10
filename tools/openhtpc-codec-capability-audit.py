#!/usr/bin/env python3
"""Read-only audit of duplicated OPENHTPC codec capability views."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

CODECS = ("mpeg2", "h264", "hevc", "hevc_main10", "vp9", "av1")


def normalized(value: Any) -> dict[str, bool] | None:
    if not isinstance(value, dict):
        return None
    return {codec: bool(value.get(codec, False)) for codec in CODECS}


def codec_views(profile: dict[str, Any]) -> dict[str, dict[str, bool]]:
    views: dict[str, dict[str, bool]] = {}
    media = profile.get("media_stack")
    observed = media.get("observed_capabilities") if isinstance(media, dict) else None
    value = normalized(observed.get("vaapi_decode") if isinstance(observed, dict) else None)
    if value is not None:
        views["media_stack.observed_capabilities.vaapi_decode"] = value
    detected = profile.get("detected")
    details = detected.get("gpu_details") if isinstance(detected, dict) else None
    if isinstance(details, list):
        for index, gpu in enumerate(details):
            value = normalized(gpu.get("vaapi_decode") if isinstance(gpu, dict) else None)
            if value is not None:
                views[f"detected.gpu_details[{index}].vaapi_decode"] = value
    topology = profile.get("gpu_topology")
    if isinstance(topology, dict):
        for role in ("display_gpu", "processing_gpu"):
            gpu = topology.get(role)
            value = normalized(gpu.get("vaapi_decode") if isinstance(gpu, dict) else None)
            if value is not None:
                views[f"gpu_topology.{role}.vaapi_decode"] = value
        for index, gpu in enumerate(topology.get("gpus", []) if isinstance(topology.get("gpus"), list) else []):
            value = normalized(gpu.get("vaapi_decode") if isinstance(gpu, dict) else None)
            if value is not None:
                views[f"gpu_topology.gpus[{index}].vaapi_decode"] = value
    return views


def _gpu_identity(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("pci_slot") or value.get("pci_address")
    return str(raw).lower() if raw else None


def consistency(profile: dict[str, Any]) -> dict[str, Any]:
    views = codec_views(profile)
    topology = profile.get("gpu_topology") if isinstance(profile.get("gpu_topology"), dict) else {}
    detected = profile.get("detected") if isinstance(profile.get("detected"), dict) else {}
    detected_rows = detected.get("gpu_details", []) if isinstance(detected.get("gpu_details"), list) else []
    topology_rows = topology.get("gpus", []) if isinstance(topology.get("gpus"), list) else []

    def rows_with_views(rows: list[Any]) -> list[tuple[str | None, dict[str, bool], int]]:
        result = []
        for index, gpu in enumerate(rows):
            value = normalized(gpu.get("vaapi_decode") if isinstance(gpu, dict) else None)
            if value is not None:
                result.append((_gpu_identity(gpu), value, index))
        return result

    detected_views = rows_with_views(detected_rows)
    topology_views = rows_with_views(topology_rows)
    reference_views = detected_views or topology_views
    contradictions: list[str] = []
    machine = views.get("media_stack.observed_capabilities.vaapi_decode")

    if reference_views and machine is not None:
        union = {codec: any(value[codec] for _, value, _ in reference_views) for codec in CODECS}
        if machine != union:
            contradictions.append("machine_union")

        reference_by_id = {gpu_id: value for gpu_id, value, _ in reference_views if gpu_id}
        for index, gpu in enumerate(topology_rows):
            identity = _gpu_identity(gpu)
            value = normalized(gpu.get("vaapi_decode") if isinstance(gpu, dict) else None)
            if identity in reference_by_id and value is not None and value != reference_by_id[identity]:
                contradictions.append(f"gpus[{index}]")
        for role in ("display_gpu", "processing_gpu"):
            role_gpu = topology.get(role)
            role_view = normalized(role_gpu.get("vaapi_decode") if isinstance(role_gpu, dict) else None)
            identity = _gpu_identity(role_gpu)
            if identity in reference_by_id and role_view is not None and role_view != reference_by_id[identity]:
                contradictions.append(role)
        status = "CONTRADICTION" if contradictions else "PASS"
    else:
        distinct = {tuple(value.items()) for value in views.values()}
        status = "UNKNOWN" if not views else "PASS" if len(distinct) == 1 else "CONTRADICTION"
    return {"status": status, "views": views, "contradictions": contradictions}


def transition(before: dict[str, bool], after: dict[str, bool]) -> dict[str, Any]:
    old, new = normalized(before) or {}, normalized(after) or {}
    gained = [codec for codec in CODECS if not old.get(codec, False) and new.get(codec, False)]
    lost = [codec for codec in CODECS if old.get(codec, False) and not new.get(codec, False)]
    return {
        "classification": "CAPABILITY_REGRESSION" if lost else "CAPABILITY_GAIN" if gained else "NO_CHANGE",
        "gained": gained,
        "lost": lost,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=pathlib.Path)
    parser.add_argument("--before", type=pathlib.Path)
    parser.add_argument("--boolean", action="store_true")
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        result: dict[str, Any] = {"capability_consistency": consistency(profile)}
        if args.before:
            previous = json.loads(args.before.read_text(encoding="utf-8"))
            old_views, new_views = codec_views(previous), codec_views(profile)
            old = old_views.get("media_stack.observed_capabilities.vaapi_decode")
            new = new_views.get("media_stack.observed_capabilities.vaapi_decode")
            result["media_stack_transition"] = transition(old or {}, new or {})
    except (OSError, ValueError) as error:
        print(f"codec capability audit failed: {error}", file=sys.stderr)
        return 2
    if args.boolean:
        status = result["capability_consistency"]["status"]
        print(f"CONSISTENT = {'True' if status == 'PASS' else 'False' if status == 'CONTRADICTION' else 'Unknown'}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["capability_consistency"]["status"] == "CONTRADICTION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
