from __future__ import annotations

import importlib.util
import ast
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
GENERATOR_PATH = PAYLOAD / "openhtpc-runtime-generator.py"
SPEC = importlib.util.spec_from_file_location("runtime_generator_dev14", GENERATOR_PATH)
GENERATOR = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(GENERATOR)

OPTIONS = (
    "vo", "gpu-api", "hwdec", "vaapi-device", "include", "scale", "dscale",
    "cscale", "dither", "dither-depth", "scaler-resizes-only",
    "correct-downscaling", "linear-downscaling", "sigmoid-upscaling",
    "target-colorspace-hint", "gamut-mapping-mode",
)


def passport(node="/dev/dri/renderD128"):
    gpu = {"vendor":"amd", "pci_slot":"0000:01:00.0", "render_node":node,
           "vulkan_device":{"name":"AMD fixture", "type":"PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU"}}
    return {
        "schema":1, "generator":{"name":"OPENHTPC Builder", "version":"4.0.0"},
        "generated_at":"RC3-PASSPORT-PRESERVE", "detected":{"machine":"synthetic"},
        "media_stack":{"observed_capabilities":{"vaapi_decode":{"h264":True}}},
        "gpu_topology":{"display_gpu":gpu, "processing_gpu":gpu, "offload_required":False},
        "video_backend":{"vendor":"amd", "status":"observed", "decode_api":"vaapi",
                         "render_api":"vulkan", "render_node":node},
        "mpv_blueprint":{"obsolete_rc3_decision":True},
        "runtime":{"status":"pending", "reason":"RC3_INTEL_VENDOR_VETO"},
        "runtime_profiles":{"profiles":{"PURE":{"generation_status":"pending"}}},
        "mpv_configuration_generated":False,
    }


