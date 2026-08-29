from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nvdec_capabilities", ROOT / "payload/openhtpc-capabilities.py")
CAPS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(CAPS)


class NvidiaNvdecCapabilityDiscovery(unittest.TestCase):
    GPU = {"pci_address":"0000:01:00.0", "vendor_id":"10de", "device_id":"2507", "kernel_driver":"nvidia"}
    VULKAN = [{"vendor_id":"0x10de", "device_id":"0x2507", "driver_name":"NVIDIA"}]
    SMI = {"0000:01:00.0":{"name":"NVIDIA GeForce RTX 3050", "driver_version":"610.57.04"}}
    DECODERS = {"mpeg2_cuvid", "h264_cuvid", "hevc_cuvid", "vp9_cuvid", "av1_cuvid"}

    def test_machine_readable_nvidia_smi_is_normalized_by_pci(self):
        parsed = CAPS.parse_nvidia_smi("00000000:01:00.0, NVIDIA GeForce RTX 3050, 610.57.04\n")
        self.assertEqual(parsed, self.SMI)

    def test_coherent_nvidia_stack_is_supported_but_never_validated(self):
        backend = CAPS.nvdec_backend(self.GPU, self.VULKAN, self.SMI, "nvdec\nnvdec-copy\n", self.DECODERS)
        self.assertEqual(backend["status"], "SUPPORTED")
        self.assertFalse(backend["validated"])
        self.assertTrue(all(backend["profiles"].values()))

    def test_nouveau_nvk_never_inherits_global_mpv_nvdec(self):
        gpu = {**self.GPU, "kernel_driver":"nouveau"}
        backend = CAPS.nvdec_backend(gpu, self.VULKAN, self.SMI, "nvdec", self.DECODERS)
        self.assertEqual(backend["status"], "UNSUPPORTED")
        self.assertFalse(any(backend["profiles"].values()))

    def test_mpv_without_nvdec_is_not_supported(self):
        backend = CAPS.nvdec_backend(self.GPU, self.VULKAN, self.SMI, "vaapi", self.DECODERS)
        self.assertEqual(backend["status"], "UNSUPPORTED")

    def test_global_nvdec_is_not_propagated_to_intel(self):
        intel = {"pci_address":"0000:00:02.0", "vendor_id":"8086", "device_id":"5912", "kernel_driver":"i915"}
        backend = CAPS.nvdec_backend(intel, self.VULKAN, self.SMI, "nvdec", self.DECODERS)
        self.assertEqual(backend["status"], "NOT_APPLICABLE")

    def test_nvdec_never_populates_legacy_vaapi_mirrors(self):
        snapshot = {"video_decode":{"codecs":{key:{"hardware_decode":{"status":"SUPPORTED"},"hardware_backends":["nvdec"]} for key in CAPS.CODECS}}}
        self.assertFalse(any(CAPS.profile_codec_observation(snapshot).values()))

    def test_successful_nvdec_playback_can_be_recorded_without_becoming_fabricated_validation(self):
        with tempfile.TemporaryDirectory() as raw:
            home=pathlib.Path(raw);snapshot=CAPS.snapshot_path(home);snapshot.parent.mkdir(parents=True)
            value={"schema":1,"probe_version":"x","generated_at":"x","hardware_fingerprint":"h","runtime_fingerprint":"r","hardware":{},"graphics":{"devices":[]},"display":{"outputs":[]},"video_decode":{},"audio":{},"optical":{},"media":{},"video_processing":{},"validation":{},"confidence":{}}
            snapshot.write_text(__import__("json").dumps(value));media=home/"fixture.mkv";media.write_bytes(b"fixture")
            runner=lambda argv,timeout:{"status":"OK","stdout":'{"streams":[{"codec_name":"h264","profile":"High","pix_fmt":"yuv420p","width":1920,"height":1080,"r_frame_rate":"24/1"}],"format":{"format_name":"matroska"}}',"stderr":""}
            record=CAPS.record_playback_validation(home,media,"nvdec",runner,"now")
            self.assertEqual(record["hardware_decode_backend"],"nvdec");self.assertEqual(record["hardware_fingerprint"],"h")


if __name__ == "__main__": unittest.main()
