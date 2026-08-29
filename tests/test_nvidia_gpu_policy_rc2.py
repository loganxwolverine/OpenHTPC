from __future__ import annotations
import importlib.util, pathlib, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("gpu_policy",ROOT/"payload/openhtpc-gpu-policy.py")
POLICY=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(POLICY)

def gpu(vendor,slot,display=False,decode="vaapi"):
    return {"vendor":vendor,"pci_slot":slot,"render_node":f"/dev/dri/{slot[-1]}","vulkan_device":{"name":vendor},
            "display_connectors":["card-HDMI-A-1"] if display else [],"active":display,
            "vaapi_decode":{"h264":decode=="vaapi"},"nvdec_decode":{"h264":decode=="nvdec"},
            "selection_score":10 if decode=="vaapi" else 3}

class NvidiaGpuPolicy(unittest.TestCase):
 def test_nvidia_only_direct(self):
  n=gpu("nvidia","0000:01:00.0",True,"nvdec");d=POLICY.select([n]);self.assertIs(d["display_gpu"],n);self.assertIs(d["processing_gpu"],n);self.assertFalse(d["offload_required"])
 def test_intel_nvidia_display_nvidia_prefers_direct_nvidia(self):
  i=gpu("intel","0000:00:02.0");n=gpu("nvidia","0000:01:00.0",True,"nvdec");self.assertIs(POLICY.select([i,n])["processing_gpu"],n)
 def test_intel_display_prefers_direct_intel(self):
  i=gpu("intel","0000:00:02.0",True);n=gpu("nvidia","0000:01:00.0",False,"nvdec");self.assertIs(POLICY.select([i,n])["processing_gpu"],i)
 def test_incapable_nvidia_display_requires_unqualified_offload(self):
  i=gpu("intel","0000:00:02.0");n=gpu("nvidia","0000:01:00.0",True,"none");d=POLICY.select([i,n]);self.assertIs(d["processing_gpu"],i);self.assertTrue(d["offload_required"])

if __name__=="__main__":unittest.main()
