#!/usr/bin/env python3
"""O1 Dev4 presentation convergence, Blu-ray-family TMDb and validator tests."""
import hashlib,importlib.machinery,importlib.util,json,os,pathlib,subprocess,tarfile,tempfile,unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";TOOLS=ROOT/"tools"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 if spec is None:spec=importlib.util.spec_from_loader(name,importlib.machinery.SourceFileLoader(name,str(path)))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
optical=load("dev4_optical",PAYLOAD/"openhtpc-optical.py")
session=load("dev4_session",PAYLOAD/"openhtpc-session-engine.py")
tmdb=load("dev4_tmdb",PAYLOAD/"openhtpc-tmdb.py")
validator=load("dev4_validator",PAYLOAD/"openhtpc-validator")
view=load("dev4_view",PAYLOAD/"openhtpc-disc-view.py")

def state(generation,canonical,legacy,title=None):
 value=optical._state(canonical,"/dev/fixture",legacy,uhd_status="UNKNOWN")
 if title:value["volume_label"]=title
 value["generation"]=generation;value["ui_state_hash"]=optical.ui_state_hash(value);return value

class PresentationConvergence(unittest.TestCase):
 def test_disc_view_contains_transient_python_failures(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);state_dir=home/".local/state/openhtpc";state_dir.mkdir(parents=True)
   (state_dir/"optical-current.json").write_text(json.dumps({"generation":3,"canonical_state":"BLURAY_VIDEO"}))
   with mock.patch.object(view,"metadata_for",side_effect=RuntimeError("physical-race")),mock.patch.object(view.optical_model,"trace_event") as trace,mock.patch.object(view.argparse.ArgumentParser,"parse_args",return_value=type("Args",(),{"home":home,"enrich":False,"disc_id":None,"generation":3})()):
    self.assertEqual(view.main(),0);self.assertEqual(trace.call_args.args[1],"PRESENTATION_FAILED")
 def test_exact_physical_sequence_acknowledges_every_generation(self):
  sequence=((42,"DVD_VIDEO","DVD","DVD A"),(43,"DRIVE_PRESENT_NO_MEDIA","EMPTY",None),(44,"BLURAY_FAMILY","BLURAY","COLOMBIANA"),(45,"DRIVE_PRESENT_NO_MEDIA","EMPTY",None),(46,"BLURAY_FAMILY","BLURAY","SECOND DISC"),(47,"DRIVE_PRESENT_NO_MEDIA","EMPTY",None))
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw)
   for generation,canonical,legacy,title in sequence:
    current=state(generation,canonical,legacy,title);optical.atomic_json(home/".local/state/openhtpc/optical-current.json",current)
    icon=PAYLOAD/"assets/ui"/optical.presentation(current)["icon"]
    session.write_live_optical_state(home,current,icon)
    session.publish_generation_fallback(home,PAYLOAD,current,"TEST_FALLBACK")
    sidecar=json.loads((home/".local/state/openhtpc/disc-sheet-state.json").read_text());live=(home/".local/state/openhtpc/flex-optical-state").read_text().splitlines()
    self.assertEqual(sidecar["optical_generation"],generation);self.assertEqual(sidecar["canonical_state"],canonical);self.assertEqual(int(live[5]),generation)
    if canonical=="DRIVE_PRESENT_NO_MEDIA":self.assertNotIn("COLOMBIANA",json.dumps(sidecar)+"\n".join(live))
 def test_same_state_reinsert_generation_is_part_of_home_key_contract(self):
  source=(PAYLOAD/"openhtpc-home.py").read_text()
  self.assertIn('int(st.get("generation", 0) or 0), optical_key()',source)
  self.assertIn('"--regenerate-only"',source)
  self.assertIn("expected_optical_generation=generation",source)
 def test_bounded_fallback_has_matching_image_sidecar_provenance(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);current=state(45,"DRIVE_PRESENT_NO_MEDIA","EMPTY");session.publish_generation_fallback(home,PAYLOAD,current,"TIMEOUT")
   self.assertTrue(session.disc_sheet_is_current(home,current));sidecar=json.loads((home/".local/state/openhtpc/disc-sheet-state.json").read_text());self.assertEqual(sidecar["presentation_state"],"FALLBACK");self.assertEqual(sidecar["error_reason"],"TIMEOUT")

