from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="ff1564ce6dce27360b793dbb2476ef98bcf70ff2"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
REGISTRY=load("shadow_registry",PAYLOAD/"openhtpc-plugin-registry.py")
CONTRACT=load("shadow_contract",PAYLOAD/"openhtpc-plugin-contracts.py")
OPTICAL=load("shadow_optical",PAYLOAD/"openhtpc-optical.py")
CORE=load("shadow_core",PAYLOAD/"openhtpc-core.py")

class ShadowFixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name)
  self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev3\n")
  self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def adapter(self):
  loaded=REGISTRY.load_entrypoint(self.home,self.install,"plugin.bluray",shadow=True);self.assertEqual(loaded["state"],"SHADOW");return loaded["module"]
 def observe(self,optical=None,provider="NOT_AVAILABLE",attempt=None,libbluray="AVAILABLE"):
  optical=optical or {};capability={"status":provider,"dependencies":{"libbluray":{"status":libbluray}}}
  playback=OPTICAL.playback_decision(optical,capability);core=CONTRACT.protected_optical_observation(optical,capability,attempt,playback)
  shadow=self.adapter().observe(core);self.assertTrue(self.adapter().equivalent(core,shadow));return core,shadow

class ManifestAndRuntime(ShadowFixture):
 def test_first_party_manifest_is_v2_compatible_and_disabled(self):
  item=self.registry()["plugins"][0];self.assertEqual((item["id"],item["plugin_api"],item["state"]),("plugin.bluray",2,"DISABLED"));self.assertFalse(item["enabled_by_default"])
 def test_declares_one_plugin_with_three_media_capabilities(self):self.assertEqual(self.adapter().DECLARED_MEDIA_CAPABILITIES,("bluray","uhd_bluray","protected_optical"))
 def test_discovery_does_not_load_entrypoint(self):
  original=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text("raise RuntimeError('executed')\n"+original);self.assertEqual(self.registry()["plugins"][0]["state"],"DISABLED")
 def test_disabled_requires_explicit_shadow_invocation(self):self.assertEqual(REGISTRY.load_entrypoint(self.home,self.install,"plugin.bluray")["reason"],"PLUGIN_DISABLED")
 def test_explicit_shadow_adapter_loads(self):self.assertEqual(self.adapter().PLUGIN_ID,"plugin.bluray")
 def test_malformed_shadow_entrypoint_is_broken_and_isolated(self):
  (self.plugin/"shadow.py").write_text("def broken(:\n");result=REGISTRY.load_entrypoint(self.home,self.install,"plugin.bluray",shadow=True);self.assertEqual(result,{"state":"BROKEN","reason":"PLUGIN_LOAD_FAILED"})
 def test_shadow_exit_is_broken_and_isolated(self):
  (self.plugin/"shadow.py").write_text("raise SystemExit(9)\n");self.assertEqual(REGISTRY.load_entrypoint(self.home,self.install,"plugin.bluray",shadow=True)["state"],"BROKEN")
 def test_path_escape_is_rejected(self):
  manifest=json.loads((self.plugin/"plugin.json").read_text());manifest["entrypoint"]="../escape.py";(self.plugin/"plugin.json").write_text(json.dumps(manifest));self.assertEqual(self.registry()["errors"][0]["reason"],"PLUGIN_PATH_INVALID")
 def test_duplicate_id_is_rejected(self):
  user=self.home/".local/share/openhtpc/plugins/available/plugin.bluray";shutil.copytree(self.plugin,user);self.assertEqual(self.registry()["plugins"][0]["state"],"BROKEN")
 def test_doctor_truthfully_reports_combined_plugin_disabled(self):
  states={item["label"]:item["status"] for item in CORE.optional_plugin_states(self.registry())};self.assertEqual(states["Blu-ray/UHD"],"DISABLED");self.assertNotIn("UHD",states)

