#!/usr/bin/env python3
"""Build the deterministic OPENHTPC 1.2.0 RC1 physical-gate candidate.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile

import openhtpc_release_metadata as release_metadata


ROOT = pathlib.Path(__file__).resolve().parents[1]
NAME = "OpenHTPC-1.2.0-RC1"
BUILD = "public-release-1.2.0-rc1"
ARTIFACTS = ROOT / "artifacts"
EXCLUDED = {".git", "artifacts", "__pycache__", "diagnostics"}


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def files() -> list[pathlib.Path]:
    return sorted(
        (path for path in ROOT.rglob("*")
         if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def write_manifest() -> None:
    paths = [path for path in files() if path.name != "MANIFEST.sha256"]
    (ROOT / "MANIFEST.sha256").write_text(
        "".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths),
        encoding="utf-8",
    )


def build() -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    metadata = release_metadata.validate_tree(ROOT, BUILD)
    write_manifest()
    ARTIFACTS.mkdir(exist_ok=True)
    archive = ARTIFACTS / f"{NAME}.tar.gz"
    checksum = pathlib.Path(str(archive) + ".sha256")
    validation = ARTIFACTS / f"{NAME}.validation.json"
    report = ARTIFACTS / f"{NAME}-report.json"
    if any(path.exists() for path in (archive, checksum, validation, report)):
        raise FileExistsError("RC1_ARTIFACT_COLLISION")

    with tempfile.NamedTemporaryFile(dir=ARTIFACTS, prefix=NAME + ".", delete=False) as raw:
        temporary = pathlib.Path(raw.name)
    try:
        with temporary.open("wb") as target, gzip.GzipFile(
            filename="", mode="wb", fileobj=target, mtime=0
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as output:
                for path in files():
                    relative = path.relative_to(ROOT)
                    info = output.gettarinfo(str(path), arcname=f"{NAME}/{relative.as_posix()}")
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = 0
                    with path.open("rb") as stream:
                        output.addfile(info, stream)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)

    release_metadata.validate_archive(archive, BUILD)
    sha256 = digest(archive)
    checksum.write_text(f"{sha256}  {archive.name}\n", encoding="utf-8")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=True,
    ).stdout.strip()
    matrix = {
        "intel_zimaboard2": ["dev14_to_rc1", "identity", "doctor_ready", "core_flex_media",
                              "disabled_ui_gating", "protected_bluray", "protected_uhd", "dvd", "quit_return"],
        "amd_ryzen": ["dev14_to_rc1", "identity", "doctor_ready", "core_flex_media",
                      "disabled_ui_gating", "protected_bluray", "protected_uhd", "dvd", "quit_return"],
        "nvidia_rtx3050": ["dev14_to_rc1", "identity", "doctor_ready", "core_flex_media",
                           "disabled_ui_gating", "protected_bluray", "protected_uhd", "dvd", "quit_return"],
    }
    validation.write_text(json.dumps({
        "schema": 1, "version": metadata["top_version"], "build": BUILD,
        "commit": commit, "artifact": archive.name, "sha256": sha256,
        "origin_version": "1.2.0-dev14",
        "origin_commit": "e47ebe11c39b493746a1e38f258d462be0c86ea2",
        "origin_artifact_sha256": "94e030482c46b041ea0d791e261d0fea11e6c545270f036ef99543e324a65194",
        "installation_method": "update.sh", "human_physical_validation_required": True,
        "physical_qualification": "PENDING", "validators": matrix,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.write_text(json.dumps({
        "schema": 1, "version": metadata["top_version"], "build_id": BUILD,
        "commit": commit, "artifact": archive.name, "sha256": sha256,
        "dev14_multi_platform_physical_baseline": "PASS",
        "functional_changes_since_dev14": False,
        "rc1_physical_qualification": "PENDING",
        "status": "OPENHTPC_1_2_0_RC1_READY_FOR_PHYSICAL_RELEASE_GATE",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return archive, checksum, validation, report


if __name__ == "__main__":
    for item in build():
        print(item)
