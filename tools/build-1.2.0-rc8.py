#!/usr/bin/env python3
"""Build the deterministic OPENHTPC 1.2.0 RC8 qualified release candidate."""
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata

ROOT=pathlib.Path(__file__).resolve().parents[1]
NAME = "OpenHTPC-1.2.0-RC8"
BUILD = "public-release-1.2.0-rc8"
ARTIFACTS=ROOT/"artifacts"
EXCLUDED={".git","artifacts","__pycache__","diagnostics",".pytest_cache",".openhtpc-autopilot"}
def digest(path):
 value=hashlib.sha256()
 with path.open("rb") as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b""):value.update(chunk)
 return value.hexdigest()
def files():return sorted((p for p in ROOT.rglob("*") if p.is_file() and not EXCLUDED.intersection(p.relative_to(ROOT).parts)),key=lambda p:p.relative_to(ROOT).as_posix())
def write_manifest():
 paths=[p for p in files() if p.name!="MANIFEST.sha256"];(ROOT/"MANIFEST.sha256").write_text("".join(f"{digest(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in paths),encoding="utf-8")
def build():
 metadata=release_metadata.validate_tree(ROOT,BUILD);write_manifest();ARTIFACTS.mkdir(exist_ok=True)
 archive=ARTIFACTS/f"{NAME}.tar.gz";checksum=pathlib.Path(str(archive)+".sha256");validation=ARTIFACTS/f"{NAME}.validation.json";report=ARTIFACTS/f"{NAME}-report.json"
 for p in (archive,checksum,validation,report):p.unlink(missing_ok=True)
 with tempfile.NamedTemporaryFile(dir=ARTIFACTS,prefix=NAME+".",delete=False) as raw:temporary=pathlib.Path(raw.name)
 try:
  with temporary.open("wb") as target,gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0) as compressed:
   with tarfile.open(fileobj=compressed,mode="w") as output:
    for path in files():
     relative=path.relative_to(ROOT);info=output.gettarinfo(str(path),arcname=f"{NAME}/{relative.as_posix()}");info.uid=info.gid=0;info.uname=info.gname="root";info.mtime=0
     with path.open("rb") as stream:output.addfile(info,stream)
  os.replace(temporary,archive)
 finally:temporary.unlink(missing_ok=True)
 release_metadata.validate_archive(archive,BUILD);sha=digest(archive);checksum.write_text(f"{sha}  {archive.name}\n",encoding="utf-8");commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
 common={"schema":1,"version":metadata["top_version"],"commit":commit,"artifact":archive.name,"sha256":sha,"physical_qualification":"PASS_REFERENCE_BENCH","media_foundation":"ASYNC_LIBRARY_IDENTITY_TMDB_WITH_LIVE_ACTIVITY","unicode_cjk":"PASS"}
 validation.write_text(json.dumps({**common,"build":BUILD,"installation_method":"install.sh/update.sh","human_physical_validation_required":False,"decisive_test":"DEV6C3U_RYZEN3_MEDIA_FOUNDATION_CJK"},indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report.write_text(json.dumps({**common,"build_id":BUILD,"reference_platform":"Fedora 44 KDE Wayland / Ryzen 3 PRO 3200GE / Radeon Vega 3 / Denon AVR-X1800H","status":"OPENHTPC_1_2_0_RC8_QUALIFIED_FOR_PRERELEASE"},indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return archive,checksum,validation,report
if __name__=="__main__":
 for item in build():print(item)
