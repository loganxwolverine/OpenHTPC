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
CURRENT_BUILD_ID = "nvidia-native-backend-dev18"


def fixture(root: pathlib.Path, *, top="1.1.2-dev5", payload="1.1.2-dev5",
            json_version="1.1.2-dev5", installer="1.1.2-dev5", build_id=BUILD_ID):
    (root / "payload").mkdir(parents=True)
    (root / "VERSION").write_text(top + "\n", encoding="utf-8")
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
        self.assertEqual(values["top_version"], "1.1.3-dev18")


if __name__ == "__main__":
    unittest.main()
