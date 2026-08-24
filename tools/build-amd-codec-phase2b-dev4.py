#!/usr/bin/env python3
"""Build the bounded AMD canonical capability consistency candidate."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pathlib
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAME = "OpenHTPC-1.1.2-AMD-Codec-Phase2B-Dev4"
ARTIFACTS = ROOT / "artifacts"
EXCLUDED_PARTS = {".git", "artifacts", "__pycache__"}


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): value.update(chunk)
    return value.hexdigest()


def files() -> list[pathlib.Path]:
    return sorted((path for path in ROOT.rglob("*") if path.is_file() and
                   not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)),
                  key=lambda path: path.relative_to(ROOT).as_posix())


def write_manifest() -> None:
    paths = [path for path in files() if path.name != "MANIFEST.sha256"]
    (ROOT / "MANIFEST.sha256").write_text(
        "".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths), encoding="utf-8")


def build() -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    write_manifest(); ARTIFACTS.mkdir(exist_ok=True)
    archive = ARTIFACTS / f"{NAME}.tar.gz"; checksum = archive.with_suffix(archive.suffix + ".sha256")
    report = ARTIFACTS / f"{NAME}-report.json"
    if any(path.exists() for path in (archive, checksum, report)):
        raise FileExistsError("AMD_CODEC_PHASE2B_DEV4_ARTIFACT_COLLISION")
    with tempfile.NamedTemporaryFile(dir=ARTIFACTS, prefix=NAME + ".", delete=False) as raw:
        temporary = pathlib.Path(raw.name)
    try:
        with temporary.open("wb") as target, gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for path in files():
                    relative = path.relative_to(ROOT); info = tar.gettarinfo(str(path), arcname=f"{NAME}/{relative.as_posix()}")
                    info.uid = info.gid = 0; info.uname = info.gname = "root"; info.mtime = 0
                    with path.open("rb") as stream: tar.addfile(info, stream)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    sha = digest(archive); checksum.write_text(f"{sha}  {archive.name}\n", encoding="utf-8")
    report.write_text(json.dumps({
        "schema": 1, "product": "OPENHTPC", "version": "1.1.2-dev4",
        "build_id": "amd-codec-canonical-refresh-consistency-dev4", "artifact": archive.name,
        "sha256": sha, "dev3_baseline": "a9e819e268a8cb4b075568cfd40f68119b46ef18",
        "status": "AMD_CODEC_PHASE2B_DEV4_SOFTWARE_TESTS_PASS_PHYSICAL_CONSISTENCY_REQUIRED",
        "published": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return archive, checksum, report


if __name__ == "__main__":
    for item in build(): print(item)
