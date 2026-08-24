from __future__ import annotations

import os
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "payload/install-openhtpc-fedora.sh"
BUILDER = ROOT / "payload/openhtpc-builder.sh"


def function_prefix() -> str:
    source = INSTALLER.read_text(encoding="utf-8")
    return source.split('[[ ${EUID} -ne 0 ]]', 1)[0]


def exercise(*, vendor: str, va_complete: bool, ffmpeg_complete: bool,
             answer: str = "N", repos: str = "rpmfusion-free", fail_install: bool = False,
             installed: str = ""):
    values = "true" if va_complete else "false"
    ffmpeg = "true" if ffmpeg_complete else "false"
    scenario = function_prefix() + f"""
amd_gpu_present={'true' if vendor == 'amd' else 'false'}
intel_gpu_present={'true' if vendor == 'intel' else 'false'}
VA_H264={values}; VA_HEVC={values}; VA_HEVC10={values}
FFMPEG_H264={ffmpeg}; FFMPEG_HEVC={ffmpeg}
DRY_RUN=false; DNF=fake-dnf; MEDIA_FILE="$TEMP_DIR/media"
rpm() {{
  if [[ $1 == -E ]]; then printf '44\\n'; return 0; fi
  if [[ $1 == -q && " {installed} " == *" $2 "* ]]; then return 0; fi
  return 1
}}
fake-dnf() {{
  if [[ " $* " == *" repolist --enabled "* ]]; then
    for value in {repos!r}; do printf '%s repo\\n' "$value"; done
  elif [[ " $* " == *" repoquery --available "* ]]; then return 0
  elif [[ " $* " == *" install "* ]]; then {'return 1' if fail_install else 'return 0'}
  fi
}}
sudo() {{ printf 'SUDO'; printf ' %s' "$@"; printf '\\n'; "$@"; }}
collect_media_stack() {{ : >"$1"; }}
read_media_capabilities() {{ :; }}
show_media_stack() {{ :; }}
install_multimedia_extension
"""
    with tempfile.TemporaryDirectory() as raw:
        path = pathlib.Path(raw) / "scenario.sh"
        path.write_text(scenario, encoding="utf-8")
        return subprocess.run(
            ["bash", str(path)], input=answer + "\n", text=True, capture_output=True,
            env={**os.environ, "HOME": raw, "TERM": "dumb"}, check=False,
        )