class BlurayFamilyTmdb(unittest.TestCase):
 def test_family_title_has_generation_scoped_cache_and_real_lookup(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture")
   current=state(44,"BLURAY_FAMILY","BLURAY","COLOMBIANA")
   pending=tmdb.disc_metadata(home,current,"COLOMBIANA",enrich=False)
   self.assertEqual(pending["status"],"READY")
   with mock.patch.object(tmdb,"lookup",return_value={"status":"PASS","title":"Colombiana","tmdb_id":1,"confidence":"AUTOMATIC_CONFIDENT_MATCH"}):
    result=tmdb.disc_metadata(home,current,"COLOMBIANA",enrich=True,commit_guard=lambda:True)
   self.assertEqual(result["status"],"PASS");cache=tmdb.cache_path(home,current,"COLOMBIANA");self.assertIn("media-cache/optical",str(cache));self.assertTrue(cache.is_file())
 def test_family_late_result_is_discarded_after_eject(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture")
   current=state(44,"BLURAY_FAMILY","BLURAY","COLOMBIANA")
   with mock.patch.object(tmdb,"lookup",return_value={"status":"PASS","title":"Colombiana","tmdb_id":1,"confidence":"AUTOMATIC_CONFIDENT_MATCH"}):result=tmdb.disc_metadata(home,current,"COLOMBIANA",enrich=True,commit_guard=lambda:False)
   self.assertEqual(result["status"],"STALE_GENERATION");self.assertFalse(tmdb.cache_path(home,current,"COLOMBIANA").exists())
 def test_search_wording_requires_started_status(self):
  source=(PAYLOAD/"openhtpc-disc-view.py").read_text()
  self.assertIn('status in {"PENDING","STARTED"}',source);self.assertIn("La fiche optique est prête",source)

class ValidatorHardening(unittest.TestCase):
 def env(self,home,lab):return {**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_VALIDATOR_ROOT":str(lab),"OPENHTPC_VALIDATOR_DISABLE_UPLOAD":"1"}
 def test_physical_47_vs_44_is_detected_and_captured(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);lab=home/"lab";runtime=home/".local/state/openhtpc";runtime.mkdir(parents=True)
   (runtime/"optical-current.json").write_text(json.dumps({"generation":47,"canonical_state":"DRIVE_PRESENT_NO_MEDIA","state":"EMPTY","device":"/dev/sr0"}))
   (runtime/"disc-sheet-state.json").write_text(json.dumps({"optical_generation":44,"canonical_state":"BLURAY_FAMILY"}))
   (runtime/"flex-optical-state").write_text("Blu-ray / UHD - COLOMBIANA\n/icon\nBLURAY\n/dev/sr0\nCOLOMBIANA\n44\n0\n")
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"observe","optical","--once"],env=self.env(home,lab),text=True,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,1,result.stdout+result.stderr);self.assertIn("PRESENTATION_GENERATION_STALE",result.stdout);self.assertTrue(list((lab/"outbox").glob("openhtpc-validator-failure-*.tar.gz")))
   status=json.loads((lab/"state/observer-status.json").read_text());self.assertEqual(status["last_canonical_generation"],47);self.assertEqual(status["last_presentation_generation"],44);self.assertEqual(status["last_flex_generation"],44);self.assertFalse(status["running"])
 def test_empty_connected_drive_is_a_udev_candidate(self):
  current={"device":"/dev/sr0","canonical_state":"DRIVE_PRESENT_NO_MEDIA"}
  with mock.patch.object(validator,"run",return_value=subprocess.CompletedProcess([],0,'{"blockdevices":[]}',"")):
   self.assertIn("/dev/sr0",validator.optical_devices(current))
 def test_capture_forensic_uses_absolute_engine_and_records_evidence(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);lab=home/"OPENHTPC-VALIDATOR";install=home/".local/lib/openhtpc";install.mkdir(parents=True);state_dir=home/".local/state/openhtpc";state_dir.mkdir(parents=True)
   (install/"openhtpc-optical.py").write_text("def optical_devices(): return []\ndef current_state(): return {'canonical_state':'DRIVE_PRESENT_NO_MEDIA','state':'EMPTY','drives':[]}\n")
   current=lab/"current";current.mkdir(parents=True);forensic=current/"openhtpc-optical-forensic.py";forensic.write_bytes((TOOLS/"openhtpc-optical-forensic.py").read_bytes());forensic.chmod(0o755)
   (state_dir/"optical-current.json").write_text(json.dumps({"generation":47,"canonical_state":"DRIVE_PRESENT_NO_MEDIA","state":"EMPTY","device":"/dev/sr0"}))
   result=subprocess.run([str(PAYLOAD/"openhtpc-validator"),"capture","--reason","PATH_TEST"],env=self.env(home,lab),text=True,capture_output=True,timeout=30)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr);bundle=next((lab/"outbox").glob("openhtpc-validator-failure-*.tar.gz"))
   with tarfile.open(bundle) as archive:
    names=archive.getnames();forensic_name=next(n for n in names if n.endswith("optical-forensic.json"));forensic_text=archive.extractfile(forensic_name).read().decode();self.assertNotIn("FileNotFoundError",forensic_text);self.assertIn("DRIVE_PRESENT_NO_MEDIA",forensic_text);self.assertTrue(any(n.endswith("presentation-files.json") for n in names));self.assertTrue(any(n.endswith("journal-user.txt") for n in names));self.assertTrue(any(n.endswith("journal-openhtpc.txt") for n in names))

if __name__=="__main__":unittest.main()
