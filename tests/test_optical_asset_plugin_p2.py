from __future__ import annotations
import hashlib,importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="ff1d6d3e4646dd6c6e96e8c25a905e7219df9e43"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
REGISTRY=load("asset_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py");VIEW=load("asset_p2_view",PAYLOAD/"openhtpc-disc-view.py")
CORE_ASSETS={"BLURAY":PAYLOAD/"assets/ui/bluray-media-badge.png","UHD_BLURAY":PAYLOAD/"assets/ui/uhd-bluray-media-badge.png"}
PLUGIN_ASSETS={"BLURAY":PAYLOAD/"plugins/available/plugin.bluray/assets/bluray-media-badge.png","UHD_BLURAY":PAYLOAD/"plugins/available/plugin.bluray/assets/uhd-bluray-media-badge.png"}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class ResourceContract(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev12\n")
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");shutil.copy2(PAYLOAD/"openhtpc-core.py",self.install/"openhtpc-core.py");shutil.copytree(PAYLOAD/"assets",self.install/"assets")
  self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def enable(self):REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True)
 def manifest(self):return json.loads((self.plugin/"plugin.json").read_text())
 def write_manifest(self,value):(self.plugin/"plugin.json").write_text(json.dumps(value))
 def test_valid_bluray_and_uhd_declarations(self):
  value=self.manifest();self.assertEqual(value["resources"],{"BLURAY":"assets/bluray-media-badge.png","UHD_BLURAY":"assets/uhd-bluray-media-badge.png"});self.assertTrue(REGISTRY.validate_manifest(value,self.plugin,"1.2.0-dev12")[0])
 def test_keys_resolve_without_inversion(self):
  self.enable()
  for key,name in (("BLURAY","bluray-media-badge.png"),("UHD_BLURAY","uhd-bluray-media-badge.png")):
   value=REGISTRY.resolve_resource(self.home,self.install,"plugin.bluray",key);self.assertEqual((value["authority"],value["path"].name),("PLUGIN_P2",name))
 def test_unknown_key_rejected(self):
  self.enable();self.assertEqual(REGISTRY.resolve_resource(self.home,self.install,"plugin.bluray","DVD")["authority"],"CORE_FALLBACK")
 def test_absolute_traversal_and_remote_declarations_rejected(self):
  for path in ("/tmp/badge.png","assets/../badge.png","http://host/badge.png","https://host/badge.png","file:///tmp/badge.png","$HOME/badge.png"):
   value=self.manifest();value["resources"]["BLURAY"]=path;self.assertFalse(REGISTRY.validate_manifest(value,self.plugin,"1.2.0-dev12")[0],path)
 def test_symlink_escape_rejected(self):
  outside=pathlib.Path(self.temp.name)/"outside.png";outside.write_bytes(CORE_ASSETS["BLURAY"].read_bytes());target=self.plugin/"assets/escape.png";target.symlink_to(outside)
  value=self.manifest();value["resources"]["BLURAY"]="assets/escape.png";self.assertFalse(REGISTRY.validate_manifest(value,self.plugin,"1.2.0-dev12")[0])
 def test_missing_and_unsupported_resource_rejected(self):
  for path in ("assets/missing.png","assets/bluray-media-badge.jpg","shadow.py"):
   value=self.manifest();value["resources"]["BLURAY"]=path;self.assertFalse(REGISTRY.validate_manifest(value,self.plugin,"1.2.0-dev12")[0])
 def test_disabled_withholds_bluray_asset(self):
  logo,authority=VIEW.resolve_badge_asset(self.home,self.install,"BLURAY","PLUGIN_UNAVAILABLE");self.assertEqual((logo,authority),(None,"PLUGIN_UNAVAILABLE"))
 def test_enabled_uses_equivalent_plugin_asset(self):
  self.enable();profile,authority=VIEW.presentation_profile(self.home,self.install,{"canonical_state":"UHD_BLURAY_VIDEO","protection":"PROTECTED"});self.assertEqual(authority,"PLUGIN_P2");self.assertEqual(pathlib.Path(profile["logo"]).name,"uhd-bluray-media-badge.png")
 def test_broken_entrypoint_uses_core_asset(self):
  self.enable();(self.plugin/"shadow.py").write_text("raise RuntimeError('broken')\n");profile,authority=VIEW.presentation_profile(self.home,self.install,{"canonical_state":"BLURAY_VIDEO"});self.assertEqual((authority,profile["logo"]),("PLUGIN_UNAVAILABLE",None))
 def test_semantic_mismatch_withholds_bluray_asset(self):
  self.enable();(self.plugin/"assets/bluray-media-badge.png").write_bytes(b"not-qualified");profile,authority=VIEW.presentation_profile(self.home,self.install,{"canonical_state":"BLURAY_VIDEO"});self.assertEqual((authority,profile["logo"]),("PLUGIN_UNAVAILABLE",None))
 def test_no_disc_dvd_and_history_do_not_request_plugin_resource(self):
  self.enable()
  for state in ({"canonical_state":"DRIVE_PRESENT_NO_MEDIA"},{"canonical_state":"DVD_VIDEO"},{"canonical_state":"DRIVE_PRESENT_NO_MEDIA","last_attempt":"OPEN_SUCCESS"},{"canonical_state":"DRIVE_PRESENT_NO_MEDIA","last_attempt":"OPEN_FAILED"}):
   profile,authority=VIEW.presentation_profile(self.home,self.install,state);self.assertEqual(authority,"PLUGIN_P2");self.assertNotIn(profile.get("logo"),map(str,PLUGIN_ASSETS.values()))

