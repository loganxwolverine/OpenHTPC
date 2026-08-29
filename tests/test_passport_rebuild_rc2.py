from __future__ import annotations
import json,os,pathlib,shutil,subprocess,sys,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload"

class PassportRebuildWorkflow(unittest.TestCase):
 def test_public_workflow_refreshes_rebuilds_and_refreshes_without_user_data_loss(self):
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);home=root/"home";install=root/"install";config=home/".config/openhtpc";install.mkdir();config.mkdir(parents=True)
   for name in ("openhtpc","openhtpc-core.py"):shutil.copy2(PAYLOAD/name,install/name)
   answers={"display":{"resolution":"3840x2160","hdr":"Je ne sais pas","refresh_rate":"60 Hz"},"audio":{"destination":"Détection système","mode":"PCM"}}
   (config/"profile.json").write_text(json.dumps({"generator":{"name":"OPENHTPC Builder"},"user_answers":answers}))
   user={"configuration_completed":True,"local_media_sources":["/media/fixture"],"tmdb":{"configured":True}}
   (config/"user-config.json").write_text(json.dumps(user));(config/"tmdb.json").write_text('{"state":"synthetic"}')
   capability=install/"openhtpc-capabilities.py";builder=install/"openhtpc-builder.sh"
   capability.write_text("#!/bin/sh\nprintf 'refresh\\n' >>\"$OPENHTPC_HOME/order\"\n")
   builder.write_text("#!/bin/sh\n[ \"$1\" = --rebuild-passport ] || exit 2\nprintf 'rebuild\\n' >>\"$OPENHTPC_HOME/order\"\n")
   capability.chmod(0o755);builder.chmod(0o755)
   env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_INSTALL_DIR":str(install)}
   result=subprocess.run([sys.executable,str(install/"openhtpc"),"rebuild-passport"],env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual((home/"order").read_text(),"refresh\nrebuild\nrefresh\n")
   self.assertEqual(json.loads((config/"user-config.json").read_text()),user);self.assertEqual((config/"tmdb.json").read_text(),'{"state":"synthetic"}')
 def test_builder_requires_saved_answers_for_noninteractive_rebuild(self):
  source=(PAYLOAD/"openhtpc-builder.sh").read_text();self.assertIn('"--rebuild-passport"',source);self.assertIn("reconstruction non interactive refusée",source)

if __name__=="__main__":unittest.main()
