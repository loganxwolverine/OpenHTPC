from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "payload/openhtpc-runtime-generator.py"
SPEC = importlib.util.spec_from_file_location("rc2_runtime_generator", GENERATOR_PATH)
GENERATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(GENERATOR)

OPTIONS = (
    "vo", "gpu-api", "hwdec", "vaapi-device", "include", "scale", "dscale",
    "cscale", "dither", "dither-depth", "scaler-resizes-only",
    "correct-downscaling", "linear-downscaling", "sigmoid-upscaling",
    "target-colorspace-hint", "gamut-mapping-mode",
)


def passport(vendor: str, *, offload: bool = False, backend: bool = True) -> dict:
    processing = {
        "vendor": vendor,
        "pci_slot": "0000:01:00.0",
        "render_node": "/dev/dri/renderD128",
    }
    display = dict(processing)
    if offload:
        display["pci_slot"] = "0000:02:00.0"
    return {
        "schema": 1,
        "generator": {"name": "OPENHTPC Builder", "version": "4.0.0"},
        "gpu_topology": {
            "display_gpu": display,
            "processing_gpu": processing,
            "offload_required": offload,
            "offload_validated": False,
        },
        "video_backend": {
            "vendor": vendor,
            "status": "observed" if backend else "proposed",
            "decode_api": "vaapi" if backend else "pending",
            "render_api": "vulkan" if backend else "pending",
            "render_node": processing["render_node"],
        },
    }


def generate(value: dict) -> tuple[dict, str | None, RuntimeError | None]:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw)
        profile = root / "profile.json"
        pure = root / "pure.conf"
        reference = root / "reference.conf"
        options = root / "options"
        values = root / "values"
        version = root / "version.json"
        profile.write_text(json.dumps(value), encoding="utf-8")
        reference_values = {
            "scale": "spline36", "dscale": "mitchell", "cscale": "spline36",
            "dither": "fruit", "dither-depth": "auto",
            "target-colorspace-hint": "auto", "gamut-mapping-mode": "auto",
        }
        options.write_text("".join(
            f" --{name} String {reference_values.get(name, 'available')}\n"
            for name in OPTIONS
        ), encoding="utf-8")
        values.write_text("gpu-next vulkan vaapi\n", encoding="utf-8")
        version.write_text(json.dumps({"version": "test", "build_id": "test"}), encoding="utf-8")
        failure = None
        try:
            GENERATOR.generate(profile, pure, reference, options, values, version)
        except RuntimeError as error:
            failure = error
        return json.loads(profile.read_text()), pure.read_text() if pure.exists() else None, failure


class Rc2QualifiedGpuRuntimeCharacterization(unittest.TestCase):
    EXPECTED_PURE = (
        "# OPENHTPC runtime test / test\n"
        "# OPENHTPC Build 4 — profil PURE isolé\n"
        "# Générée depuis profile.json ; ne pas copier dans ~/.config/mpv/mpv.conf\n"
        "vo=gpu-next\n"
        "gpu-api=vulkan\n"
        "hwdec=vaapi\n"
        "vaapi-device=/dev/dri/renderD128\n"
    )

    def test_intel_single_gpu_runtime_is_exactly_preserved(self):
        result, pure, failure = generate(passport("intel"))
        self.assertIsNone(failure)
        self.assertEqual(result["runtime"]["display_path"], "direct")
        self.assertEqual(pure, self.EXPECTED_PURE)

    def test_amd_single_gpu_runtime_is_exactly_preserved(self):
        result, pure, failure = generate(passport("amd"))
        self.assertIsNone(failure)
        self.assertEqual(result["runtime"]["display_path"], "direct")
        self.assertEqual(pure, self.EXPECTED_PURE)

    def test_unqualified_multi_gpu_path_remains_blocked(self):
        result, pure, failure = generate(passport("amd", offload=True))
        self.assertIsNotNone(failure)
        self.assertEqual(result["runtime"]["status"], "pending")
        self.assertEqual(result["runtime"]["display_path"], "offload_pending")
        self.assertIsNone(pure)

    def test_invalid_backend_never_generates_a_configuration(self):
        result, pure, failure = generate(passport("amd", backend=False))
        self.assertIsNotNone(failure)
        self.assertEqual(result["runtime"]["status"], "pending")
        self.assertFalse(result["mpv_configuration_generated"])
        self.assertIsNone(pure)


if __name__ == "__main__":
    unittest.main()
