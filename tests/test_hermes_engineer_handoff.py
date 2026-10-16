from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/hermes-engineer/openhtpc-hermes-engineer.py"
SPEC = importlib.util.spec_from_file_location("openhtpc_hermes_engineer", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True, capture_output=True
    ).stdout


def repository(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "canonical"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "VERSION").write_text("1.3.1\n", encoding="utf-8")
    (root / "tracked.txt").write_text("before\n", encoding="utf-8")
    (root / ".agents/skills/example").mkdir(parents=True)
    (root / ".agents/skills/example/SKILL.md").write_text("example\n", encoding="utf-8")
    git(root, "add", "VERSION", "tracked.txt")
    git(root, "commit", "-m", "baseline")
    return root


def test_prepare_copies_dirty_state_without_canonical_git_authority(tmp_path: pathlib.Path) -> None:
    root = repository(tmp_path)
    (root / "tracked.txt").write_text("after\n", encoding="utf-8")
    (root / "notes").mkdir()
    (root / "notes/untracked.md").write_text("handoff\n", encoding="utf-8")
    before = git(root, "status", "--porcelain=v2", "--branch", "--untracked-files=all")

    task_root = MODULE.create_workspace(root, tmp_path / "state", "minor-check", "Inspect only")
    workspace = task_root / "workspace"

    assert git(root, "status", "--porcelain=v2", "--branch", "--untracked-files=all") == before
    assert git(workspace, "remote") == ""
    assert git(workspace, "branch", "--show-current").strip() == "hermes/minor-check"
    assert (workspace / "tracked.txt").read_text(encoding="utf-8") == "after\n"
    assert (workspace / "notes/untracked.md").read_text(encoding="utf-8") == "handoff\n"
    handoff = json.loads((workspace / "OPENHTPC_HANDOFF.json").read_text(encoding="utf-8"))
    assert handoff["source"]["head"] == git(root, "rev-parse", "HEAD").strip()
    assert handoff["workspace_baseline_commit"] == git(workspace, "rev-parse", "HEAD").strip()
    assert handoff["workspace_baseline_commit"] != handoff["source"]["head"]
    assert handoff["permissions"]["push"] is False
    assert handoff["workspace_isolation"]["canonical_git_authority"] is False


def test_prepare_rejects_secret_like_untracked_path(tmp_path: pathlib.Path) -> None:
    root = repository(tmp_path)
    (root / ".env").write_text("SECRET=not-a-real-secret\n", encoding="utf-8")
    with pytest.raises(MODULE.EngineerError, match="unsafe untracked handoff path"):
        MODULE.create_workspace(root, tmp_path / "state", "secret-check", "Reject secrets")


def test_prepare_refuses_existing_task(tmp_path: pathlib.Path) -> None:
    root = repository(tmp_path)
    state = tmp_path / "state"
    MODULE.create_workspace(root, state, "same-task", "First")
    with pytest.raises(MODULE.EngineerError, match="task already exists"):
        MODULE.create_workspace(root, state, "same-task", "Second")


def test_container_is_isolated_from_canonical_repository(tmp_path: pathlib.Path) -> None:
    task = tmp_path / "task"
    for name in ("workspace", "home"):
        (task / name).mkdir(parents=True)
    skills = tmp_path / "canonical/.agents/skills"
    skills.mkdir(parents=True)
    (task / "task.json").write_text(
        json.dumps({"canonical_skills_path": str(skills)}), encoding="utf-8"
    )
    args = MODULE.container_args(task, "engineer:test", ("--version",))
    rendered = " ".join(args)
    assert "/var/run/docker.sock" not in rendered
    assert str(MODULE.MIGRATION_STATE / "hermes.env.private") not in rendered
    assert str(task / "home/provider.env") in rendered
    assert "--cap-drop ALL" in rendered
    assert "--security-opt no-new-privileges" in rendered
    assert "--env HERMES_HOME=/engineer-home" in rendered
    assert "--env HERMES_WRITE_SAFE_ROOT=/workspace" in rendered
    assert f"{skills}:/workspace/.agents/skills:ro,z" in rendered
    assert f"--user {MODULE.os.getuid()}:{MODULE.os.getgid()}" in rendered


def test_export_excludes_preexisting_dirty_handoff_state(tmp_path: pathlib.Path) -> None:
    root = repository(tmp_path)
    (root / "tracked.txt").write_text("canonical dirty\n", encoding="utf-8")
    task_root = MODULE.create_workspace(root, tmp_path / "state", "export-check", "Edit safely")
    workspace = task_root / "workspace"
    (workspace / "tracked.txt").write_text("hermes edit\n", encoding="utf-8")

    export = MODULE.export_task(task_root)
    patch = (export / "changes.patch").read_text(encoding="utf-8")

    assert "-canonical dirty" in patch
    assert "+hermes edit" in patch
    assert "-before" not in patch
