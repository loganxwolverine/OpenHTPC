from __future__ import annotations
import ctypes,importlib.machinery,importlib.util,json,pathlib,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
OPTICAL=load("dev5_optical",PAYLOAD/"openhtpc-optical.py");VIEW=load("dev5_view",PAYLOAD/"openhtpc-disc-view.py");CORE=load("dev5_core",PAYLOAD/"openhtpc-core.py")

class BadgeTruth(unittest.TestCase):
 def test_bluray_and_family_keep_generic_badge(self):
  self.assertEqual(VIEW.MEDIA_PROFILES["BLURAY_VIDEO"]["logo"],"assets/ui/bluray-media-badge.png")
  self.assertEqual(VIEW.MEDIA_PROFILES["BLURAY_FAMILY"]["logo"],"assets/ui/bluray-media-badge.png")
 def test_reliably_classified_uhd_gets_4k_badge(self):
  profile=VIEW.MEDIA_PROFILES["UHD_BLURAY_VIDEO"];self.assertEqual(profile["logo"],"assets/ui/uhd-bluray-media-badge.png");self.assertEqual(profile["badge"],"ULTRA HD BLU-RAY 4K")
 def test_unknown_exact_type_never_uses_uhd_badge(self):self.assertNotEqual(VIEW.MEDIA_PROFILES["BLURAY_FAMILY"]["logo"],VIEW.MEDIA_PROFILES["UHD_BLURAY_VIDEO"]["logo"])
 def test_public_libbluray_file_api_returns_index_signature(self):
  closed=[];file_object=OPTICAL._BlurayFile()
  @OPTICAL._BlurayFileClose
  def close(_file):closed.append(True)
  @OPTICAL._BlurayFileRead
  def read(_file,buffer,size):
   value=b"INDX0300";ctypes.memmove(buffer,value,min(size,len(value)));return min(size,len(value))
  file_object.close=close;file_object.read=read
  class Function:
   def __init__(self,callback):self.callback=callback;self.argtypes=None;self.restype=None
   def __call__(self,*args):return self.callback(*args)
  library=type("Library",(),{})();library.bd_open_file_dec=Function(lambda _handle,_path:ctypes.pointer(file_object))
  self.assertEqual(OPTICAL._libbluray_bdmv_header(library,1),"INDX0300");self.assertEqual(closed,[True])

class CurrentVsHistory(unittest.TestCase):
 def test_eject_clears_current_classification_without_last_attempt(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);state_dir=home/".local/state/openhtpc";state_dir.mkdir(parents=True)
   attempt=state_dir/"protected-optical-last-attempt.json";attempt.write_text(json.dumps({"status":"OPEN_SUCCESS"}))
   OPTICAL.publish(home,{"canonical_state":"UHD_BLURAY_VIDEO","state":"UHD","device":"/dev/sr0","protection":"PROTECTED"},generation=1)
   current=OPTICAL.publish(home,OPTICAL._state("DRIVE_PRESENT_NO_MEDIA","/dev/sr0","EMPTY"),generation=2)
   self.assertNotIn("protection",current);self.assertEqual(json.loads(attempt.read_text())["status"],"OPEN_SUCCESS")
 def test_doctor_reads_last_attempt_only_as_history(self):
  source=(PAYLOAD/"openhtpc-core.py").read_text();self.assertIn('read_json(state_root / "optical-current.json")',source);self.assertIn('read_json(state_root / "protected-optical-last-attempt.json")',source)

class FrozenBoundaries(unittest.TestCase):
 def test_backend_dvd_tmdb_keydb_and_gpu_sources_unchanged_from_dev4(self):
  for name in ("openhtpc-play-dvd","openhtpc-tmdb.py","openhtpc-protected-optical.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh"):
   baseline=subprocess.run(["git","show",f"940c03764f4e6c0fbde01066c89553b8b648b161:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline)
 def test_no_network_acquisition(self):
  source="\n".join((PAYLOAD/name).read_text().lower() for name in ("openhtpc-optical.py","openhtpc-play-optical","openhtpc-protected-optical-backend.py"))
  for marker in ("urlopen(","import requests","curl ","wget ","http://","https://","download_keydb","fetch_keys"):self.assertNotIn(marker,source)

if __name__=="__main__":unittest.main()
