from __future__ import annotations
import importlib.util,inspect,json,pathlib,shutil,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="f3ba9cf66a6c8c184439ffd2eca5ed65efad7957"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
OPTICAL=load("structural_p2_optical",PAYLOAD/"openhtpc-optical.py");REGISTRY=load("structural_p2_registry",PAYLOAD/"openhtpc-plugin-registry.py")
PLUGIN=load("structural_p2_plugin",PAYLOAD/"plugins/available/plugin.bluray/shadow.py")

def primitive(header=None,protection="UNKNOWN",complete=False):
 return {"bdmv_index_header":header,"structural_protection_evidence":protection,"structural_probe_complete":complete}
def library(**values):
 base={"bluray_detected":True,"aacs_detected":False,"aacs_handled":False,"bdplus_detected":False,"bdplus_handled":False,"probe_open_succeeded":True,"bdmv_index_header":None};base.update(values);return OPTICAL.core_normalize_libbluray_primitives(base)

class ContractAndEquivalence(unittest.TestCase):
 def equivalent(self,value):
  self.assertTrue(OPTICAL.valid_structural_primitives(value));core=OPTICAL.core_normalize_structural_primitives(value);plugin=PLUGIN.normalize_structural_primitives(value)
  self.assertEqual(plugin,core);self.assertTrue(OPTICAL.valid_structural_fragment(plugin));return plugin
 def test_input_contract_valid_and_strict(self):
  self.assertTrue(OPTICAL.valid_structural_primitives(primitive()))
  for value in (None,{},primitive(header=3),primitive(complete=1),primitive(protection="AACS"),{**primitive(),"path":"BDMV/index.bdmv"}):self.assertFalse(OPTICAL.valid_structural_primitives(value))
 def test_output_contract_valid_and_unknown_values_rejected(self):
  value=self.equivalent(primitive());self.assertFalse(OPTICAL.valid_structural_fragment({}));self.assertFalse(OPTICAL.valid_structural_fragment({**value,"structural_index_version":"0400"}));self.assertFalse(OPTICAL.valid_structural_fragment({**value,"media_family":"BLURAY"}))
 def test_no_evidence_and_bdmv_absent(self):
  value=self.equivalent(primitive());self.assertEqual((value["structural_info_available"],value["bluray_structure_present"],value["structural_index_version"]),(False,False,"NONE"))
 def test_bdmv_and_index_versions(self):
  for header,version in (("INDX0100","0100"),("INDX0200","0200"),("INDX0300","0300")):
   value=self.equivalent(primitive(header,"UNPROTECTED",True));self.assertEqual((value["bluray_structure_present"],value["structural_index_version"]),(True,version))
 def test_unknown_and_malformed_index_are_conservative(self):
  for header in ("INDX0400","broken",""):
   value=self.equivalent(primitive(header));self.assertEqual(value["structural_index_version"],"OTHER")
 def test_unreadable_or_failed_acquisition_is_incomplete(self):
  value=self.equivalent(primitive(None,"UNKNOWN",False));self.assertFalse(value["structural_probe_complete"]);self.assertEqual(value["structural_protection"],"UNKNOWN")
 def test_structural_aacs_evidence_is_preserved_without_classification(self):
  value=self.equivalent(primitive(None,"PROTECTED",True));self.assertEqual(value["structural_protection"],"PROTECTED");self.assertNotIn("protection",value)
 def test_reliable_absence_and_incomplete_remain_distinct(self):
  absent=self.equivalent(primitive("INDX0200","UNPROTECTED",True));incomplete=self.equivalent(primitive(None,"UNKNOWN",False));self.assertEqual(absent["structural_protection"],"UNPROTECTED");self.assertEqual(incomplete["structural_protection"],"UNKNOWN")
 def test_bdplus_is_not_fabricated_by_structural_contract(self):
  value=self.equivalent(primitive(None,"PROTECTED",True));self.assertFalse(any("bdplus" in key.lower() for key in value));self.assertFalse(OPTICAL.valid_structural_primitives({**primitive(),"structural_bdplus_evidence_present":True}))
 def test_normalization_has_no_final_identity_outputs(self):
  value=self.equivalent(primitive("INDX0300","PROTECTED",True))
  for key in ("media_family","exact_type","protection","protection_mechanism","classification_source","classification_confidence"):self.assertNotIn(key,value)
 def test_phase8_establishes_uhd_and_protection(self):
  structural=self.equivalent(primitive("INDX0300","PROTECTED",True));facts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=OPTICAL.core_normalize_libbluray_primitives(None),structural_fragment=structural);result=OPTICAL.classify_bluray_probe_facts(facts)
  self.assertEqual((result["exact_type"],result["protection"]),("UHD_BLURAY","PROTECTED"))
 def test_core_merge_keeps_fragments_distinct_and_source_precedence(self):
  structural=self.equivalent(primitive("INDX0200","PROTECTED",True));facts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=library(aacs_detected=False,bdmv_index_header="INDX0300"),structural_fragment=structural);result=OPTICAL.classify_bluray_probe_facts(facts)
  self.assertEqual((facts["index_version"],facts["index_source"]),("0200","DISC_STRUCTURE"));self.assertEqual((result["classification_source"],result["protection"]),("LIBBLURAY","UNPROTECTED"))
 def test_each_source_can_independently_feed_core_merge(self):
  none=self.equivalent(primitive());structural=self.equivalent(primitive("INDX0300","UNPROTECTED",True))
  libfacts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=library(bdmv_index_header="INDX0200"),structural_fragment=none);structfacts=OPTICAL.normalized_bluray_probe_facts(bd_detected=True,libbluray_fragment=OPTICAL.core_normalize_libbluray_primitives(None),structural_fragment=structural)
  self.assertEqual((libfacts["index_source"],structfacts["index_source"]),("LIBBLURAY","DISC_STRUCTURE"))

