#!/usr/bin/env python3
"""Dev11 generation-scoped optical auto-open navigation contracts."""
import importlib.util,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";FLEX=ROOT/"vendor/flex-launcher/src/launcher.c"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
session=load("dev11_session",PAYLOAD/"openhtpc-session-engine.py")
def state(generation,canonical,legacy=None):return {"generation":generation,"canonical_state":canonical,"state":legacy or canonical,"device":"/dev/sr0"}
EMPTY=lambda generation:state(generation,"DRIVE_PRESENT_NO_MEDIA","EMPTY")
class TransitionPolicy(unittest.TestCase):
 def test_01_home_empty_insert_dvd_requests_generation(self):self.assertEqual(session.optical_navigation_event(EMPTY(4),state(5,"DVD_VIDEO","DVD")),(5,0))
 def test_02_home_empty_insert_bluray_family_requests_generation(self):self.assertEqual(session.optical_navigation_event(EMPTY(6),state(7,"BLURAY_FAMILY","BLURAY")),(7,0))
 def test_03_startup_existing_disc_has_no_transition(self):self.assertEqual(session.optical_navigation_event(state(8,"DVD_VIDEO","DVD"),state(8,"DVD_VIDEO","DVD")),(0,0))
 def test_04_home_regeneration_same_generation_has_no_request(self):self.assertEqual(session.optical_navigation_event(EMPTY(9),EMPTY(9)),(0,0))
 def test_05_eject_reinsert_same_format_is_new_request(self):
  self.assertEqual(session.optical_navigation_event(state(10,"DVD_VIDEO","DVD"),EMPTY(11)),(0,11));self.assertEqual(session.optical_navigation_event(EMPTY(11),state(12,"DVD_VIDEO","DVD")),(12,0))
 def test_06_family_a_eject_family_b_is_new_request(self):
  self.assertEqual(session.optical_navigation_event(state(20,"BLURAY_FAMILY","BLURAY"),EMPTY(21)),(0,21));self.assertEqual(session.optical_navigation_event(EMPTY(21),state(22,"BLURAY_FAMILY","BLURAY")),(22,0))
 def test_07_generation_cannot_move_backward(self):self.assertEqual(session.optical_navigation_event(EMPTY(30),state(29,"DVD_VIDEO","DVD")),(0,0))
 def test_08_disc_eject_requests_generation(self):self.assertEqual(session.optical_navigation_event(state(40,"DVD_VIDEO","DVD"),EMPTY(41)),(0,41))
class RequestPublication(unittest.TestCase):
 def write(self,current,auto=0,eject=0):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);home=pathlib.Path(temp.name);target=session.write_live_optical_state(home,current,pathlib.Path("icon.png"),auto,eject);return target.read_text().splitlines()
 def test_09_tmdb_absent_does_not_gate_dvd_request(self):self.assertEqual(self.write(state(5,"DVD_VIDEO","DVD"),5)[6:],["5","0"])
 def test_10_network_state_is_not_consulted(self):self.assertEqual(self.write(state(7,"BLURAY_FAMILY","BLURAY"),7)[6:],["7","0"])
 def test_11_stale_auto_request_is_discarded(self):self.assertEqual(self.write(state(12,"DVD_VIDEO","DVD"),10)[6:],["0","0"])
 def test_12_only_current_new_generation_is_published(self):self.assertEqual(self.write(state(14,"BLURAY_FAMILY","BLURAY"),14)[6:],["14","0"])
 def test_13_stale_eject_request_is_discarded(self):self.assertEqual(self.write(EMPTY(16),0,15)[6:],["0","0"])
 def test_14_current_eject_request_is_published(self):self.assertEqual(self.write(EMPTY(16),0,16)[6:],["0","16"])
class FlexAuthority(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.source=FLEX.read_text();cls.binary_strings=subprocess.check_output(["strings",str(PAYLOAD/"flex/bin/flex-launcher")],text=True)
 def test_15_system_media_and_settings_cannot_auto_open(self):
  self.assertIn("current_menu == default_menu",self.source);self.assertNotIn('strcmp(current_menu->name, "SYSTEME")',self.source[self.source.index("auto_open_generation == gen_num"):self.source.index("eject_home_generation == gen_num")])
 def test_16_playback_consumes_without_navigation(self):
  self.assertIn("last_auto_opened_generation = gen_num",self.source);self.assertIn("!(state.application_running || state.application_launching)",self.source);self.assertLess(self.source.index("refresh_live_optical_state();",self.source.index("// Post-event loop updates")),self.source.index("if (!(state.application_running",self.source.index("// Post-event loop updates")))
 def test_17_manual_home_return_same_generation_does_not_reopen(self):self.assertIn("last_auto_opened_generation != gen_num",self.source)
 def test_18_eject_home_only_from_disc_sheet(self):self.assertIn("is_disc_sheet())\n                load_menu(default_menu",self.source)
 def test_19_controller_publishes_request_only_after_generation_render(self):
  home=(PAYLOAD/"openhtpc-home.py").read_text();success=home.index("if successful and completed_generation");publish=home.index("pending_auto_open_generation, pending_eject_home_generation",success);detect=home.index("optical_navigation_event",publish);self.assertLess(success,publish);self.assertLess(publish,detect)
 def test_20_shipped_flex_contains_navigation_runtime(self):
  for marker in ("DISQUE","SYSTEM_METADATA","SYSTEM_TMDB"):self.assertIn(marker,self.binary_strings)
 def test_21_default_menu_identity_not_translated_label(self):self.assertIn("current_menu == default_menu",self.source)
 def test_22_disc_sheet_identity_is_canonical_menu_id(self):self.assertIn('strcmp(current_menu->name, "DISQUE") == 0',self.source)
if __name__=="__main__":unittest.main()
