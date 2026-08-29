from __future__ import annotations

import json
import pathlib
import importlib.util
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILDER = ROOT / "payload/openhtpc-builder.sh"
GENERATOR = ROOT / "payload/openhtpc-runtime-generator.py"
SPEC = importlib.util.spec_from_file_location("runtime_generator", GENERATOR)
RUNTIME = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(RUNTIME)

REQUIRED = (
    "vo", "gpu-api", "hwdec", "vaapi-device", "include", "scale", "dscale",
    "cscale", "dither", "dither-depth", "scaler-resizes-only",
    "correct-downscaling", "linear-downscaling", "sigmoid-upscaling",
    "target-colorspace-hint", "gamut-mapping-mode",
)


def profile(vendor="amd", *, vulkan=True, render_node=True, offload=False, observed=True):
    node = "/dev/dri/renderD-test" if render_node else None
    gpu = {"vendor":vendor, "pci_slot":"0000:01:00.0", "render_node":node,
           "vulkan_device":{"name":"hardware", "type":"PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU"} if vulkan else None}
    return {"schema":1, "generator":{"name":"OPENHTPC Builder", "version":"4.0.0"},
        "gpu_topology":{"display_gpu":gpu, "processing_gpu":gpu,
                        "offload_required":offload, "offload_validated":False},
        "video_backend":{"vendor":vendor, "status":"observed" if observed and vulkan and render_node else "proposed",
                         "decode_api":"vaapi" if render_node else None,
                         "render_api":"vulkan" if vulkan else None, "render_node":node},
        "mpv_blueprint":{},
    }


def execute(value: dict) -> tuple[dict, str | None, RuntimeError | None]:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw); profile_path = root / "profile.json"
        pure = root / "pure.conf"; reference = root / "reference.conf"
        options = root / "options.txt"; values = root / "values.txt"
        profile_path.write_text(json.dumps(value), encoding="utf-8")
        option_lines = []
        reference_values = {"scale":"spline36", "dscale":"mitchell", "cscale":"spline36",
                            "dither":"fruit", "dither-depth":"auto",
                            "target-colorspace-hint":"auto", "gamut-mapping-mode":"auto"}
        for name in REQUIRED: option_lines.append(f" --{name} String {reference_values.get(name, 'available')}")
        options.write_text("\n".join(option_lines) + "\n", encoding="utf-8")
        values.write_text("gpu-next vulkan vaapi\n", encoding="utf-8")
        version = root / "version.json"
        version.write_text(json.dumps({"version":"test", "build_id":"test-build"}), encoding="utf-8")
        failure = None
        try:
            RUNTIME.generate(profile_path, pure, reference, options, values, version)
        except RuntimeError as exc:
            failure = exc
        updated = json.loads(profile_path.read_text(encoding="utf-8"))
        return updated, pure.read_text(encoding="utf-8") if pure.is_file() else None, failure


class AmdBaseRuntimeP0(unittest.TestCase):
    def test_intel_known_good_generation_is_unchanged(self):
        result, pure, failure = execute(profile("intel")); self.assertIsNone(failure)
        self.assertEqual(result["runtime"]["status"], "ready")
        self.assertEqual(result["runtime_profiles"]["profiles"]["PURE"]["generation_status"], "generated")
        self.assertIn("gpu-api=vulkan", pure)

    def test_amd_observed_direct_path_generates_candidate(self):
        result, pure, failure = execute(profile("amd")); self.assertIsNone(failure)
        self.assertEqual(result["runtime_profiles"]["available"], ["PURE", "REFERENCE"])
        self.assertEqual(result["runtime_profiles"]["profiles"]["PURE"]["validation_status"], "validation_pending")
        self.assertIn("hwdec=vaapi", pure)
        self.assertIn("vaapi-device=/dev/dri/renderD-test", pure)

    def test_amd_without_hardware_vulkan_is_blocked(self):
        result, pure, failure = execute(profile("amd", vulkan=False))
        self.assertRegex(str(failure), "RUNTIME_REGENERATION_NOT_READY")
        self.assertEqual(result["runtime"]["status"], "pending"); self.assertIsNone(pure)

    def test_amd_without_render_node_is_blocked(self):
        result, pure, failure = execute(profile("amd", render_node=False))
        self.assertRegex(str(failure), "RUNTIME_REGENERATION_NOT_READY")
        self.assertEqual(result["runtime"]["status"], "pending"); self.assertIsNone(pure)

    def test_llvmpipe_only_is_blocked_by_hardware_selection(self):
        value = profile("unknown", vulkan=False); value["gpu_topology"]["processing_gpu"] = None
        result, pure, failure = execute(value)
        self.assertRegex(str(failure), "RUNTIME_REGENERATION_NOT_READY")
        self.assertEqual(result["runtime"]["reason"], "Aucun GPU de traitement fiable n’a été retenu."); self.assertIsNone(pure)

    def test_unvalidated_offload_remains_blocked(self):
        value = profile("amd", offload=True)
        value["gpu_topology"]["display_gpu"] = {**value["gpu_topology"]["display_gpu"], "pci_slot":"0000:02:00.0"}
        result, pure, failure = execute(value)
        self.assertRegex(str(failure), "RUNTIME_REGENERATION_NOT_READY")
        self.assertEqual(result["runtime"]["reason"], "Chemin multi-GPU à valider."); self.assertIsNone(pure)

    def test_equivalent_unknown_vendor_uses_same_capability_decision(self):
        result, pure, failure = execute(profile("future-vendor")); self.assertIsNone(failure)
        self.assertEqual(result["runtime"]["status"], "ready"); self.assertIsNotNone(pure)

    def test_vendor_veto_is_absent_but_capability_gates_remain(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertNotIn('backend.get("vendor") != "intel"', source)
        for marker in ('backend.get("status") != "observed"', 'decode_api not in {"vaapi", "nvdec"}',
                       'backend.get("render_api") != "vulkan"', 'not processing.get("render_node")',
                       'display_path == "offload_pending"'):
            self.assertIn(marker, source)

    def test_runtime_keeps_mpv_native_software_fallback_policy(self):
        result, pure, failure = execute(profile("amd")); self.assertIsNone(failure)
        self.assertEqual(result["runtime"]["status"], "ready")
        self.assertIn("hwdec=vaapi", pure)
        self.assertNotIn("hwdec-codecs=", pure)
        self.assertNotIn("hwdec-software-fallback=no", pure)


if __name__ == "__main__": unittest.main()
