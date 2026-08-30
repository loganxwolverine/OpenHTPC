#!/usr/bin/env python3
"""Protected optical backend Dev3 contracts with no protected fixtures."""
from __future__ import annotations
import importlib.machinery,importlib.util,json,pathlib,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
OPTICAL=load("dev3_optical",PAYLOAD/"openhtpc-optical.py");DISPATCH=load("dev3_dispatch",PAYLOAD/"openhtpc-play-optical");BACKEND=load("dev3_backend",PAYLOAD/"openhtpc-protected-optical-backend.py")

def capability(status="AVAILABLE",bluray="AVAILABLE",aacs="AVAILABLE",bdplus="NOT_AVAILABLE"):
 return {"capability":"PROTECTED_OPTICAL_SUPPORT","status":status,"dependencies":{"libbluray":{"status":bluray},"libaacs":{"status":aacs},"libbdplus":{"status":bdplus}},"external_key_database":{"status":"DETECTED" if status=="AVAILABLE" else "NOT_CONFIGURED"}}
def optical(protection="PROTECTED",canonical="BLURAY_VIDEO",generation=9):
 return {"canonical_state":canonical,"state":"UHD" if canonical=="UHD_BLURAY_VIDEO" else "BLURAY","protection":protection,"device":"/dev/sr0","generation":generation}

class Fixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=pathlib.Path(self.temp.name);self.runtime=self.home/"runtime.conf";self.runtime.write_text("vo=null\n")
  (self.home/".config/openhtpc/runtime").mkdir(parents=True);(self.home/".local/state/openhtpc").mkdir(parents=True)
  (self.home/".config/openhtpc/profile.json").write_text(json.dumps({"runtime":{"status":"ready"},"runtime_profiles":{"profiles":{"PURE":{"generation_status":"generated","config_path":str(self.runtime)}}}}))
 def write(self,state,model):
  (self.home/".local/state/openhtpc/optical-current.json").write_text(json.dumps(state));(self.home/".config/openhtpc/runtime/capabilities.json").write_text(json.dumps({"optical":{"protected_media":model}}))
 def token(self,state,model):return OPTICAL.playback_action_token(state,model)
 def runner(self,opened=True,returncode=0):
  def run(command,**_kwargs):
   target=pathlib.Path(next(arg.split("=",1)[1] for arg in command if arg.startswith("--log-file=")))
   target.write_text("Video: libbluray fixture\nVO: null\n" if opened else "disc open failed\n")
   return type("Result",(),{"returncode":returncode})()
  return run

class Backend(Fixture):
 def test_unprotected_bluray_without_external_configuration_opens(self):
  request={"device":"/dev/sr0","media_type":"BLURAY","protection":"UNPROTECTED","provider_status":"NOT_CONFIGURED"}
  result=BACKEND.open_disc(self.home,request,runner=self.runner(),finder=lambda _name:"/usr/bin/mpv",clock=iter((0.0,2.0)).__next__);self.assertEqual(result["status"],"OPEN_SUCCESS")
 def test_protected_available_attempts_backend(self):
  state=optical();model=capability();self.write(state,model);seen=[]
  result=DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),backend=lambda _home,request:seen.append(request) or {"status":"OPEN_SUCCESS"},device_exists=lambda _device:True)
  self.assertEqual(result["status"],"OPEN_SUCCESS");self.assertEqual(seen[0]["protection"],"PROTECTED")
 def test_protected_not_configured_never_attempts_backend(self):
  state=optical();model=capability("NOT_CONFIGURED");self.write(state,model);seen=[]
  with self.assertRaisesRegex(ValueError,"NOT_CONFIGURED"):DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),backend=lambda *_args:seen.append(True),device_exists=lambda _device:True)
  self.assertEqual(seen,[])
 def test_open_failure_is_clean(self):
  request={"device":"/dev/sr0","media_type":"BLURAY","protection":"PROTECTED","provider_status":"AVAILABLE"}
  result=BACKEND.open_disc(self.home,request,runner=self.runner(False,2),finder=lambda _name:"/usr/bin/mpv",clock=iter((0.0,1.0)).__next__);self.assertEqual((result["status"],result["reason"]),("OPEN_FAILED","DISC_OPEN_REFUSED"))
 def test_uhd_backend_refusal_is_clean(self):
  request={"device":"/dev/sr0","media_type":"UHD_BLURAY","protection":"PROTECTED","provider_status":"AVAILABLE"}
  result=BACKEND.open_disc(self.home,request,runner=self.runner(False,2),finder=lambda _name:"mpv",clock=iter((0.0,1.0)).__next__);self.assertEqual(result["status"],"OPEN_FAILED")
 def test_immediate_mpv_exit_is_failure(self):
  request={"device":"/dev/sr0","media_type":"BLURAY","protection":"UNPROTECTED","provider_status":"NOT_CONFIGURED"}
  result=BACKEND.open_disc(self.home,request,runner=self.runner(),finder=lambda _name:"mpv",clock=iter((0.0,0.1)).__next__);self.assertEqual(result["reason"],"MPV_EXITED_IMMEDIATELY")
 def test_mpv_not_started_is_failure(self):
  request={"device":"/dev/sr0","media_type":"BLURAY","protection":"UNPROTECTED","provider_status":"NOT_CONFIGURED"}
  self.assertFalse(BACKEND.open_disc(self.home,request,finder=lambda _name:None)["process_started"])

