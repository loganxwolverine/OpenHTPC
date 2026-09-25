#!/usr/bin/env python3
"""Build the deterministic OPENHTPC 1.2.0 stable release.

The public archive is exported from the exact Git commit. Flex is rebuilt from
that exported source tree and its schema-2 provenance is generated before the
manifest and archive are written. A stale repository prebuilt Flex binary is
never trusted for a public release.
"""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import gzip
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any

import openhtpc_release_metadata as release_metadata

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAME = "OpenHTPC-1.2.0"
BUILD = "public-release-1.2.0"
ARTIFACTS = ROOT / "artifacts"
DEV_TRANCHE = "PUBLIC_1_2_0"
WORKSTREAM = "STABLE_RELEASE"


def load_devctl():
    path = ROOT / "tools/openhtpc-devctl"
    loader = importlib.machinery.SourceFileLoader("openhtpc_devctl_release", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("STABLE_DEVCTL_SPEC_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


devctl = load_devctl()


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def exact_head() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        capture_output=True, check=True,
    ).stdout
    if status.strip():
        raise RuntimeError("STABLE_RELEASE_WORKTREE_DIRTY")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=True,
    ).stdout.strip()
    if not devctl.COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeError("STABLE_RELEASE_COMMIT_INVALID")
    return commit


