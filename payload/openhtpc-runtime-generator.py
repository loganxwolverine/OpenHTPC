#!/usr/bin/env python3
"""Generate current OPENHTPC MPV runtime from an existing Hardware Passport."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile


def atomic_json(path: pathlib.Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def generate(profile_path: pathlib.Path, pure_path: pathlib.Path,
             reference_path: pathlib.Path, options_path: pathlib.Path,
             values_path: pathlib.Path, version_path: pathlib.Path) -> dict:
    options = options_path.read_text(encoding="utf-8", errors="replace")
    values = values_path.read_text(encoding="utf-8", errors="replace")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    version = json.loads(version_path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or profile.get("schema") != 1:
        raise RuntimeError("HARDWARE_PASSPORT_SCHEMA_UNSUPPORTED")
    if profile.get("generator", {}).get("name") != "OPENHTPC Builder":
        raise RuntimeError("HARDWARE_PASSPORT_INVALID")

    topology = profile["gpu_topology"]
    backend = profile["video_backend"]
    display = topology.get("display_gpu")
    processing = topology.get("processing_gpu")
    same_gpu = bool(display and processing and display.get("pci_slot") == processing.get("pci_slot"))
    if topology.get("offload_required") is True:
        display_path = "offload_pending"
    elif same_gpu and topology.get("offload_required") is False:
        display_path = "direct"
    else:
        display_path = "pending"

    required_options = (
        "vo", "gpu-api", "hwdec", "vaapi-device", "include", "scale", "dscale",
        "cscale", "dither", "dither-depth", "scaler-resizes-only",
        "correct-downscaling", "linear-downscaling", "sigmoid-upscaling",
        "target-colorspace-hint", "gamut-mapping-mode",
    )
    options_available = all(re.search(rf"^ --{re.escape(name)}\s", options, re.MULTILINE) for name in required_options)
    values_available = all(token in values for token in ("gpu-next", "vulkan", "vaapi"))
    reference_values_available = all(
        re.search(rf"^ --{name}\s+.*\b{re.escape(value)}\b", options, re.MULTILINE)
        for name, value in (
            ("scale", "spline36"), ("dscale", "mitchell"), ("cscale", "spline36"),
            ("dither", "fruit"), ("dither-depth", "auto"),
            ("target-colorspace-hint", "auto"), ("gamut-mapping-mode", "auto"),
        )
    )

    reason = None
    ready = True
    if not processing:
        ready, reason = False, "Aucun GPU de traitement fiable n’a été retenu."
    elif display_path == "offload_pending":
        ready, reason = False, "Chemin multi-GPU à valider."
    elif display_path != "direct":
        ready, reason = False, "Le chemin entre affichage et traitement reste à valider."
    elif backend.get("status") != "observed":
        ready, reason = False, "Le backend vidéo n’est pas observé."
    elif backend.get("decode_api") != "vaapi" or backend.get("render_api") != "vulkan":
        ready, reason = False, "VA-API et Vulkan ne sont pas tous deux observés."
    elif not processing.get("render_node"):
        ready, reason = False, "Aucun render node fiable n’est associé au GPU de traitement."
    elif not options_available or not values_available or not reference_values_available:
        ready, reason = False, "Le MPV installé n’expose pas toutes les options requises."

    pure_path.parent.mkdir(parents=True, exist_ok=True)
    provenance = f"# OPENHTPC runtime {version['version']} / {version['build_id']}\n"
    if ready:
        pure_content = (
            provenance + "# OPENHTPC Build 4 — profil PURE isolé\n"
            "# Générée depuis profile.json ; ne pas copier dans ~/.config/mpv/mpv.conf\n"
            "vo=gpu-next\ngpu-api=vulkan\nhwdec=vaapi\n"
            f"vaapi-device={processing['render_node']}\n"
        )
        reference_content = (
            provenance + "# OPENHTPC Build 4 — profil REFERENCE isolé\n"
            "# Fonctions natives MPV/libplacebo uniquement ; validation visuelle requise\n"
            "vo=gpu-next\ngpu-api=vulkan\nhwdec=vaapi\n"
            f"vaapi-device={processing['render_node']}\n"
            "scale=spline36\ndscale=mitchell\ncscale=spline36\ndither=fruit\n"
            "dither-depth=auto\nscaler-resizes-only=yes\ncorrect-downscaling=yes\n"
            "linear-downscaling=yes\nsigmoid-upscaling=yes\n"
            "target-colorspace-hint=auto\ngamut-mapping-mode=auto\n"
        )
        for path, content in ((pure_path, pure_content), (reference_path, reference_content)):
            temporary = path.with_suffix(".conf.tmp")
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
    else:
        pure_path.unlink(missing_ok=True)
        reference_path.unlink(missing_ok=True)

    last_video = profile.get("playback_validation", {}).get("last_test", {}).get("video", {})
    pure_validated = bool(ready and last_video.get("status") == "validated"
                          and last_video.get("hwdec_observed") == backend.get("decode_api")
                          and last_video.get("renderer_observed") == backend.get("render_api")
                          and last_video.get("vo_observed") == "gpu-next")
    profile["runtime_profiles"] = {
        "available": ["PURE", "REFERENCE"] if ready else [], "enhanced": "pending",
        "default": "PURE", "selection_scope": "playback", "selected": None,
        "profiles": {
            "PURE": {"description": "Chaîne minimale fidèle sans traitement esthétique",
                     "generation_status": "generated" if ready else "pending",
                     "validation_status": "validated" if pure_validated else "validation_pending",
                     "config_path": str(pure_path) if ready else None},
            "REFERENCE": {"description": "Rendu fidèle avec scaling, chroma et dithering natifs MPV/libplacebo",
                          "generation_status": "generated" if ready else "pending",
                          "validation_status": "validation_pending",
                          "config_path": str(reference_path) if ready else None},
            "ENHANCED": {"description": "Profil futur", "generation_status": "pending",
                         "validation_status": "pending", "config_path": None},
        },
    }
    profile["runtime"] = {
        "status": "ready" if ready else "pending", "config_path": str(pure_path) if ready else None,
        "backend": backend, "display_path": display_path,
        "reason": "Configuration candidate générée ; validation de lecture requise." if ready else reason,
        "configuration_generated": ready, "configuration_applied_globally": False,
        "playback_validated": False,
        "mpv_options_verified": options_available and values_available and reference_values_available,
        "generation_provenance": {"version": version["version"], "build_id": version["build_id"]},
    }
    profile["mpv_configuration_generated"] = ready
    atomic_json(profile_path, profile)
    if not ready:
        raise RuntimeError(f"RUNTIME_REGENERATION_NOT_READY: {reason}")
    return profile


def main() -> int:
    if len(sys.argv) != 7:
        print("usage: openhtpc-runtime-generator.py PROFILE PURE REFERENCE OPTIONS VALUES VERSION", file=sys.stderr)
        return 2
    generate(*(pathlib.Path(value) for value in sys.argv[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