class AuthorityAndIsolation(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev12\n")
  shutil.copy2(PAYLOAD/"openhtpc-plugin-registry.py",self.install/"openhtpc-plugin-registry.py");self.plugin=self.install/"plugins/available/plugin.bluray";shutil.copytree(PAYLOAD/"plugins/available/plugin.bluray",self.plugin)
 def test_disabled_selects_core(self):self.assertEqual(OPTICAL.selected_structural_normalization(self.home,self.install,primitive("INDX0300"))[0],"CORE_FALLBACK")
 def test_enabled_selects_equivalent_plugin(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);authority,value=OPTICAL.selected_structural_normalization(self.home,self.install,primitive("INDX0300","PROTECTED",True));self.assertEqual((authority,value["structural_index_version"]),("PLUGIN_P2","0300"))
 def test_broken_malformed_or_mismatch_uses_core(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);path=self.plugin/"shadow.py";path.write_text(path.read_text().replace('"structural_probe_complete":value["structural_probe_complete"]','"structural_probe_complete":False'))
  authority,value=OPTICAL.selected_structural_normalization(self.home,self.install,primitive("INDX0200","UNPROTECTED",True));self.assertEqual(authority,"CORE_FALLBACK");self.assertTrue(value["structural_probe_complete"])
 def test_invalid_input_uses_safe_unknown_core_fragment(self):
  authority,value=OPTICAL.selected_structural_normalization(self.home,self.install,{"path":"/tmp/disc"});self.assertEqual(authority,"CORE_FALLBACK");self.assertEqual(value["structural_protection"],"UNKNOWN")
 def test_failure_does_not_prevent_core_classification_or_publication(self):
  REGISTRY.set_enabled(self.home,self.install,"plugin.bluray",True);(self.plugin/"shadow.py").write_text("raise RuntimeError('broken')\n")
  def runner(command):
   if command[0]=="lsblk":return subprocess.CompletedProcess(command,0,json.dumps({"blockdevices":[{"fstype":"udf","label":"DISC","mountpoints":[]}]}),"")
   if command[0]=="udevadm":return subprocess.CompletedProcess(command,0,"ID_CDROM_MEDIA=1\nID_CDROM_MEDIA_BD=1\n","")
   return subprocess.CompletedProcess(command,1,"","")
  state=OPTICAL.probe_device(pathlib.Path("/dev/sr0"),runner,lambda _:("INDX0300","BDMV/index.bdmv"),lambda _:"PROTECTED",lambda _:None,home=self.home,install=self.install)
  self.assertEqual((state["structural_normalization_authority"],state["canonical_state"]),("CORE_FALLBACK","UHD_BLURAY_VIDEO"));OPTICAL.publish(self.home,state,generation=2)
  self.assertEqual(json.loads((self.home/".local/state/openhtpc/optical-current.json").read_text())["generation"],2)

class SecurityAndRegressions(unittest.TestCase):
 def test_plugin_receives_no_path_handle_file_or_callable(self):
  for value in (pathlib.Path("/tmp/disc"),object(),lambda:None,3,{**primitive(),"device":"/dev/sr0"},{**primitive(),"fd":4},{**primitive(),"file":object()}):self.assertFalse(OPTICAL.valid_structural_primitives(value))
 def test_plugin_structural_normalizer_has_no_io(self):
  source=inspect.getsource(PLUGIN.normalize_structural_primitives).lower()
  for marker in ("pathlib","subprocess","os.","ctypes","cdll","udev","/dev/","open(","stat(","read(","write(","socket","http://","https://","curl","wget","exec(","eval("):
   self.assertNotIn(marker,source)
 def test_core_keeps_every_structural_io_operation(self):
  source=(PAYLOAD/"openhtpc-optical.py").read_text();self.assertIn('(root/relative).open("rb").read(8)',source);self.assertIn("(root/relative).lstat()",source);self.assertIn("(root/relative).is_file()",source);self.assertIn("_mountpoints(block)",source)
 def test_no_capability_history_or_metadata_contamination(self):
  value=primitive("INDX0300","PROTECTED",True)
  for key in ("keydb","provider","capability","last_attempt","open_success","open_failed","tmdb","badge"):self.assertNotIn(key,value)
 def test_prior_phase_contracts_remain_present(self):
  for name in ("doctor_rows","presentation_descriptor","capability_contribution","playback_decision","ui_contribution","classify_probe_facts","normalize_libbluray_primitives"):self.assertTrue(callable(getattr(PLUGIN,name)))
 def test_production_playback_media_and_gpu_sources_unchanged(self):
  names=("openhtpc-play-dvd","openhtpc-play","openhtpc-capabilities.py","openhtpc-protected-optical.py","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-playback-policy.py")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout;self.assertEqual((PAYLOAD/name).read_text(),baseline,name)

if __name__=="__main__":unittest.main()
