from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="bd4c306d75a9d7a5fd7d63c7c79755cfc7561959"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
CORE=load("presentation_p2_core",PAYLOAD/"openhtpc-core.py");REGISTRY=load("presentation_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("presentation_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py");VIEW=load("presentation_p2_view",PAYLOAD/"openhtpc-disc-view.py")

def state(canonical,protection="UNKNOWN",**extra):return {"canonical_state":canonical,"protection":protection,**extra}

class Mapping(unittest.TestCase):
 def equivalent(self,value):
  core=CORE.core_optical_presentation_descriptor(value);plugin=PLUGIN.presentation_descriptor(value);self.assertEqual(plugin,core);self.assertTrue(CORE._valid_optical_presentation_descriptor(plugin));return plugin
 def test_valid_contract_and_no_disc(self):self.assertFalse(self.equivalent(state("DRIVE_PRESENT_NO_MEDIA"))["owned"])
 def test_dvd_claims_no_ownership(self):self.assertFalse(self.equivalent(state("DVD_VIDEO"))["owned"])
 def test_bluray(self):self.assertEqual(self.equivalent(state("BLURAY_VIDEO"))["badge_key"],"BLURAY")
 def test_bluray_family_unknown(self):
  value=self.equivalent(state("BLURAY_FAMILY"));self.assertEqual((value["presentation_key"],value["badge_key"]),("BLURAY_FAMILY","BLURAY"))
 def test_bluray_protection_independent(self):
  self.assertEqual(self.equivalent(state("BLURAY_VIDEO","PROTECTED")),self.equivalent(state("BLURAY_VIDEO","UNPROTECTED")))
 def test_uhd_protection_independent_and_exact_text(self):
  protected=self.equivalent(state("UHD_BLURAY_VIDEO","PROTECTED"));unprotected=self.equivalent(state("UHD_BLURAY_VIDEO","UNPROTECTED"))
  self.assertEqual(protected,unprotected);self.assertEqual((protected["badge_key"],protected["display_label"]),("UHD_BLURAY","ULTRA HD BLU-RAY 4K"))
 def test_unknown_protection_does_not_change_exact_badge(self):
  self.assertEqual(self.equivalent(state("BLURAY_VIDEO"))["badge_key"],"BLURAY");self.assertEqual(self.equivalent(state("UHD_BLURAY_VIDEO"))["badge_key"],"UHD_BLURAY")
 def test_noncanonical_heuristics_never_select_uhd(self):
  value=state("BLURAY_FAMILY",video_codec="HEVC",width=3840,height=2160,hdr=True,volume_label="UHD 4K",disc_title="UHD")
  self.assertEqual(self.equivalent(value)["badge_key"],"BLURAY")
 def test_eject_and_history_never_create_badge(self):
  value=state("DRIVE_PRESENT_NO_MEDIA",last_attempt="OPEN_SUCCESS");self.assertFalse(self.equivalent(value)["owned"])
 def test_malformed_and_unknown_keys_rejected(self):
  self.assertFalse(CORE._valid_optical_presentation_descriptor({"badge_key":"UHD_BLURAY"}))
  bad={**CORE.core_optical_presentation_descriptor(state("BLURAY_VIDEO")),"badge_key":"../../asset.png"};self.assertFalse(CORE._valid_optical_presentation_descriptor(bad))
 def test_core_asset_resolution_is_allowlisted(self):self.assertEqual(VIEW.BADGE_ASSETS,{"BLURAY":"assets/ui/bluray-media-badge.png","UHD_BLURAY":"assets/ui/uhd-bluray-media-badge.png"})
 def test_doctor_phase3_remains_equivalent(self):
  inputs={"protected":{},"optical":state("UHD_BLURAY_VIDEO","PROTECTED"),"last_attempt":{"status":"OPEN_SUCCESS"}}
  self.assertEqual(PLUGIN.doctor_rows(inputs),CORE.core_protected_optical_doctor_rows(inputs))

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir()
  (self.install/"VERSION").write_text("1.2.0-dev5\n");shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py")
  shutil.copytree(PAYLOAD/"assets",self.install/"assets")
  self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def test_disabled_uses_core(self):self.assertEqual(CORE.optical_presentation_descriptor(self.home,self.install,self.registry(),state("UHD_BLURAY_VIDEO"))[0],"CORE_FALLBACK")
 def test_enabled_uses_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=CORE.optical_presentation_descriptor(self.home,self.install,self.registry(),state("UHD_BLURAY_VIDEO"));self.assertEqual((authority,value["badge_key"]),("PLUGIN_P2","UHD_BLURAY"))
 def test_broken_or_mismatched_uses_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"badge_key":"UHD_BLURAY"','"badge_key":"UNKNOWN"'))
  registry=self.registry();authority,value=CORE.optical_presentation_descriptor(self.home,self.install,registry,state("UHD_BLURAY_VIDEO"));self.assertEqual((authority,value["badge_key"]),("CORE_FALLBACK","UHD_BLURAY"));self.assertEqual(registry["plugins"][0]["state"],"BROKEN")
 def test_renderer_resolves_enabled_descriptor_without_plugin_path(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);shutil.copy2(PAYLOAD/"openhtpc-core.py",self.install/"openhtpc-core.py")
  profile,authority=VIEW.presentation_profile(self.home,self.install,state("UHD_BLURAY_VIDEO"));self.assertEqual((authority,pathlib.Path(profile["logo"]).name,profile["badge"]),("PLUGIN_P2","uhd-bluray-media-badge.png","ULTRA HD BLU-RAY 4K"))

class Boundaries(unittest.TestCase):
 def test_plugin_is_data_only_without_render_io_or_execution(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("pathlib","pil","image","flex","assets/",".png","subprocess","os.system","open(","write(","read_text(","keydb.cfg","find_library","ctypes","socket","urlopen","bd://","mpv","dispatcher"):self.assertNotIn(marker,source)
 def test_production_media_sources_unchanged(self):
  names=("openhtpc-protected-optical.py","openhtpc-protected-optical-backend.py","openhtpc-play-optical","openhtpc-play-dvd","openhtpc-play","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh","openhtpc-playback-policy.py","openhtpc-session-engine.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_qualified_badge_assets_unchanged(self):
  for name in ("bluray-media-badge.png","uhd-bluray-media-badge.png"):
   baseline=subprocess.run(["git","show",f"{BASE}:payload/assets/ui/{name}"],cwd=ROOT,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/"assets/ui"/name).read_bytes(),baseline)

if __name__=="__main__":unittest.main()