class AmdCodecPhase2BEnablement(unittest.TestCase):
    def test_amd_restricted_stack_proposes_both_required_complements(self):
        result = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False)
        self.assertIn("mesa-va-drivers-freeworld libavcodec-freeworld", result.stdout)
        self.assertNotIn("intel-media-driver", result.stdout)

    def test_complete_stack_has_no_transaction(self):
        result = exercise(vendor="amd", va_complete=True, ffmpeg_complete=True)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Transaction proposée", result.stdout)
        self.assertNotIn("SUDO", result.stdout)

    def test_already_installed_complements_are_not_reinstalled(self):
        result = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False,
                          installed="mesa-va-drivers-freeworld libavcodec-freeworld")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Transaction proposée", result.stdout)

    def test_intel_and_amd_package_families_do_not_cross(self):
        intel = exercise(vendor="intel", va_complete=False, ffmpeg_complete=True)
        amd = exercise(vendor="amd", va_complete=False, ffmpeg_complete=True)
        self.assertIn("intel-media-driver", intel.stdout)
        self.assertNotIn("mesa-va-drivers-freeworld", intel.stdout)
        self.assertIn("mesa-va-drivers-freeworld", amd.stdout)
        self.assertNotIn("intel-media-driver", amd.stdout)

    def test_refusal_performs_no_mutation(self):
        result = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False, answer="N", repos="")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("SUDO", result.stdout)
        self.assertIn("pile Fedora est conservée", result.stdout)

    def test_enabled_rpmfusion_uses_exact_additive_transaction(self):
        result = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False, answer="o")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SUDO fake-dnf install --refresh mesa-va-drivers-freeworld libavcodec-freeworld", result.stdout)
        self.assertNotIn("rpmfusion-free-release-44", result.stdout)
        self.assertNotIn(" swap ", result.stdout)

    def test_absent_rpmfusion_requires_consent_before_bootstrap(self):
        refused = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False, answer="N", repos="")
        accepted = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False, answer="o", repos="")
        self.assertNotIn("rpmfusion-free-release-44", refused.stdout)
        self.assertIn("rpmfusion-free-release-44", accepted.stdout)

    def test_transaction_failure_stops_without_fake_capability(self):
        result = exercise(vendor="amd", va_complete=False, ffmpeg_complete=False, answer="o", fail_install=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("L'installation de l'extension multimédia a échoué", result.stderr)
        self.assertNotIn("Media Stack observée après extension", result.stdout)

    def test_capability_refresh_and_qualified_runtime_are_preserved(self):
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('"$INSTALL_DIR/openhtpc-capabilities.py" --refresh', installer)
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertNotIn('backend.get("vendor") != "intel"', builder)
        self.assertIn('hwdec=vaapi', builder)
        self.assertIn('gpu-api=vulkan', builder)

    def test_installer_always_runs_canonical_refresh_after_noop_package_path(self):
        installer = INSTALLER.read_text(encoding="utf-8")
        canonical = '"$INSTALL_DIR/openhtpc-capabilities.py" --refresh'
        self.assertEqual(installer.count(canonical), 1)
        self.assertGreater(installer.index(canonical), installer.index("install_multimedia_extension"))

    def run_profile_refresh(self, initial, values=(True, True, True, False, True, False)):
        scenario = function_prefix() + """
DNF=fake-dnf; MEDIA_FILE="$TEMP_DIR/media"
fake-dnf() { printf 'rpmfusion-free repo\\n'; }
VA_MPEG2=%s; VA_H264=%s; VA_HEVC=%s; VA_HEVC10=%s; VA_VP9=%s; VA_AV1=%s
FFMPEG_H264=true; FFMPEG_HEVC=true; FFMPEG_AV1=false
printf 'vainfo: Driver version: Mesa fixture\\n' >"$MEDIA_FILE"
refresh_profile_media_stack
""" % tuple("true" if value else "false" for value in values)
        with tempfile.TemporaryDirectory() as raw:
            config = pathlib.Path(raw) / ".config/openhtpc"
            config.mkdir(parents=True)
            profile = config / "profile.json"
            profile.write_text(json.dumps(initial))
            script = pathlib.Path(raw) / "refresh.sh"
            script.write_text(scenario, encoding="utf-8")
            result = subprocess.run(["bash", str(script)], text=True, capture_output=True,
                                    env={**os.environ, "HOME": raw, "TERM": "dumb"}, check=False)
            return result, json.loads(profile.read_text())

    def test_targeted_passport_refresh_preserves_runtime_and_records_truth(self):
        result, updated = self.run_profile_refresh({"runtime": {"status": "ready"}, "sentinel": "preserved"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(updated["runtime"], {"status": "ready"})
        self.assertEqual(updated["sentinel"], "preserved")
        self.assertTrue(updated["media_stack"]["rpmfusion_enabled"])
        self.assertTrue(updated["media_stack"]["observed_capabilities"]["vaapi_decode"]["h264"])
        self.assertFalse(updated["media_stack"]["observed_capabilities"]["vaapi_decode"]["hevc_main10"])

    def test_media_stack_owns_current_observation_and_all_topology_mirrors_follow(self):
        old = {"mpeg2": True, "h264": False, "hevc": False, "hevc_main10": False, "vp9": True, "av1": False}
        initial = {"media_stack": {"observed_capabilities": {"vaapi_decode": old}},
                   "gpu_topology": {"display_gpu": {"vaapi_decode": old.copy()},
                                    "processing_gpu": {"vaapi_decode": old.copy()},
                                    "gpus": [{"vaapi_decode": old.copy()}]}}
        result, updated = self.run_profile_refresh(initial, (False, True, True, True, True, False))
        self.assertEqual(result.returncode, 0, result.stderr)
        current = updated["media_stack"]["observed_capabilities"]["vaapi_decode"]
        for gpu in (updated["gpu_topology"]["display_gpu"], updated["gpu_topology"]["processing_gpu"],
                    updated["gpu_topology"]["gpus"][0]):
            self.assertEqual(gpu["vaapi_decode"], current)
        self.assertIn("capability=vaapi_decode.mpeg2 before=true after=false change=LOSS", result.stdout)
        self.assertIn("capability=vaapi_decode.h264 before=false after=true change=GAIN", result.stdout)
        self.assertIn("capability=vaapi_decode.hevc before=false after=true change=GAIN", result.stdout)

    def test_second_refresh_is_idempotent(self):
        initial = {"media_stack": {"observed_capabilities": {"vaapi_decode": {"mpeg2": True}}}}
        first_result, first = self.run_profile_refresh(initial)
        second_result, second = self.run_profile_refresh(first)
        self.assertEqual((first_result.returncode, second_result.returncode), (0, 0))
        self.assertEqual(first, second)
        self.assertNotIn("CAPABILITY_CHANGE", second_result.stdout)

    def test_invalid_profile_fails_without_partial_update(self):
        scenario = function_prefix() + """
DNF=fake-dnf; MEDIA_FILE="$TEMP_DIR/media"; fake-dnf() { :; }
VA_MPEG2=false; VA_H264=true; VA_HEVC=true; VA_HEVC10=true; VA_VP9=true; VA_AV1=false
FFMPEG_H264=true; FFMPEG_HEVC=true; FFMPEG_AV1=false
: >"$MEDIA_FILE"
refresh_profile_media_stack
"""
        with tempfile.TemporaryDirectory() as raw:
            config = pathlib.Path(raw) / ".config/openhtpc"; config.mkdir(parents=True)
            target = config / "profile.json"; target.write_text("{broken", encoding="utf-8")
            script = pathlib.Path(raw) / "refresh.sh"; script.write_text(scenario, encoding="utf-8")
            result = subprocess.run(["bash", str(script)], text=True, capture_output=True,
                                    env={**os.environ, "HOME": raw, "TERM": "dumb"}, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "{broken")

    def test_rpmfusion_truth_accepts_any_enabled_family(self):
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("grep -Eq '^rpmfusion-(free|nonfree)(-|$)'", builder)
        self.assertNotIn("grep -Fxq rpmfusion-free &&", builder)


if __name__ == "__main__":
    unittest.main()