class Dev14UpdateRuntimeRegeneration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name); self.home = self.base / "home"
        self.config = self.home / ".config/openhtpc"; self.config.mkdir(parents=True)
        self.runtime = self.config / "runtime/mpv"; self.runtime.mkdir(parents=True)
        self.profile_path = self.config / "profile.json"
        self.profile_path.write_text(json.dumps(passport()), encoding="utf-8")
        (self.runtime / "pure.conf").write_text("RC3_STALE_PURE\nhwdec=no\n", encoding="utf-8")
        (self.runtime / "reference.conf").write_text("RC3_STALE_REFERENCE\n", encoding="utf-8")
        self.options = self.base / "options"; self.values = self.base / "values"
        reference = {"scale":"spline36", "dscale":"mitchell", "cscale":"spline36",
                     "dither":"fruit", "dither-depth":"auto", "target-colorspace-hint":"auto",
                     "gamut-mapping-mode":"auto"}
        self.options.write_text("".join(f" --{name} String {reference.get(name, 'available')}\n" for name in OPTIONS), encoding="utf-8")
        self.values.write_text("gpu-next vulkan vaapi\n", encoding="utf-8")
        self.version = self.base / "version.json"
        self.version.write_text(json.dumps({"version":"1.1.3-dev14", "build_id":"update-runtime-regeneration-dev14"}), encoding="utf-8")

    def generate(self):
        return GENERATOR.generate(self.profile_path, self.runtime / "pure.conf",
                                  self.runtime / "reference.conf", self.options, self.values, self.version)

    def test_01_rc3_stale_runtime_is_replaced_by_current_files(self):
        self.generate(); pure = (self.runtime / "pure.conf").read_text()
        self.assertNotIn("RC3_STALE", pure); self.assertIn("1.1.3-dev14 / update-runtime-regeneration-dev14", pure)

    def test_02_current_mpv_policy_and_hardware_path_are_materialized(self):
        self.generate(); pure = (self.runtime / "pure.conf").read_text()
        self.assertIn("vo=gpu-next", pure); self.assertIn("gpu-api=vulkan", pure)
        self.assertIn("hwdec=vaapi", pure); self.assertIn("vaapi-device=/dev/dri/renderD128", pure)

    def test_03_stale_runtime_policy_cannot_survive(self):
        result = self.generate()
        self.assertEqual(result["runtime"]["status"], "ready")
        self.assertNotIn("RC3_INTEL_VENDOR_VETO", json.dumps(result))
        self.assertEqual(result["runtime"]["generation_provenance"]["build_id"], "update-runtime-regeneration-dev14")

    def test_04_valid_hardware_passport_acquisition_data_is_preserved(self):
        before = json.loads(self.profile_path.read_text())
        self.generate(); after = json.loads(self.profile_path.read_text())
        for key in ("generator", "generated_at", "detected", "gpu_topology", "video_backend", "media_stack", "mpv_blueprint"):
            self.assertEqual(after[key], before[key])

    def test_05_generation_is_idempotent(self):
        self.generate(); first = (self.runtime / "pure.conf").read_bytes()
        self.generate(); second = (self.runtime / "pure.conf").read_bytes()
        self.assertEqual(first, second)

    def test_06_failure_removes_stale_configs_and_raises(self):
        self.values.write_text("missing required values\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_REGENERATION_NOT_READY"):
            self.generate()
        self.assertFalse((self.runtime / "pure.conf").exists())
        self.assertEqual(json.loads(self.profile_path.read_text())["runtime"]["status"], "pending")

    def test_07_invalid_passport_fails_without_deleting_user_state(self):
        value = passport(); value["schema"] = 999; self.profile_path.write_text(json.dumps(value))
        user = self.config / "user-config.json"; user.write_text('{"audio_output_mode":"PCM"}')
        with self.assertRaisesRegex(RuntimeError, "HARDWARE_PASSPORT_SCHEMA_UNSUPPORTED"):
            self.generate()
        self.assertTrue(user.is_file())

    def test_08_builder_exposes_noninteractive_authoritative_regeneration(self):
        source = (PAYLOAD / "openhtpc-builder.sh").read_text()
        self.assertIn('--regenerate-runtime', source)
        self.assertEqual(source.count('"$RUNTIME_GENERATOR" "$PROFILE_FILE"'), 2)

    def test_09_update_orders_capability_refresh_before_runtime_regeneration(self):
        installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
        refresh = '"$INSTALL_DIR/openhtpc-capabilities.py" --refresh'
        regenerate = '"$INSTALLED_BUILDER" --regenerate-runtime'
        self.assertLess(installer.index(refresh), installer.index(regenerate))
        self.assertIn('die "La régénération du runtime courant a échoué', installer)

    def test_10_fresh_install_still_runs_normal_builder(self):
        installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
        self.assertIn('elif [[ ! -f ${HOME}/.config/openhtpc/profile.json ]]; then', installer)
        self.assertIn('"$INSTALLED_BUILDER"\n    stage RUNTIME', installer)

    def test_11_update_executes_and_preserves_persistent_state(self):
        candidate = self.base / "candidate"; payload = candidate / "payload"
        payload.mkdir(parents=True)
        for name in ("update.sh", "install.sh", "legacy-managed-files-dev27.txt"):
            shutil.copy2(ROOT / name, candidate / name)
        for source in PAYLOAD.iterdir():
            if source.is_file(): shutil.copy2(source, payload / source.name)
        for relative in ("plugins/README.md", "plugins/available/plugin.bluray/plugin.json",
                         "plugins/available/plugin.bluray/shadow.py",
                         "plugins/available/plugin.bluray/assets/bluray-media-badge.png",
                         "plugins/available/plugin.bluray/assets/uhd-bluray-media-badge.png",
                         "flex/bin/flex-launcher", "flex/BUILD-METADATA.json",
                         "flex/assets/fonts/OpenSans-Regular.ttf", "flex/assets/icons/drive-empty.png",
                         "flex/assets/icons/dvd.png", "assets/branding/openhtpc-logo.png",
                         "assets/branding/openhtpc-wallpaper.png"):
            target = payload / relative; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PAYLOAD / relative, target)
        for relative in ("assets/ui", "assets/benchmark", "assets/shaders"):
            (payload / relative).mkdir(parents=True, exist_ok=True)
        # Bounded system adapters keep the real updater and installer focused on
        # migration semantics without package, network, or hardware mutation.
        (payload / "openhtpc-fedora-dependencies.py").write_text("#!/usr/bin/env python3\nraise SystemExit(0)\n")
        (payload / "openhtpc-dvd-dependencies.py").write_text("#!/usr/bin/env python3\nprint('LIBDVDCSS_STATE=LIBDVDCSS_READY')\n")
        (payload / "openhtpc-capabilities.py").write_text("""#!/usr/bin/env python3
import json,os,pathlib
p=pathlib.Path(os.environ['HOME'])/'.config/openhtpc/profile.json'
v=json.loads(p.read_text());v['canonical_capability_refresh']='DEV14_CURRENT';p.write_text(json.dumps(v))
count=pathlib.Path(os.environ['HOME'])/'.local/state/openhtpc/capability-refresh-count'
count.parent.mkdir(parents=True,exist_ok=True);count.write_text(str(int(count.read_text())+1 if count.exists() else 1))
raise SystemExit(0)
""")
        for name in ("openhtpc-fedora-dependencies.py", "openhtpc-dvd-dependencies.py", "openhtpc-capabilities.py"):
            (payload / name).chmod(0o755)
        install = self.home / ".local/lib/openhtpc"; install.mkdir(parents=True)
        (install / ".openhtpc-managed-files").write_text("VERSION\n")
        persistent = {
            self.config / "user-config.json":{"audio_output_mode":"PCM", "media_sources":["/media/fixture"]},
            self.config / "tmdb.json":{"credential":"synthetic-not-secret"},
            self.home / ".local/share/openhtpc/media-cache/dvd/disc-fixture/metadata.json":{"confirmed_tmdb_id":123},
        }
        for path, value in persistent.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
        fakebin = self.base / "bin"; fakebin.mkdir()
        mpv = fakebin / "mpv"
        mpv.write_text("#!/bin/sh\ncase \"$*\" in *--list-options*) cat \"$OPENHTPC_TEST_OPTIONS\";; *) printf 'gpu-next vulkan vaapi\\n';; esac\n")
        mpv.chmod(0o755)
        for name, body in {
            "rpm":"#!/bin/sh\n[ \"${1:-}\" = -q ] && exit 0\n[ \"${1:-}\" = -E ] && { printf '44\\n'; exit 0; }\nexit 0\n",
            "dnf5":"#!/bin/sh\nexit 0\n",
            "lspci":"#!/bin/sh\nprintf '0000:01:00.0 VGA compatible controller [1002:ffff]\\n'\n",
        }.items():
            path=fakebin/name;path.write_text(body);path.chmod(0o755)
        env = {**os.environ, "HOME":str(self.home), "OPENHTPC_HOME":str(self.home), "OPENHTPC_INSTALL_DIR":str(install),
               "OPENHTPC_TEST_OPTIONS":str(self.options), "PATH":str(fakebin)+os.pathsep+os.environ["PATH"]}
        env.pop("DISPLAY", None); env.pop("WAYLAND_DISPLAY", None)
        result = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, value in persistent.items(): self.assertEqual(json.loads(path.read_text()), value)
        self.assertEqual(json.loads(self.profile_path.read_text())["generated_at"], "RC3-PASSPORT-PRESERVE")
        self.assertEqual(json.loads(self.profile_path.read_text())["canonical_capability_refresh"], "DEV14_CURRENT")
        refresh_count = self.home / ".local/state/openhtpc/capability-refresh-count"
        self.assertEqual(refresh_count.read_text(), "1")
        self.assertNotIn("RC3_STALE", (self.runtime / "pure.conf").read_text())
        target = json.loads((payload / "version.json").read_text())
        self.assertIn(f'{target["version"]} / {target["build_id"]}', (self.runtime / "pure.conf").read_text())
        second = subprocess.run([str(candidate / "update.sh")], cwd=candidate, env=env, text=True, capture_output=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(refresh_count.read_text(), "2")
        for path, value in persistent.items(): self.assertEqual(json.loads(path.read_text()), value)
        self.assertEqual(json.loads(self.profile_path.read_text())["runtime"]["status"], "ready")

    def test_12_fixture_is_bounded_and_never_copies_the_repository(self):
        tree = ast.parse(pathlib.Path(__file__).read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(call.func, ast.Attribute) and call.func.attr == "copytree" for call in calls))

    def test_13_managed_ownership_includes_only_generated_helper_not_user_runtime(self):
        manifest = (PAYLOAD / "managed-files.txt").read_text().splitlines()
        self.assertIn("openhtpc-runtime-generator.py", manifest)
        self.assertFalse(any(value.startswith(".config/") or "pure.conf" in value for value in manifest))

    def test_14_installer_propagates_passport_capability_and_runtime_failures(self):
        installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text()
        self.assertIn("Hardware Passport absent : impossible de régénérer", installer)
        self.assertIn("refresh canonique des capacités a échoué", installer)
        self.assertIn("La régénération du runtime courant a échoué", installer)
        self.assertNotIn('"$INSTALLED_BUILDER" --regenerate-runtime || true', installer)


if __name__ == "__main__":
    unittest.main()
