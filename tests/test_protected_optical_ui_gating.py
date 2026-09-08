from __future__ import annotations

import importlib.machinery,importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest


ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
OPTICAL=load("phase2_optical",PAYLOAD/"openhtpc-optical.py")
SESSION=load("phase2_session",PAYLOAD/"openhtpc-session-engine.py")
DISC_SHEET=load("phase2_disc_sheet",PAYLOAD/"openhtpc-disc-sheet.py")
DISPATCH=load("phase2_dispatch",PAYLOAD/"openhtpc-play-optical")
REGISTRY=load("phase2_registry",PAYLOAD/"openhtpc-plugin-registry.py")

def capability(status="NOT_CONFIGURED",bluray="AVAILABLE",bdplus="NOT_AVAILABLE"):
 return {"capability":"PROTECTED_OPTICAL_SUPPORT","status":status,
         "dependencies":{"libbluray":{"status":bluray},"libaacs":{"status":"AVAILABLE"},"libbdplus":{"status":bdplus}},
         "external_key_database":{"status":"DETECTED" if status=="AVAILABLE" else "NOT_CONFIGURED"}}
def state(canonical="BLURAY_VIDEO",protection="PROTECTED",generation=7):
 return {"canonical_state":canonical,"state":"UHD" if canonical=="UHD_BLURAY_VIDEO" else "BLURAY",
         "device":"/dev/sr0","generation":generation,"protection":protection,"volume_label":"FIXTURE"}

class PlaybackDecision(unittest.TestCase):
 def test_dvd_without_key_database_keeps_existing_action(self):
  value=state("DVD_VIDEO","UNPROTECTED");self.assertEqual(OPTICAL.playback_decision(value,capability())["playback_action"],"ENABLED")
 def test_unprotected_bluray_needs_no_key_database(self):
  decision=OPTICAL.playback_decision(state(protection="UNPROTECTED"),capability("NOT_CONFIGURED"));self.assertEqual((decision["playback_action"],decision["playback_reason"]),("ENABLED","UNPROTECTED_MEDIA"))
 def test_unprotected_uhd_needs_no_key_database_when_structural_support_exists(self):
  decision=OPTICAL.playback_decision(state("UHD_BLURAY_VIDEO","UNPROTECTED"),capability("NOT_AVAILABLE"));self.assertEqual(decision["playback_action"],"ENABLED")
 def test_protected_bluray_provider_available_enables(self):
  self.assertEqual(OPTICAL.playback_decision(state(),capability("AVAILABLE"))["playback_action"],"ENABLED")
 def test_protected_bluray_not_configured_disables(self):
  self.assertEqual(OPTICAL.playback_decision(state(),capability("NOT_CONFIGURED"))["playback_reason"],"PROTECTED_SUPPORT_NOT_CONFIGURED")
 def test_protected_bluray_not_available_disables(self):
  self.assertEqual(OPTICAL.playback_decision(state(),capability("NOT_AVAILABLE"))["playback_action"],"DISABLED")
 def test_protected_bluray_blocked_disables(self):
  self.assertEqual(OPTICAL.playback_decision(state(),capability("BLOCKED"))["playback_action"],"DISABLED")
 def test_protected_uhd_uses_same_capability_gate(self):
  self.assertEqual(OPTICAL.playback_decision(state("UHD_BLURAY_VIDEO"),capability("AVAILABLE"))["playback_action"],"ENABLED")
 def test_unknown_protection_is_conservatively_disabled(self):
  decision=OPTICAL.playback_decision(state(protection="UNKNOWN"),capability("AVAILABLE"));self.assertEqual((decision["playback_action"],decision["playback_reason"]),("DISABLED","PROTECTION_UNKNOWN"))
 def test_libbdplus_absence_does_not_block_generic_authorization(self):
  self.assertEqual(OPTICAL.playback_decision(state(),capability("AVAILABLE",bdplus="NOT_AVAILABLE"))["playback_action"],"ENABLED")

class ProtectionMetadata(unittest.TestCase):
 def test_mounted_aacs_metadata_marks_protected_without_reading_content(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);(root/"AACS").mkdir();self.assertEqual(OPTICAL._protection_state({"mountpoints":[str(root)]}),"PROTECTED")
 def test_mounted_bdmv_without_aacs_marks_unprotected(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);(root/"BDMV").mkdir();(root/"BDMV/index.bdmv").touch();self.assertEqual(OPTICAL._protection_state({"mountpoints":[str(root)]}),"UNPROTECTED")

