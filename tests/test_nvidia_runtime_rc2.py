from __future__ import annotations
import importlib.util,json,pathlib,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("nv_runtime",ROOT/"payload/openhtpc-runtime-generator.py")
RUNTIME=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUNTIME)
CORE_SPEC=importlib.util.spec_from_file_location("nv_core",ROOT/"payload/openhtpc-core.py")
CORE=importlib.util.module_from_spec(CORE_SPEC);CORE_SPEC.loader.exec_module(CORE)
COMMON=("vo","gpu-api","hwdec","include","scale","dscale","cscale","dither","dither-depth","scaler-resizes-only","correct-downscaling","linear-downscaling","sigmoid-upscaling","target-colorspace-hint","gamut-mapping-mode")

def execute(api,values,include_vaapi_option=True,offload=False):
 with tempfile.TemporaryDirectory() as raw:
  root=pathlib.Path(raw);gpu={"pci_slot":"0000:01:00.0","render_node":"/dev/dri/renderD128"};display=dict(gpu)
  if offload:display["pci_slot"]="0000:00:02.0"
  profile={"schema":1,"generator":{"name":"OPENHTPC Builder","version":"4"},"gpu_topology":{"display_gpu":display,"processing_gpu":gpu,"offload_required":offload},"video_backend":{"status":"observed","decode_api":api,"render_api":"vulkan","render_node":gpu["render_node"]}}
  pp=root/"profile";pure=root/"pure";reference=root/"reference";opts=root/"opts";vals=root/"vals";version=root/"version"
  pp.write_text(json.dumps(profile));names=COMMON+(("vaapi-device",) if include_vaapi_option else ())
  rv={"scale":"spline36","dscale":"mitchell","cscale":"spline36","dither":"fruit","dither-depth":"auto","target-colorspace-hint":"auto","gamut-mapping-mode":"auto"}
  opts.write_text("".join(f" --{n} String {rv.get(n,'available')}\n" for n in names));vals.write_text(values);version.write_text('{"version":"test","build_id":"test"}')
  error=None
  try:RUNTIME.generate(pp,pure,reference,opts,vals,version)
  except RuntimeError as exc:error=exc
  return json.loads(pp.read_text()),pure.read_text() if pure.exists() else None,reference.read_text() if reference.exists() else None,error

class NvidiaRuntime(unittest.TestCase):
 def test_nvdec_pure_has_no_vaapi_device(self):
  result,pure,_,error=execute("nvdec","gpu-next vulkan nvdec\n",False);self.assertIsNone(error);self.assertIn("hwdec=nvdec\n",pure);self.assertNotIn("vaapi-device",pure);self.assertEqual(result["runtime"]["status"],"ready")
 def test_nvdec_reference_keeps_historical_scaling(self):
  _,_,reference,error=execute("nvdec","gpu-next vulkan nvdec\n",False);self.assertIsNone(error);self.assertIn("hwdec=nvdec",reference);self.assertIn("scale=spline36",reference);self.assertIn("gamut-mapping-mode=auto",reference)
 def test_nvdec_does_not_require_vaapi_value(self):self.assertIsNone(execute("nvdec","gpu-next vulkan nvdec\n",False)[3])
 def test_nvdec_value_is_required(self):self.assertIsNotNone(execute("nvdec","gpu-next vulkan vaapi\n",False)[3])
 def test_vaapi_option_and_value_remain_required(self):
  self.assertIsNotNone(execute("vaapi","gpu-next vulkan vaapi\n",False)[3]);self.assertIsNotNone(execute("vaapi","gpu-next vulkan nvdec\n",True)[3])
 def test_unqualified_offload_remains_blocked(self):self.assertIsNotNone(execute("nvdec","gpu-next vulkan nvdec\n",False,True)[3])
 def test_doctor_generated_runtime_passes_for_current_direct_nvdec(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);config=home/".config/openhtpc";runtime_dir=config/"runtime";runtime_dir.mkdir(parents=True);pure=runtime_dir/"pure.conf";pure.write_text("hwdec=nvdec\n")
   source={"hardware_fingerprint":"h","runtime_fingerprint":"r","generated_at":"now"}
   profile={"generator":{"name":"OPENHTPC Builder"},"capability_source":source,"runtime":{"status":"ready","generation_provenance":{"capability_source":source}},"runtime_profiles":{"profiles":{"PURE":{"config_path":str(pure)}}}}
   (config/"profile.json").write_text(json.dumps(profile));(runtime_dir/"capabilities.json").write_text(json.dumps({"hardware_fingerprint":"h","runtime_fingerprint":"r"}))
   state=CORE.capability_state(home,home/"install");self.assertTrue(state["VIDEO_RUNTIME_READY"]);self.assertEqual(state["VIDEO_RUNTIME_PROVENANCE"],"CURRENT")

if __name__=="__main__":unittest.main()
