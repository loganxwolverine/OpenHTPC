#!/usr/bin/env python3
"""Pure capability-driven GPU topology selection; performs no probes."""
from __future__ import annotations

from typing import Any


def usable(gpu: dict[str, Any]) -> bool:
    return bool(gpu.get("render_node") and gpu.get("vulkan_device") and
                (any(gpu.get("vaapi_decode", {}).values()) or any(gpu.get("nvdec_decode", {}).values())))


def select(gpus: list[dict[str, Any]]) -> dict[str, Any]:
    displays = [gpu for gpu in gpus if gpu.get("active") is True or gpu.get("display_connectors")]
    display = displays[0] if len(displays) == 1 else None
    valid = [gpu for gpu in gpus if usable(gpu)]
    processing = None
    confidence = "pending"
    if display in valid:
        processing, confidence = display, "high"
        reason = "GPU d’affichage avec décodage matériel et Vulkan observés ; chemin direct préféré."
    elif len(valid) == 1:
        processing = valid[0]
        confidence = "high" if processing.get("vulkan_device") and any(processing.get("vaapi_decode", {}).values()) else "medium"
        reason = "Seul GPU matériel avec render node et capacités observées."
    elif len(valid) > 1:
        ranked = sorted(valid, key=lambda item: item.get("selection_score", 0), reverse=True)
        margin = ranked[0].get("selection_score", 0) - ranked[1].get("selection_score", 0)
        if margin >= 2 and ranked[0].get("vulkan_device"):
            processing, confidence = ranked[0], "medium"
            reason = "Capacités VA-API/Vulkan observées supérieures aux autres GPU matériels."
        else:
            reason = "Plusieurs GPU matériels ont des capacités trop proches ou incomplètes."
    else:
        reason = "Aucun GPU matériel ne dispose d’une association complète mesurée."
    return {"display_gpu":display, "processing_gpu":processing,
            "offload_required": display.get("pci_slot") != processing.get("pci_slot") if display and processing else None,
            "reason":reason, "confidence":confidence, "display_candidates":len(displays)}
