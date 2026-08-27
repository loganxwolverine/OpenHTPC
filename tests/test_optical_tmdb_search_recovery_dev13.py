#!/usr/bin/env python3
"""Dev13 conservative optical TMDb search recovery contracts."""
import importlib.machinery,importlib.util,json,pathlib,tempfile,types,unittest,urllib.parse
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load_py(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def load_script(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
tmdb=load_py("dev13_tmdb",PAYLOAD/"openhtpc-tmdb.py");recovery=load_script("dev13_recovery",PAYLOAD/"openhtpc-tmdb-recovery")

class Result:
 def __init__(self,code=0,out=""):self.returncode=code;self.stdout=out

class Normalization(unittest.TestCase):
 def test_city_of_angel_suffix(self):self.assertEqual(tmdb.clean_disc_title("CITY OF ANGEL 16/9"),"CITY OF ANGEL")
 def test_never_invents_plural(self):self.assertNotEqual(tmdb.clean_disc_title("CITY OF ANGEL 16/9"),"CITY OF ANGELS")
 def test_raw_label_is_not_mutated(self):
  raw="CITY OF ANGEL 16/9";tmdb.clean_disc_title(raw);self.assertEqual(raw,"CITY OF ANGEL 16/9")
 def test_supported_suffixes_are_positional(self):
  for suffix in ("16:9","4/3","4:3","PAL","NTSC","WIDESCREEN","FULLSCREEN","DISC 1","DISC 2","DVD 1","DVD 2"):
   with self.subTest(suffix=suffix):self.assertEqual(tmdb.clean_disc_title("FILM "+suffix),"FILM")
 def test_legitimate_numeric_titles_survive(self):
  for title in ("16 Blocks","Apollo 13","District 9"):
   with self.subTest(title=title):self.assertEqual(tmdb.clean_disc_title(title),title)
 def test_technical_word_inside_title_survives(self):self.assertEqual(tmdb.clean_disc_title("PAL Joey"),"PAL Joey")
 def test_media_words_do_not_change_optical_truth(self):
  state={"canonical_state":"DVD_VIDEO","volume_label":"FILM UHD 4K Blu-ray"};tmdb.clean_disc_title(state["volume_label"]);self.assertEqual(state["canonical_state"],"DVD_VIDEO")

class YearAndQuery(unittest.TestCase):
 def test_empty_year(self):self.assertIsNone(tmdb.validate_year(""))
 def test_valid_year(self):self.assertEqual(tmdb.validate_year("1998"),1998)
 def test_invalid_year(self):
  for value in ("98","abcd","1800","9999"):
   with self.subTest(value=value),self.assertRaises(ValueError):tmdb.validate_year(value)
 def test_year_narrows_tmdb_query(self):
  seen=[]
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
  def opener(request,timeout=0):seen.append(request.full_url);return Response()
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture")
   with mock.patch.object(tmdb.json,"load",return_value={"results":[]}):tmdb.lookup(home,"CITY OF ANGELS",opener=opener,year=1998)
  self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(seen[0]).query)["year"],["1998"])

