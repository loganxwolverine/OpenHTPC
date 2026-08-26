#!/usr/bin/env python3
"""O1 Dev2 canonical presentation truth reproducing physical BD/UHD findings."""
import importlib.util, json, pathlib, shutil, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]; PAYLOAD=ROOT/"payload"
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
optical=load("dev2_optical",PAYLOAD/"openhtpc-optical.py")
session=load("dev2_session",PAYLOAD/"openhtpc-session-engine.py")
sheet=load("dev2_sheet",PAYLOAD/"openhtpc-disc-sheet.py")
view=load("dev2_view",PAYLOAD/"openhtpc-disc-view.py")

def physical_family(**extra):
    return {"canonical_state":"BLURAY_FAMILY","state":"BLURAY","uhd_status":"UNKNOWN",
            "playable":False,"playback_provider":None,"playback_status":"MEDIA_TYPE_INDETERMINATE",
            "device":"/dev/fixture",**extra}

class CanonicalPresentationTruth(unittest.TestCase):
    def test_physical_family_never_claims_specific_provider(self):
        menu=session.disc_menu_entries(physical_family(),PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4)))
        presentation=(PAYLOAD/"openhtpc-disc-view.py").read_text(encoding="utf-8")
        self.assertIn('"BLU-RAY / UHD DÉTECTÉ"',presentation); self.assertIn('"Type exact non déterminé"',presentation)
        self.assertNotIn("DISQUE BLU-RAY DÉTECTÉ",menu); self.assertNotIn("Type exact",menu)
        self.assertIn("ÉJECTER",menu); self.assertIn("RETOUR",menu)
        self.assertNotIn("Plugin Blu-ray requis",menu); self.assertNotIn("Plugin UHD requis",menu)

    def test_uhd_and_4k_title_cannot_upgrade_family_identity(self):
        state=physical_family(volume_label="FILM_4K_UHD",disc_title="ULTRA HD EDITION")
        self.assertEqual(optical.presentation(state)["media_label"],"BLU-RAY / UHD")
        self.assertTrue(session.optical_home_label(state).startswith("Blu-ray / UHD -"))
        self.assertNotIn("Plugin UHD requis",session.disc_menu_entries(state,PAYLOAD,tuple(pathlib.Path(f"i{x}") for x in range(4))))

    def test_family_fallback_is_not_dvd(self):
        media=optical.presentation(physical_family())
        self.assertEqual(media["poster_label"],"BLU-RAY / UHD"); self.assertNotIn("DVD",media["poster_label"])
        self.assertEqual(sheet.model(pathlib.Path("/tmp"),PAYLOAD,physical_family())["artwork"].name,"optical-empty.png")

    def test_exact_bluray_fallback(self):
        state={"canonical_state":"BLURAY_VIDEO","state":"BLURAY"}
        self.assertEqual(optical.presentation(state)["poster_label"],"BLU-RAY")
        self.assertEqual(sheet.model(pathlib.Path("/tmp"),PAYLOAD,state)["artwork"].name,"bluray-media.png")

    def test_exact_uhd_fallback(self):
        state={"canonical_state":"UHD_BLURAY_VIDEO","state":"BLURAY","volume_label":"ordinary"}
        self.assertEqual(optical.presentation(state)["poster_label"],"ULTRA HD BLU-RAY")
        self.assertEqual(sheet.model(pathlib.Path("/tmp"),PAYLOAD,state)["artwork"].name,"uhd-bluray-media.png")

    def test_dvd_fallback_remains_dvd(self):
        state={"canonical_state":"DVD_VIDEO","state":"DVD","device":"/dev/fixture"}
        self.assertEqual(optical.presentation(state)["poster_label"],"DVD")
        self.assertEqual(sheet.model(pathlib.Path("/tmp"),PAYLOAD,state)["artwork"].name,"dvd-media.png")

    def test_tmdb_pending_does_not_change_identity_or_use_poster(self):
        state=physical_family(volume_label="COLOMBIANA_4K_UHD")
        self.assertIsNone(view.committed_poster({"status":"PENDING","poster_file":"wrong.jpg"}))
        self.assertEqual(optical.canonical_state(state),"BLURAY_FAMILY")

    def test_tmdb_no_result_keeps_family_fallback(self):
        state=physical_family()
        self.assertIsNone(view.committed_poster({"status":"NO_RESULT"}))
        self.assertEqual(view.MEDIA_PROFILES[optical.canonical_state(state)]["badge"],"BLU-RAY / UHD")

    def test_tmdb_poster_may_replace_fallback_without_identity_change(self):
        state=physical_family(); metadata={"status":"PASS","poster_file":"poster.jpg","title":"Film"}
        self.assertEqual(view.committed_poster(metadata),"poster.jpg")
        self.assertEqual(optical.canonical_state(state),"BLURAY_FAMILY")

    def test_eject_removes_stale_artwork_and_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            home=pathlib.Path(raw); optical.publish(home,physical_family(disc_title="OLD_UHD"),generation=1)
            empty=optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/fixture","EMPTY")
            current=optical.publish(home,empty,generation=2)
            self.assertNotIn("disc_title",current); self.assertEqual(optical.canonical_state(current),"DRIVE_PRESENT_NO_MEDIA")
            self.assertEqual(optical.presentation(current)["fallback_artwork"],"optical-empty.png")

if __name__=="__main__": unittest.main()
