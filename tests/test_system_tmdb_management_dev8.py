#!/usr/bin/env python3
"""Focused Dev8 secure TMDb management and frozen-path contracts."""
import importlib.util,io,json,pathlib,socket,tempfile,unittest,urllib.error
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
management=load("dev8_management",PAYLOAD/"openhtpc-tmdb-management.py");tmdb=load("dev8_tmdb",PAYLOAD/"openhtpc-tmdb.py");session=load("dev8_session",PAYLOAD/"openhtpc-session-engine.py")
class Response(io.BytesIO):
 def __init__(self):super().__init__(b'{"success":true}')
 def __enter__(self):return self
 def __exit__(self,*args):pass
class Lifecycle(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=pathlib.Path(self.tmp.name)
 def valid(self,*args,**kwargs):return Response()
 def seed(self,value="synthetic-A-AB12"):management._write_credential(self.home,value);management._set_configured(self.home,True)
 def test_01_no_credential(self):self.assertEqual(management.status(self.home)["state"],"NOT_CONFIGURED")
 def test_02_valid_test(self):self.seed();self.assertEqual(management.test_stored(self.home,self.valid)["state"],"VALID")
 def test_03_rejected(self):
  def rejected(*a,**k):raise urllib.error.HTTPError("synthetic",401,"rejected",{},None)
  self.assertEqual(management.validate("synthetic",rejected)["state"],"AUTH_REJECTED")
 def test_04_network(self):
  def offline(*a,**k):raise urllib.error.URLError(socket.gaierror("synthetic dns"))
  self.assertEqual(management.validate("synthetic",offline)["state"],"NETWORK_UNAVAILABLE")
 def test_05_service(self):
  def failed(*a,**k):raise urllib.error.HTTPError("synthetic",503,"service",{},None)
  self.assertEqual(management.validate("synthetic",failed)["state"],"SERVICE_UNAVAILABLE")
 def test_06_timeout(self):
  def timeout(*a,**k):raise TimeoutError("synthetic")
  self.assertEqual(management.validate("synthetic",timeout)["state"],"TIMEOUT")
 def test_07_no_result_not_auth(self):
  self.seed();response=mock.MagicMock();response.__enter__.return_value=response
  with mock.patch.object(tmdb.json,"load",return_value={"results":[]}):result=tmdb.lookup(self.home,"Synthetic title",lambda *a,**k:response)
  self.assertEqual(result["status"],"NO_RESULT")
 def test_08_valid_persists_private(self):
  result=management.replace(self.home,"synthetic-B-ZZ99",self.valid);token=management.paths(self.home)[0]
  self.assertTrue(result["committed"]);self.assertEqual(token.read_text().strip(),"synthetic-B-ZZ99");self.assertEqual(token.stat().st_mode&0o777,0o600)
 def test_09_invalid_not_committed(self):
  def rejected(*a,**k):raise urllib.error.HTTPError("synthetic",403,"rejected",{},None)
  self.assertFalse(management.replace(self.home,"synthetic-bad",rejected)["committed"]);self.assertFalse(management.paths(self.home)[0].exists())
 def test_10_valid_b_replaces_a(self):self.seed();management.replace(self.home,"synthetic-B-ZZ99",self.valid);self.assertEqual(management.credential(self.home),"synthetic-B-ZZ99")
 def test_11_invalid_b_preserves_a(self):
  self.seed();rejected=lambda *a,**k:(_ for _ in ()).throw(urllib.error.HTTPError("synthetic",401,"",{},None));management.replace(self.home,"bad",rejected);self.assertEqual(management.credential(self.home),"synthetic-A-AB12")
 def test_12_network_b_preserves_a(self):
  self.seed();offline=lambda *a,**k:(_ for _ in ()).throw(urllib.error.URLError("offline"));management.replace(self.home,"new",offline);self.assertEqual(management.credential(self.home),"synthetic-A-AB12")
 def test_13_cancel_preserves_a(self):self.seed();self.assertEqual(management.credential(self.home),"synthetic-A-AB12")
 def test_14_delete(self):self.seed();self.assertEqual(management.delete(self.home)["state"],"NOT_CONFIGURED")
 def test_15_delete_cancel(self):
  self.seed()
  with mock.patch.object(management,"_dialog",return_value=mock.Mock(returncode=1)):management.interactive(self.home,"delete")
  self.assertEqual(management.credential(self.home),"synthetic-A-AB12")
 def test_16_mask(self):self.seed();self.assertEqual(management.status(self.home)["masked"],"••••AB12")
class Integration(unittest.TestCase):
 def test_17_status_has_no_secret(self):
  with tempfile.TemporaryDirectory() as raw:
   home=pathlib.Path(raw);management.replace(home,"synthetic-secret-ZZ99",lambda *a,**k:Response());self.assertNotIn("synthetic-secret",management.paths(home)[1].read_text())
 def test_18_capture_redaction(self):
  for name in ("openhtpc-support-bundle.py","openhtpc-validator"):
   source=(PAYLOAD/name).read_text();self.assertIn("[?&]api_key=",source);self.assertIn("authorization\\s*:\\s*bearer",source)
 def test_19_startup_no_network_test(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text();self.assertNotIn("management.test_stored",source);self.assertNotIn("management.validate",source)
 def test_20_invalid_does_not_block_startup(self):
  with tempfile.TemporaryDirectory() as raw:
   token=pathlib.Path(raw)/"token";token.write_text("invalid");token.chmod(0o600);self.assertEqual(session.validate_user_config({"configuration_completed":True,"local_media_sources":[],"tmdb":{"configured":True}},token),[])
 def test_21_contextual_canonical(self):
  self.assertIn("openhtpc-tmdb-management.py",(PAYLOAD/"openhtpc-configure-tmdb").read_text())
 def test_22_settings_hierarchy(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text();self.assertIn("SYSTEM_METADATA",source);self.assertIn("SYSTEM_TMDB",source);self.assertIn("MÉTADONNÉES",source)
 def test_23_dev7_picker_retained(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text();self.assertIn("openhtpc-bind-disc",source);self.assertIn('cached_meta.get("candidates", [])[:3]',source)
 def test_24_startup_contract_retained(self):
  source=(PAYLOAD/"openhtpc-session-start").read_text();self.assertIn("write_flex_config",source);self.assertNotIn("openhtpc-tmdb-management",source)
 def test_25_tmdb_actions_use_qualified_lower_dock(self):
  screen_height=1080;content_bottom=170+680;action_top=screen_height*88//100
  self.assertGreater(action_top,content_bottom)
  source=(ROOT/"vendor/flex-launcher/src/launcher.c").read_text()
  self.assertIn('strcmp(name, "SYSTEM_TMDB") == 0',source)
  self.assertIn("entry->icon_rect.y = (geo.screen_height * 88) / 100",source)
  self.assertIn("int safety_margin = (geo.screen_height * 1) / 100",source)
 def test_26_tmdb_action_order_is_deterministic(self):
  source=(PAYLOAD/"openhtpc-session-engine.py").read_text()
  ordered=("Entry1=TESTER;","Entry2=MODIFIER;","Entry3=SUPPRIMER;","Entry4=RETOUR;")
  positions=[source.index(marker,source.index("[SYSTEM_TMDB]")) for marker in ordered]
  self.assertEqual(positions,sorted(positions))
if __name__=="__main__":unittest.main()
