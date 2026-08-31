from __future__ import annotations
import importlib.util,inspect,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="1638455fe12e0439967cd8641b3f8abbef1e5adc"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
OPTICAL=load("normalization_p2_optical",PAYLOAD/"openhtpc-optical.py");REGISTRY=load("normalization_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("normalization_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def primitive(*,bluray=True,aacs=False,aacs_handled=False,bdplus=False,bdplus_handled=False,index=None,complete=True):
 return {"bluray_detected":bluray,"aacs_detected":aacs,"aacs_handled":aacs_handled,"bdplus_detected":bdplus,"bdplus_handled":bdplus_handled,
         "probe_open_succeeded":complete,"bdmv_index_header":index}

class ContractAndEquivalence(unittest.TestCase):
 def equivalent(self,value):
  self.assertTrue(OPTICAL.valid_libbluray_primitives(value));core=OPTICAL.core_normalize_libbluray_primitives(value);plugin=PLUGIN.normalize_libbluray_primitives(value)
  self.assertEqual(plugin,core);self.assertTrue(OPTICAL.valid_libbluray_fragment(plugin));return plugin
 def test_primitive_contract_valid_and_strict(self):
  self.assertTrue(OPTICAL.valid_libbluray_primitives(None));self.assertTrue(OPTICAL.valid_libbluray_primitives(primitive()))
  for value in ({},primitive(bluray=1),{**primitive(),"device":"/dev/sr0"},{**primitive(),"aacs_detected":"yes"}):self.assertFalse(OPTICAL.valid_libbluray_primitives(value))
 def test_output_contract_valid_and_strict(self):
  value=self.equivalent(primitive());self.assertFalse(OPTICAL.valid_libbluray_fragment({}));self.assertFalse(OPTICAL.valid_libbluray_fragment({**value,"media_family":"BLURAY"}));self.assertFalse(OPTICAL.valid_libbluray_fragment({**value,"libbluray_index_version":"0400"}))
 def test_disc_info_unavailable(self):
  value=self.equivalent(None);self.assertFalse(value["libbluray_info_available"]);self.assertIsNone(value["aacs_detected"])
 def test_bluray_detection_true_and_false(self):
  self.assertTrue(self.equivalent(primitive(bluray=True))["libbluray_bluray_detected"]);self.assertFalse(self.equivalent(primitive(bluray=False))["libbluray_bluray_detected"])
 def test_index_versions(self):
  for header,version,available in (("INDX0200","0200",True),("INDX0300","0300",True),(None,"NONE",False),("broken","OTHER",True),("INDX0400","OTHER",True)):
   value=self.equivalent(primitive(index=header));self.assertEqual((value["libbluray_index_version"],value["libbluray_index_available"]),(version,available))
 def test_aacs_detected_and_handled_remain_independent(self):
  for handled in (True,False):
   value=self.equivalent(primitive(aacs=True,aacs_handled=handled));self.assertTrue(value["aacs_detected"]);self.assertIs(value["aacs_handled"],handled)
  self.assertFalse(self.equivalent(primitive())["aacs_detected"])
 def test_bdplus_detected_and_handled_remain_independent(self):
  for handled in (True,False):
   value=self.equivalent(primitive(bdplus=True,bdplus_handled=handled));self.assertTrue(value["bdplus_detected"]);self.assertIs(value["bdplus_handled"],handled)
  self.assertFalse(self.equivalent(primitive())["bdplus_detected"])
 def test_combined_and_partial_facts(self):
  combined=self.equivalent(primitive(aacs=True,bdplus=True));self.assertTrue(combined["aacs_detected"] and combined["bdplus_detected"])
  self.assertFalse(self.equivalent(primitive(complete=False))["libbluray_probe_complete"])
 def test_normalization_does_not_classify(self):
  value=self.equivalent(primitive(aacs=True,index="INDX0300"))
  for field in ("media_family","exact_type","protection","classification_source","classification_confidence"):self.assertNotIn(field,value)
 def test_core_merge_preserves_independent_structural_facts(self):
  fragment=self.equivalent(primitive(index="INDX0300"));structural=OPTICAL.core_normalize_structural_primitives({"bdmv_index_header":"INDX0200","structural_protection_evidence":"PROTECTED","structural_probe_complete":True});facts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=fragment,structural_fragment=structural)
  self.assertEqual((facts["index_version"],facts["index_source"],facts["structural_protection"]),("0200","DISC_STRUCTURE","PROTECTED"))
 def test_phase8_classification_remains_separate(self):
  fragment=self.equivalent(primitive(index="INDX0300",aacs=True,aacs_handled=False));structural=OPTICAL.core_normalize_structural_primitives({"bdmv_index_header":None,"structural_protection_evidence":"UNKNOWN","structural_probe_complete":False});facts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=fragment,structural_fragment=structural)
  result=OPTICAL.classify_bluray_probe_facts(facts);self.assertEqual((result["exact_type"],result["protection"]),("UHD_BLURAY","PROTECTED"))

