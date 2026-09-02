from __future__ import annotations
import importlib.util,json,os,pathlib,subprocess,tempfile,unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1];PAYLOAD=ROOT/"payload";BASE="83c58460275813f7ac05c67fc75e51fb020ec2fd"
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
REGISTRY=load("p2_registry",PAYLOAD/"openhtpc-plugin-registry.py");CORE=load("p2_core",PAYLOAD/"openhtpc-core.py")
def manifest(plugin_id="plugin.sample",api=2,minimum="1.2.0",maximum=None,entrypoint=None,enabled=False):
 return {"schema":"openhtpc-plugin-v2","id":plugin_id,"name":"Sample Plugin","version":"0.1.0","plugin_api":api,
         "openhtpc":{"minimum":minimum,"maximum":maximum},"category":"media","entrypoint":entrypoint,
         "capabilities":["capability","doctor"],"dependencies":{"plugins":[],"capabilities":[]},
         "system_dependencies":["sample-runtime"],"enabled_by_default":enabled,"resources":{},"doctor":{"label":"Sample Plugin","capability":"sample-ready"}}

class RegistryFixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=pathlib.Path(self.temp.name);self.home=root/"home";self.install=root/"install";self.install.mkdir();(self.install/"VERSION").write_text("1.2.0-dev2\n")
 def add(self,value,plugin_id="plugin.sample",user=False,raw=False):
  base=REGISTRY.paths(self.home,self.install)["available"][1 if user else 0];target=base/plugin_id;target.mkdir(parents=True)
  (target/"plugin.json").write_text(value if raw else json.dumps(value));return target

class ManifestAndDiscovery(RegistryFixture):
 def test_valid_manifest_is_installed_and_disabled(self):
  self.add(manifest());item=REGISTRY.registry(self.home,self.install)["plugins"][0];self.assertEqual((item["installation_state"],item["state"]),("INSTALLED","DISABLED"))
 def test_malformed_manifest_is_broken(self):self.add("{",raw=True);self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["state"],"BROKEN")
 def test_missing_field_is_broken(self):
  value=manifest();value.pop("category");self.add(value);self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_SCHEMA_INVALID")
 def test_duplicate_plugin_id_is_rejected(self):
  self.add(manifest());self.add(manifest(),user=True);value=REGISTRY.registry(self.home,self.install);self.assertEqual(value["plugins"][0]["state"],"BROKEN");self.assertEqual(value["errors"][0]["reason"],"PLUGIN_DUPLICATE")
 def test_unsupported_plugin_api(self):self.add(manifest(api=1));self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_API_UNSUPPORTED")
 def test_openhtpc_version_incompatible(self):self.add(manifest(minimum="2.0.0"));self.assertEqual(REGISTRY.registry(self.home,self.install)["plugins"][0]["state"],"INCOMPATIBLE")
 def test_disabled_and_enabled_compatible_plugin(self):
  self.add(manifest());self.assertEqual(REGISTRY.registry(self.home,self.install)["plugins"][0]["state"],"DISABLED")
  self.assertEqual(REGISTRY.set_enabled(self.home,self.install,"plugin.sample",True)["plugins"][0]["state"],"AVAILABLE")
 def test_deterministic_ordering(self):
  self.add(manifest("plugin.zulu"),"plugin.zulu");self.add(manifest("plugin.alpha"),"plugin.alpha");self.assertEqual([item["id"] for item in REGISTRY.registry(self.home,self.install)["plugins"]],["plugin.alpha","plugin.zulu"])
 def test_directory_traversal_entrypoint_rejected(self):self.add(manifest(entrypoint="../escape"));self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_PATH_INVALID")
 def test_absolute_entrypoint_rejected(self):self.add(manifest(entrypoint="/bin/true"));self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_PATH_INVALID")
 def test_symlink_plugin_directory_rejected(self):
  root=REGISTRY.paths(self.home,self.install)["available"][0];root.mkdir(parents=True);outside=self.install/"outside";outside.mkdir();(root/"plugin.sample").symlink_to(outside,target_is_directory=True)
  self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_PATH_INVALID")
 def test_symlink_entrypoint_rejected(self):
  target=self.add(manifest(entrypoint="entry.py"));outside=self.install/"outside.py";outside.write_text("pass\n");(target/"entry.py").symlink_to(outside)
  self.assertEqual(REGISTRY.registry(self.home,self.install)["errors"][0]["reason"],"PLUGIN_PATH_INVALID")
 def test_discovery_does_not_execute_entrypoint(self):
  target=self.add(manifest(entrypoint="entry.py"));marker=self.home/"executed";(target/"entry.py").write_text(f"open({str(marker)!r},'w').write('bad')\n");REGISTRY.registry(self.home,self.install);self.assertFalse(marker.exists())
 def test_discovery_performs_no_network_access(self):
  self.add(manifest());
  with mock.patch("socket.socket",side_effect=AssertionError("network attempted")):self.assertEqual(len(REGISTRY.registry(self.home,self.install)["plugins"]),1)
 def test_snapshot_is_deterministic(self):
  self.add(manifest());REGISTRY.publish(self.home,self.install);path=REGISTRY.paths(self.home,self.install)["snapshot"];first=path.read_bytes();REGISTRY.publish(self.home,self.install);self.assertEqual(path.read_bytes(),first)

