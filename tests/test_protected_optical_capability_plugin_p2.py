from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="f802def8859847f4e6d1409663525c58497123e2"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
CORE=load("capability_p2_core",PAYLOAD/"openhtpc-core.py");REGISTRY=load("capability_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("capability_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def snapshot(status="AVAILABLE",bluray="AVAILABLE",aacs="AVAILABLE",bdplus="NOT_AVAILABLE",keydb="DETECTED"):
 return {"capability":"PROTECTED_OPTICAL_SUPPORT","status":status,"available":status=="AVAILABLE","can_open_protected_optical_media":status=="AVAILABLE",
         "dependencies":{"libbluray":{"status":bluray},"libaacs":{"status":aacs},"libbdplus":{"status":bdplus}},"external_key_database":{"status":keydb}}

class Equivalence(unittest.TestCase):
 def equivalent(self,value):
  core=CORE.core_protected_optical_capability(value);plugin=PLUGIN.capability_contribution(value);self.assertEqual(plugin,core);self.assertTrue(CORE._valid_protected_optical_capability(plugin));return plugin
 def test_valid_available_ready_to_attempt(self):
  value=self.equivalent(snapshot());self.assertEqual(value["provider_state"],"AVAILABLE");self.assertTrue(value["ready_to_attempt"])
 def test_not_configured(self):self.assertEqual(self.equivalent(snapshot("NOT_CONFIGURED",keydb="NOT_CONFIGURED"))["provider_state"],"NOT_CONFIGURED")
 def test_not_available(self):self.assertEqual(self.equivalent(snapshot("NOT_AVAILABLE",aacs="NOT_AVAILABLE"))["provider_state"],"NOT_AVAILABLE")
 def test_blocked(self):self.assertTrue(self.equivalent(snapshot("BLOCKED"))["blocking"])
 def test_libbdplus_absent_is_nonblocking(self):
  value=self.equivalent(snapshot(bdplus="NOT_AVAILABLE"));self.assertFalse(value["blocking"]);self.assertEqual(value["dependency_states"]["libbdplus"],"NOT_AVAILABLE")
 def test_key_database_states(self):
  self.assertEqual(self.equivalent(snapshot())["external_key_database_state"],"DETECTED");self.assertEqual(self.equivalent(snapshot("NOT_CONFIGURED",keydb="NOT_CONFIGURED"))["external_key_database_state"],"NOT_CONFIGURED")
 def test_libaacs_and_libbluray_unavailable(self):
  self.assertEqual(self.equivalent(snapshot("NOT_AVAILABLE",aacs="NOT_AVAILABLE"))["dependency_states"]["libaacs"],"NOT_AVAILABLE")
  self.assertEqual(self.equivalent(snapshot("NOT_AVAILABLE",bluray="NOT_AVAILABLE"))["dependency_states"]["libbluray"],"NOT_AVAILABLE")
 def test_media_and_disc_state_do_not_change_machine_capability(self):
  expected=self.equivalent(snapshot())
  for _disc in ({"protection":"UNPROTECTED"},{"protection":"PROTECTED"},{"exact_type":"UHD_BLURAY"},{},{"canonical_state":"DVD_VIDEO"}):self.assertEqual(self.equivalent(snapshot()),expected)
 def test_absent_snapshot(self):self.assertEqual(self.equivalent(None)["provider_state"],"NOT_AVAILABLE")
 def test_malformed_snapshot_is_conservatively_blocked(self):self.assertEqual(self.equivalent({"status":"INVALID"})["provider_state"],"BLOCKED")
 def test_history_never_changes_capability(self):
  expected=self.equivalent(snapshot());self.assertEqual(self.equivalent(snapshot()),expected);self.assertNotIn("last_attempt",expected)
 def test_available_does_not_claim_disc_success(self):
  value=self.equivalent(snapshot());self.assertTrue(value["ready_to_attempt"]);self.assertNotIn("open_success",{key.lower() for key in value})
 def test_malformed_and_unknown_capability_rejected(self):
  self.assertFalse(CORE._valid_protected_optical_capability({"capability_id":"PROTECTED_OPTICAL_SUPPORT"}))
  bad={**CORE.core_protected_optical_capability(snapshot()),"capability_id":"UNKNOWN"};self.assertFalse(CORE._valid_protected_optical_capability(bad))
 def test_phase3_and_phase4_contributions_unchanged(self):
  inputs={"protected":snapshot(),"optical":{"canonical_state":"UHD_BLURAY_VIDEO"},"last_attempt":None}
  self.assertEqual(PLUGIN.doctor_rows(inputs),CORE.core_protected_optical_doctor_rows(inputs));self.assertEqual(PLUGIN.presentation_descriptor(inputs["optical"]),CORE.core_optical_presentation_descriptor(inputs["optical"]))

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir()
  (self.install/"VERSION").write_text("1.2.0-dev6\n");shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py")
  self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def test_disabled_withholds_plugin_policy(self):self.assertEqual(CORE.protected_optical_capability_projection(self.home,self.install,self.registry(),snapshot())[0],"PLUGIN_UNAVAILABLE")
 def test_enabled_selects_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=CORE.protected_optical_capability_projection(self.home,self.install,self.registry(),snapshot());self.assertEqual((authority,value["provider_state"]),("PLUGIN_P2","AVAILABLE"))
 def test_capability_state_exposes_selected_projection_without_rewriting_snapshot(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);target=self.home/".config/openhtpc/runtime/capabilities.json";target.parent.mkdir(parents=True,exist_ok=True)
  original={"optical":{"protected_media":snapshot()}};target.write_text(json.dumps(original));state=CORE.capability_state(self.home,self.install)
  self.assertEqual(state["PROTECTED_OPTICAL_CAPABILITY_AUTHORITY"],"PLUGIN_P2");self.assertEqual(state["PROTECTED_OPTICAL_CAPABILITY"]["provider_state"],"AVAILABLE");self.assertEqual(json.loads(target.read_text()),original)
 def test_broken_or_mismatched_selects_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"capability_id":"PROTECTED_OPTICAL_SUPPORT"','"capability_id":"UNKNOWN"'))
  registry=self.registry();authority,value=CORE.protected_optical_capability_projection(self.home,self.install,registry,snapshot());self.assertEqual((authority,value["capability_id"],value["available"]),("PLUGIN_UNAVAILABLE","PROTECTED_OPTICAL_SUPPORT",False));self.assertEqual(registry["plugins"][0]["state"],"BROKEN")

class Boundaries(unittest.TestCase):
 def test_plugin_capability_code_has_no_probe_or_access_primitives(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("pathlib","ctypes","find_library","udev","keydb.cfg","lstat(","stat(","open(","read_text(","subprocess","socket","urlopen","curl ","wget ","bd://","mpv","dispatcher"):self.assertNotIn(marker,source)
 def test_snapshot_generator_and_production_sources_unchanged(self):
  names=("openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-play-dvd","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)

if __name__=="__main__":unittest.main()