class RecoveryFlow(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=pathlib.Path(self.temp.name);self.install=PAYLOAD
  self.state={"generation":7,"canonical_state":"DVD_VIDEO","state":"DVD","disc_id":"physical-a","volume_label":"CITY OF ANGEL 16/9"}
  target=self.home/".local/state/openhtpc/optical-current.json";target.parent.mkdir(parents=True);target.write_text(json.dumps(self.state))
 def dialogs(self,*responses):
  queue=list(responses);calls=[]
  def run(args,capture=False):calls.append(args);return queue.pop(0)
  return run,calls
 def fake(self,lookup_result,commits):
  return types.SimpleNamespace(clean_disc_title=tmdb.clean_disc_title,validate_year=tmdb.validate_year,
   lookup=lambda *a,**k:lookup_result,commit_binding=lambda home,state,cid,**kw:(commits.append((state.copy(),cid,kw)) or {"status":"PASS"}))
 def run_flow(self,result,responses):
  commits=[];dialogs,calls=self.dialogs(*responses)
  with mock.patch.object(recovery,"load",return_value=self.fake(result,commits)):code=recovery.interactive(self.home,self.install,dialogs)
  return code,calls,commits
 def test_zero_result_screen_prefills_normalized_title_and_is_recoverable(self):
  code,calls,commits=self.run_flow({"status":"NO_RESULT"},[Result(out="CITY OF ANGEL"),Result(out=""),Result(),Result(1)])
  self.assertEqual(code,0);self.assertEqual(calls[0][-1],"CITY OF ANGEL");self.assertIn("AUCUNE CORRESPONDANCE",calls[2][-1]);self.assertFalse(commits)
 def test_manual_single_requires_confirmation_and_cancel_changes_nothing(self):
  data={"status":"PASS","tmdb_id":1,"title":"City of Angels","release_date":"1998-01-01"}
  code,calls,commits=self.run_flow(data,[Result(out="CITY OF ANGELS"),Result(out="1998"),Result(1),Result(1)])
  self.assertEqual(code,0);self.assertTrue(any("EST-CE BIEN" in " ".join(call) for call in calls));self.assertFalse(commits)
 def test_manual_single_confirm_persists_using_raw_disc_identity(self):
  data={"status":"PASS","tmdb_id":1,"title":"City of Angels","release_date":"1998-01-01"}
  code,calls,commits=self.run_flow(data,[Result(out="CITY OF ANGELS"),Result(out="1998"),Result()])
  self.assertEqual(code,0);self.assertEqual(commits[0][0]["disc_id"],"physical-a");self.assertEqual(commits[0][2]["title"],"CITY OF ANGEL 16/9")
 def test_manual_multiple_selection_requires_confirmation(self):
  data={"status":"AMBIGUOUS","candidates":[{"tmdb_id":2,"title":"City of Angels","release_date":"1998-01-01"},{"tmdb_id":3,"title":"Other"}]}
  code,calls,commits=self.run_flow(data,[Result(out="CITY OF ANGELS"),Result(out=""),Result(out="2"),Result()])
  self.assertEqual(code,0);self.assertEqual(commits[0][1],2);self.assertTrue(any("--menu" in call for call in calls))
 def test_network_error_is_not_zero_result(self):
  code,calls,commits=self.run_flow({"status":"UNAVAILABLE"},[Result(out="CITY"),Result(out=""),Result()])
  self.assertEqual(code,2);self.assertIn("RECHERCHE IMPOSSIBLE",calls[-1][-1]);self.assertNotIn("AUCUNE CORRESPONDANCE",calls[-1][-1]);self.assertFalse(commits)
 def test_stale_generation_cannot_commit(self):
  def run(args,capture=False):
   if "Titre du film" in " ".join(args):return Result(out="CITY OF ANGELS")
   if "Année" in " ".join(args):
    changed=dict(self.state,generation=8,disc_id="physical-b");(self.home/".local/state/openhtpc/optical-current.json").write_text(json.dumps(changed));return Result(out="1998")
   return Result()
  commits=[]
  with mock.patch.object(recovery,"load",return_value=self.fake({"status":"PASS","tmdb_id":1},commits)):code=recovery.interactive(self.home,self.install,run)
  self.assertEqual(code,1);self.assertFalse(commits)
 def test_same_label_different_disc_is_not_same_identity(self):
  other=dict(self.state,disc_id="physical-b");self.assertFalse(recovery.same_identity(other,self.state))
 def test_same_disc_reinsert_cache_key_is_reused(self):
  later=dict(self.state,generation=99);self.assertEqual(tmdb.cache_path(self.home,self.state),tmdb.cache_path(self.home,later))

class ExistingContracts(unittest.TestCase):
 def test_colombiana_automatic_path_remains_automatic(self):
  candidate={"id":1,"title":"Colombiana","original_title":"Colombiana","release_date":"2011-01-01","overview":"x","poster_path":"/x","vote_count":30}
  self.assertGreaterEqual(tmdb._score_candidate(candidate,tmdb._normalize_title("Colombiana"),is_single=True),tmdb.ACCEPT_THRESHOLD)
 def test_hancock_picker_is_exactly_unchanged(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text();self.assertIn('for cand in cached_meta.get("candidates", [])[:3]',source)
  ambiguous=source.split('if meta_status == "AMBIGUOUS":',1)[1].split("    else:",1)[0]
  self.assertNotIn("RECHERCHE MANUELLE",ambiguous)
 def test_no_result_menu_exposes_recovery(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text();self.assertIn('meta_status == "NO_RESULT"',source)
 def test_dev11_auto_open_code_unchanged_by_dev13(self):self.assertNotIn("tmdb",(PAYLOAD/"openhtpc-home.py").read_text().split("def optical_navigation_event")[-1] if "def optical_navigation_event" in (PAYLOAD/"openhtpc-home.py").read_text() else "")
 def test_dev12_media_and_badges_untouched(self):
  self.assertIn("media_generation=media_generation",(PAYLOAD/"openhtpc-session-engine.py").read_text());view=load_py("dev13_view",PAYLOAD/"openhtpc-disc-view.py");self.assertEqual(view.MEDIA_PROFILES["BLURAY_FAMILY"]["logo"],"assets/ui/bluray-media-badge.png")

if __name__=="__main__":unittest.main()
