#!/usr/bin/env python3
from __future__ import annotations
import importlib.machinery,importlib.util,json,os,pathlib,re,tempfile,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"
def load(name,path):
 loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);mod=importlib.util.module_from_spec(spec);loader.exec_module(mod);return mod
session=load("dev15_session",PAYLOAD/"openhtpc-session-engine.py");sources=load("dev15_sources",PAYLOAD/"openhtpc-media-sources");play=load("dev15_play",PAYLOAD/"openhtpc-play")
class LivePublication(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=pathlib.Path(self.tmp.name);self.config=self.home/".config/openhtpc/flex-v1.ini";self.config.parent.mkdir(parents=True);pure=self.home/"pure.conf";pure.write_text("vo=null\n");profile={"generator":{"name":"OPENHTPC Builder","version":"4"},"detected":{},"gpu_topology":{"processing_gpu":{}},"video_backend":{"status":"observed","decode_api":"vaapi","render_api":"vulkan","render_node":"/dev/null"},"runtime":{"status":"ready","playback_validated":False},"runtime_profiles":{"profiles":{"PURE":{"generation_status":"generated","config_path":str(pure)}}}};(self.home/".config/openhtpc/profile.json").write_text(json.dumps(profile));(self.home/".config/openhtpc/user-config.json").write_text(json.dumps({"configuration_completed":True,"local_media_sources":[],"tmdb":{"configured":False}}));self.a=self.home/"media-a";self.b=self.home/"media-b";(self.a/"Dvd").mkdir(parents=True);self.b.mkdir();(self.a/"Dvd/Alerte.mkv").write_bytes(b"x");(self.b/"Second.mkv").write_bytes(b"x");session.publish_flex_config(self.config,self.home,[],PAYLOAD)
 def model(self,path=None):return json.loads((path or session.current_media_manifest(self.home)).read_text())
 def visible(self):
  text=self.config.read_text();return set(re.findall(r"mact_[0-9a-f]{32}",text))
 def assert_coherent(self):
  candidate=self.model(self.config.with_name(self.config.name+".media-actions.json"));active=self.model();self.assertEqual(candidate["manifest_generation"],active["manifest_generation"]);self.assertEqual(self.visible(),{t for t,v in active["items"].items() if v["item_type"]=="file"});return active
 def page(self,item):(self.home/".local/state/openhtpc/media-actions/current-page").parent.mkdir(parents=True,exist_ok=True);(self.home/".local/state/openhtpc/media-actions/current-page").write_text(item["page_id"]+"\n")
 def test_zero_to_one_real_add_and_security(self):
  self.assertEqual(sources.add_source(self.home,PAYLOAD,str(self.a)),(True,"SOURCE_AJOUTEE"));model=self.assert_coherent();token=next(t for t,v in model["items"].items() if v["relative_path"]=="Dvd/Alerte.mkv");self.page(model["items"][token]);self.assertEqual(play.load_media_action(self.home,token),model["items"][token]);self.assertTrue(play.resolve_media_request(self.home,model["items"][token]["source_id"],"Dvd/Alerte.mkv",model["items"][token]["page_id"])[0].is_absolute());self.assertNotIn(str(self.a/"Dvd/Alerte.mkv"),self.config.read_text());self.assertRaisesRegex(ValueError,"INVALID_ACTION_TOKEN",play.load_media_action,self.home,"mact_bad")
 def test_one_two_remove_all_and_readd(self):
  sources.add_source(self.home,PAYLOAD,str(self.a));old=next(iter(self.assert_coherent()["items"]));sources.add_source(self.home,PAYLOAD,str(self.b));self.assert_coherent();self.assertRaisesRegex(ValueError,"TOKEN_NOT_FOUND",play.load_media_action,self.home,old);sources.remove_source(self.home,PAYLOAD,str(self.a));self.assert_coherent();sources.remove_source(self.home,PAYLOAD,str(self.b));self.assertEqual(self.assert_coherent()["items"],{});sources.add_source(self.home,PAYLOAD,str(self.a));self.assert_coherent()
 def test_duplicate_refresh_and_dev12_optical_preserve(self):
  sources.add_source(self.home,PAYLOAD,str(self.a));model=self.assert_coherent();generation=model["manifest_generation"];token=next(iter(model["items"]));self.assertEqual(sources.add_source(self.home,PAYLOAD,str(self.a)),(True,"SOURCE_DEJA_AJOUTEE"));model=self.assert_coherent();self.assertNotEqual(model["manifest_generation"],generation);session.write_flex_config(self.config,self.home,[self.a],PAYLOAD,expected_optical_generation=0,media_generation=model["manifest_generation"]);self.assertEqual(self.model(self.config.with_name(self.config.name+".media-actions.json"))["manifest_generation"],model["manifest_generation"]);self.assertIn(next(iter(model["items"])),self.model()["items"])
 def test_failure_after_manifest_activation_restores_previous_generation(self):
  sources.add_source(self.home,PAYLOAD,str(self.a));candidate=self.config.with_name(self.config.name+".media-actions.json");current=session.current_media_manifest(self.home);user=self.home/".config/openhtpc/user-config.json";before={p:p.read_bytes() for p in (self.config,candidate,current,user)};old=self.model();old_generation=old["manifest_generation"];old_token=next(t for t,v in old["items"].items() if v["relative_path"]=="Dvd/Alerte.mkv");self.page(old["items"][old_token]);self.assertEqual(play.load_media_action(self.home,old_token),old["items"][old_token]);real_replace=os.replace;failed=False;attempted={}
  def fail_final(source,target):
   nonlocal failed
   source=pathlib.Path(source);target=pathlib.Path(target)
   if target==self.config and source.name.startswith(self.config.name+".") and ".publish." not in source.name and not failed:
    attempted.update(self.model());failed=True;raise OSError("INJECT_FINAL_CONFIG_FAILURE")
   return real_replace(source,target)
  with mock.patch.object(os,"replace",side_effect=fail_final):result=sources.add_source(self.home,PAYLOAD,str(self.b))
  self.assertTrue(failed);self.assertNotEqual(attempted["manifest_generation"],old_generation);new_token=next(t for t,v in attempted["items"].items() if v["relative_path"]=="Second.mkv");self.assertEqual({p:p.read_bytes() for p in (self.config,candidate,current)}, {p:before[p] for p in (self.config,candidate,current)});self.assert_coherent();self.assertEqual(self.model()["manifest_generation"],old_generation);self.assertEqual(play.load_media_action(self.home,old_token),old["items"][old_token]);self.assertRaisesRegex(ValueError,"TOKEN_NOT_FOUND",play.load_media_action,self.home,new_token);self.assertEqual(user.read_bytes(),before[user]);self.assertFalse(result[0],"publication failure must not report source-add success")
 def test_remove_failure_restores_config_publication_and_unrelated_keys(self):
  sources.add_source(self.home,PAYLOAD,str(self.a));sources.add_source(self.home,PAYLOAD,str(self.b));user=self.home/".config/openhtpc/user-config.json";data=json.loads(user.read_text());data.update({"audio_output_mode":"PCM","presentation_mode":"PURE","unrelated":{"keep":True}});sources.save_config(self.home,data);sources.refresh_system(self.home,PAYLOAD);candidate=self.config.with_name(self.config.name+".media-actions.json");current=session.current_media_manifest(self.home);before={p:p.read_bytes() for p in (self.config,candidate,current,user)};model=self.model();token=next(t for t,v in model["items"].items() if v["relative_path"]=="Second.mkv");self.page(model["items"][token]);real_replace=os.replace;failed=False
  def fail_final(source,target):
   nonlocal failed
   source=pathlib.Path(source);target=pathlib.Path(target)
   if target==self.config and source.name.startswith(self.config.name+".") and ".publish." not in source.name and not failed:failed=True;raise OSError("INJECT_REMOVE_FINAL_CONFIG_FAILURE")
   return real_replace(source,target)
  with mock.patch.object(os,"replace",side_effect=fail_final):result=sources.remove_source(self.home,PAYLOAD,str(self.b))
  self.assertTrue(failed);self.assertFalse(result[0]);self.assertEqual({p:p.read_bytes() for p in before},before);self.assertEqual(play.load_media_action(self.home,token),model["items"][token]);self.assertEqual(json.loads(user.read_text())["unrelated"],{"keep":True})
if __name__=="__main__":unittest.main()
