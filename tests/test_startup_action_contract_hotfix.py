#!/usr/bin/env python3
"""P0 startup action-contract regression for dynamic optical HOME labels."""
import importlib.util,pathlib,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("startup_hotfix_ui",ROOT/"payload/openhtpc-ui.py")
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)

def model(label,optical_action=":submenu DISQUE"):
 return f"""[OPENHTPC]
Entry1={label};/icon;{optical_action}
Entry2=ÉJECTER;/icon;:fork true
Entry3=MÉDIA;/icon;:submenu MEDIA
Entry4=SYSTÈME;/icon;:submenu SYSTEME
Entry5=ÉTEINDRE;/icon;:submenu ALIMENTATION
[SYSTEME]
Entry1=RETOUR;/icon;:back
[ALIMENTATION]
Entry1=QUITTER OPENHTPC;/icon;:fork true
Entry2=ÉTEINDRE LE PC;/icon;systemctl poweroff
Entry3=RETOUR;/icon;:back
"""

class StartupActionContract(unittest.TestCase):
 def test_empty_startup_contract(self):self.assertIn("OPENHTPC",ui.validate_config_text(model("LECTEUR · Aucun disque")))
 def test_dvd_startup_contract(self):self.assertIn("OPENHTPC",ui.validate_config_text(model("DVD - FILM")))
 def test_bluray_family_startup_contract(self):self.assertIn("OPENHTPC",ui.validate_config_text(model("Blu-ray / UHD - COLOMBIANA")))
 def test_label_cannot_replace_the_real_optical_action(self):
  with self.assertRaisesRegex(ValueError,"UI_ACTION_MISSING:OPENHTPC:LECTEUR"):ui.validate_config_text(model("Blu-ray / UHD - COLOMBIANA",":fork true"))
 def test_start_quit_start_contract(self):
  first=ui.validate_config_text(model("Blu-ray / UHD - COLOMBIANA"));self.assertIn("QUITTER OPENHTPC",first["ALIMENTATION"])
  second=ui.validate_config_text(model("LECTEUR · Aucun disque"));self.assertIn("OPENHTPC",second)

if __name__=="__main__":unittest.main()
