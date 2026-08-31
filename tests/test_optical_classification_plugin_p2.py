from __future__ import annotations
import importlib.util,inspect,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="01736c3e23ed3ba505f0d3049aab81f5f7c007ca"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
OPTICAL=load("classification_p2_optical",PAYLOAD/"openhtpc-optical.py");REGISTRY=load("classification_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("classification_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def info(bluray=True,aacs=False,aacs_handled=False,bdplus=False,bdplus_handled=False):
 return {"bluray_detected":bluray,"aacs_detected":aacs,"aacs_handled":aacs_handled,"bdplus_detected":bdplus,"bdplus_handled":bdplus_handled,"probe_open_succeeded":False}
def facts(*,bd=True,header=None,source=None,library=None,structural="UNKNOWN"):
 fragment=OPTICAL.core_normalize_libbluray_primitives(library)
 return OPTICAL.normalized_bluray_probe_facts(bd_detected=bd,header=header,header_source=source,libbluray_fragment=fragment,structural_protection=structural)

class ContractsAndEquivalence(unittest.TestCase):
 def equivalent(self,value):
  self.assertTrue(OPTICAL.valid_bluray_probe_facts(value));core=OPTICAL.classify_bluray_probe_facts(value);plugin=PLUGIN.classify_probe_facts(value)
  self.assertEqual(plugin,core);self.assertTrue(OPTICAL.valid_bluray_classification(plugin));return plugin
 def test_valid_and_malformed_raw_contract(self):
  self.assertTrue(OPTICAL.valid_bluray_probe_facts(facts()));self.assertFalse(OPTICAL.valid_bluray_probe_facts({"bluray_detected":True}))
 def test_valid_malformed_and_unknown_result(self):
  value=self.equivalent(facts(library=info()));self.assertFalse(OPTICAL.valid_bluray_classification({"owned":True}));self.assertFalse(OPTICAL.valid_bluray_classification({**value,"exact_type":"LASERDISC"}))
 def test_no_evidence(self):self.assertFalse(self.equivalent(facts(bd=False))["owned"])
 def test_bluray_family_only(self):
  value=self.equivalent(facts(library=info()));self.assertEqual((value["media_family"],value["exact_type"],value["canonical_state"]),("BLURAY","UNKNOWN","BLURAY_FAMILY"))
 def test_standard_bluray_library_and_structural_headers(self):
  library=self.equivalent(facts(header="INDX0200",source="LIBBLURAY",library=info()));structural=self.equivalent(facts(header="INDX0100",source="DISC_STRUCTURE",structural="UNPROTECTED"))
  self.assertEqual(library["exact_type"],"BLURAY");self.assertEqual(structural["exact_type"],"BLURAY")
 def test_uhd_proof_from_each_acquisition_source(self):
  for source,library in (("LIBBLURAY",info()),("DISC_STRUCTURE",None)):
   value=self.equivalent(facts(header="INDX0300",source=source,library=library));self.assertEqual((value["exact_type"],value["canonical_state"]),("UHD_BLURAY","UHD_BLURAY_VIDEO"))
 def test_noncanonical_uhd_hints_are_not_contract_fields(self):
  expected=self.equivalent(facts(library=info()))
  for key,value in (("codec","HEVC"),("height",2160),("resolution","3840x2160"),("hdr",True),("dolby_vision",True),("volume_label","UHD"),("title","MOVIE 4K")):
   altered={**facts(library=info()),key:value};self.assertFalse(OPTICAL.valid_bluray_probe_facts(altered));self.assertEqual(self.equivalent(facts(library=info())),expected)
 def test_aacs_detection_and_handled_are_separate(self):
  for handled in (True,False):
   value=self.equivalent(facts(library=info(aacs=True,aacs_handled=handled)));self.assertEqual((value["protection"],value["protection_mechanisms"]),("PROTECTED",["AACS"]))
 def test_bdplus_detection_and_handled_are_separate(self):
  for handled in (True,False):
   value=self.equivalent(facts(library=info(bdplus=True,bdplus_handled=handled)));self.assertEqual((value["protection"],value["protection_mechanisms"]),("PROTECTED",["BDPLUS"]))
 def test_aacs_and_bdplus(self):self.assertEqual(self.equivalent(facts(library=info(aacs=True,bdplus=True)))["protection_mechanisms"],["AACS","BDPLUS"])
 def test_reliable_absence_and_insufficient_evidence(self):
  self.assertEqual(self.equivalent(facts(library=info()))["protection"],"UNPROTECTED");self.assertEqual(self.equivalent(facts())["protection"],"UNKNOWN")
 def test_libbluray_precedence_and_structural_fallback(self):
  library=self.equivalent(facts(library=info(),structural="PROTECTED"));fallback=self.equivalent(facts(structural="PROTECTED"))
  self.assertEqual((library["classification_source"],library["protection"]),("LIBBLURAY","UNPROTECTED"));self.assertEqual((fallback["classification_source"],fallback["protection"]),("DISC_STRUCTURE","PROTECTED"))
 def test_partial_probe_is_conservative(self):
  value=self.equivalent(facts(library=info(bluray=False)));self.assertEqual((value["protection"],value["classification_source"],value["classification_confidence"]),("UNKNOWN","LIBBLURAY","PARTIAL"))
 def test_source_availability_combinations(self):
  self.assertEqual(self.equivalent(facts(library=info()))["classification_source"],"LIBBLURAY");self.assertEqual(self.equivalent(facts(structural="UNPROTECTED"))["classification_source"],"DISC_STRUCTURE");self.assertEqual(self.equivalent(facts())["classification_source"],"UNKNOWN")
 def test_history_capability_and_keydb_are_not_inputs(self):
  value=facts(header="INDX0300",source="DISC_STRUCTURE",structural="UNKNOWN");expected=self.equivalent(value)
  for forbidden in ("last_attempt","OPEN_SUCCESS","OPEN_FAILED","provider_state","keydb_state"):
   self.assertNotIn(forbidden,value);self.assertEqual(self.equivalent(value),expected)

class Authority(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev10\n")
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def test_disabled_selects_core(self):self.assertEqual(OPTICAL.selected_bluray_classification(self.home,self.install,facts(library=info()))[0],"CORE_FALLBACK")
 def test_enabled_selects_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=OPTICAL.selected_bluray_classification(self.home,self.install,facts(header="INDX0300",source="LIBBLURAY",library=info()));self.assertEqual((authority,value["exact_type"]),("PLUGIN_P2","UHD_BLURAY"))
 def test_enabled_classifier_flows_through_core_probe_and_publication(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True)
  def runner(command):
   if command[0]=="lsblk":return subprocess.CompletedProcess(command,0,json.dumps({"blockdevices":[{"fstype":"udf","label":"DISC","mountpoints":[]}]}),"")
   if command[0]=="udevadm":return subprocess.CompletedProcess(command,0,"ID_CDROM_MEDIA=1\nID_CDROM_MEDIA_BD=1\n","")
   return subprocess.CompletedProcess(command,1,"","")
  state=OPTICAL.probe_device(pathlib.Path("/dev/sr0"),runner,lambda _block:("INDX0300","BDMV/index.bdmv"),lambda _block:"UNKNOWN",lambda _device:info(),home=self.home,install=self.install)
  self.assertEqual((state["classification_authority"],state["canonical_state"]),("PLUGIN_P2","UHD_BLURAY_VIDEO"));published=OPTICAL.publish(self.home,state,generation=7)
  self.assertEqual(json.loads((self.home/".local/state/openhtpc/optical-current.json").read_text()),published)
 def test_broken_or_mismatch_uses_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);source=(self.plugin/"shadow.py").read_text();(self.plugin/"shadow.py").write_text(source.replace('"exact_type":exact','"exact_type":"LASERDISC"'))
  authority,value=OPTICAL.selected_bluray_classification(self.home,self.install,facts(header="INDX0300",source="LIBBLURAY",library=info()));self.assertEqual((authority,value["exact_type"]),("CORE_FALLBACK","UHD_BLURAY"))
 def test_malformed_raw_facts_fall_back_conservatively(self):
  authority,value=OPTICAL.selected_bluray_classification(self.home,self.install,{"bluray_detected":True});self.assertEqual(authority,"CORE_FALLBACK");self.assertFalse(value["owned"])

class Boundaries(unittest.TestCase):
 def test_classifier_is_pure_and_has_no_forbidden_io(self):
  source=inspect.getsource(PLUGIN.classify_probe_facts).lower()
  for marker in ("pathlib","subprocess","os.","udev","/dev/","bdmv","indx0300","ctypes","find_library","bd_get_disc_info","libaacs_detected","libbdplus_detected","keydb","open(","stat(","write(","socket","http://","https://","curl","wget","exec(","eval("):
   self.assertNotIn(marker,source)
 def test_raw_contract_contains_no_locations_or_history(self):
  value=facts(header="INDX0300",source="DISC_STRUCTURE");self.assertFalse(any(word in key for key in value for word in ("path","device","mount","history","attempt","keydb")))
 def test_core_probe_and_publication_remain_authoritative(self):
  source=(PAYLOAD/"openhtpc-optical.py").read_text();self.assertIn('runner(["udevadm"',source);self.assertIn("_libbluray_disc_info",source);self.assertIn('atomic_json(home/".local/state/openhtpc/optical-current.json",value)',source)
  self.assertNotIn("atomic_json",inspect.getsource(PLUGIN.classify_probe_facts))
 def test_production_security_and_media_sources_unchanged(self):
  names=("openhtpc-play-optical","openhtpc-protected-optical-backend.py","openhtpc-session-engine.py","openhtpc-disc-sheet.py","openhtpc-disc-view.py","openhtpc-play-dvd","openhtpc-play","openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-playback-policy.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_prior_p2_contracts_remain_equivalent(self):
  optical={"canonical_state":"UHD_BLURAY_VIDEO","protection":"PROTECTED"};snapshot={"status":"AVAILABLE","dependencies":{"libbluray":{"status":"AVAILABLE"}}};presentation=OPTICAL.presentation(optical)
  self.assertEqual(PLUGIN.presentation_descriptor(optical)["badge_key"],"UHD_BLURAY");self.assertEqual(PLUGIN.playback_decision(optical,snapshot)["playback_action"],"ENABLED");self.assertEqual(PLUGIN.ui_contribution({"owned":True,"display_label":"ULTRA HD BLU-RAY 4K","badge_key":"UHD_BLURAY"},{"owned":True,"playback_action":"ENABLED"})["action_intent"],"PLAY_CURRENT_OPTICAL_MEDIA")

if __name__=="__main__":unittest.main()