class AuthorityAndFailureIsolation(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev11\n")
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def test_disabled_selects_core(self):self.assertEqual(OPTICAL.selected_libbluray_normalization(self.home,self.install,primitive())[0],"CORE_FALLBACK")
 def test_enabled_selects_exact_plugin_equivalent(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=OPTICAL.selected_libbluray_normalization(self.home,self.install,primitive(index="INDX0300"));self.assertEqual((authority,value["libbluray_index_version"]),("PLUGIN_P2","0300"))
 def test_broken_or_mismatching_plugin_falls_back(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);path=self.plugin/"shadow.py";path.write_text(path.read_text().replace('"libbluray_probe_complete":value.get("probe_open_succeeded",False)', '"libbluray_probe_complete":False'))
  authority,value=OPTICAL.selected_libbluray_normalization(self.home,self.install,primitive(complete=True));self.assertEqual(authority,"CORE_FALLBACK");self.assertTrue(value["libbluray_probe_complete"])
 def test_invalid_primitives_follow_safe_core_error_behavior(self):
  authority,value=OPTICAL.selected_libbluray_normalization(self.home,self.install,{"bluray_detected":True});self.assertEqual(authority,"CORE_FALLBACK");self.assertFalse(value["libbluray_info_available"])
 def test_core_probe_merge_publication_survives_plugin_failure(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);(self.plugin/"shadow.py").write_text("raise RuntimeError('broken')\n")
  def runner(command):
   if command[0]=="lsblk":return subprocess.CompletedProcess(command,0,json.dumps({"blockdevices":[{"fstype":"udf","label":"DISC","mountpoints":[]}]}),"")
   if command[0]=="udevadm":return subprocess.CompletedProcess(command,0,"ID_CDROM_MEDIA=1\nID_CDROM_MEDIA_BD=1\n","")
   return subprocess.CompletedProcess(command,1,"","")
  state=OPTICAL.probe_device(pathlib.Path("/dev/sr0"),runner,lambda _: (None,None),lambda _:"UNKNOWN",lambda _:primitive(index="INDX0300",aacs=True),home=self.home,install=self.install)
  self.assertEqual((state["libbluray_normalization_authority"],state["canonical_state"]),("CORE_FALLBACK","UHD_BLURAY_VIDEO"));OPTICAL.publish(self.home,state,generation=1)
  self.assertEqual(json.loads((self.home/".local/state/openhtpc/optical-current.json").read_text())["canonical_state"],"UHD_BLURAY_VIDEO")

class BoundariesAndRegressions(unittest.TestCase):
 def test_no_live_or_executable_input_contract(self):
  for value in (object(),lambda:None,3,"/dev/sr0",{"bluray_detected":True,"aacs_detected":False,"aacs_handled":False,"bdplus_detected":False,"bdplus_handled":False,"fd":4}):self.assertFalse(OPTICAL.valid_libbluray_primitives(value))
 def test_plugin_normalizer_has_no_io_or_acquisition(self):
  source=inspect.getsource(PLUGIN.normalize_libbluray_primitives).lower()
  for marker in ("pathlib","subprocess","os.","ctypes","cdll","udev","/dev/","bdmv/","open(","stat(","write(","socket","http://","https://","curl","wget","exec(","eval("):
   self.assertNotIn(marker,source)
 def test_core_keeps_libbluray_and_index_acquisition(self):
  source=(PAYLOAD/"openhtpc-optical.py").read_text();self.assertIn("ctypes.CDLL",source);self.assertIn("bd_get_disc_info",source);self.assertIn('bd_open_file_dec(handle,b"BDMV/index.bdmv")',source);self.assertIn("_bdmv_header",source)
  plugin_source=inspect.getsource(PLUGIN.normalize_libbluray_primitives);self.assertNotIn("CDLL",plugin_source);self.assertNotIn("bd_get_disc_info",plugin_source)
 def test_phase3_through_phase8_contracts_still_exist(self):
  for name in ("doctor_rows","presentation_descriptor","capability_contribution","playback_decision","ui_contribution","classify_probe_facts"):self.assertTrue(callable(getattr(PLUGIN,name)))
 def test_non_optical_production_sources_unchanged(self):
  names=("openhtpc-play-optical","openhtpc-protected-optical-backend.py","openhtpc-session-engine.py","openhtpc-disc-sheet.py","openhtpc-disc-view.py","openhtpc-play-dvd","openhtpc-play","openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-playback-policy.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)

if __name__=="__main__":unittest.main()
