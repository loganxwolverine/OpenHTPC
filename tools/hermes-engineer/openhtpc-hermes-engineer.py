#!/usr/bin/env python3
"""Create and run isolated OPENHTPC engineering handoffs for Hermes.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
from typing import Sequence


def discover_root() -> pathlib.Path:
    configured = os.environ.get("OPENHTPC_ROOT")
    candidates = [pathlib.Path(configured)] if configured else []
    candidates.extend((pathlib.Path.cwd(), pathlib.Path(__file__).resolve().parents[2]))
    for candidate in candidates:
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate.resolve()
    return pathlib.Path.cwd().resolve()


ROOT = discover_root()
DEFAULT_STATE = pathlib.Path.home() / ".local/state/openhtpc-hermes-engineering"
MIGRATION_STATE = pathlib.Path.home() / ".local/state/openhtpc-hermes-migration/20261011"
HERMES_ACTIVE_ENV = pathlib.Path.home() / ".local/share/hermes-agent/.env"
DEFAULT_IMAGE = "openhtpc-hermes-engineer:0.21.6-openhtpc1"
TASK_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,63}")
SENSITIVE_PARTS = {
    ".env",
    "credentials",
    "credential",
    "private-key",
    "private_key",
    "id_rsa",
    "id_ed25519",
    "keydb.cfg",
    "auth.json",
}


class EngineerError(RuntimeError):
    """A bounded handoff operation failed closed."""


def run(
    argv: Sequence[str],
    *,
    cwd: pathlib.Path | None = None,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        list(argv), cwd=cwd, input=input_bytes, capture_output=True, check=False
    )
    if check and result.returncode:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise EngineerError(f"command failed ({result.returncode}): {shlex.join(argv)}\n{stderr}")
    return result


def git_text(root: pathlib.Path, *args: str) -> str:
    return run(("git", "-C", str(root), *args)).stdout.decode("utf-8", "replace")


def validate_task(task: str) -> str:
    if not TASK_RE.fullmatch(task):
        raise EngineerError("task must match [a-z0-9][a-z0-9_-]{2,63}")
    return task


def is_sensitive(relative: pathlib.PurePosixPath) -> bool:
    lowered = {part.lower() for part in relative.parts}
    return bool(lowered & SENSITIVE_PARTS) or any(
        part.lower().endswith((".pem", ".key", ".p12", ".pfx")) for part in relative.parts
    )


def untracked_paths(root: pathlib.Path) -> list[pathlib.PurePosixPath]:
    raw = run(
        ("git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard")
    ).stdout
    paths = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        relative = pathlib.PurePosixPath(item.decode("utf-8", "strict"))
        if relative.is_absolute() or ".." in relative.parts or is_sensitive(relative):
            raise EngineerError(f"unsafe untracked handoff path: {relative}")
        paths.append(relative)
    return paths


def copy_untracked(root: pathlib.Path, workspace: pathlib.Path) -> list[str]:
    copied: list[str] = []
    for relative in untracked_paths(root):
        source = root.joinpath(*relative.parts)
        target = workspace.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
        elif source.is_dir():
            shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
        copied.append(relative.as_posix())
    return copied


def project_state(root: pathlib.Path) -> dict[str, object]:
    return {
        "branch": git_text(root, "branch", "--show-current").strip(),
        "head": git_text(root, "rev-parse", "HEAD").strip(),
        "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "status": git_text(root, "status", "--short", "--branch", "--untracked-files=all"),
        "stashes": git_text(root, "stash", "list").splitlines(),
    }


def create_workspace(
    root: pathlib.Path, state_root: pathlib.Path, task: str, objective: str
) -> pathlib.Path:
    validate_task(task)
    if not objective.strip():
        raise EngineerError("objective must not be empty")
    root = root.resolve(strict=True)
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    task_root = state_root / "tasks" / task
    if task_root.exists():
        raise EngineerError(f"task already exists: {task}")

    before = project_state(root)
    workspace = task_root / "workspace"
    task_root.mkdir(mode=0o700, parents=True)
    try:
        run(("git", "clone", "--no-hardlinks", "--no-checkout", str(root), str(workspace)))
        run(("git", "remote", "remove", "origin"), cwd=workspace)
        run(("git", "checkout", "-b", f"hermes/{task}", str(before["head"])), cwd=workspace)
        patch = run(("git", "-C", str(root), "diff", "--binary", "HEAD", "--")).stdout
        if patch:
            run(("git", "apply", "--binary", "-"), cwd=workspace, input_bytes=patch)
        copied = copy_untracked(root, workspace)

        # Freeze the exact dirty handoff snapshot in an isolated local commit. This
        # makes every later diff/export Hermes-only while preserving source HEAD
        # separately as canonical provenance. The clone has no remote authority.
        run(("git", "config", "user.name", "OPENHTPC Hermes Handoff"), cwd=workspace)
        run(
            ("git", "config", "user.email", "hermes-handoff@openhtpc.invalid"),
            cwd=workspace,
        )
        run(("git", "add", "-A"), cwd=workspace)
        run(
            ("git", "commit", "--allow-empty", "--no-gpg-sign", "-m", "OPENHTPC handoff baseline"),
            cwd=workspace,
        )
        baseline_commit = git_text(workspace, "rev-parse", "HEAD").strip()

        created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        handoff = {
            "schema": "openhtpc-hermes-handoff-v1",
            "created_utc": created,
            "source": before,
            "objective": objective.strip(),
            "workspace_branch": f"hermes/{task}",
            "workspace_baseline_commit": baseline_commit,
            "canonical_skills_path": str(root / ".agents/skills"),
            "workspace_isolation": {
                "standalone_clone": True,
                "canonical_git_authority": False,
                "remotes": [],
                "host_ssh_mounted": False,
                "docker_socket_mounted": False,
            },
            "permissions": {
                "workspace_write": True,
                "local_commit": True,
                "push": False,
                "merge_canonical": False,
                "deploy": False,
                "release": False,
                "physical_operation": False,
                "protected_stash_operation": False,
            },
            "untracked_paths_copied": copied,
        }
        (workspace / "OPENHTPC_HANDOFF.json").write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (workspace / "OPENHTPC_HANDOFF.md").write_text(
            "# OPENHTPC Hermes engineering handoff\n\n"
            f"Objective: {objective.strip()}\n\n"
            f"Source branch: `{before['branch']}`\n\n"
            f"Source HEAD: `{before['head']}`\n\n"
            f"Isolated baseline commit: `{baseline_commit}`\n\n"
            "Read `AGENTS.md`, `docs/OPENHTPC_CONTINUITY.md`, "
            "`docs/OPENHTPC_ACTORS.md`, `OPENHTPC-ROADMAP.md` and this JSON before acting.\n\n"
            "This is an isolated clone. Local edits and local commits are allowed. "
            "Push, canonical merge, deployment, release, physical operations and protected-stash operations are forbidden.\n",
            encoding="utf-8",
        )
        exclude = workspace / ".git/info/exclude"
        with exclude.open("a", encoding="utf-8") as stream:
            stream.write("\nOPENHTPC_HANDOFF.json\nOPENHTPC_HANDOFF.md\n")
        (task_root / "home/.ssh").mkdir(mode=0o700, parents=True)
        (task_root / "reports").mkdir(mode=0o700)
        (task_root / "exports").mkdir(mode=0o700)
        (task_root / "task.json").write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        after = project_state(root)
        if before != after:
            raise EngineerError("canonical repository changed while preparing handoff")
        return task_root
    except Exception:
        if task_root.exists():
            shutil.rmtree(task_root)
        raise


def docker_prefix() -> list[str]:
    if os.access("/var/run/docker.sock", os.R_OK | os.W_OK):
        return []
    return ["sg", "docker", "-c"]


def docker_call(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    prefix = docker_prefix()
    if prefix:
        return run((*prefix, shlex.join(args)), check=check)
    return run(args, check=check)


def base_image() -> str:
    metadata = json.loads((MIGRATION_STATE / "target-image.private.json").read_text(encoding="utf-8"))
    return metadata[0]["Id"]


def build_image(image: str) -> None:
    docker_call(
        (
            "docker",
            "build",
            "--build-arg",
            f"HERMES_BASE={base_image()}",
            "--tag",
            image,
            str(ROOT / "tools/hermes-engineer"),
        )
    )


def container_args(task_root: pathlib.Path, image: str, entry_args: Sequence[str]) -> list[str]:
    uid = os.getuid()
    gid = os.getgid()
    args = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--user",
        f"{uid}:{gid}",
        "--workdir",
        "/opt/hermes",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--env-file",
        str(task_root / "home/provider.env"),
        "--env",
        "HOME=/engineer-home",
        "--env",
        "HERMES_HOME=/engineer-home",
        "--env",
        "HERMES_WRITE_SAFE_ROOT=/workspace",
        "--env",
        "API_SERVER_ENABLED=false",
        "--volume",
        f"{task_root / 'workspace'}:/workspace:rw,z",
        "--volume",
        f"{task_root / 'home'}:/engineer-home:rw,z",
    ]
    task_metadata = task_root / "task.json"
    if task_metadata.is_file():
        metadata = json.loads(task_metadata.read_text(encoding="utf-8"))
        skills = pathlib.Path(str(metadata.get("canonical_skills_path", "")))
        if skills.is_dir():
            args.extend(("--volume", f"{skills}:/workspace/.agents/skills:ro,z"))
    args.extend(
        (
            "--volume",
            "/home/steve/.local/share/hermes-agent/codegraph/codegraph-server-linux-x64:/opt/codegraph/codegraph-server:ro,z",
            "--entrypoint",
            "/opt/hermes/hermes",
            image,
            *entry_args,
        )
    )
    return args


def provision_provider_env(task_root: pathlib.Path, image: str) -> pathlib.Path:
    target = task_root / "home/provider.env"
    script = (
        "import os,pathlib\n"
        "source=pathlib.Path('/source.env').read_text(encoding='utf-8').splitlines()\n"
        "matches=[line for line in source if line.startswith('OPENROUTER_API_KEY=') and line.split('=',1)[1]]\n"
        "assert len(matches)==1, 'exactly one non-empty OPENROUTER_API_KEY is required'\n"
        "target=pathlib.Path('/dest/provider.env')\n"
        "if target.exists(): target.unlink()\n"
        "target.write_text(matches[0]+'\\n',encoding='utf-8')\n"
        "target.chmod(0o600)\n"
        "os.chown(target,int(os.environ['TARGET_UID']),int(os.environ['TARGET_GID']))\n"
    )
    helper = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "0:0",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "DAC_READ_SEARCH",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "CHOWN",
        "--security-opt",
        "no-new-privileges",
        "--env",
        f"TARGET_UID={os.getuid()}",
        "--env",
        f"TARGET_GID={os.getgid()}",
        "--volume",
        f"{HERMES_ACTIVE_ENV}:/source.env:ro,z",
        "--volume",
        f"{task_root / 'home'}:/dest:rw,z",
        "--entrypoint",
        "python3",
        image,
        "-c",
        script,
    ]
    docker_call(helper)
    if not target.is_file() or target.stat().st_mode & 0o077:
        raise EngineerError("task OpenRouter credential was not provisioned with mode 0600")
    return target


def configure_task(task_root: pathlib.Path, image: str) -> None:
    provision_provider_env(task_root, image)
    for key, value in (
        ("model.default", "deepseek/deepseek-v4.1-flash"),
        ("model.provider", "openrouter"),
        ("model.base_url", "https://openrouter.ai/api/v1"),
    ):
        configure = container_args(task_root, image, ("config", "set", key, value))
        docker_call(configure)
    trust = container_args(task_root, image, ("--in", "/workspace", "skills", "trust", "/workspace"))
    docker_call(trust)
    remove = container_args(task_root, image, ("mcp", "remove", "codegraph"))
    docker_call(remove, check=False)
    add = container_args(
        task_root,
        image,
        (
            "mcp",
            "add",
            "codegraph",
            "--command",
            "/opt/codegraph/codegraph-server",
            "--env",
            "CODEGRAPH_TELEMETRY=off",
            "--args",
            "--mcp",
            "--workspace",
            "/workspace",
            "--exclude",
            "artifacts",
            "--embedding-model",
            "static",
            "--profile",
            "graph",
            "--graph-only",
        ),
    )
    docker_call(add)


def run_task(task_root: pathlib.Path, image: str, prompt: str) -> pathlib.Path:
    configure_task(task_root, image)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = task_root / "reports" / f"hermes-{stamp}.md"
    invocation = container_args(
        task_root,
        image,
        (
            "--in",
            "/workspace",
            "--model",
            "deepseek/deepseek-v4.1-flash",
            "--provider",
            "openrouter",
            "--reasoning",
            "high",
            "-z",
            prompt,
        ),
    )
    result = docker_call(invocation, check=False)
    report.write_bytes(result.stdout)
    (report.with_suffix(".stderr")).write_bytes(result.stderr)
    (report.with_suffix(".exit")).write_text(f"{result.returncode}\n", encoding="ascii")
    if result.returncode:
        raise EngineerError(f"Hermes run failed with exit code {result.returncode}; see {report}")
    return report


def export_task(task_root: pathlib.Path) -> pathlib.Path:
    workspace = task_root / "workspace"
    metadata = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
    baseline = str(metadata["workspace_baseline_commit"])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_root = task_root / "exports" / stamp
    export_root.mkdir(mode=0o700)
    (export_root / "changes.patch").write_bytes(
        run(("git", "diff", "--binary", baseline, "--"), cwd=workspace).stdout
    )
    untracked = run(
        ("git", "ls-files", "-z", "--others", "--exclude-standard"), cwd=workspace
    ).stdout
    (export_root / "untracked.paths.z").write_bytes(untracked)
    (export_root / "status.txt").write_text(
        git_text(workspace, "status", "--short", "--branch", "--untracked-files=all"),
        encoding="utf-8",
    )
    return export_root


def task_root(state_root: pathlib.Path, task: str) -> pathlib.Path:
    validate_task(task)
    path = state_root / "tasks" / task
    if not (path / "workspace/.git").exists():
        raise EngineerError(f"unknown task: {task}")
    return path


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--state-root", type=pathlib.Path, default=DEFAULT_STATE)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("task")
    prepare.add_argument("objective")
    execute = sub.add_parser("run")
    execute.add_argument("task")
    execute.add_argument("prompt")
    status = sub.add_parser("status")
    status.add_argument("task")
    export = sub.add_parser("export")
    export.add_argument("task")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "build":
            build_image(args.image)
            print(args.image)
        elif args.command == "prepare":
            print(create_workspace(args.root, args.state_root, args.task, args.objective))
        elif args.command == "run":
            print(run_task(task_root(args.state_root, args.task), args.image, args.prompt))
        elif args.command == "status":
            workspace = task_root(args.state_root, args.task) / "workspace"
            print(git_text(workspace, "status", "--short", "--branch", "--untracked-files=all"), end="")
        elif args.command == "export":
            print(export_task(task_root(args.state_root, args.task)))
        return 0
    except (EngineerError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