class DoctorAndLifecycle(RegistryFixture):
 def test_doctor_state_mapping_and_absence(self):
  self.assertEqual({item["label"]:item["status"] for item in CORE.optional_plugin_states({})}["Blu-ray"],"NOT_INSTALLED")
  value={"plugins":[{**manifest("plugin.sample"),"state":"INCOMPATIBLE"}]};self.assertEqual(CORE.optional_plugin_states(value)[-1],{"label":"Sample Plugin","status":"INCOMPATIBLE"})
 def test_bluray_and_uhd_remain_not_installed(self):
  states={item["label"]:item["status"] for item in CORE.optional_plugin_states(REGISTRY.registry(self.home,self.install))};self.assertEqual((states["Blu-ray"],states["UHD"]),("NOT_INSTALLED","NOT_INSTALLED"))
 def test_installer_and_update_ownership(self):
  installer=(PAYLOAD/"install-openhtpc-fedora.sh").read_text();managed=(PAYLOAD/"managed-files.txt").read_text();update=(ROOT/"update.sh").read_text();uninstall=(ROOT/"uninstall.sh").read_text()
  self.assertIn("openhtpc-plugin-registry.py",installer);self.assertIn("openhtpc-plugin-registry.py",managed);self.assertIn("plugins/available",installer)
  for user_path in ("plugins-enabled-v2.json","plugin-data","plugin-registry-v2.json"):self.assertNotIn(user_path,update)
  self.assertIn("1\\.2\\.0-dev[0-9]+",uninstall)
 def test_explicit_hooks_are_bounded(self):self.assertEqual(REGISTRY.HOOKS,{"capability","doctor","ui_menu","media_handler","dispatcher"})

class QualifiedBoundaries(unittest.TestCase):
 def test_qualified_sources_unchanged(self):
  names=("openhtpc-protected-optical.py","openhtpc-play-dvd","openhtpc-media-browser.py","openhtpc-tmdb.py","openhtpc-runtime-generator.py","openhtpc-gpu-policy.py","openhtpc-builder.sh")
  for name in names:
   baseline=subprocess.run(["git","show",f"{BASE}:payload/{name}"],cwd=ROOT,text=True,capture_output=True,check=True).stdout
   self.assertEqual((PAYLOAD/name).read_text(),baseline,name)
 def test_no_network_or_arbitrary_manifest_execution(self):
  source=(PAYLOAD/"openhtpc-plugin-registry.py").read_text().lower()
  for marker in ("subprocess","shell=true","urlopen(","requests.","curl ","wget ","http://","https://","exec(","eval("):self.assertNotIn(marker,source)

if __name__=="__main__":unittest.main()