class MenuAndDispatcher(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=pathlib.Path(self.temp.name)
  (self.home/".config/openhtpc/runtime").mkdir(parents=True);(self.home/".local/state/openhtpc").mkdir(parents=True)
  self.icons=tuple(PAYLOAD/"assets/ui"/name for name in ("media.png","media.png","eject.png","retour.png"))
 def write(self,optical_state,model):
  (self.home/".local/state/openhtpc/optical-current.json").write_text(json.dumps(optical_state))
  (self.home/".config/openhtpc/runtime/capabilities.json").write_text(json.dumps({"optical":{"protected_media":model}}))
 def menu(self,optical_state):return SESSION.disc_menu_entries(optical_state,PAYLOAD,self.icons,self.home)
 def sheet_menu(self,optical_state,install=PAYLOAD):
  data={"state":optical_state,"title":"FIXTURE","metadata":{"status":"NOT_CONFIGURED"},"artwork":self.icons[0],"duration":None}
  return DISC_SHEET.write_menu(self.home,install,data).read_text()
 def enable(self,install=PAYLOAD):REGISTRY.set_enabled(self.home,install,"plugin.bluray",True)
 def test_disabled_action_is_not_emitted_and_clear_reason_is_shown(self):
  self.enable();current=state();self.write(current,capability("NOT_CONFIGURED"));text=self.menu(current)
  self.assertNotIn("openhtpc-play-optical",text);self.assertIn("DIAGNOSTIC",text);self.assertIn("ÉJECTER",text);self.assertIn("RETOUR",text)
 def test_available_action_is_generation_bound(self):
  self.enable();current=state();self.write(current,capability("AVAILABLE"));text=self.menu(current)
  self.assertIn("openhtpc-play-optical --device /dev/sr0 --generation 7",text);self.assertIn("openhtpc-play-optical",self.sheet_menu(current))
 def test_forged_or_stale_action_is_refused_server_side(self):
  current=state();self.write(current,capability("NOT_AVAILABLE"))
  unavailable=OPTICAL.playback_action_token(current,capability("NOT_AVAILABLE"))
  with self.assertRaisesRegex(ValueError,"OPTICAL_PLAYBACK_PROTECTED_SUPPORT_NOT_AVAILABLE"):DISPATCH.authorize(self.home,PAYLOAD,"/dev/sr0",7,unavailable,lambda _device:True)
  self.write(current,capability("AVAILABLE"))
  token=OPTICAL.playback_action_token(current,capability("AVAILABLE"))
  with self.assertRaisesRegex(ValueError,"STALE_OPTICAL_GENERATION"):DISPATCH.authorize(self.home,PAYLOAD,"/dev/sr0",6,token,lambda _device:True)
  with self.assertRaisesRegex(ValueError,"OPTICAL_DEVICE_MISMATCH"):DISPATCH.authorize(self.home,PAYLOAD,"/dev/sr1",7,token,lambda _device:True)
 def test_next_menu_generation_reflects_capability_refresh(self):
  self.enable();current=state();self.write(current,capability("NOT_CONFIGURED"));before=self.menu(current)
  self.write(current,capability("AVAILABLE"));after=self.menu(current)
  self.assertNotIn("openhtpc-play-optical",before);self.assertIn("openhtpc-play-optical",after)
  self.assertIn("protected_capability_signature",(PAYLOAD/"openhtpc-home.py").read_text())
 def test_physically_observed_disabled_plugin_withholds_bluray_play_action(self):
  current={**state(),"playable":False,"playback_status":"PLUGIN_REQUIRED"};self.write(current,capability("AVAILABLE"))
  plugin=next(item for item in REGISTRY.registry(self.home,PAYLOAD)["plugins"] if item["id"]=="plugin.bluray")
  self.assertEqual(plugin["state"],"DISABLED")
  text=self.menu(current);self.assertNotIn("LIRE LE BLU-RAY",text);self.assertNotIn("openhtpc-play-optical",text);self.assertNotIn("openhtpc-play-optical",self.sheet_menu(current))
 def test_broken_plugin_withholds_bluray_play_action(self):
  install=self.home/"broken-install";install.mkdir();shutil.copy2(PAYLOAD/"VERSION",install/"VERSION");shutil.copy2(PAYLOAD/"openhtpc-core.py",install/"openhtpc-core.py");shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",install/"openhtpc-plugin-registry.py")
  plugin=install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",plugin);source=(plugin/"shadow.py").read_text();(plugin/"shadow.py").write_text(source.replace('"playback_reason":reason','"playback_reason":"INVALID"'))
  self.enable(install);current=state();self.write(current,capability("AVAILABLE"));text=SESSION.disc_menu_entries(current,install,self.icons,self.home)
  self.assertNotIn("LIRE LE BLU-RAY",text);self.assertNotIn("openhtpc-play-optical",text)
 def test_absent_plugin_withholds_bluray_play_action(self):
  install=self.home/"absent-install";install.mkdir();shutil.copy2(PAYLOAD/"VERSION",install/"VERSION");shutil.copy2(PAYLOAD/"openhtpc-core.py",install/"openhtpc-core.py");shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",install/"openhtpc-plugin-registry.py")
  current=state();self.write(current,capability("AVAILABLE"));text=SESSION.disc_menu_entries(current,install,self.icons,self.home)
  self.assertNotIn("LIRE LE BLU-RAY",text);self.assertNotIn("openhtpc-play-optical",text)
 def test_available_uhd_action_remains_generation_bound(self):
  self.enable();current=state("UHD_BLURAY_VIDEO");self.write(current,capability("AVAILABLE"));text=self.menu(current)
  self.assertIn("LIRE LE UHD BLU-RAY",text);self.assertIn("openhtpc-play-optical --device /dev/sr0 --generation 7",text)
 def test_dvd_action_remains_core_owned(self):
  current=state("DVD_VIDEO","UNPROTECTED");self.write(current,capability("NOT_AVAILABLE"));text=self.menu(current)
  self.assertIn("LIRE LE DVD",text);self.assertIn("openhtpc-play-dvd",text);self.assertNotIn("openhtpc-play-optical",text)

class PhaseBoundary(unittest.TestCase):
 def test_no_network_or_key_acquisition_code_was_added(self):
  code="\n".join((PAYLOAD/name).read_text() for name in ("openhtpc-optical.py","openhtpc-play-optical"))
  for forbidden in ("urlopen(","requests.","curl ","wget ","download_keydb","fetch_keys"):
   self.assertNotIn(forbidden,code.lower())
 def test_dispatcher_delegates_only_after_authorization(self):
  code=(PAYLOAD/"openhtpc-play-optical").read_text();self.assertIn("authorize(home,install",code);self.assertIn("openhtpc-protected-optical-backend.py",code)

if __name__=="__main__":unittest.main()