class EquivalenceLifecycleAndIsolation(unittest.TestCase):
 def test_exact_asset_sha_equivalence(self):
  self.assertEqual(digest(CORE_ASSETS["BLURAY"]),digest(PLUGIN_ASSETS["BLURAY"]));self.assertEqual(digest(CORE_ASSETS["UHD_BLURAY"]),digest(PLUGIN_ASSETS["UHD_BLURAY"]))
  self.assertEqual((digest(CORE_ASSETS["BLURAY"]),digest(CORE_ASSETS["UHD_BLURAY"])),("1ff114faa2319c3528440a966e1c0e7eacee999650635ddeed0be4d878703776","7d2130b7a20b6bcc5e34f67c1fe903898296e76113749d38a993cf50e6e17b09"))
 def test_qualified_visual_dimensions_and_uhd_wording_preserved(self):
  from PIL import Image
  for path in (*CORE_ASSETS.values(),*PLUGIN_ASSETS.values()):
   with Image.open(path) as image:self.assertEqual(image.size,(512,256))
  self.assertEqual(VIEW.MEDIA_PROFILES["UHD_BLURAY_VIDEO"]["badge"],"ULTRA HD BLU-RAY 4K")
 def test_install_and_managed_lifecycle_include_assets(self):
  installer=(PAYLOAD/"install-openhtpc-fedora.sh").read_text();managed=(PAYLOAD/"managed-files.txt").read_text()
  for name in ("bluray-media-badge.png","uhd-bluray-media-badge.png"):
   relative=f"plugins/available/plugin.bluray/assets/{name}";self.assertIn(relative,installer);self.assertIn(relative,managed)
  cleanup=(PAYLOAD/"openhtpc-update-managed-files").read_text();self.assertIn("previous_entries - target_entries",cleanup);self.assertIn("candidate.unlink()",cleanup)
 def test_plugin_entrypoint_has_no_asset_or_flex_io(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("assets/",".png","pathlib","image.open","flex","open(","write(","urlopen","http://","https://","file://","subprocess","os.system","keydb","/dev/"):self.assertNotIn(marker,source)
 def test_resource_failure_does_not_touch_authoritative_subsystems(self):
  names=("openhtpc-optical.py","openhtpc-core.py","openhtpc-protected-optical.py","openhtpc-play-dvd","openhtpc-play","openhtpc-capabilities.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-playback-policy.py")
  for name in names:
   if name in {"openhtpc-disc-view.py","openhtpc-core.py","openhtpc-plugin-registry.py"}:continue
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_flex_renderer_remains_core_owned(self):
  source=(PAYLOAD/"openhtpc-disc-view.py").read_text();self.assertIn("Image.open(logo_path)",source);self.assertIn("base.paste(logo_scaled",source);self.assertNotIn("Image",(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text())

if __name__=="__main__":unittest.main()
