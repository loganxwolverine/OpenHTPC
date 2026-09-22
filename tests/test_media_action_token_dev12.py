#!/usr/bin/env python3
"""Dev12 MEDIA action-token generation binding and security regressions."""
from __future__ import annotations
import importlib.machinery,importlib.util,json,os,pathlib,subprocess,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module
session=load("dev12_session",PAYLOAD/"openhtpc-session-engine.py");play=load("dev12_play",PAYLOAD/"openhtpc-play")

class MediaActionBinding(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=pathlib.Path(self.temp.name);self.install=PAYLOAD
  self.source=self.home/"Movies";self.page_a=self.source/"Classics";self.page_b=self.source/"Modern/Nested";self.page_a.mkdir(parents=True);self.page_b.mkdir(parents=True)
  (self.page_a/"Alerte.mkv").write_bytes(b"video");(self.page_b/"300 Rise of an Empire (2014).mkv").write_bytes(b"video")
  config=self.home/".config/openhtpc";config.mkdir(parents=True);(config/"user-config.json").write_text(json.dumps({"configuration_completed":True,"local_media_sources":[str(self.source)]}))
  self.flex=config/"flex-v1.ini";self.current=session.current_media_manifest(self.home)
 def generate(self,generation):
  self.assertTrue(session.write_flex_config(self.flex,self.home,[self.source],self.install,media_generation=generation));session.activate_media_manifest(self.flex,self.home)
  return json.loads(self.current.read_text())
 def actions(self,model):return {item["relative_path"]:(token,item) for token,item in model["items"].items() if item["item_type"]=="file"}
 def set_page(self,page):
  target=self.home/".local/state/openhtpc/media-actions/current-page";target.parent.mkdir(parents=True,exist_ok=True);target.write_text(page+"\n")
 def test_two_distinct_hashed_and_nested_pages_accept_current_tokens(self):
  model=self.generate("media-current");actions=self.actions(model);self.assertEqual(set(actions),{"Classics/Alerte.mkv","Modern/Nested/300 Rise of an Empire (2014).mkv"})
  pages=set()
  for token,item in actions.values():
   self.assertRegex(item["page_id"],r"^MEDIA_D[0-9a-f]{8}$");self.assertRegex(item.get("parent_page_id",""),r"^MEDIA_[0-9a-f]{16}$");self.set_page(item["page_id"]);self.assertEqual(play.load_media_action(self.home,token),item);pages.add(item["page_id"])
  self.assertEqual(len(pages),2)
 def test_optical_only_regeneration_preserves_active_media_generation_and_tokens(self):
  first=self.generate("media-stable");first_actions=self.actions(first)
  self.assertTrue(session.write_flex_config(self.flex,self.home,[self.source],self.install,expected_optical_generation=0))
  candidate=json.loads(self.flex.with_name(self.flex.name+".media-actions.json").read_text());self.assertEqual(candidate["manifest_generation"],"media-stable");self.assertEqual(set(candidate["items"]),set(first["items"]));self.assertEqual(self.actions(candidate),first_actions)
 def test_wrong_page_unknown_malformed_and_old_generation_are_rejected(self):
  current=self.generate("generation-one");token,item=self.actions(current)["Classics/Alerte.mkv"];self.set_page(self.actions(current)["Modern/Nested/300 Rise of an Empire (2014).mkv"][1]["page_id"])
  with self.assertRaisesRegex(ValueError,"STALE_PAGE"):play.load_media_action(self.home,token)
  self.set_page(item["page_id"])
  with self.assertRaisesRegex(ValueError,"TOKEN_NOT_FOUND"):play.load_media_action(self.home,"mact_"+"0"*32)
  with self.assertRaisesRegex(ValueError,"INVALID_ACTION_TOKEN"):play.load_media_action(self.home,"mact_bad")
  old_token=token;new=self.generate("generation-two");self.assertEqual(new["manifest_generation"],"generation-two");self.assertNotEqual(current["manifest_generation"],new["manifest_generation"]);self.assertNotIn(old_token,new["items"])
  with self.assertRaisesRegex(ValueError,"TOKEN_NOT_FOUND"):play.load_media_action(self.home,old_token)
 def test_item_and_source_identity_checks_remain_enforced(self):
  model=self.generate("identity-current");token,item=self.actions(model)["Classics/Alerte.mkv"];self.set_page(item["page_id"])
  trusted=play.load_media_action(self.home,token);relative=pathlib.PurePosixPath(trusted["relative_path"]);expected=session.media_item_id(trusted["source_id"],relative,"file");self.assertEqual(trusted["semantic_id"],expected)
  with self.assertRaisesRegex(ValueError,"PLAYBACK_SOURCE_INVALID"):play.resolve_media_request(self.home,"0"*16,trusted["relative_path"],trusted["page_id"])
  tampered=dict(trusted,semantic_id="0"*24);self.assertNotEqual(tampered["semantic_id"],expected)
 def test_valid_token_reaches_dispatcher_absolute_file_and_mpv_launch(self):
  model=self.generate("dispatch-current");token,item=self.actions(model)["Modern/Nested/300 Rise of an Empire (2014).mkv"];self.set_page(item["page_id"])
  runtime=self.home/".config/openhtpc/pure.conf";runtime.write_text("vo=null\n");(runtime.parent/"profile.json").write_text(json.dumps({"runtime":{"status":"ready"},"runtime_profiles":{"profiles":{"PURE":{"generation_status":"generated","config_path":str(runtime)}}}}))
  fake=self.home/"fakebin";fake.mkdir();mpv=fake/"mpv";mpv.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$OPENHTPC_TEST_ARGV\"\n");mpv.chmod(0o755);argv_log=self.home/"mpv.argv"
  env={**os.environ,"HOME":str(self.home),"OPENHTPC_HOME":str(self.home),"OPENHTPC_INSTALL_DIR":str(self.install),"OPENHTPC_TEST_ARGV":str(argv_log),"PATH":str(fake)+os.pathsep+os.environ["PATH"]}
  env.pop("DISPLAY",None);env.pop("WAYLAND_DISPLAY",None)
  result=subprocess.run([str(self.install/"openhtpc-play"),token],env=env,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr);args=argv_log.read_text().splitlines();self.assertEqual(args[-1],str((self.page_b/"300 Rise of an Empire (2014).mkv").resolve()));self.assertTrue(pathlib.Path(args[-1]).is_absolute());self.assertTrue(pathlib.Path(args[-1]).is_file())
  state=json.loads((self.home/".local/state/openhtpc/media-action-last.json").read_text());self.assertTrue(state["dispatcher_seen"]);self.assertTrue(state["path_resolved"]);self.assertTrue(state["path_absolute"]);self.assertTrue(state["file_exists"]);self.assertTrue(state["process_started"])
 def test_generated_flex_uses_tokens_and_never_raw_paths(self):
  model=self.generate("no-raw-path");text=self.flex.read_text();self.assertIn("openhtpc-play mact_",text);self.assertNotIn(str(self.page_a/"Alerte.mkv"),text);self.assertNotIn(str(self.page_b/"300 Rise of an Empire (2014).mkv"),text);self.assertEqual(len(self.actions(model)),2)

if __name__=="__main__":unittest.main()
