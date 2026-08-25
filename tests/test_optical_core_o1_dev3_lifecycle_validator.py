#!/usr/bin/env python3
"""Dev3 lifecycle, cancellation, provenance and validator automation tests."""
import importlib.util,json,os,pathlib,subprocess,tarfile,tempfile,unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
optical=load("dev3_optical",PAYLOAD/"openhtpc-optical.py");session=load("dev3_session",PAYLOAD/"openhtpc-session-engine.py");tmdb=load("dev3_tmdb",PAYLOAD/"openhtpc-tmdb.py")
def cp(command,code=0,out=""):return subprocess.CompletedProcess(command,code,out,"")
def family(title):return optical._state("BLURAY_FAMILY","/dev/fixture","BLURAY",volume_label=title,uhd_status="UNKNOWN",detection_evidence=["UDEV_MMC_BD_MEDIA"])

class Lifecycle(unittest.TestCase):
 def test_mmc_bd_converges_directly_without_lsdvd_or_initializing(self):
  calls=[]
  def runner(command):
   calls.append(command)
   if command[0]=="lsblk":return cp(command,out=json.dumps({"blockdevices":[{"name":"fixture","type":"rom","fstype":"udf","label":"COLOMBIANA","mountpoints":[]}]}))
   if command[0]=="udevadm":return cp(command,out="ID_CDROM=1\nID_CDROM_MEDIA=1\nID_CDROM_MEDIA_BD=1\n")
   return cp(command,1)
  with tempfile.TemporaryDirectory() as raw:
   base=pathlib.Path(raw);sysblock=base/"sys";device=sysblock/"fixture/device";device.mkdir(parents=True);(device/"type").write_text("5\n")
   state=optical.refresh_state(base,runner,sysblock)
   self.assertEqual(state["canonical_state"],"BLURAY_FAMILY");self.assertNotEqual(state["state"],"INITIALIZING")
   self.assertNotIn("lsdvd",[call[0] for call in calls])
 def test_empty_family_a_empty_family_b_and_uhd_family_get_fresh_generations(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);states=[]
   for value in (optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/x","EMPTY"),family("Colombiana"),optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/x","EMPTY"),family("Second Film"),optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/x","EMPTY"),family("Physical UHD")):
    states.append(optical.publish(home,value))
   self.assertEqual([item["generation"] for item in states],list(range(1,7)))
   self.assertNotIn("Colombiana",json.dumps(states[-1]));self.assertEqual(states[-1]["canonical_state"],"BLURAY_FAMILY")
 def test_eject_clears_initializing_title_artwork_actions_and_advances(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);old={**family("Colombiana"),"state":"INITIALIZING","canonical_state":"DETECTION_INDETERMINATE","disc_title":"Colombiana"}
   first=optical.publish(home,old);empty=optical.publish(home,optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/x","EMPTY"))
   self.assertGreater(empty["generation"],first["generation"]);self.assertNotIn("disc_title",empty);self.assertNotIn("volume_label",empty)
   menu=session.disc_menu_entries(empty,PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)))
   self.assertNotIn("Colombiana",menu);self.assertNotIn("INITIALISATION",menu)
 def test_disc_sheet_requires_current_generation_provenance(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);(home/".cache/openhtpc").mkdir(parents=True);(home/".local/state/openhtpc").mkdir(parents=True)
   state={**family("Current"),"generation":12,"ui_state_hash":"hash12"};(home/".cache/openhtpc/disc-sheet.png").write_bytes(b"png")
   optical.atomic_json(home/".local/state/openhtpc/disc-sheet-state.json",{"optical_generation":10,"canonical_state":"BLURAY_FAMILY","ui_state_hash":"hash10"})
   self.assertFalse(session.disc_sheet_is_current(home,state))
   optical.atomic_json(home/".local/state/openhtpc/disc-sheet-state.json",{"optical_generation":12,"canonical_state":"BLURAY_FAMILY","ui_state_hash":"hash12"})
   self.assertTrue(session.disc_sheet_is_current(home,state))
 def test_generation_10_tmdb_result_is_rejected_after_generation_12(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("not-read")
   state={"disc_id":"disc-a","generation":10,"duration":100}
   with mock.patch.object(tmdb,"lookup",return_value={"status":"PASS","title":"Colombiana","poster_path":"/poster.jpg"}):
    result=tmdb.disc_metadata(home,state,"Colombiana",enrich=True,commit_guard=lambda:False)
   self.assertEqual(result["status"],"STALE_GENERATION");self.assertTrue(result["stale_discarded"])
   self.assertFalse(any((home/".local/share/openhtpc/media-cache").rglob("metadata.json")))

class Validator(unittest.TestCase):
 def test_apply_latest_verifies_manifest_and_runs_only_declared_update(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);lab=home/"lab";inbox=lab/"inbox";inbox.mkdir(parents=True);source=home/"candidate";payload=source/"payload";payload.mkdir(parents=True)
   (source/"VERSION").write_text("1.1.3-dev3\n");(payload/"VERSION").write_text("1.1.3-dev3\n");(payload/"version.json").write_text(json.dumps({"version":"1.1.3-dev3","build_id":"optical-state-lifecycle-validator-dev3"}))
   update=source/"update.sh";update.write_text("#!/bin/sh\ntouch \"$OPENHTPC_VALIDATOR_ROOT/state/update-ran\"\n");update.chmod(0o755)
   archive=inbox/"candidate.tar.gz"
   with tarfile.open(archive,"w:gz") as output:output.add(source,arcname="candidate")
   digest=__import__("hashlib").sha256(archive.read_bytes()).hexdigest();manifest={"version":"1.1.3-dev3","build":"optical-state-lifecycle-validator-dev3","commit":"fixture","artifact":archive.name,"sha256":digest,"intended_validator_phase":"O1_DEV3","installation_method":"update.sh","required_pre_checks":[["/bin/true"]],"required_post_checks":[["/bin/true"]],"playback_allowed":False,"local_kde_observation_required":True,"stop_openhtpc":False}
   (inbox/"candidate.validation.json").write_text(json.dumps(manifest));env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_VALIDATOR_ROOT":str(lab)}
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"apply-latest"],env=env,text=True,capture_output=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertTrue((lab/"state/update-ran").is_file());self.assertIn("VALIDATOR_APPLY PASS",result.stdout)
 def test_capture_is_one_archive_and_redacts_secret_lines(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);install=home/".local/lib/openhtpc";install.mkdir(parents=True);(install/"version.json").write_text('{"token":"secret-value"}')
   lab=home/"lab";env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_VALIDATOR_ROOT":str(lab),"OPENHTPC_VALIDATOR_DISABLE_UPLOAD":"1"}
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"capture","--reason","TEST"],env=env,text=True,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr);archives=list((lab/"outbox").glob("openhtpc-validator-failure-*.tar.gz"));self.assertEqual(len(archives),1)
   with tarfile.open(archives[0]) as bundle:
    version=next(member for member in bundle.getmembers() if member.name.endswith("installed-version.json"));text=bundle.extractfile(version).read().decode()
   self.assertNotIn("secret-value",text);self.assertIn("[REDACTED]",text)
 def test_observer_captures_objective_stale_eject_presentation(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);state=home/".local/state/openhtpc";state.mkdir(parents=True)
   (state/"optical-current.json").write_text(json.dumps({"generation":11,"canonical_state":"DRIVE_PRESENT_NO_MEDIA","state":"EMPTY"}))
   (state/"disc-sheet-state.json").write_text(json.dumps({"optical_generation":10,"canonical_state":"BLURAY_FAMILY"}))
   lab=home/"lab";env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_VALIDATOR_ROOT":str(lab),"OPENHTPC_VALIDATOR_DISABLE_UPLOAD":"1"}
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"observe","optical","--once"],env=env,text=True,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,1);self.assertIn("PRESENTATION_GENERATION_STALE",result.stdout)
   self.assertEqual(len(list((lab/"outbox").glob("openhtpc-validator-failure-*.tar.gz"))),1)
 def test_observer_bounds_initializing_and_captures_before_changes(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);state=home/".local/state/openhtpc";state.mkdir(parents=True)
   (state/"optical-current.json").write_text(json.dumps({"generation":7,"canonical_state":"DETECTION_INDETERMINATE","state":"INITIALIZING","disc_title":"Frozen"}))
   lab=home/"lab";env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_VALIDATOR_ROOT":str(lab),"OPENHTPC_VALIDATOR_DISABLE_UPLOAD":"1"}
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"observe","optical","--once","--timeout","0"],env=env,text=True,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,1);self.assertIn("INITIALIZING_TIMEOUT",result.stdout)
   self.assertTrue(list((lab/"outbox").glob("openhtpc-validator-failure-*.tar.gz")))

if __name__=="__main__":unittest.main()
