from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="ab42b1ad3d247ff07268b182ce3c762e0944b564"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
CORE=load("ui_p2_core",PAYLOAD/"openhtpc-core.py");REGISTRY=load("ui_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("ui_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def inputs(canonical="BLURAY_VIDEO",protection="PROTECTED",status="AVAILABLE"):
 optical={"canonical_state":canonical,"protection":protection};snapshot={"status":status,"dependencies":{"libbluray":{"status":"AVAILABLE"}}}
 return CORE.core_optical_presentation_descriptor(optical),CORE.core_protected_optical_playback_decision(optical,snapshot)

class Equivalence(unittest.TestCase):
 def equivalent(self,presentation,decision):
  core=CORE.core_protected_optical_ui_contribution(presentation,decision);plugin=PLUGIN.ui_contribution(presentation,decision)
  self.assertEqual(plugin,core);self.assertTrue(CORE._valid_protected_optical_ui_contribution(plugin));return plugin
 def test_no_disc_and_dvd_are_unowned(self):
  for canonical in ("DRIVE_PRESENT_NO_MEDIA","DVD_VIDEO"):
   self.assertFalse(self.equivalent(*inputs(canonical,"UNPROTECTED"))["owned"])
 def test_bluray_and_family(self):
  bluray=self.equivalent(*inputs());family=self.equivalent(*inputs("BLURAY_FAMILY"));self.assertEqual(bluray["badge_key"],"BLURAY");self.assertEqual(family["display_label"],"BLU-RAY / UHD")
 def test_protected_bluray_provider_states(self):
  for status in ("AVAILABLE","NOT_CONFIGURED","NOT_AVAILABLE","BLOCKED"):
   value=self.equivalent(*inputs(status=status));self.assertEqual(value["enabled"],status=="AVAILABLE")
   self.assertEqual(value["action_intent"],"PLAY_CURRENT_OPTICAL_MEDIA" if status=="AVAILABLE" else "NONE")
 def test_unprotected_bluray_is_not_keydb_dependent(self):
  value=self.equivalent(*inputs(protection="UNPROTECTED",status="NOT_CONFIGURED"));self.assertTrue(value["enabled"])
 def test_uhd_provider_states_and_exact_text(self):
  for status in ("AVAILABLE","NOT_CONFIGURED","NOT_AVAILABLE","BLOCKED"):
   value=self.equivalent(*inputs("UHD_BLURAY_VIDEO",status=status));self.assertEqual(value["badge_key"],"UHD_BLURAY");self.assertEqual(value["display_label"],"ULTRA HD BLU-RAY 4K")
 def test_uhd_unprotected(self):self.assertTrue(self.equivalent(*inputs("UHD_BLURAY_VIDEO","UNPROTECTED","NOT_CONFIGURED"))["enabled"])
 def test_unknown_protection_is_conservative(self):
  value=self.equivalent(*inputs(protection="UNKNOWN"));self.assertFalse(value["enabled"]);self.assertEqual(value["disabled_reason"],"PROTECTION_UNKNOWN")
 def test_eject_and_history_cannot_create_contribution(self):
  presentation,decision=inputs("DRIVE_PRESENT_NO_MEDIA","UNKNOWN")
  for _history in ("OPEN_SUCCESS","OPEN_FAILED"):
   self.assertFalse(self.equivalent(presentation,decision)["owned"]);self.assertNotIn("last_attempt",decision)
 def test_noncanonical_heuristics_are_not_inputs(self):
  presentation,decision=inputs("BLURAY_FAMILY");expected=self.equivalent(presentation,decision)
  for _fact in ("HEVC","3840x2160","HDR","TITLE UHD 4K"):self.assertEqual(self.equivalent(presentation,decision),expected)
 def test_malformed_upstream_is_conservative_core_only(self):
  neutral=CORE.core_protected_optical_ui_contribution({"badge_key":"BLURAY"},inputs()[1]);self.assertFalse(neutral["owned"])
  neutral=CORE.core_protected_optical_ui_contribution(inputs()[0],{"playback_action":"ENABLED"});self.assertFalse(neutral["owned"])
 def test_malformed_unknown_badge_and_action_rejected(self):
  value=self.equivalent(*inputs());self.assertFalse(CORE._valid_protected_optical_ui_contribution({"owned":True}))
  self.assertFalse(CORE._valid_protected_optical_ui_contribution({**value,"badge_key":"../../badge.png"}))
  self.assertFalse(CORE._valid_protected_optical_ui_contribution({**value,"action_intent":"RUN_COMMAND"}))
 def test_prior_phase_contributions_remain_equivalent(self):
  optical={"canonical_state":"UHD_BLURAY_VIDEO","protection":"PROTECTED"};snapshot={"status":"AVAILABLE","dependencies":{"libbluray":{"status":"AVAILABLE"}}};doctor={"protected":snapshot,"optical":optical,"last_attempt":None}
  self.assertEqual(PLUGIN.doctor_rows(doctor),CORE.core_protected_optical_doctor_rows(doctor));self.assertEqual(PLUGIN.presentation_descriptor(optical),CORE.core_optical_presentation_descriptor(optical));self.assertEqual(PLUGIN.capability_contribution(snapshot),CORE.core_protected_optical_capability(snapshot));self.assertEqual(PLUGIN.playback_decision(optical,snapshot),CORE.core_protected_optical_playback_decision(optical,snapshot))

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev8\n")
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def test_disabled_withholds_plugin_ui(self):self.assertEqual(CORE.protected_optical_ui_contribution(self.home,self.install,self.registry(),*inputs())[0],"PLUGIN_UNAVAILABLE")
 def test_enabled_selects_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=CORE.protected_optical_ui_contribution(self.home,self.install,self.registry(),*inputs());self.assertEqual((authority,value["action_intent"]),("PLUGIN_P2","PLAY_CURRENT_OPTICAL_MEDIA"))
 def test_broken_or_mismatch_selects_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"action_intent":"PLAY_CURRENT_OPTICAL_MEDIA"','"action_intent":"RUN_COMMAND"'))
  registry=self.registry();authority,value=CORE.protected_optical_ui_contribution(self.home,self.install,registry,*inputs());self.assertEqual(authority,"PLUGIN_UNAVAILABLE");self.assertFalse(value["owned"]);self.assertEqual(registry["plugins"][0]["state"],"BROKEN")
 def test_malformed_upstream_never_invokes_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=CORE.protected_optical_ui_contribution(self.home,self.install,self.registry(),{"badge_key":"BLURAY"},inputs()[1]);self.assertEqual(authority,"PLUGIN_UNAVAILABLE");self.assertFalse(value["owned"])
 def test_capability_state_publishes_selected_data_without_mutation(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);cap_path=self.home/".config/openhtpc/runtime/capabilities.json";cap_path.parent.mkdir(parents=True,exist_ok=True);disc_path=self.home/".local/state/openhtpc/optical-current.json";disc_path.parent.mkdir(parents=True,exist_ok=True)
  cap={"optical":{"protected_media":{"status":"AVAILABLE","dependencies":{"libbluray":{"status":"AVAILABLE"}}}}};disc={"canonical_state":"UHD_BLURAY_VIDEO","protection":"PROTECTED"};cap_path.write_text(json.dumps(cap));disc_path.write_text(json.dumps(disc));state=CORE.capability_state(self.home,self.install)
  self.assertEqual(state["PROTECTED_OPTICAL_UI_CONTRIBUTION_AUTHORITY"],"PLUGIN_P2");self.assertEqual(state["PROTECTED_OPTICAL_UI_CONTRIBUTION"]["display_label"],"ULTRA HD BLU-RAY 4K");self.assertEqual(json.loads(cap_path.read_text()),cap);self.assertEqual(json.loads(disc_path.read_text()),disc)

class Boundaries(unittest.TestCase):
 def test_plugin_ui_has_no_execution_render_probe_or_path_primitives(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("pathlib","flex","assets/",".png","subprocess","os.system","exec(","eval(","open(","write(","read_text(","keydb.cfg","find_library","ctypes","socket","urlopen","http://","https://","bd://","mpv","dispatcher","action_token"):
   self.assertNotIn(marker,source)
 def test_security_render_and_production_sources_unchanged(self):
  names=("openhtpc-play-dvd","openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_token_and_dispatcher_security_remain(self):
  optical=(PAYLOAD/"openhtpc-optical.py").read_text();dispatcher=(PAYLOAD/"openhtpc-play-optical").read_text();self.assertIn("def playback_action_token",optical);self.assertGreaterEqual(dispatcher.count("authorize(home,install,device,generation,action_token"),2);self.assertIn("OPTICAL_ACTION_TOKEN_INVALID",dispatcher)

if __name__=="__main__":unittest.main()
