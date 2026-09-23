from __future__ import annotations

import importlib.util
import json
import pathlib
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/openhtpc_release_metadata.py"
SPEC = importlib.util.spec_from_file_location("release_metadata", TOOL)
MODULE = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(MODULE)
BUILD_ID = "amd-codec-release-metadata-consistency-dev5"
CURRENT_BUILD_ID = "public-release-1.2.0-rc8"


def fixture(root: pathlib.Path, *, top="1.1.2-dev5", payload="1.1.2-dev5",
            json_version="1.1.2-dev5", installer="1.1.2-dev5", build_id=BUILD_ID):
    (root / "payload").mkdir(parents=True)
    (root / "VERSION").write_text(top + "\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"# OPENHTPC {top.replace('-', ' ').upper()}\nVersion: `{top}`\n"
        f"sha256sum -c {MODULE.release_artifact_name(top)}.sha256\n",
        encoding="utf-8",
    )
    (root / "payload/VERSION").write_text(payload + "\n", encoding="utf-8")
    (root / "payload/version.json").write_text(json.dumps({"version": json_version, "build_id": build_id}), encoding="utf-8")
    (root / "payload/install-openhtpc-fedora.sh").write_text(
        f'#!/bin/bash\nreadonly OPENHTPC_VERSION="{installer}"\n', encoding="utf-8")


class ReleaseMetadataConsistency(unittest.TestCase):
    def temporary(self):
        raw = tempfile.TemporaryDirectory(); self.addCleanup(raw.cleanup); return pathlib.Path(raw.name)

    def test_exact_dev4_split_state_is_rejected(self):
        root = self.temporary(); fixture(root, payload="1.1.2-dev2", installer="1.1.2-dev2")
        with self.assertRaisesRegex(ValueError, "RELEASE_METADATA_VERSION_MISMATCH"):
            MODULE.validate_tree(root, BUILD_ID)

    def test_each_version_representation_is_guarded(self):
        for field in ("payload", "json_version", "installer"):
            with self.subTest(field=field):
                root = self.temporary(); fixture(root, **{field: "1.1.2-old"})
                with self.assertRaisesRegex(ValueError, "RELEASE_METADATA_VERSION_MISMATCH"):
                    MODULE.validate_tree(root, BUILD_ID)

    def test_build_id_is_guarded(self):
        root = self.temporary(); fixture(root, build_id="stale-build")
        with self.assertRaisesRegex(ValueError, "RELEASE_METADATA_BUILD_ID_MISMATCH"):
            MODULE.validate_tree(root, BUILD_ID)

    def test_propagation_uses_only_root_version_and_intended_build(self):
        root = self.temporary(); fixture(root, payload="1.1.2-dev2", json_version="1.1.2-dev4",
                                        installer="1.1.2-dev2", build_id="old")
        values = MODULE.propagate(root, BUILD_ID)
        self.assertEqual(set(values[key] for key in ("top_version", "payload_version", "json_version", "installer_version")), {"1.1.2-dev5"})
        self.assertEqual(values["build_id"], BUILD_ID)

    def test_extracted_archive_metadata_is_validated(self):
        root = self.temporary(); tree = root / "candidate"; fixture(tree)
        archive = root / "candidate.tar.gz"
        with tarfile.open(archive, "w:gz") as output: output.add(tree, arcname="candidate")
        self.assertEqual(MODULE.validate_archive(archive, BUILD_ID)["top_version"], "1.1.2-dev5")

    def test_installed_layout_simulation_matches_cli_and_doctor_metadata(self):
        root = self.temporary(); fixture(root)
        MODULE.validate_installed_layout(root / "payload", "1.1.2-dev5", BUILD_ID)

    def test_current_source_tree_is_consistent(self):
        values = MODULE.validate_tree(ROOT, CURRENT_BUILD_ID)
        self.assertEqual(values["top_version"], "1.2.0-rc8")

    def test_current_distribution_readme_matches_release_identity(self):
        version = MODULE.canonical_version(ROOT)
        MODULE.validate_distribution_readme((ROOT / "README.md").read_text(encoding="utf-8"), version)

    def test_stale_distribution_readme_identity_is_rejected(self):
        stale = "# OPENHTPC 1.1.2 AMD Base Validation Candidate\nVersion: `1.1.2-dev1`\n"
        with self.assertRaisesRegex(ValueError, "RELEASE_README_ACTIVE_IDENTITY_MISMATCH"):
            MODULE.validate_distribution_readme(stale, "1.2.0-rc1")

    def test_rc2_builder_requires_human_physical_validation(self):
        builder = (ROOT / "tools/build-1.1.3-rc2.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.1.3-rc2"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"rc2_physical_qualification": "PENDING"', builder)

    def test_1_2_0_rc3_builder_requires_human_physical_release_gate(self):
        builder = (ROOT / "tools/build-1.2.0-rc3.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc3"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"protected_bluray_audio_fix": "SOFTWARE_PASS_PHYSICAL_VALIDATION_REQUIRED"', builder)

    def test_1_2_0_rc4_builder_requires_human_physical_release_gate(self):
        builder = (ROOT / "tools/build-1.2.0-rc4.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc4"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"protected_bluray_audio_fix": "PIPEWIRE_HDMI_HD_PASSTHROUGH_PREPARATION"', builder)

    def test_1_2_0_rc5_builder_requires_human_physical_release_gate(self):
        builder = (ROOT / "tools/build-1.2.0-rc5.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc5"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"protected_bluray_audio_fix": "PIPEWIRE_EFFECTIVE_IEC958_VERIFICATION"', builder)

    def test_1_2_0_rc6_builder_requires_human_physical_release_gate(self):
        builder = (ROOT / "tools/build-1.2.0-rc6.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc6"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"media_audio_fix": "MEDIA_PIPEWIRE_IEC958_RECOVERY"', builder)

    def test_1_2_0_rc7_builder_requires_human_physical_release_gate(self):
        builder = (ROOT / "tools/build-1.2.0-rc7.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc7"', builder)
        self.assertIn('"physical_qualification": "PENDING"', builder)
        self.assertIn('"media_audio_fix": "HD_BITSTREAM_DISPLAY_RESYNC_LIFECYCLE"', builder)

    def test_1_2_0_rc8_builder_records_completed_physical_qualification(self):
        builder = (ROOT / "tools/build-1.2.0-rc8.py").read_text(encoding="utf-8")
        self.assertIn('BUILD = "public-release-1.2.0-rc8"', builder)
        self.assertIn('"physical_qualification": "PASS_REFERENCE_BENCH"', builder)
        self.assertIn('"human_physical_validation_required": False', builder)
        self.assertIn('"unicode_cjk": "PASS"', builder)

    def test_1_2_0_rc8_builder_rebuilds_flex_from_exact_commit_and_fails_closed(self):
        builder = (ROOT / "tools/build-1.2.0-rc8.py").read_text(encoding="utf-8")
        self.assertIn("devctl._export_commit(commit, staging, scratch)", builder)
        self.assertIn("devctl._build_flex(flex_source", builder)
        self.assertIn('"schema": 2', builder)
        self.assertIn('"source_commit": commit', builder)
        self.assertIn('for marker in ("LiveActivityState", "FallbackFont")', builder)
        self.assertIn("devctl._verify_artifact(archive)", builder)
        self.assertNotIn("for path in files():", builder)


if __name__ == "__main__":
    unittest.main()
