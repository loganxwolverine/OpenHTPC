from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="4a7d07d0fb880e621d23a948e8dea4fceecb3821"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
CORE=load("decision_p2_core",PAYLOAD/"openhtpc-core.py");OPTICAL=load("decision_p2_optical",PAYLOAD/"openhtpc-optical.py")
REGISTRY=load("decision_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py");PLUGIN=load("decision_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def optical(canonical="BLURAY_VIDEO",protection="PROTECTED",**extra):return {"canonical_state":canonical,"protection":protection,**extra}
def snapshot(status="AVAILABLE",bluray="AVAILABLE",aacs="AVAILABLE",bdplus="NOT_AVAILABLE",keydb="DETECTED"):
 return {"status":status,"dependencies":{"libbluray":{"status":bluray},"libaacs":{"status":aacs},"libbdplus":{"status":bdplus}},"external_key_database":{"status":keydb}}

class Equivalence(unittest.TestCase):
 def equivalent(self,state,capability):
  core=CORE.core_protected_optical_playback_decision(state,capability);plugin=PLUGIN.playback_decision(state,capability)
  self.assertEqual(plugin,core);self.assertEqual({key:value for key,value in core.items() if key!="owned"},OPTICAL.playback_decision(state,capability));return plugin
 def test_no_disc_and_dvd_are_unowned(self):
  self.assertFalse(self.equivalent(optical("DRIVE_PRESENT_NO_MEDIA","UNKNOWN"),snapshot())["owned"])
  dvd=self.equivalent(optical("DVD_VIDEO","UNPROTECTED"),snapshot());self.assertFalse(dvd["owned"]);self.assertEqual(dvd["playback_reason"],"DVD_EXISTING_PATH")
 def test_unprotected_bluray_is_not_keydb_dependent(self):
  value=self.equivalent(optical(protection="UNPROTECTED"),snapshot("NOT_CONFIGURED",keydb="NOT_CONFIGURED"));self.assertTrue(value["playable"]);self.assertEqual(value["playback_reason"],"UNPROTECTED_MEDIA")
 def test_unprotected_needs_structural_bluray_support(self):self.assertEqual(self.equivalent(optical(protection="UNPROTECTED"),snapshot("NOT_AVAILABLE",bluray="NOT_AVAILABLE"))["playback_reason"],"STRUCTURAL_SUPPORT_NOT_AVAILABLE")
 def test_protected_bluray_provider_states(self):
  expected={"AVAILABLE":("ENABLED","PROTECTED_SUPPORT_AVAILABLE"),"NOT_CONFIGURED":("DISABLED","PROTECTED_SUPPORT_NOT_CONFIGURED"),"NOT_AVAILABLE":("DISABLED","PROTECTED_SUPPORT_NOT_AVAILABLE"),"BLOCKED":("DISABLED","PROTECTED_SUPPORT_BLOCKED")}
  for status,result in expected.items():self.assertEqual((lambda value:(value["playback_action"],value["playback_reason"]))(self.equivalent(optical(),snapshot(status))),result)
 def test_protected_uhd_provider_states(self):
  for status in ("AVAILABLE","NOT_CONFIGURED","NOT_AVAILABLE","BLOCKED"):self.assertEqual(self.equivalent(optical("UHD_BLURAY_VIDEO"),snapshot(status))["media_type"],"UHD_BLURAY")
 def test_bluray_family_and_unknown_exact(self):
  value=self.equivalent(optical("BLURAY_FAMILY"),snapshot());self.assertTrue(value["owned"]);self.assertEqual(value["media_type"],"BLURAY")
 def test_unknown_protection_is_conservative(self):
  value=self.equivalent(optical(protection="UNKNOWN"),snapshot());self.assertFalse(value["playable"]);self.assertEqual(value["playback_reason"],"PROTECTION_UNKNOWN")
 def test_absent_snapshot_and_dependency_failures(self):
  self.assertEqual(self.equivalent(optical(),None)["playback_reason"],"PROTECTED_SUPPORT_NOT_AVAILABLE")
  self.assertEqual(self.equivalent(optical(),snapshot("NOT_AVAILABLE",bluray="NOT_AVAILABLE"))["playback_action"],"DISABLED")
  self.assertEqual(self.equivalent(optical(),snapshot("NOT_AVAILABLE",aacs="NOT_AVAILABLE"))["playback_action"],"DISABLED")
 def test_libbdplus_absence_does_not_block_available_aacs(self):self.assertTrue(self.equivalent(optical(),snapshot(bdplus="NOT_AVAILABLE"))["playable"])
 def test_history_is_not_an_input_and_eject_clears_decision(self):
  for _history in ("OPEN_SUCCESS","OPEN_FAILED"):
   value=self.equivalent(optical("DRIVE_PRESENT_NO_MEDIA","UNKNOWN",last_attempt=_history),snapshot());self.assertFalse(value["owned"]);self.assertFalse(value["playable"])
 def test_available_means_attempt_not_success(self):
  value=self.equivalent(optical(),snapshot());self.assertTrue(value["playable"]);self.assertNotIn("success"," ".join(value).lower())
 def test_malformed_and_unknown_contributions_rejected(self):
  self.assertFalse(CORE._valid_protected_optical_playback_decision({"owned":True}))
  bad=CORE.core_protected_optical_playback_decision(optical(),snapshot());bad["playback_reason"]="UNKNOWN";self.assertFalse(CORE._valid_protected_optical_playback_decision(bad))
  malformed=CORE.core_protected_optical_playback_decision(optical(),{"status":"INVALID"});self.assertFalse(CORE._valid_protected_optical_playback_decision(malformed))
 def test_prior_phase_contributions_remain_equivalent(self):
  state=optical("UHD_BLURAY_VIDEO");capability=snapshot();inputs={"protected":capability,"optical":state,"last_attempt":None}
  self.assertEqual(PLUGIN.doctor_rows(inputs),CORE.core_protected_optical_doctor_rows(inputs));self.assertEqual(PLUGIN.presentation_descriptor(state),CORE.core_optical_presentation_descriptor(state));self.assertEqual(PLUGIN.capability_contribution(capability),CORE.core_protected_optical_capability(capability))

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir()
  (self.install/"VERSION").write_text("1.2.0-dev7\n");shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def test_disabled_withholds_plugin_policy(self):self.assertEqual(CORE.protected_optical_playback_decision_projection(self.home,self.install,self.registry(),optical(),snapshot())[0],"PLUGIN_UNAVAILABLE")
 def test_enabled_selects_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=CORE.protected_optical_playback_decision_projection(self.home,self.install,self.registry(),optical(),snapshot());self.assertEqual((authority,value["playback_action"]),("PLUGIN_P2","ENABLED"))
 def test_capability_state_publishes_projection_without_mutating_sources(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);cap_path=self.home/".config/openhtpc/runtime/capabilities.json";cap_path.parent.mkdir(parents=True,exist_ok=True);state_path=self.home/".local/state/openhtpc/optical-current.json";state_path.parent.mkdir(parents=True,exist_ok=True)
  cap={"optical":{"protected_media":snapshot()}};disc=optical();cap_path.write_text(json.dumps(cap));state_path.write_text(json.dumps(disc));state=CORE.capability_state(self.home,self.install)
  self.assertEqual(state["PROTECTED_OPTICAL_PLAYBACK_DECISION_AUTHORITY"],"PLUGIN_P2");self.assertEqual(state["PROTECTED_OPTICAL_PLAYBACK_DECISION"]["playback_action"],"ENABLED");self.assertEqual(json.loads(cap_path.read_text()),cap);self.assertEqual(json.loads(state_path.read_text()),disc)
 def test_broken_or_mismatch_selects_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"playback_reason":reason','"playback_reason":"UNKNOWN"'))
  registry=self.registry();authority,value=CORE.protected_optical_playback_decision_projection(self.home,self.install,registry,optical(),snapshot());self.assertEqual(authority,"PLUGIN_UNAVAILABLE");self.assertEqual((value["playback_action"],value["playback_reason"]),("DISABLED","PLUGIN_BROKEN"));self.assertEqual(registry["plugins"][0]["state"],"BROKEN")

class Boundaries(unittest.TestCase):
 def test_plugin_decision_has_no_execution_or_probe_primitives(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("pathlib","ctypes","find_library","udev","keydb.cfg","lstat(","stat(","open(","read_text(","subprocess","socket","urlopen","curl ","wget ","bd://","mpv","dispatcher","action_token","flex"):
   self.assertNotIn(marker,source)
 def test_security_and_production_sources_unchanged(self):
  names=("openhtpc-play-dvd","openhtpc-play","openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-playback-policy.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_dispatcher_revalidation_and_forged_token_guards_remain(self):
  source=(PAYLOAD/"openhtpc-play-optical").read_text();self.assertGreaterEqual(source.count("authorize(home,install,device,generation,action_token"),2);self.assertIn("OPTICAL_ACTION_TOKEN_INVALID",source);self.assertIn('decision=optical.playback_decision(state,capability)',source)

if __name__=="__main__":unittest.main()