class Revalidation(Fixture):
 def test_stale_capability_token_is_refused_before_backend(self):
  state=optical();old=capability();self.write(state,old);token=self.token(state,old);self.write(state,capability("NOT_CONFIGURED"));seen=[]
  with self.assertRaisesRegex(ValueError,"ACTION_TOKEN_INVALID"):DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,token,backend=lambda *_args:seen.append(True),device_exists=lambda _device:True)
  self.assertEqual(seen,[])
 def test_removed_device_is_refused(self):
  state=optical();model=capability();self.write(state,model)
  with self.assertRaisesRegex(ValueError,"DEVICE_REMOVED"):DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),device_exists=lambda _device:False)
 def test_libaacs_absence_prevents_protected_attempt(self):
  state=optical();model=capability("NOT_AVAILABLE",aacs="NOT_AVAILABLE");self.write(state,model);seen=[]
  with self.assertRaisesRegex(ValueError,"NOT_AVAILABLE"):DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),backend=lambda *_args:seen.append(True),device_exists=lambda _device:True)
  self.assertEqual(seen,[])
 def test_libbdplus_absence_does_not_block_generic_attempt(self):
  state=optical();model=capability(bdplus="NOT_AVAILABLE");self.write(state,model)
  result=DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),backend=lambda *_args:{"status":"OPEN_SUCCESS"},device_exists=lambda _device:True);self.assertEqual(result["status"],"OPEN_SUCCESS")
 def test_disc_failure_does_not_mutate_machine_capability(self):
  state=optical();model=capability();self.write(state,model)
  DISPATCH.dispatch(self.home,PAYLOAD,"/dev/sr0",9,self.token(state,model),backend=lambda *_args:{"status":"OPEN_FAILED","reason":"DISC_OPEN_REFUSED"},device_exists=lambda _device:True)
  snapshot=json.loads((self.home/".config/openhtpc/runtime/capabilities.json").read_text());self.assertEqual(snapshot["optical"]["protected_media"]["status"],"AVAILABLE")
  self.assertEqual(json.loads((self.home/".local/state/openhtpc/protected-optical-last-attempt.json").read_text())["status"],"OPEN_FAILED")

class Boundaries(unittest.TestCase):
 def test_backend_uses_normal_libbluray_mpv_source(self):
  source=(PAYLOAD/"openhtpc-protected-optical-backend.py").read_text();self.assertIn('"bd://"',source);self.assertIn('"--bluray-device=',source)
 def test_key_database_is_never_opened_by_backend_or_dispatcher(self):
  source="\n".join((PAYLOAD/name).read_text() for name in ("openhtpc-protected-optical-backend.py","openhtpc-play-optical"));self.assertNotIn("KEYDB.cfg",source);self.assertNotIn("aacs/",source)
 def test_no_network_acquisition(self):
  source="\n".join((PAYLOAD/name).read_text().lower() for name in ("openhtpc-protected-optical-backend.py","openhtpc-play-optical"))
  for marker in ("urlopen(","import requests","curl ","wget ","http://","https://","download_keydb","fetch_keys"):self.assertNotIn(marker,source)
 def test_dvd_dispatcher_is_unchanged_from_phase2(self):
  import subprocess
  baseline=subprocess.run(["git","show","8553e6061ee8cea8e2dbe02e07d2a3249bb69f32:payload/openhtpc-play-dvd"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
  self.assertEqual((PAYLOAD/"openhtpc-play-dvd").read_text(),baseline)
 def test_gpu_runtime_generators_are_unchanged_from_phase2(self):
  import subprocess
  for name in ("openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh"):
   baseline=subprocess.run(["git","show",f"8553e6061ee8cea8e2dbe02e07d2a3249bb69f32:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline)

if __name__=="__main__":unittest.main()