class Equivalence(ShadowFixture):
 @staticmethod
 def disc(canonical="BLURAY_VIDEO",protection="PROTECTED",mechanisms=None,source="LIBBLURAY"):
  return {"canonical_state":canonical,"protection":protection,"protection_mechanisms":mechanisms or ["AACS"],"classification_source":source}
 def test_no_disc(self):self.assertEqual(self.observe({"canonical_state":"DRIVE_PRESENT_NO_MEDIA"})[0]["media_family"],"NONE")
 def test_dvd_does_not_claim_bluray_or_uhd(self):self.assertEqual(self.observe(self.disc("DVD_VIDEO","UNPROTECTED",["NONE"],"DISC_STRUCTURE"))[0]["media_family"],"DVD")
 def test_unprotected_bluray(self):self.assertEqual(self.observe(self.disc(protection="UNPROTECTED",mechanisms=["NONE"]),provider="NOT_CONFIGURED")[0]["playback_state"],"ENABLED")
 def test_protected_bluray_available(self):self.assertEqual(self.observe(self.disc(),"AVAILABLE")[0]["playback_state"],"ENABLED")
 def test_protected_bluray_not_configured(self):self.assertEqual(self.observe(self.disc(),"NOT_CONFIGURED")[0]["playback_state"],"DISABLED")
 def test_protected_bluray_not_available(self):self.assertEqual(self.observe(self.disc(),"NOT_AVAILABLE")[0]["provider_state"],"NOT_AVAILABLE")
 def test_protected_bluray_blocked(self):self.assertEqual(self.observe(self.disc(),"BLOCKED")[0]["provider_state"],"BLOCKED")
 def test_uhd_bluray(self):self.assertEqual(self.observe(self.disc("UHD_BLURAY_VIDEO"),"AVAILABLE")[0]["exact_type"],"UHD_BLURAY")
 def test_bluray_family_exact_unknown(self):self.assertEqual(self.observe(self.disc("BLURAY_FAMILY"),"AVAILABLE")[0]["exact_type"],"UNKNOWN")
 def test_protection_unknown(self):self.assertEqual(self.observe(self.disc(protection="UNKNOWN",mechanisms=["UNKNOWN"]),"AVAILABLE")[0]["protection"],"UNKNOWN")
 def test_open_success_history(self):self.assertEqual(self.observe(self.disc(),"AVAILABLE",{"status":"OPEN_SUCCESS"})[0]["last_attempt"],"OPEN_SUCCESS")
 def test_open_failed_history(self):self.assertEqual(self.observe(self.disc(),"AVAILABLE",{"status":"OPEN_FAILED"})[0]["last_attempt"],"OPEN_FAILED")
 def test_eject_clears_current_and_preserves_history(self):
  core,_=self.observe({"canonical_state":"DRIVE_PRESENT_NO_MEDIA"},"AVAILABLE",{"status":"OPEN_SUCCESS"});self.assertEqual((core["media_family"],core["exact_type"],core["protection"],core["last_attempt"]),("NONE","UNKNOWN","UNKNOWN","OPEN_SUCCESS"))

class Boundaries(unittest.TestCase):
 def test_shadow_has_no_probe_keydb_playback_or_ownership_primitives(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("libbluray","libaacs","keydb","indx0300","bd://","mpv","dispatcher","subprocess","socket","urlopen","open("):self.assertNotIn(marker,source)
 def test_registry_has_no_network_or_shell_loader(self):
  source=(PAYLOAD/"openhtpc-plugin-registry.py").read_text().lower()
  for marker in ("subprocess","shell=true","os.system","urlopen(","requests.","curl ","wget ","http://","https://","eval("):self.assertNotIn(marker,source)
 def test_qualified_production_sources_unchanged(self):
  names=("openhtpc-optical.py","openhtpc-protected-optical.py","openhtpc-protected-optical-backend.py","openhtpc-play-optical","openhtpc-play-dvd","openhtpc-play","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh","openhtpc-playback-policy.py","openhtpc-session-engine.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_installer_manages_shadow_without_dependencies(self):
  installer=(PAYLOAD/"install-openhtpc-fedora.sh").read_text();managed=(PAYLOAD/"managed-files.txt").read_text()
  for path in ("openhtpc-plugin-contracts.py","plugins/available/plugin.bluray/plugin.json","plugins/available/plugin.bluray/shadow.py"):self.assertIn(path,managed)
  self.assertIn("plugin.bluray",installer)

if __name__=="__main__":unittest.main()
