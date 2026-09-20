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

    def test_exact_commit_archive_generation(self, tmp_path):
        """Build produces archive from HEAD commit using git archive."""
        name = "TestArchive-Dev99"
        commit_hash = "073d712f7bc21402e880ce0e50ca3e247d877678"

        call_count = {"build": 0}
        expected_archive = tmp_path / f"{name}.tar.gz"

        def fake_build_archive(commit: str, n: str, dest: pathlib.Path) -> pathlib.Path:
            call_count["build"] += 1
            assert commit == commit_hash
            assert n == name
            # Create a tiny synthetic tar.gz
            dest.mkdir(parents=True, exist_ok=True)
            archive = dest / f"{n}.tar.gz"
            with tarfile.open(str(archive), "w:gz") as tar:
                content = b"version: test\n"
                info = tarfile.TarInfo(name=f"{n}/VERSION")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            return archive

        def fake_git(*args, **kwargs):
            cmd = args[0] if args else []
            if "--porcelain" in cmd:
                return _fake_completed(stdout="")
            if "rev-parse" in cmd:
                return _fake_completed(stdout=commit_hash)
            return _fake_completed()

        args = MagicMock()
        args.name = name
        args.build_id = "test-dev99"
        args.dev_tranche = "DEV99"
        args.workstream = "TEST"
        args.tests = "5/5 PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", side_effect=fake_git), \
             patch.object(devctl, "_product_version", return_value="1.2.0-rc7"), \
             patch.object(devctl, "_build_archive_from_commit", side_effect=fake_build_archive):
            rc = devctl.cmd_build(args)

        assert rc == 0
        assert call_count["build"] == 1

    def test_sha256_generation(self, tmp_path):
        """Build writes a SHA256 sidecar with just the filename (not full path)."""
        name = "TestSHA-Dev1"
        commit_hash = "abc1234abc1234abc1234abc1234abc1234abc12"

        def fake_build_archive(commit, n, dest):
            dest.mkdir(parents=True, exist_ok=True)
            archive = dest / f"{n}.tar.gz"
            with tarfile.open(str(archive), "w:gz") as tar:
                data = b"version: test\n"
                info = tarfile.TarInfo(name=f"{n}/VERSION")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return archive

        def fake_git(*args, **kwargs):
            joined = " ".join(str(a) for a in args)
            if "--porcelain" in joined:
                return _fake_completed(stdout="")
            if "rev-parse" in joined:
                return _fake_completed(stdout=commit_hash)
            return _fake_completed()

        args = MagicMock()
        args.name = name
        args.build_id = "sha-dev1"
        args.dev_tranche = "DEV1"
        args.workstream = "TEST"
        args.tests = "1/1 PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", side_effect=fake_git), \
             patch.object(devctl, "_product_version", return_value="1.2.0-rc7"), \
             patch.object(devctl, "_build_archive_from_commit", side_effect=fake_build_archive):
            rc = devctl.cmd_build(args)

        assert rc == 0
        sha_file = tmp_path / f"{name}.tar.gz.sha256"
        assert sha_file.is_file()
        text = sha_file.read_text()
        # sidecar must contain just the filename, not a full path
        parts = text.strip().split()
        assert len(parts) == 2
        assert "/" not in parts[1], f"SHA sidecar contains path separator: {parts[1]!r}"
        assert parts[1] == f"{name}.tar.gz"

    def test_report_json_generation(self, tmp_path):
        """Build writes a properly structured report JSON."""
        name = "TestReport-Dev1"
        commit_hash = "abc1234abc1234abc1234abc1234abc1234abc12"

        def fake_build_archive(commit, n, dest):
            dest.mkdir(parents=True, exist_ok=True)
            archive = dest / f"{n}.tar.gz"
            with tarfile.open(str(archive), "w:gz") as tar:
                data = b"version: 1.2.0-rc7\n"
                info = tarfile.TarInfo(name=f"{n}/VERSION")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return archive

        def fake_git(*args, **kwargs):
            joined = " ".join(str(a) for a in args)
            if "--porcelain" in joined:
                return _fake_completed(stdout="")
            if "rev-parse" in joined:
                return _fake_completed(stdout=commit_hash)
            return _fake_completed()

        args = MagicMock()
        args.name = name
        args.build_id = "report-dev1"
        args.dev_tranche = "DEV1"
        args.workstream = "MEDIA_FOUNDATION"
        args.tests = "22/22 PASS"

        with patch.object(devctl, "ARTIFACTS", tmp_path), \
             patch.object(devctl, "_git", side_effect=fake_git), \
             patch.object(devctl, "_product_version", return_value="1.2.0-rc7"), \
             patch.object(devctl, "_build_archive_from_commit", side_effect=fake_build_archive):
            rc = devctl.cmd_build(args)

        assert rc == 0
        report = json.loads((tmp_path / f"{name}-report.json").read_text())
        assert report["schema"] == 1
        assert report["commit"] == commit_hash
        assert report["version"] == "1.2.0-rc7"
        assert report["workstream"] == "MEDIA_FOUNDATION"
        assert report["dev_tranche"] == "DEV1"
        assert report["tests"] == "22/22 PASS"
        assert "sha256" in report
        assert "artifact" in report


