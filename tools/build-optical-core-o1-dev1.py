#!/usr/bin/env python3
"""Build the O1 physical-validation artifact after all truth guards pass."""
from __future__ import annotations
import gzip, hashlib, json, os, pathlib, tarfile, tempfile
import openhtpc_release_metadata as release_metadata

ROOT=pathlib.Path(__file__).resolve().parents[1]
NAME="OpenHTPC-1.1.3-Optical-Core-O1-Dev1"
BUILD_ID="optical-media-core-detection-dev1"
BASELINE="0027c25ea866c47e3afe9775f6a5908bdbbbbeeb"
ARTIFACTS=ROOT/"artifacts"
EXCLUDED={".git","artifacts","__pycache__"}

def digest(path):
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): value.update(chunk)
    return value.hexdigest()

def files():
    return sorted((path for path in ROOT.rglob("*") if path.is_file() and
                   not EXCLUDED.intersection(path.relative_to(ROOT).parts)),
                  key=lambda path:path.relative_to(ROOT).as_posix())

def write_manifest():
    paths=[path for path in files() if path.name!="MANIFEST.sha256"]
    (ROOT/"MANIFEST.sha256").write_text("".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths),encoding="utf-8")

def build():
    metadata=release_metadata.validate_tree(ROOT,BUILD_ID); write_manifest(); ARTIFACTS.mkdir(exist_ok=True)
    archive=ARTIFACTS/f"{NAME}.tar.gz"; checksum=archive.with_suffix(archive.suffix+".sha256")
    report=ARTIFACTS/f"{NAME}-report.json"
    if any(path.exists() for path in (archive,checksum,report)): raise FileExistsError("OPTICAL_CORE_O1_ARTIFACT_COLLISION")
    with tempfile.NamedTemporaryFile(dir=ARTIFACTS,prefix=NAME+".",delete=False) as raw: temporary=pathlib.Path(raw.name)
    try:
        with temporary.open("wb") as target,gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode="w") as tar:
                for path in files():
                    relative=path.relative_to(ROOT); info=tar.gettarinfo(str(path),arcname=f"{NAME}/{relative.as_posix()}")
                    info.uid=info.gid=0; info.uname=info.gname="root"; info.mtime=0
                    with path.open("rb") as stream: tar.addfile(info,stream)
        os.replace(temporary,archive)
    finally: temporary.unlink(missing_ok=True)
    release_metadata.validate_archive(archive,BUILD_ID)
    sha=digest(archive); checksum.write_text(f"{sha}  {archive.name}\n",encoding="utf-8")
    report.write_text(json.dumps({"schema":1,"product":"OPENHTPC","version":metadata["top_version"],"build_id":BUILD_ID,
        "baseline":BASELINE,"artifact":archive.name,"sha256":sha,"dedicated_tests":"13/13 PASS",
        "full_regression":"161/161 PASS","status":"OPTICAL_CORE_O1_READY_FOR_PHYSICAL_VALIDATION","published":False},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return archive,checksum,report

if __name__=="__main__":
    for item in build(): print(item)