def write_manifest(staging: pathlib.Path) -> None:
    files = sorted(
        (path for path in staging.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"),
        key=lambda path: path.relative_to(staging).as_posix(),
    )
    (staging / "MANIFEST.sha256").write_text(
        "".join(f"{digest(path)}  {path.relative_to(staging).as_posix()}\n" for path in files),
        encoding="utf-8",
    )


def write_deterministic_archive(staging: pathlib.Path, archive: pathlib.Path) -> None:
    with tempfile.NamedTemporaryFile(dir=ARTIFACTS, prefix=NAME + ".", delete=False) as raw:
        temporary = pathlib.Path(raw.name)
    try:
        with temporary.open("wb") as target, gzip.GzipFile(
            filename="", mode="wb", fileobj=target, mtime=0
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as output:
                for path in sorted(
                    (p for p in staging.rglob("*") if p.is_file()),
                    key=lambda p: p.relative_to(staging).as_posix(),
                ):
                    relative = path.relative_to(staging)
                    info = output.gettarinfo(
                        str(path), arcname=f"{NAME}/{relative.as_posix()}"
                    )
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = 0
                    with path.open("rb") as stream:
                        output.addfile(info, stream)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def stage_exact_release(commit: str, staging: pathlib.Path, scratch: pathlib.Path) -> dict[str, Any]:
    devctl._export_commit(commit, staging, scratch)
    metadata = release_metadata.validate_tree(staging, BUILD)

    flex_source = staging / "vendor/flex-launcher"
    fingerprint = devctl._source_fingerprint(flex_source)
    upstream = (flex_source / "UPSTREAM_COMMIT").read_text(encoding="utf-8").strip()
    if not devctl.COMMIT_PATTERN.fullmatch(upstream):
        raise RuntimeError("STABLE_FLEX_UPSTREAM_INVALID")

    built = devctl._build_flex(flex_source, scratch / "flex-build")
    staged_binary = staging / "payload/flex/bin/flex-launcher"
    staged_binary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, staged_binary)
    staged_binary.chmod(0o755)
    if digest(staged_binary) != digest(built):
        raise RuntimeError("STABLE_FLEX_STAGE_MISMATCH")

    flex_metadata: dict[str, Any] = {
        "schema": 2,
        "binary_sha256": digest(staged_binary),
        "elf_build_id": devctl._elf_build_id(staged_binary),
        "source_commit": commit,
        "source_revision": f"upstream-{upstream}+openhtpc-{commit}",
        "upstream_commit": upstream,
        "flex_source_fingerprint": fingerprint,
        "artifact_build_id": BUILD,
        "dev_tranche": DEV_TRANCHE,
        "workstream": WORKSTREAM,
        "product_version": metadata["top_version"],
    }
    devctl._validate_flex_metadata(flex_metadata)
    (staging / "payload/flex/BUILD-METADATA.json").write_text(
        json.dumps(flex_metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Preserve the RC8 Flex provenance guards.
    strings = subprocess.run(
        ["strings", str(staged_binary)], text=True, capture_output=True, check=True
    ).stdout
    for marker in ("LiveActivityState", "FallbackFont"):
        if marker not in strings:
            raise RuntimeError(f"STABLE_FLEX_REQUIRED_MARKER_MISSING:{marker}")

    # Fail closed if the RC9 couch-UX changes are absent from the exact
    # exported source tree being packaged.
    required_text_markers = {
        "payload/openhtpc-session-engine.py": (
            "MÉDIATHÈQUE —",
            "À rechercher",
            "ANALYSER MES MÉDIAS",
            "NAS / RÉSEAU",
        ),
        "payload/openhtpc-media-picker": ("NAS / RÉSEAU",),
    }
    for relative, markers in required_text_markers.items():
        text = (staging / relative).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                raise RuntimeError(f"STABLE_UX_REQUIRED_MARKER_MISSING:{relative}:{marker}")

    write_manifest(staging)
    return {"release": metadata, "flex": flex_metadata}


def build():
    commit = exact_head()
    ARTIFACTS.mkdir(exist_ok=True)
    archive = ARTIFACTS / f"{NAME}.tar.gz"
    checksum = pathlib.Path(str(archive) + ".sha256")
    validation = ARTIFACTS / f"{NAME}.validation.json"
    report = ARTIFACTS / f"{NAME}-report.json"
    for path in (archive, checksum, validation, report):
        path.unlink(missing_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="openhtpc-1.2.0-release-") as raw:
            scratch = pathlib.Path(raw)
            staging = scratch / "stage"
            staging.mkdir()
            staged = stage_exact_release(commit, staging, scratch)
            write_deterministic_archive(staging, archive)

        release_metadata.validate_archive(archive, BUILD)
        sha = digest(archive)
        checksum.write_text(f"{sha}  {archive.name}\n", encoding="utf-8")

        common = {
            "schema": 1,
            "version": staged["release"]["top_version"],
            "commit": commit,
            "artifact": archive.name,
            "sha256": sha,
            "physical_qualification": "PASS_REFERENCE_BENCH",
            "media_foundation": "RC8_FOUNDATION_PRESERVED",
            "media_ux": "LIBRARY_SUMMARY_UNMATCHED_REVIEW_SOURCE_DISCOVERY_FIRST_USE",
            "network_sources": "MOUNTED_NETWORK_DISCOVERY_WITHOUT_MOUNT_OWNERSHIP",
            "unicode_cjk": "PASS",
            "regression_vs_rc8": "NO_NEW_FAILURES_2164_PASS_2_SKIP_16_BASELINE_FAILURES",
            "flex_binary_sha256": staged["flex"]["binary_sha256"],
            "flex_source_commit": staged["flex"]["source_commit"],
            "dev_tranche": DEV_TRANCHE,
            "workstream": WORKSTREAM,
            "promotion_basis": "RC9_QUALIFIED_BEHAVIOR_NO_PRODUCT_CHANGE",
        }
        validation.write_text(
            json.dumps(
                {
                    **common,
                    "build": BUILD,
                    "installation_method": "install.sh/update.sh",
                    "human_physical_validation_required": False,
                    "decisive_test": "RC9_DEV8_INTEL_ARC_MEDIA_UX_REFERENCE_BENCH",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        report.write_text(
            json.dumps(
                {
                    **common,
                    "build_id": BUILD,
                    "reference_platform": "Fedora 44 KDE Wayland / Intel Core i5-6500 / Intel Arc A310 / Denon AVR-X1800H",
                    "status": "OPENHTPC_1_2_0_STABLE_QUALIFIED_FOR_RELEASE",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

        errors = devctl._verify_artifact(archive)
        if errors:
            raise RuntimeError("STABLE_RELEASE_VERIFY_FAILED: " + "; ".join(errors))
    except Exception:
        for path in (archive, checksum, validation, report):
            path.unlink(missing_ok=True)
        raise

    return archive, checksum, validation, report


if __name__ == "__main__":
    for item in build():
        print(item)
