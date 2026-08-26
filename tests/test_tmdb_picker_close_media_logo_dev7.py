#!/usr/bin/env python3
"""Dev7 bounded picker-close and official media-logo contracts."""
import importlib.util,json,pathlib,tempfile,unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
tmdb=load("dev7_tmdb",PAYLOAD/"openhtpc-tmdb.py")
session=load("dev7_session",PAYLOAD/"openhtpc-session-engine.py")
view=load("dev7_view",PAYLOAD/"openhtpc-disc-view.py")

def family(generation=21):
 return {"generation":generation,"canonical_state":"BLURAY_FAMILY","state":"BLURAY","device":"/dev/sr0","volume_label":"HANCOCK","uhd_status":"UNKNOWN"}

class PickerClose(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=pathlib.Path(self.temp.name);self.state=family()
  token=self.home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture")
  self.cache=tmdb.cache_path(self.home,self.state,"HANCOCK");self.cache.parent.mkdir(parents=True)

 def menu(self):return session.disc_menu_entries(self.state,PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)),self.home)

 def test_multi_result_picker_visible_and_selectable(self):
  self.cache.write_text(json.dumps({"status":"AMBIGUOUS","candidates":[{"tmdb_id":1,"title":"Hancock","release_date":"2008-01-01"},{"tmdb_id":2,"title":"Hancock","release_date":"1991-01-01"}]}))
  menu=self.menu();self.assertIn("Hancock  ·  2008",menu);self.assertIn("Hancock  ·  1991",menu);self.assertIn("openhtpc-bind-disc",menu)

 def test_successful_commit_removes_candidates_from_regenerated_disc_menu(self):
  self.cache.write_text(json.dumps({"status":"AMBIGUOUS","candidates":[{"tmdb_id":1,"title":"Hancock"}]}))
  details={"title":"Hancock","release_date":"2008-07-01","poster_path":None,"overview":"Résumé","credits":{}}
  with mock.patch.object(tmdb,"_fetch_movie_details",return_value=details):result=tmdb.commit_binding(self.home,self.state,1,title="HANCOCK",commit_guard=lambda:True)
  self.assertEqual(result["status"],"PASS");menu=self.menu();self.assertNotIn("openhtpc-bind-disc",menu);self.assertNotIn("Hancock  ·",menu)
  self.assertEqual(json.loads(self.cache.read_text())["title"],"Hancock")

 def test_home_watches_generation_scoped_bluray_metadata_transition(self):
  source=(PAYLOAD/"openhtpc-home.py").read_text(encoding="utf-8")
  self.assertIn("tmdb.cache_path(home, st, str(title))",source);self.assertIn("AMBIGUOUS:{c_ids}",source);self.assertIn(":PASS:{data.get('tmdb_id')}",source)
  self.assertNotIn('if not disc_id:\n        return ""',source)

 def test_single_result_contract_unchanged(self):
  self.cache.write_text(json.dumps({"status":"PASS","confidence":"AUTOMATIC_CONFIDENT_MATCH","tmdb_id":7,"title":"Colombiana"}))
  self.assertNotIn("openhtpc-bind-disc",self.menu())

 def test_eject_and_stale_generation_cannot_keep_or_commit_picker(self):
  old=self.cache;self.assertIsNone(tmdb.cache_path(self.home,{"generation":22,"canonical_state":"DRIVE_PRESENT_NO_MEDIA"},"HANCOCK"))
  details={"title":"Old","poster_path":None,"credits":{}}
  with mock.patch.object(tmdb,"_fetch_movie_details",return_value=details):result=tmdb.commit_binding(self.home,self.state,1,title="HANCOCK",commit_guard=lambda:False)
  self.assertEqual(result["status"],"STALE_GENERATION");self.assertFalse(old.exists())

class MediaLogo(unittest.TestCase):
 def test_official_logo_assets_are_distinct_from_fallback_artwork(self):
  for badge,art in (("dvd-media-badge.png","dvd-media.png"),("bluray-media-badge.png","bluray-media.png"),("uhd-bluray-media-badge.png","uhd-bluray-media.png")):
   self.assertTrue((PAYLOAD/"assets/ui"/badge).is_file());self.assertTrue((PAYLOAD/"assets/ui"/art).is_file());self.assertNotEqual(badge,art)

 def test_canonical_visual_mapping_never_upgrades_family_to_uhd(self):
  self.assertEqual(view.MEDIA_PROFILES["DVD_VIDEO"]["logo"],"assets/ui/dvd-media-badge.png")
  self.assertEqual(view.MEDIA_PROFILES["BLURAY_VIDEO"]["logo"],"assets/ui/bluray-media-badge.png")
  self.assertEqual(view.MEDIA_PROFILES["BLURAY_FAMILY"]["logo"],"assets/ui/bluray-media-badge.png")
  self.assertNotEqual(view.MEDIA_PROFILES["BLURAY_FAMILY"]["logo"],view.MEDIA_PROFILES["UHD_BLURAY_VIDEO"]["logo"])

 def test_family_text_truth_and_startup_contract_remain(self):
  source=(PAYLOAD/"openhtpc-disc-view.py").read_text(encoding="utf-8");self.assertIn('"BLU-RAY / UHD DÉTECTÉ"',source);self.assertIn('"Type exact non déterminé"',source)
  menu=session.disc_menu_entries(family(),PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)))
  self.assertIn("ÉJECTER",menu);self.assertIn("RETOUR",menu);self.assertNotIn("Type exact",menu)

if __name__=="__main__":unittest.main()
