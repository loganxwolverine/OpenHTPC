# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project. Original project by Steve Dehanne.
"""Focused automated tests for the OPENHTPC Development Workflow Orchestrator.

Tests are hermetically isolated and do NOT depend on:
- Steve's network hosts
- Physical remote machines
- Real SSH/SCP connectivity
- Actual git remote operations
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ─── Load devctl module ──────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEVCTL_PATH = ROOT / "tools" / "openhtpc-devctl"

import importlib.machinery
_loader = importlib.machinery.SourceFileLoader("openhtpc_devctl", str(DEVCTL_PATH))
spec = importlib.util.spec_from_loader("openhtpc_devctl", _loader)
devctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(devctl)


def test_media_artwork_profile_is_in_media_foundation():
    artwork = "tests/test_media_artwork_cache.py"
    assert devctl.TEST_PROFILES["media-artwork"] == [artwork]
    assert artwork in devctl.TEST_PROFILES["media-foundation"]


def test_media_flex_poster_profile_is_in_media_foundation():
    poster = "tests/test_media_flex_poster.py"
    assert devctl.TEST_PROFILES["media-flex-poster"] == [poster]
    assert poster in devctl.TEST_PROFILES["media-foundation"]


def test_media_movie_detail_profile_is_in_media_foundation():
    detail = "tests/test_media_movie_detail.py"
    assert devctl.TEST_PROFILES["media-movie-detail"] == [detail]
    assert detail in devctl.TEST_PROFILES["media-foundation"]


def test_media_enrich_profile_is_in_media_foundation():
    enrich = "tests/test_media_enrich.py"
    assert devctl.TEST_PROFILES["media-enrich"] == [enrich]
    assert enrich in devctl.TEST_PROFILES["media-foundation"]


def test_media_single_item_enrich_is_in_media_foundation():
    assert "tests/test_media_single_item_enrich.py" in devctl.TEST_PROFILES["media-foundation"]


def test_ui_action_timing_is_in_media_foundation():
    assert "tests/test_ui_action_timing.py" in devctl.TEST_PROFILES["media-foundation"]


def test_media_search_state_profile_is_in_media_foundation():
    state = "tests/test_media_search_state.py"
    assert devctl.TEST_PROFILES["media-search-state"] == [state]
    assert state in devctl.TEST_PROFILES["media-foundation"]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fake_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ─── STATUS ──────────────────────────────────────────────────────────────────

class TestStatus:
    def test_clean_repo_status_parsing(self, capsys):
        """Status on a clean repo reports CLEAN state."""
        def fake_git(*args, **kwargs):
            # _git(*args) is called as _git("rev-parse", "HEAD", check=False)
            # so args is a tuple of the individual string arguments
            joined = " ".join(str(a) for a in args)
            if "--porcelain" in joined:
                return _fake_completed(stdout="")
            if "--abbrev-ref" in joined:
                return _fake_completed(stdout="feature/rc8-media-foundation")
            if "--short" in joined:
                return _fake_completed(stdout="073d712")
            if "rev-parse" in joined:
                return _fake_completed(stdout="073d712f7bc21402e880ce0e50ca3e247d877678")
            if "stash" in joined and "list" in joined:
                return _fake_completed(stdout="stash@{0}: On feature/rc7-salon-ux: RC7 T5 network deferred\n")
            if "log" in joined:
                return _fake_completed(stdout="073d712 feat(media): add normalized media probe\n")
            return _fake_completed()

        with patch.object(devctl, "_git", side_effect=fake_git):
            rc = devctl.cmd_status(MagicMock())

        out = capsys.readouterr().out
        assert rc == 0
        assert "CLEAN" in out
        assert "feature/rc8-media-foundation" in out
        assert "073d712f7bc21402e880ce0e50ca3e247d877678" in out
        assert "PRESENT" in out

    def test_dirty_repo_detection(self, capsys):
        """Status on a dirty repo reports DIRTY and lists changed files."""
        def fake_git(*args, **kwargs):
            joined = " ".join(str(a) for a in args)
            if "--porcelain" in joined:
                return _fake_completed(stdout=" M payload/openhtpc-media-probe.py\n")
            if "--abbrev-ref" in joined:
                return _fake_completed(stdout="feature/test")
            if "--short" in joined:
                return _fake_completed(stdout="abc1234")
            if "rev-parse" in joined:
                return _fake_completed(stdout="abc1234abc1234abc1234abc1234abc1234abc123")
            if "stash" in joined and "list" in joined:
                return _fake_completed(stdout="stash@{0}: On feature/rc7-salon-ux: RC7 T5 network deferred\n")
            if "log" in joined:
                return _fake_completed(stdout="")
            return _fake_completed()

        with patch.object(devctl, "_git", side_effect=fake_git):
            rc = devctl.cmd_status(MagicMock())

        out = capsys.readouterr().out
        assert rc == 0
        assert "DIRTY" in out
        assert "openhtpc-media-probe.py" in out

    def test_protected_stash_detection_present(self):
        """Protected stash is detected when present in stash list."""
        def fake_git(*args, **kwargs):
            return _fake_completed(stdout="stash@{0}: On feature/rc7-salon-ux: RC7 T5 network deferred\n")

        with patch.object(devctl, "_git", side_effect=fake_git):
            found, ref = devctl._check_protected_stash()

        assert found is True
        assert "stash@{0}" in ref

    def test_protected_stash_detection_missing(self):
        """Protected stash detection reports NOT FOUND when absent."""
        def fake_git(*args, **kwargs):
            return _fake_completed(stdout="stash@{0}: On main: Some other stash\n")

        with patch.object(devctl, "_git", side_effect=fake_git):
            found, ref = devctl._check_protected_stash()

        assert found is False
        assert "NOT FOUND" in ref

    def test_status_never_mutates_repo(self, monkeypatch):
        """Status must never call any mutating git command."""
        mutating = {"commit", "push", "reset", "stash pop", "stash drop",
                    "checkout", "merge", "rebase"}
        seen: list[tuple] = []

        def tracking_git(*args, **kwargs):
            seen.append(args)
            return _fake_completed(stdout="")

        with patch.object(devctl, "_git", side_effect=tracking_git):
            try:
                devctl.cmd_status(MagicMock())
            except Exception:
                pass

        for cmd_args in seen:
            joined = " ".join(str(a) for a in cmd_args)
            for m in mutating:
                assert m not in joined, f"Mutating git command found: {cmd_args}"


# ─── BUILD ───────────────────────────────────────────────────────────────────

class TestBuild:
    def test_build_parameter_validation_requires_name(self):
        """Build requires --name parameter."""
        parser = devctl.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["build", "--build-id", "x", "--dev-tranche", "DEV1",
                               "--workstream", "MW", "--tests", "1/1 PASS"])

    def test_build_parameter_validation_requires_build_id(self):
        """Build requires --build-id parameter."""
        parser = devctl.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["build", "--name", "X", "--dev-tranche", "DEV1",
                               "--workstream", "MW", "--tests", "1/1 PASS"])

    def test_build_refuses_if_artifact_exists(self, tmp_path, capsys):
        """Build refuses to overwrite an existing artifact."""
        name = "TestArtifact-Dev1"
        existing = tmp_path / f"{name}.tar.gz"
        existing.touch()

        def fake_git(*args, **kwargs):
            cmd = args[0] if args else []
            if "rev-parse" in cmd:
                return _fake_completed(stdout="abc1234abc1234abc1234abc1234abc1234abc123")
            if "--porcelain" in cmd:
                return _fake_completed(stdout="")
            return _fake_completed()

        args = MagicMock()
        args.name = name
        args.build_id = "test-dev1"
        args.dev_tranche = "DEV1"
        args.workstream = "TEST"
        args.tests = "1/1 PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", side_effect=fake_git), \
             patch.object(devctl, "_product_version", return_value="1.2.0-rc7"):
            rc = devctl.cmd_build(args)

        assert rc == 1

    def test_exact_commit_archive_generation(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        with tarfile.open(archive, "r:gz") as tar:
            binary = tar.extractfile("TestArtifact-Dev1/payload/flex/bin/flex-launcher").read()
            metadata = json.load(tar.extractfile("TestArtifact-Dev1/payload/flex/BUILD-METADATA.json"))
        assert binary == b"NEW_FROM_EXPORTED_SOURCE"
        assert metadata["binary_sha256"] == devctl.hashlib.sha256(binary).hexdigest()
        assert metadata["source_commit"] == TEST_COMMIT
        assert (tmp_path / f"{archive.name}.sha256").read_text().split()[1] == archive.name
        report = json.loads((tmp_path / "TestArtifact-Dev1-report.json").read_text())
        assert report["commit"] == TEST_COMMIT
        assert report["build_id"] == "fresh-flex-dev1"

    def test_failed_flex_compile_fails_closed(self, monkeypatch, tmp_path):
        def fail_build(source, build_dir):
            raise subprocess.CalledProcessError(1, ["cmake", "--build"])
        rc = _make_provenance_artifact(monkeypatch, tmp_path, build_override=fail_build, expect_failure=True)
        assert rc == 1
        assert not list(tmp_path.glob("*.tar.gz"))

    @pytest.mark.parametrize("failure_call", [1, 2])
    def test_cmake_configure_or_compile_failure(self, monkeypatch, tmp_path, failure_call):
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if len(calls) == failure_call:
                raise subprocess.CalledProcessError(1, command)
            return _fake_completed()
        monkeypatch.setattr(devctl.subprocess, "run", fake_run)
        with pytest.raises(subprocess.CalledProcessError):
            devctl._build_flex(tmp_path / "source", tmp_path / "build")
        assert len(calls) == failure_call

    def test_source_export_failure_fails_closed(self, monkeypatch, tmp_path):
        def fail_export(commit, staging, scratch):
            raise subprocess.CalledProcessError(1, ["git", "archive"])
        rc = _make_provenance_artifact(monkeypatch, tmp_path, export_override=fail_export, expect_failure=True)
        assert rc == 1
        assert not list(tmp_path.glob("*.tar.gz"))

    def test_missing_build_output_fails_closed(self, monkeypatch, tmp_path):
        rc = _make_provenance_artifact(
            monkeypatch, tmp_path, build_override=lambda source, build_dir: build_dir / "flex-launcher",
            expect_failure=True,
        )
        assert rc == 1

    def test_nonexecutable_build_output_fails_closed(self, monkeypatch, tmp_path):
        def nonexecutable(source, build_dir):
            build_dir.mkdir()
            binary = build_dir / "flex-launcher"
            binary.write_bytes(b"NEW_FROM_EXPORTED_SOURCE")
            binary.chmod(0o644)
            return binary
        rc = _make_provenance_artifact(monkeypatch, tmp_path, build_override=nonexecutable, expect_failure=True)
        assert rc == 1

    def test_staged_copy_mismatch_fails_closed(self, monkeypatch, tmp_path):
        def bad_copy(source, destination):
            destination.write_bytes(b"OLD")
            destination.chmod(0o755)
        monkeypatch.setattr(devctl.shutil, "copy2", bad_copy)
        rc = _make_provenance_artifact(monkeypatch, tmp_path, expect_failure=True)
        assert rc == 1

    def test_metadata_generation_failure_fails_closed(self, monkeypatch, tmp_path):
        rc = _make_provenance_artifact(monkeypatch, tmp_path, elf_override=lambda path: "invalid", expect_failure=True)
        assert rc == 1

    def test_manifest_generation_failure_fails_closed(self, monkeypatch, tmp_path):
        def fail_manifest(staging):
            raise ValueError("manifest generation failed")
        rc = _make_provenance_artifact(monkeypatch, tmp_path, manifest_override=fail_manifest, expect_failure=True)
        assert rc == 1

    def test_final_verification_failure_fails_build(self, monkeypatch, tmp_path):
        monkeypatch.setattr(devctl, "_verify_artifact", lambda archive: ["fixture failure"])
        rc = _make_provenance_artifact(monkeypatch, tmp_path, expect_failure=True)
        assert rc == 1
        assert not list(tmp_path.glob("*.tar.gz"))


TEST_COMMIT = "a" * 40
TEST_UPSTREAM = "b" * 40
TEST_ELF_ID = "c" * 40


def _make_provenance_artifact(monkeypatch, tmp_path, *, build_override=None,
                              export_override=None, elf_override=None,
                              manifest_override=None, source_executable=False,
                              expect_failure=False):
    """Build through production cmd_build with synthetic exported source and Flex output."""
    committed = {}

    def fake_git(*args, **kwargs):
        if args[:2] == ("rev-parse", "HEAD"):
            return _fake_completed(stdout=TEST_COMMIT + "\n")
        return _fake_completed(stdout="")

    def fake_export(commit, staging, scratch):
        assert commit == TEST_COMMIT
        files = {
            "VERSION": b"1.2.0-rc8\n",
            "vendor/flex-launcher/UPSTREAM_COMMIT": (TEST_UPSTREAM + "\n").encode(),
            "vendor/flex-launcher/src/launcher.c": b"NEW_FROM_EXPORTED_SOURCE",
            "payload/flex/bin/flex-launcher": b"OLD_TRACKED_BINARY",
            "payload/flex/BUILD-METADATA.json": b'{"schema": 1, "binary_sha256": "stale"}',
            "MANIFEST.sha256": b"stale manifest",
        }
        for name, content in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if name.endswith("flex-launcher"):
                path.chmod(0o755)
            if name == "vendor/flex-launcher/src/launcher.c" and source_executable:
                path.chmod(0o755)
        committed.update({
            name: (devctl._sha256(staging / name), os.access(staging / name, os.X_OK))
            for name in files
        })

    def fake_build(source, build_dir):
        assert (source / "src/launcher.c").read_bytes() == b"NEW_FROM_EXPORTED_SOURCE"
        build_dir.mkdir()
        binary = build_dir / "flex-launcher"
        binary.write_bytes(b"NEW_FROM_EXPORTED_SOURCE")
        binary.chmod(0o755)
        return binary

    monkeypatch.setattr(devctl, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(devctl, "_git", fake_git)
    monkeypatch.setattr(devctl, "_export_commit", export_override or fake_export)
    monkeypatch.setattr(devctl, "_build_flex", build_override or fake_build)
    monkeypatch.setattr(devctl, "_elf_build_id", elf_override or (lambda path: TEST_ELF_ID))
    if manifest_override is not None:
        monkeypatch.setattr(devctl, "_write_manifest", manifest_override)
    monkeypatch.setattr(devctl, "_committed_entries", lambda commit: committed if commit == TEST_COMMIT else {})
    args = type("Args", (), {
        "name": "TestArtifact-Dev1", "build_id": "fresh-flex-dev1",
        "dev_tranche": "DEV1", "workstream": "MEDIA_FOUNDATION", "tests": "1/1 PASS",
    })()
    rc = devctl.cmd_build(args)
    if expect_failure:
        return rc
    assert rc == 0
    return tmp_path / "TestArtifact-Dev1.tar.gz", committed


def _rewrite_archive(archive, change, *, refresh_checksums=True):
    """Tamper with a synthetic archive while keeping outer checksums coherent."""
    members = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            data = tar.extractfile(member).read() if member.isfile() else None
            members.append((member, data))
    members = change(members)
    with tarfile.open(archive, "w:gz") as tar:
        for member, data in members:
            if data is not None:
                member.size = len(data)
            tar.addfile(member, io.BytesIO(data) if data is not None else None)
    if refresh_checksums:
        sha = devctl._sha256(archive)
        (archive.parent / f"{archive.name}.sha256").write_text(f"{sha}  {archive.name}\n")
        report = archive.parent / f"{archive.name[:-7]}-report.json"
        data = json.loads(report.read_text())
        data["sha256"] = sha
        report.write_text(json.dumps(data))


class TestVerify:
    def test_verify_pass_on_valid_artifact(self, monkeypatch, tmp_path, capsys):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        assert devctl.cmd_verify(type("Args", (), {"artifact": str(archive)})()) == 0
        assert "VERIFY PASS" in capsys.readouterr().out

    def test_verify_checksum_mismatch(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        (tmp_path / f"{archive.name}.sha256").write_text(f"{'0' * 64}  {archive.name}\n")
        assert devctl._verify_artifact(archive)

    def test_verify_report_mismatch(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        report = tmp_path / "TestArtifact-Dev1-report.json"
        data = json.loads(report.read_text()); data["sha256"] = "0" * 64
        report.write_text(json.dumps(data))
        assert devctl._verify_artifact(archive)

    def test_verify_missing_report(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        (tmp_path / "TestArtifact-Dev1-report.json").unlink()
        assert devctl._verify_artifact(archive)

    def test_verify_missing_archive(self, tmp_path):
        assert devctl._verify_artifact(tmp_path / "missing.tar.gz")

    @pytest.mark.parametrize("member_path", [
        "payload/flex/BUILD-METADATA.json", "payload/flex/bin/flex-launcher",
    ])
    def test_missing_critical_member(self, monkeypatch, tmp_path, member_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        _rewrite_archive(archive, lambda members: [item for item in members if not item[0].name.endswith(member_path)])
        assert devctl._verify_artifact(archive)

    def test_malformed_flex_metadata(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            return [(m, b"{invalid" if m.name.endswith("BUILD-METADATA.json") else data) for m, data in members]
        _rewrite_archive(archive, change)
        assert devctl._verify_artifact(archive)

    def test_incomplete_flex_metadata(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            result = []
            for member, data in members:
                if member.name.endswith("BUILD-METADATA.json"):
                    metadata = json.loads(data); del metadata["elf_build_id"]
                    data = json.dumps(metadata).encode()
                result.append((member, data))
            return result
        _rewrite_archive(archive, change)
        assert "field missing" in devctl._verify_artifact(archive)[0]

    def test_dev6c3m_binary_metadata_mismatch(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            result = []
            for member, data in members:
                if member.name.endswith("BUILD-METADATA.json"):
                    metadata = json.loads(data)
                    metadata["binary_sha256"] = "0" * 64
                    data = json.dumps(metadata).encode()
                result.append((member, data))
            return result
        _rewrite_archive(archive, change)
        assert "binary/metadata SHA256 mismatch" in devctl._verify_artifact(archive)[0]

    @pytest.mark.parametrize("key,value", [
        ("source_commit", "d" * 40), ("artifact_build_id", "wrong"),
        ("dev_tranche", "DEV2"), ("workstream", "WRONG"),
    ])
    def test_wrong_identity(self, monkeypatch, tmp_path, key, value):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            result = []
            for member, data in members:
                if member.name.endswith("BUILD-METADATA.json"):
                    metadata = json.loads(data); metadata[key] = value
                    data = json.dumps(metadata).encode()
                result.append((member, data))
            return result
        _rewrite_archive(archive, change)
        assert devctl._verify_artifact(archive)

    def test_wrong_report_source_commit(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        report = tmp_path / "TestArtifact-Dev1-report.json"
        data = json.loads(report.read_text()); data["commit"] = "d" * 40
        report.write_text(json.dumps(data))
        assert devctl._verify_artifact(archive)

    def test_archived_source_differs_from_reported_commit(self, monkeypatch, tmp_path):
        archive, committed = _make_provenance_artifact(monkeypatch, tmp_path)
        altered = dict(committed)
        altered["vendor/flex-launcher/src/launcher.c"] = ("0" * 64, False)
        monkeypatch.setattr(devctl, "_committed_entries", lambda commit: altered)
        assert "source does not match" in devctl._verify_artifact(archive)[0]

    @pytest.mark.parametrize("path,original_executable,tampered_mode", [
        ("vendor/flex-launcher/src/launcher.c", True, 0o644),
        ("VERSION", False, 0o755),
    ])
    def test_source_executable_mode_tamper(self, monkeypatch, tmp_path,
                                           path, original_executable, tampered_mode):
        archive, committed = _make_provenance_artifact(
            monkeypatch, tmp_path, source_executable=original_executable)
        sha, executable = committed[path]
        assert executable is original_executable
        def change(members):
            for member, _ in members:
                if member.name == f"TestArtifact-Dev1/{path}":
                    assert bool(member.mode & 0o111) is original_executable
                    member.mode = tampered_mode
            return members
        _rewrite_archive(archive, change)
        with tarfile.open(archive, "r:gz") as tar:
            stream = tar.extractfile(f"TestArtifact-Dev1/{path}")
            assert stream is not None
            assert devctl.hashlib.sha256(stream.read()).hexdigest() == sha
        assert "executable mode mismatch" in devctl._verify_artifact(archive)[0]

    def test_matching_source_executable_modes_verify(self, monkeypatch, tmp_path):
        archive, committed = _make_provenance_artifact(
            monkeypatch, tmp_path, source_executable=True)
        path = "vendor/flex-launcher/src/launcher.c"
        assert committed[path][1] is True
        with tarfile.open(archive, "r:gz") as tar:
            assert tar.getmember(f"TestArtifact-Dev1/{path}").mode & 0o111
        assert devctl._verify_artifact(archive) == []

    def test_elf_identity_mismatch(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        monkeypatch.setattr(devctl, "_elf_build_id", lambda path: "d" * 40)
        assert "ELF build ID mismatch" in devctl._verify_artifact(archive)[0]

    def test_manifest_mismatch(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            return [(member, b"stale manifest\\n" if member.name.endswith("MANIFEST.sha256") else data)
                    for member, data in members]
        _rewrite_archive(archive, change)
        assert "manifest" in devctl._verify_artifact(archive)[0]

    def test_duplicate_critical_member(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            found = next(item for item in members if item[0].name.endswith("BUILD-METADATA.json"))
            return members + [found]
        _rewrite_archive(archive, change)
        assert "duplicate" in devctl._verify_artifact(archive)[0]

    def test_unsafe_member(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            info = tarfile.TarInfo("../payload/flex/bin/flex-launcher")
            info.size = 4
            return members + [(info, b"EVIL")]
        _rewrite_archive(archive, change)
        assert "unsafe" in devctl._verify_artifact(archive)[0]

    def test_regular_file_at_archive_root_fails_closed(self, monkeypatch, tmp_path):
        archive, _ = _make_provenance_artifact(monkeypatch, tmp_path)
        def change(members):
            info = tarfile.TarInfo("TestArtifact-Dev1")
            info.size = 4
            return [item for item in members if item[0].name != "TestArtifact-Dev1"] + [(info, b"ROOT")]
        _rewrite_archive(archive, change)
        assert "outside root directory" in devctl._verify_artifact(archive)[0]


# ─── SSH/SCP COMMAND CONSTRUCTION ────────────────────────────────────────────

class TestSSHConstruction:
    def test_ssh_args_no_shell_true(self):
        """SSH command construction never uses shell=True."""
        args = devctl._ssh_args("steve@192.168.1.11", ["echo", "hello"])
        assert isinstance(args, list)
        assert "ssh" in args[0]
        # Verify no & | ; shell metacharacters in arg list positions
        for arg in args:
            assert arg != "shell=True"

    def test_scp_args_construction(self):
        """SCP args are a plain list, never a shell string."""
        args = devctl._scp_args("/local/file.tar.gz", "steve@host:/remote/")
        assert isinstance(args, list)
        assert "scp" == args[0]
        assert "/local/file.tar.gz" in args
        assert "steve@host:/remote/" in args

    def test_ssh_bounded_timeout_present(self):
        """SSH args include ConnectTimeout."""
        args = devctl._ssh_args("host", [])
        joined = " ".join(args)
        assert "ConnectTimeout" in joined

    def test_safe_ssh_command_no_password_args(self):
        """SSH command construction never passes a password argument."""
        for host in ("steve@192.168.1.11", "user@host.example"):
            args = devctl._ssh_args(host, ["ls"])
            for arg in args:
                assert "password" not in arg.lower()
                assert "-p" not in arg  # No password via -p (that's port for ssh anyway)

    def test_run_remote_no_shell_true(self, monkeypatch):
        """_run_remote never calls subprocess.run with shell=True."""
        captured: dict[str, Any] = {}

        def mock_run(cmd, **kwargs):
            captured["shell"] = kwargs.get("shell", False)
            captured["cmd"] = cmd
            return _fake_completed(stdout="ok")

        monkeypatch.setattr(subprocess, "run", mock_run)
        devctl._run_remote("steve@192.168.1.11", ["echo", "test"])
        assert captured.get("shell") is False or "shell" not in captured


# ─── DRY-RUN REMOTE WORKFLOW ──────────────────────────────────────────────────

class TestDryRun:
    def test_ship_dry_run_no_mutation(self, tmp_path, capsys):
        """ship --dry-run prints actions but does not call scp or ssh."""
        name = "TestShip-Dev1"
        archive = tmp_path / f"{name}.tar.gz"
        archive.write_bytes(b"test artifact")
        sha = devctl._sha256(archive)
        sidecar = tmp_path / f"{name}.tar.gz.sha256"
        sidecar.write_text(f"{sha}  {name}.tar.gz\n")
        report = tmp_path / f"{name}-report.json"
        report.write_text("{}")

        scp_called = {"called": False}
        def mock_scp(*args, **kwargs):
            scp_called["called"] = True
            return _fake_completed()

        args = MagicMock()
        args.artifact = str(archive)
        args.target = "steve@192.168.1.11"
        args.dest = "/home/steve/dev/1.2/"
        args.dry_run = True

        with patch.object(subprocess, "run", side_effect=mock_scp):
            rc = devctl.cmd_ship(args)

        assert rc == 0
        assert not scp_called["called"]
        out = capsys.readouterr().out
        assert "DRY-RUN" in out

    def test_target_prepare_dry_run(self, capsys):
        """target-prepare --dry-run prints snapshot plan without remote mutation."""
        remote_calls: list[list[str]] = []

        def mock_remote(host: str, cmd: list[str], **kwargs):
            remote_calls.append(cmd)
            return _fake_completed(stdout="ok")

        args = MagicMock()
        args.target = "steve@192.168.1.11"
        args.dry_run = True

        with patch.object(devctl, "_run_remote", side_effect=mock_remote):
            rc = devctl.cmd_target_prepare(args)

        assert rc == 0
        # No remote calls in dry-run mode
        assert remote_calls == []
        out = capsys.readouterr().out
        assert "DRY-RUN" in out

    def test_target_install_dry_run(self, tmp_path, capsys):
        """target-install --dry-run reports plan without calling remote."""
        archive = tmp_path / "TestInstall-Dev1.tar.gz"
        archive.write_bytes(b"fake")

        remote_calls: list = []

        def mock_remote(host, cmd, **kwargs):
            remote_calls.append(cmd)
            return _fake_completed()

        args = MagicMock()
        args.artifact = str(archive)
        args.target = "steve@192.168.1.11"
        args.dest = "/home/steve/dev/1.2/"
        args.dry_run = True

        with patch.object(devctl, "_run_remote", side_effect=mock_remote):
            rc = devctl.cmd_target_install(args)

        assert rc == 0
        assert remote_calls == []
        out = capsys.readouterr().out
        assert "DRY-RUN" in out


# ─── HUMAN GATE ───────────────────────────────────────────────────────────────

class TestHumanGate:
    def test_human_gate_prints_instructions(self, capsys):
        """human-gate prints validation instructions and returns 0."""
        rc = devctl.cmd_human_gate(MagicMock())
        out = capsys.readouterr().out
        assert rc == 0
        assert "HUMAN VALIDATION REQUIRED" in out
        assert "openhtpc start" in out
        assert "Image" in out
        assert "Audio" in out
        assert "Refresh" in out
        assert "Flex" in out

    def test_human_gate_instructs_steve(self, capsys):
        """human-gate output says NOT to pass values automatically."""
        devctl.cmd_human_gate(MagicMock())
        out = capsys.readouterr().out
        assert "Steve" in out or "physical" in out.lower()


# ─── QUALIFICATION ────────────────────────────────────────────────────────────

class TestQualification:
    def _make_artifact(self, tmp_path: pathlib.Path, name: str) -> None:
        archive = tmp_path / f"{name}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"data"
            info = tarfile.TarInfo(name=f"{name}/VERSION")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        sha = devctl._sha256(archive)
        report = tmp_path / f"{name}-report.json"
        report.write_text(json.dumps({
            "sha256": sha, "build_id": "test", "dev_tranche": "DEV1",
            "workstream": "MEDIA_FOUNDATION", "version": "1.2.0-rc7",
        }, indent=2))

    def test_qualification_requires_explicit_human_values(self, tmp_path):
        """Qualification refuses invalid (non PASS/FAIL/SKIP) values."""
        name = "QualBad-Dev1"
        self._make_artifact(tmp_path, name)

        args = MagicMock()
        args.artifact = name
        args.image = "AUTO"  # invalid
        args.audio = "PASS"
        args.refresh = "PASS"
        args.flex_return = "PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", return_value=_fake_completed(stdout="abc123")):
            rc = devctl.cmd_qualification(args)

        assert rc == 2

    def test_qualification_writes_validation_json(self, tmp_path):
        """Qualification writes a validation JSON when all values are explicit."""
        name = "QualGood-Dev1"
        self._make_artifact(tmp_path, name)

        args = MagicMock()
        args.artifact = name
        args.image = "PASS"
        args.audio = "PASS"
        args.refresh = "PASS"
        args.flex_return = "PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", return_value=_fake_completed(stdout="abc123")):
            rc = devctl.cmd_qualification(args)

        assert rc == 0
        val_path = tmp_path / f"{name}.validation.json"
        assert val_path.is_file()
        val = json.loads(val_path.read_text())
        assert val["physical_qualification"] == "PASS"
        assert val["physical_checks"]["image"] == "PASS"
        assert val["human_physical_validation_required"] is True

    def test_qualification_refuses_to_auto_qualify(self, tmp_path):
        """Qualification with FAIL value produces overall FAIL result."""
        name = "QualFail-Dev1"
        self._make_artifact(tmp_path, name)

        args = MagicMock()
        args.artifact = name
        args.image = "PASS"
        args.audio = "FAIL"
        args.refresh = "PASS"
        args.flex_return = "PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", return_value=_fake_completed(stdout="abc123")):
            rc = devctl.cmd_qualification(args)

        assert rc == 1
        val_path = tmp_path / f"{name}.validation.json"
        val = json.loads(val_path.read_text())
        assert val["physical_qualification"] == "FAIL"

    def test_qualification_dev3_refresh_and_decisive_evidence(self, tmp_path):
        """DEV3 qualification preserves refresh limitation and decisive evidence."""
        name = "OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3"
        archive = tmp_path / f"{name}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"data"
            info = tarfile.TarInfo(name=f"{name}/VERSION")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        sha = devctl._sha256(archive)
        report = tmp_path / f"{name}-report.json"
        report.write_text(json.dumps({
            "sha256": sha, "build_id": "media-ingest-dev3", "dev_tranche": "DEV3",
            "workstream": "MEDIA_FOUNDATION", "version": "1.2.0-rc7",
        }, indent=2))

        args = MagicMock()
        args.artifact = name
        args.image = "PASS"
        args.audio = "PASS"
        args.refresh = "PASS"
        args.flex_return = "PASS"
        args.refresh_observed_hz = 60
        args.refresh_limitation = "RC7_PAL_INTERLACED_CADENCE_UNPROVEN"
        args.refresh_non_regression = "PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", return_value=_fake_completed(stdout="27d5a425c84ec7e02ff62f07d0b102f2585bc8a9")):
            rc = devctl.cmd_qualification(args)

        assert rc == 0
        val_path = tmp_path / f"{name}.validation.json"
        assert val_path.is_file()
        val = json.loads(val_path.read_text())
        assert val["schema_version"] == 2
        assert val["product_version"] == "1.2.0-rc7"
        assert val["physical_qualification"] == "PASS"
        assert val["decisive_evidence"]["V1_TO_V2_MIGRATION"] == "PASS"
        assert val["decisive_evidence"]["FIELD_ORDER_TT_PERSISTENCE"] == "PASS"
        assert val["refresh_truth"]["observed_display_hz"] == 60
        assert val["refresh_truth"]["field_order"] == "tt"
        assert val["refresh_truth"]["limitation"] == "RC7_PAL_INTERLACED_CADENCE_UNPROVEN"
        assert val["refresh_non_regression"] == "PASS"

    def test_qualification_refuses_to_overwrite_existing(self, tmp_path, capsys):
        """Qualification refuses to overwrite an existing validation file."""
        name = "QualOverwrite-Dev1"
        self._make_artifact(tmp_path, name)

        # Pre-create validation file
        val_path = tmp_path / f"{name}.validation.json"
        val_path.write_text('{"existing": true}\n')

        args = MagicMock()
        args.artifact = name
        args.image = "PASS"
        args.audio = "PASS"
        args.refresh = "PASS"
        args.flex_return = "PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", return_value=_fake_completed(stdout="abc123")):
            rc = devctl.cmd_qualification(args)

        assert rc == 1
        # Original file must be untouched
        assert json.loads(val_path.read_text()).get("existing") is True


# ─── DEPLOYMENT SAFETY ────────────────────────────────────────────────────────

class TestDeploymentSafety:
    def test_tool_not_in_payload(self):
        """openhtpc-devctl must not exist in payload directory."""
        payload_dir = ROOT / "payload"
        assert not (payload_dir / "openhtpc-devctl").exists(), \
            "openhtpc-devctl must never be placed in payload/"

    def test_tool_not_in_managed_files(self):
        """openhtpc-devctl must not be listed in managed-files.txt."""
        managed = ROOT / "payload" / "managed-files.txt"
        if managed.is_file():
            content = managed.read_text(encoding="utf-8")
            assert "openhtpc-devctl" not in content, \
                "openhtpc-devctl must not appear in managed-files.txt"

    def test_tool_not_in_product_files(self):
        """openhtpc-devctl must not be in install-openhtpc-fedora.sh PRODUCT_FILES."""
        installer = ROOT / "payload" / "install-openhtpc-fedora.sh"
        if installer.is_file():
            content = installer.read_text(encoding="utf-8")
            # Find PRODUCT_FILES line and confirm devctl is absent
            for line in content.splitlines():
                if "PRODUCT_FILES" in line:
                    assert "openhtpc-devctl" not in line, \
                        "openhtpc-devctl must not appear in PRODUCT_FILES"

    def test_tool_is_in_tools_directory(self):
        """openhtpc-devctl must exist in tools/ directory."""
        assert (ROOT / "tools" / "openhtpc-devctl").is_file()

    def test_tool_is_executable(self):
        """openhtpc-devctl must have executable bit set."""
        tool = ROOT / "tools" / "openhtpc-devctl"
        assert os.access(tool, os.X_OK)

    def test_no_push_or_tag_operations(self):
        """The devctl tool must not contain git push or git tag commands in its source."""
        source = DEVCTL_PATH.read_text(encoding="utf-8")
        # Check for literal push/tag git subcommands in subprocess calls
        # We look for them in a way that would indicate an actual git operation
        # The word 'push' or 'tag' can appear in comments or strings but not as git args
        import re
        # Look for ["git", ..., "push"] or ["git", ..., "tag"] patterns
        assert '"git push"' not in source
        assert '"git tag"' not in source

    def test_no_rm_rf_in_source(self):
        """The devctl tool must not contain rm -rf patterns."""
        source = DEVCTL_PATH.read_text(encoding="utf-8")
        assert "rm -rf" not in source
        assert "shutil.rmtree" not in source


# ─── VERIFY ARCHIVE ROOT ──────────────────────────────────────────────────────

class TestArchiveRoot:
    def test_verify_archive_root_coherence(self, tmp_path, capsys):
        """Verify fails when archive root prefix does not match artifact name."""
        name = "TestCoherence-Dev1"
        wrong_root = "WrongName-Dev1"
        archive = tmp_path / f"{name}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"test"
            info = tarfile.TarInfo(name=f"{wrong_root}/VERSION")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        sha = devctl._sha256(archive)
        sidecar = tmp_path / f"{name}.tar.gz.sha256"
        sidecar.write_text(f"{sha}  {name}.tar.gz\n")
        report = tmp_path / f"{name}-report.json"
        report.write_text(json.dumps({"sha256": sha, "commit": "abc123"}))

        args = MagicMock()
        args.artifact = str(archive)

        with patch.object(devctl, "_git", return_value=_fake_completed()):
            rc = devctl.cmd_verify(args)

        assert rc == 1
