#!/usr/bin/env python3
"""Bounded Dev6 TMDb picker and optical sheet presentation contracts."""
import importlib.util,json,pathlib,tempfile,unittest
from unittest import mock
from PIL import Image,ImageFont

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
tmdb=load("dev6_tmdb",PAYLOAD/"openhtpc-tmdb.py")
session=load("dev6_session",PAYLOAD/"openhtpc-session-engine.py")
view=load("dev6_view",PAYLOAD/"openhtpc-disc-view.py")

def optical(generation=12,canonical="BLURAY_FAMILY",title="HANCOCK"):
 return {"generation":generation,"canonical_state":canonical,"state":"BLURAY" if canonical!="DVD_VIDEO" else "DVD",
         "device":"/dev/sr0","volume_label":title,"disc_id":"dvd-1" if canonical=="DVD_VIDEO" else None,
         "uhd_status":"UNKNOWN"}

class TmdbDataFlow(unittest.TestCase):
 def test_single_result_remains_direct_pass(self):
  values={"results":[{"id":1,"title":"Colombiana","release_date":"2011-07-27","poster_path":"/c.jpg","overview":"Résumé","vote_count":50}]}
  response=mock.MagicMock();response.__enter__.return_value=response
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture")
   with mock.patch.object(tmdb.json,"load",return_value=values):result=tmdb.lookup(home,"Colombiana",opener=lambda *a,**k:response)
  self.assertEqual(result["status"],"PASS");self.assertEqual(result["tmdb_id"],1)

 def test_bluray_generation_cache_produces_nonempty_focused_picker(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);state=optical();target=tmdb.cache_path(home,state,"HANCOCK");target.parent.mkdir(parents=True)
   target.write_text(json.dumps({"status":"AMBIGUOUS","candidates":[
    {"tmdb_id":1,"title":"Hancock","release_date":"2008-07-01","poster_path":"/a.jpg"},
    {"tmdb_id":2,"title":"Hancock","release_date":"1963-01-01","poster_path":"/b.jpg"}]}))
   menu=session.disc_menu_entries(state,PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)),home)
  entries=[line for line in menu.splitlines() if line.startswith("Entry")]
  self.assertIn("Hancock  ·  2008",entries[0]);self.assertIn("--generation 12",entries[0]);self.assertIn("--tmdb-id 1",entries[0])
  self.assertIn("Hancock  ·  1963",entries[1]);self.assertEqual(entries[0].split("=",1)[0],"Entry1")
  self.assertRegex(entries[-1],r"^Entry\d+=RETOUR;")

 def test_navigation_contract_has_multiple_ordered_selectable_entries(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text()
  self.assertIn("for cand in cached_meta.get(\"candidates\", [])[:3]",source)
  self.assertIn("--tmdb-id {cid}",source)

 def test_selected_result_commits_only_while_generation_is_current(self):
  details={"title":"Hancock","release_date":"2008-07-01","poster_path":None,"overview":"Résumé","credits":{}}
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture");state=optical()
   with mock.patch.object(tmdb,"_fetch_movie_details",return_value=details):
    result=tmdb.commit_binding(home,state,1,title="HANCOCK",commit_guard=lambda:True)
   self.assertEqual(result["status"],"PASS");self.assertEqual(json.loads(tmdb.cache_path(home,state,"HANCOCK").read_text())["tmdb_id"],1)

 def test_late_selection_is_rejected_and_does_not_restore_old_metadata(self):
  details={"title":"Old film","release_date":"2008-01-01","poster_path":None,"credits":{}}
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);token=home/".config/openhtpc/secrets/tmdb-token";token.parent.mkdir(parents=True);token.write_text("fixture");state=optical()
   with mock.patch.object(tmdb,"_fetch_movie_details",return_value=details):result=tmdb.commit_binding(home,state,1,title="HANCOCK",commit_guard=lambda:False)
   self.assertEqual(result["status"],"STALE_GENERATION");self.assertFalse(tmdb.cache_path(home,state,"HANCOCK").exists())

 def test_eject_or_new_generation_invalidates_picker_cache_identity(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);old=tmdb.cache_path(home,optical(12),"HANCOCK")
   self.assertIsNone(tmdb.cache_path(home,{"generation":13,"canonical_state":"DRIVE_PRESENT_NO_MEDIA"},"HANCOCK"))
   self.assertNotEqual(old,tmdb.cache_path(home,optical(14),"HANCOCK"))

class OpticalSheetPolish(unittest.TestCase):
 def test_canonical_badge_mapping(self):
  self.assertEqual({key:view.MEDIA_PROFILES[key]["badge"] for key in view.MEDIA_PROFILES},{
   "DVD_VIDEO":"DVD VIDÉO","BLURAY_VIDEO":"BLU-RAY","UHD_BLURAY_VIDEO":"ULTRA HD BLU-RAY",
   "BLURAY_FAMILY":"BLU-RAY / UHD","UNKNOWN_OPTICAL_MEDIA":"MÉDIA OPTIQUE"})

 def test_family_text_badge_is_poster_attached_with_real_poster(self):
  font_path=PAYLOAD/"flex/assets/fonts/OpenSans-Regular.ttf";font=lambda n:ImageFont.truetype(str(font_path),n)
  image=Image.new("RGBA",(1920,1080),(0,0,0,0));result=view._draw_text_badge_overlay(image,view.MEDIA_PROFILES["BLURAY_FAMILY"],font)
  self.assertIs(result,image);self.assertIsNotNone(image.getbbox());self.assertLess(image.getbbox()[0],520)

 def test_badge_and_metadata_have_distinct_layout_contract(self):
  source=(PAYLOAD/"openhtpc-disc-view.py").read_text()
  self.assertIn("_draw_text_badge_overlay(base,media_prof,font)",source)
  self.assertIn('d.text((585,y+3),"  •  ".join(bits)',source)

 def test_family_status_is_information_not_action(self):
  menu=session.disc_menu_entries(optical(),PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)))
  self.assertNotIn("DISQUE BLU-RAY DÉTECTÉ",menu);self.assertNotIn("Type exact",menu)
  self.assertIn("ÉJECTER",menu);self.assertIn("RETOUR",menu)
  source=(PAYLOAD/"openhtpc-disc-view.py").read_text();self.assertIn('"BLU-RAY / UHD DÉTECTÉ"',source);self.assertIn('"Type exact non déterminé"',source)

 def test_dvd_actions_remain_unchanged(self):
  menu=session.disc_menu_entries(optical(canonical="DVD_VIDEO",title="FILM"),PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)))
  for label in ("LIRE LE DVD","MODE VIDÉO : PURE","ÉJECTER","RETOUR"):self.assertIn(label,menu)

if __name__=="__main__":unittest.main()
