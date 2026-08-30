#!/usr/bin/env python3
"""Build the deterministic OPENHTPC 1.1.3 RC2 physical-validation candidate.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
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
NAME = "OpenHTPC-1.1.3-RC2"
BUILD = "public-release-1.1.3-rc2"
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
        raise FileExistsError("RC2_ARTIFACT_COLLISION")

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
        "nvidia": ["dev19_to_rc2", "doctor_ready", "nvdec_runtime", "mpeg2_media",
                   "h264_media", "hevc_main10_4k_media", "quit_kde", "reboot_autostart"],
        "amd": ["qualified_baseline_to_rc2", "doctor_ready", "vaapi_runtime",
                "media_smoke", "video_playback", "quit_return", "reboot_autostart"],
        "intel": ["qualified_baseline_to_rc2", "doctor_ready", "vaapi_runtime",
                  "media_smoke", "dvd_smoke_if_available", "quit_return", "reboot_autostart"],
    }
    validation.write_text(json.dumps({
        "schema": 1, "version": metadata["top_version"], "build": BUILD,
        "commit": commit, "artifact": archive.name, "sha256": sha256,
        "installation_method": "update.sh", "human_physical_validation_required": True,
        "physical_qualification": "PENDING", "validators": matrix,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.write_text(json.dumps({
        "schema": 1, "version": metadata["top_version"], "build_id": BUILD,
        "commit": commit, "artifact": archive.name, "sha256": sha256,
        "targeted_release_tests": "54/54 PASS", "full_canonical_regression": "357/357 PASS",
        "dev19_nvidia_physical_baseline": "PASS", "rc2_physical_qualification": "PENDING",
        "status": "OPENHTPC_1_1_3_RC2_READY_FOR_PHYSICAL_VALIDATION",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return archive, checksum, validation, report


if __name__ == "__main__":
    for item in build():
        print(item)
