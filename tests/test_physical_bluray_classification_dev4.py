from __future__ import annotations

import importlib.util,json,pathlib,subprocess,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
spec=importlib.util.spec_from_file_location("dev4_optical",PAYLOAD/"openhtpc-optical.py")
OPTICAL=importlib.util.module_from_spec(spec);spec.loader.exec_module(OPTICAL)

def completed(command,code=0,out=""):return subprocess.CompletedProcess(command,code,out,"")
def runner(label="PROJECT X",bd=True):
 def invoke(command):
  if command[0]=="lsblk":return completed(command,out=json.dumps({"blockdevices":[{"fstype":"udf","label":label,"mountpoints":[]}]}))
  if command[0]=="udevadm":return completed(command,out="ID_CDROM_MEDIA=1\n"+("ID_CDROM_MEDIA_BD=1\n" if bd else ""))
  if command[0]=="lsdvd":return completed(command,1)
  return completed(command,1)
 return invoke
def info(**values):return {"bluray_detected":True,"aacs_detected":False,"aacs_handled":False,"bdplus_detected":False,"bdplus_handled":False,"probe_open_succeeded":False,**values}
def probe(library,header=None,label="PROJECT X",bd=True):
 return OPTICAL.probe_device(pathlib.Path("/dev/sr0"),runner(label,bd),lambda _block:(header,"BDMV/index.bdmv") if header else (None,None),lambda _block:"UNKNOWN",lambda _device:library)

class Classification(unittest.TestCase):
 def test_libbluray_detects_bluray_family_without_mount(self):
  state=probe(info());self.assertEqual((state["canonical_state"],state["classification_source"]),("BLURAY_FAMILY","LIBBLURAY"))
 def test_aacs_detected_is_protected_even_when_not_handled(self):
  state=probe(info(aacs_detected=True,aacs_handled=False));self.assertEqual((state["protection"],state["protection_mechanisms"]),("PROTECTED",["AACS"]))
  self.assertFalse(state["libbluray_disc_info"]["aacs_handled"])
 def test_aacs_false_does_not_claim_protected(self):self.assertEqual(probe(info())["protection"],"UNPROTECTED")
 def test_bdplus_is_exposed_independently(self):self.assertEqual(probe(info(bdplus_detected=True))["protection_mechanisms"],["BDPLUS"])
 def test_libbdplus_availability_is_not_part_of_disc_classification(self):
  self.assertEqual(probe(info(aacs_detected=True,bdplus_detected=False))["protection"],"PROTECTED")
 def test_exact_variant_unknown_is_not_global_unknown(self):
  state=probe(info(aacs_detected=True));self.assertEqual((state["canonical_state"],state["classification_confidence"]),("BLURAY_FAMILY","PARTIAL"))
 def test_index_0300_is_documented_uhd_proof(self):self.assertEqual(probe(info(),"INDX0300")["canonical_state"],"UHD_BLURAY_VIDEO")
 def test_libbluray_index_0300_is_same_canonical_uhd_proof(self):
  state=probe(info(bdmv_index_header="INDX0300"));self.assertEqual((state["canonical_state"],state["bdmv_index_path"]),("UHD_BLURAY_VIDEO","libbluray:BDMV/index.bdmv"))
 def test_hevc_or_resolution_alone_is_not_uhd(self):
  state=probe(info());state["video"]={"codec":"HEVC","width":3840,"height":2160};self.assertEqual(state["canonical_state"],"BLURAY_FAMILY")
 def test_uhd_label_is_not_uhd_proof(self):self.assertEqual(probe(info(),label="ULTRA UHD MOVIE")["canonical_state"],"BLURAY_FAMILY")
 def test_hdr_alone_is_not_uhd_proof(self):
  state=probe(info());state["video"]={"hdr":True};self.assertEqual(state["canonical_state"],"BLURAY_FAMILY")
 def test_reliable_absence_of_protection_is_unprotected(self):self.assertEqual(probe(info())["protection_mechanisms"],["NONE"])
 def test_contradictory_aacs_fact_wins_conservatively(self):
  state=probe(info(bluray_detected=False,aacs_detected=True),bd=True);self.assertEqual((state["canonical_state"],state["protection"]),("BLURAY_FAMILY","PROTECTED"))

class GatingAndBoundaries(unittest.TestCase):
 def capability(self,status):return {"status":status,"dependencies":{"libbluray":{"status":"AVAILABLE"}}}
 def state(self,protection):return {"canonical_state":"BLURAY_FAMILY","state":"BLURAY","device":"/dev/sr0","generation":1,"protection":protection}
 def test_family_protected_available_is_enabled(self):self.assertEqual(OPTICAL.playback_decision(self.state("PROTECTED"),self.capability("AVAILABLE"))["playback_action"],"ENABLED")
 def test_family_protected_not_configured_is_disabled(self):self.assertEqual(OPTICAL.playback_decision(self.state("PROTECTED"),self.capability("NOT_CONFIGURED"))["playback_action"],"DISABLED")
 def test_unknown_protection_remains_disabled(self):self.assertEqual(OPTICAL.playback_decision(self.state("UNKNOWN"),self.capability("AVAILABLE"))["playback_action"],"DISABLED")
 def test_dispatcher_consumes_canonical_state_without_classifier(self):
  source=(PAYLOAD/"openhtpc-play-optical").read_text();self.assertIn("canonical_state(state)",source);self.assertNotIn("bd_get_disc_info",source)
 def test_no_key_content_or_network_acquisition(self):
  source="\n".join((PAYLOAD/name).read_text().lower() for name in ("openhtpc-optical.py","openhtpc-play-optical","openhtpc-protected-optical-backend.py"))
  for marker in ("keydb.cfg","urlopen(","import requests","curl ","wget ","http://","https://","download_keydb","fetch_keys"):self.assertNotIn(marker,source)
 def test_dvd_tmdb_backend_and_gpu_sources_unchanged_from_dev3(self):
  for name in ("openhtpc-play-dvd","openhtpc-tmdb.py","openhtpc-protected-optical-backend.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh"):
   baseline=subprocess.run(["git","show",f"5c67efd82fa2c34d1f4e40b3f3e837ed3c0259f8:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline)

if __name__=="__main__":unittest.main()
