from __future__ import annotations
import importlib.util,json,pathlib,shutil,subprocess,tempfile,unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="ab42b1ad3d247ff07268b182ce3c762e0944b564"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
CORE=load("doctor_p2_core",PAYLOAD/"openhtpc-core.py");REGISTRY=load("doctor_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("doctor_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def capability(status="AVAILABLE",bdplus="NOT_AVAILABLE",keydb="DETECTED"):
 return {"status":status,"dependencies":{"libbluray":{"status":"AVAILABLE"},"libaacs":{"status":"AVAILABLE"},"libbdplus":{"status":bdplus}},"external_key_database":{"status":keydb}}
def disc(canonical="BLURAY_VIDEO",protection="PROTECTED",mechanisms=None,source="LIBBLURAY"):
 return {"canonical_state":canonical,"protection":protection,"protection_mechanisms":mechanisms or ["AACS"],"classification_source":source}
def inputs(optical=None,provider=None,attempt=None):return {"protected":provider or capability(),"optical":optical or {},"last_attempt":attempt}

class Equivalence(unittest.TestCase):
 def equivalent(self,value):self.assertEqual(PLUGIN.doctor_rows(value),CORE.core_protected_optical_doctor_rows(value))
 def test_core_and_plugin_baselines(self):
  value=inputs(disc());self.assertTrue(CORE.core_protected_optical_doctor_rows(value));self.assertTrue(PLUGIN.doctor_rows(value));self.equivalent(value)
 def test_no_disc(self):self.equivalent(inputs())
 def test_dvd(self):self.equivalent(inputs(disc("DVD_VIDEO","UNPROTECTED",["NONE"],"DISC_STRUCTURE")))
 def test_unprotected_bluray(self):self.equivalent(inputs(disc(protection="UNPROTECTED",mechanisms=["NONE"])))
 def test_protected_available(self):self.equivalent(inputs(disc(),capability("AVAILABLE")))
 def test_not_configured(self):self.equivalent(inputs(disc(),capability("NOT_CONFIGURED",keydb="NOT_CONFIGURED")))
 def test_not_available(self):self.equivalent(inputs(disc(),capability("NOT_AVAILABLE")))
 def test_blocked(self):
  value=inputs(disc(),capability("BLOCKED"));self.equivalent(value);self.assertTrue(PLUGIN.doctor_rows(value)[0]["blocking"])
 def test_uhd(self):self.equivalent(inputs(disc("UHD_BLURAY_VIDEO")))
 def test_bluray_family_unknown(self):self.equivalent(inputs(disc("BLURAY_FAMILY")))
 def test_protection_unknown(self):self.equivalent(inputs(disc(protection="UNKNOWN",mechanisms=["UNKNOWN"])))
 def test_libbdplus_absent(self):self.equivalent(inputs(disc(),capability(bdplus="NOT_AVAILABLE")))
 def test_key_database_detected_and_not_configured(self):
  self.equivalent(inputs(disc(),capability(keydb="DETECTED")));self.equivalent(inputs(disc(),capability("NOT_CONFIGURED",keydb="NOT_CONFIGURED")))
 def test_open_success_and_failed(self):
  self.equivalent(inputs(disc(),attempt={"status":"OPEN_SUCCESS"}));self.equivalent(inputs(disc(),attempt={"status":"OPEN_FAILED"}))
 def test_open_failure_diagnostics_are_exposed_and_non_blocking(self):
  attempt={"status":"OPEN_FAILED","device":"/dev/sr1","generation":12,"reason":"DISC_OPEN_REFUSED","process_started":True,"exit_code":2,"elapsed_seconds":1.25}
  value=inputs(disc("UHD_BLURAY_VIDEO"),attempt=attempt);self.equivalent(value);rows=PLUGIN.doctor_rows(value)
  statuses={row["label"]:row["status"] for row in rows}
  self.assertEqual(statuses["Protected attempt device"],"/dev/sr1");self.assertEqual(statuses["Protected attempt reason"],"DISC_OPEN_REFUSED")
  self.assertTrue(all(not row["blocking"] for row in rows if row["label"].startswith("Protected attempt") or row["label"]=="Last protected disc attempt"))
 def test_eject_clears_current_but_keeps_history(self):
  value=inputs({"canonical_state":"DRIVE_PRESENT_NO_MEDIA"},attempt={"status":"OPEN_SUCCESS"});self.equivalent(value)
  labels={row["label"] for row in PLUGIN.doctor_rows(value)};self.assertNotIn("Optical media family",labels);self.assertIn("Last protected disc attempt",labels)
 def test_provider_capability_absent(self):self.equivalent({"protected":{},"optical":disc(),"last_attempt":None})

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name)
  self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev4\n")
  (self.install/"version.json").write_text(json.dumps({"version":"test","build_id":"test","build_date":"test"}))
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py")
  self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def registry(self):return REGISTRY.registry(self.home,self.install)
 def test_disabled_withholds_plugin_doctor(self):self.assertEqual(CORE.protected_optical_doctor_projection(self.home,self.install,self.registry(),inputs(disc()))[0],"PLUGIN_UNAVAILABLE")
 def test_enabled_selects_plugin_without_duplicate_rows(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,rows=CORE.protected_optical_doctor_projection(self.home,self.install,self.registry(),inputs(disc()))
  self.assertEqual(authority,"PLUGIN_P2");labels=[row["label"] for row in rows];self.assertEqual(len(labels),len(set(labels)))
 def test_broken_runtime_falls_back_and_marks_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);(self.plugin/"shadow.py").write_text("raise SystemExit(7)\n");registry=self.registry()
  authority,rows=CORE.protected_optical_doctor_projection(self.home,self.install,registry,inputs(disc()));self.assertEqual(authority,"PLUGIN_UNAVAILABLE");self.assertFalse(rows)
  self.assertEqual(registry["plugins"][0]["state"],"BROKEN");self.assertEqual(registry["errors"][-1]["reason"],"PLUGIN_DOCTOR_BROKEN")
 def test_missing_or_malformed_optional_plugin_uses_fallback(self):
  shutil.rmtree(self.plugin);self.assertEqual(CORE.protected_optical_doctor_projection(self.home,self.install,self.registry(),inputs())[0],"PLUGIN_UNAVAILABLE")
 def test_plugin_cannot_change_blocking_semantics(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"blocking":False},\n  {"label":"libaacs"','"blocking":True},\n  {"label":"libaacs"'))
  registry=self.registry();authority,_=CORE.protected_optical_doctor_projection(self.home,self.install,registry,inputs(disc()));self.assertEqual(authority,"PLUGIN_UNAVAILABLE")
 def test_enabled_and_broken_doctor_paths_keep_overall_ready(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);state_dir=self.home/".local/state/openhtpc";state_dir.mkdir(parents=True,exist_ok=True)
  (state_dir/"optical-current.json").write_text(json.dumps(disc()));base={"HARDWARE_PASSPORT_READY":True,"HARDWARE_PASSPORT_PROVENANCE":"CURRENT","VIDEO_RUNTIME_READY":True,
   "AUDIO_RUNTIME_READY":True,"VIDEO_RUNTIME_PROVENANCE":"CURRENT","FLEX_READY":True,"MEDIA_BROWSER_READY":True,"AUTOSTART_READY":True,
   "PLUGIN_REGISTRY_READY":True,"OPTICAL_STATE_INITIALIZED":True,"OPTICAL_DRIVE_PRESENT":False,"DVD_READY":False,"TMDB_CONFIGURED":False,
   "plugins":[],"PROTECTED_OPTICAL_SUPPORT":capability("NOT_CONFIGURED")}
  lifecycle={"ui_instances":0,"monitor_instances":0,"runtime_ownership":"PASS","appliance_state":"STOPPED","crash_loop_state":"PASS","recent_flex_crashes":0}
  def report():
   base["PLUGIN_REGISTRY"]=self.registry()
   with mock.patch.object(CORE,"capability_state",return_value=base),mock.patch.object(CORE,"_runtime_lifecycle",return_value=lifecycle),mock.patch.object(CORE,"graphical_runtime",return_value={"status":"NOT_RUNNING","session":"Wayland","desktop":"KDE","pid":""}),mock.patch.object(CORE,"_dvdcss_status",return_value="NOT_CONFIGURED"),mock.patch.object(CORE,"_plasma_suppression",return_value="INACTIVE"),mock.patch.object(CORE,"_plasma_shell_status",return_value="PASS"),mock.patch.object(CORE.os,"access",return_value=True),mock.patch.object(CORE.shutil,"which",return_value="/usr/bin/mpv"),mock.patch.object(CORE.ctypes.util,"find_library",return_value="libSDL2.so"):
    return CORE.health_report(self.home,self.install)
  enabled=report();self.assertEqual((enabled["overall"],enabled["protected_optical_doctor_authority"]),("READY","PLUGIN_P2"))
  (self.plugin/"shadow.py").write_text("raise SystemExit(3)\n");broken=report();self.assertEqual((broken["overall"],broken["protected_optical_doctor_authority"]),("READY","PLUGIN_UNAVAILABLE"))
  self.assertEqual({item["label"]:item["status"] for item in broken["optional"]}["Blu-ray/UHD"],"BROKEN")

class Boundaries(unittest.TestCase):
 def test_plugin_has_no_probe_keydb_network_playback_ui_or_dispatcher(self):
  source=(PAYLOAD/"plugins/available/plugin.bluray/shadow.py").read_text().lower()
  for marker in ("ctypes","find_library","keydb.cfg","indx0300","bd://","mpv","dispatcher","flex","assets/",".png","subprocess","socket","urlopen","read_text(","read_bytes(","stat(","open("):self.assertNotIn(marker,source)
 def test_discovery_remains_data_only(self):
  source=(PAYLOAD/"openhtpc-plugin-registry.py").read_text().lower();self.assertNotIn("doctor_rows",source)
 def test_production_sources_unchanged(self):
  names=("openhtpc-protected-optical.py","openhtpc-play-dvd","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline,name)

if __name__=="__main__":unittest.main()