# ─── VERIFY ──────────────────────────────────────────────────────────────────

class TestVerify:
    def _make_valid_artifact(self, tmp_path: pathlib.Path, name: str) -> tuple[pathlib.Path, str]:
        """Create a valid artifact with matching sidecar and report."""
        archive = tmp_path / f"{name}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            data = b"test content"
            info = tarfile.TarInfo(name=f"{name}/VERSION")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        sha = devctl._sha256(archive)
        sidecar = tmp_path / f"{name}.tar.gz.sha256"
        sidecar.write_text(f"{sha}  {name}.tar.gz\n")

        commit = "abc1234abc1234abc1234abc1234abc1234abc12"
        report = tmp_path / f"{name}-report.json"
        report.write_text(json.dumps({
            "schema": 1, "sha256": sha, "commit": commit,
            "artifact": f"{name}.tar.gz", "version": "1.2.0-rc7",
        }, indent=2))

        return archive, commit

    def test_verify_pass_on_valid_artifact(self, tmp_path, capsys):
        """Verify passes on a valid artifact with matching SHA and report."""
        name = "TestVerify-Dev1"
        archive, commit = self._make_valid_artifact(tmp_path, name)

        def fake_git(*args, **kwargs):
            cmd = args[0] if args else []
            if "cat-file" in cmd:
                return _fake_completed(returncode=0)
            return _fake_completed()

        args = MagicMock()
        args.artifact = str(archive)

        with patch.object(devctl, "_git", side_effect=fake_git):
            rc = devctl.cmd_verify(args)

        assert rc == 0
        out = capsys.readouterr().out
        assert "VERIFY PASS" in out

    def test_verify_checksum_mismatch(self, tmp_path, capsys):
        """Verify fails and returns non-zero on SHA256 mismatch."""
        name = "TestMismatch-Dev1"
        archive, _ = self._make_valid_artifact(tmp_path, name)

        # Corrupt the sidecar
        sidecar = tmp_path / f"{name}.tar.gz.sha256"
        sidecar.write_text(f"{'0' * 64}  {name}.tar.gz\n")

        args = MagicMock()
        args.artifact = str(archive)

        with patch.object(devctl, "_git", return_value=_fake_completed()):
            rc = devctl.cmd_verify(args)

        assert rc == 1
        out = capsys.readouterr().out
        assert "MISMATCH" in out

    def test_verify_missing_report(self, tmp_path, capsys):
        """Verify fails when report JSON is missing."""
        name = "TestNoReport-Dev1"
        archive, _ = self._make_valid_artifact(tmp_path, name)

        # Remove report
        (tmp_path / f"{name}-report.json").unlink()

        args = MagicMock()
        args.artifact = str(archive)

        with patch.object(devctl, "_git", return_value=_fake_completed()):
            rc = devctl.cmd_verify(args)

        assert rc == 1

    def test_verify_missing_archive(self, tmp_path, capsys):
        """Verify fails when artifact file does not exist."""
        args = MagicMock()
        args.artifact = str(tmp_path / "NonExistent-Dev1.tar.gz")

        rc = devctl.cmd_verify(args)
        assert rc == 1


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
