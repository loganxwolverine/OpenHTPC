#!/usr/bin/env python3
"""Build the deterministic OPENHTPC protected-optical Dev5 artifact."""
from __future__ import annotations
import gzip,hashlib,os,pathlib,tarfile,tempfile
import openhtpc_release_metadata as release_metadata

ROOT=pathlib.Path(__file__).resolve().parents[1]
NAME="OpenHTPC-1.1.4-Protected-Optical-Qualification-UX-Dev5"
BUILD="protected-optical-qualification-ux-dev5"
ARTIFACTS=ROOT/"artifacts"
EXCLUDED={".git","artifacts","__pycache__","diagnostics"}

def digest(path):
 value=hashlib.sha256()
 with path.open("rb") as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b""):value.update(chunk)
 return value.hexdigest()
def files():return sorted((path for path in ROOT.rglob("*") if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts)),key=lambda path:path.relative_to(ROOT).as_posix())
def write_manifest():
 paths=[path for path in files() if path.name!="MANIFEST.sha256"]
 (ROOT/"MANIFEST.sha256").write_text("".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths),encoding="utf-8")
def build():
 release_metadata.validate_tree(ROOT,BUILD);write_manifest();ARTIFACTS.mkdir(exist_ok=True)
 archive=ARTIFACTS/f"{NAME}.tar.gz";sidecar=pathlib.Path(str(archive)+".sha256")
 if archive.exists() or sidecar.exists():raise FileExistsError("DEV5_ARTIFACT_COLLISION")
 with tempfile.NamedTemporaryFile(dir=ARTIFACTS,prefix=NAME+".",delete=False) as raw:temporary=pathlib.Path(raw.name)
 try:
  with temporary.open("wb") as target,gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0) as compressed:
   with tarfile.open(fileobj=compressed,mode="w") as output:
    for path in files():
     relative=path.relative_to(ROOT);entry=output.gettarinfo(str(path),arcname=f"{NAME}/{relative.as_posix()}")
     entry.uid=entry.gid=0;entry.uname=entry.gname="root";entry.mtime=0
     with path.open("rb") as stream:output.addfile(entry,stream)
  os.replace(temporary,archive)
 finally:temporary.unlink(missing_ok=True)
 release_metadata.validate_archive(archive,BUILD);sha=digest(archive);sidecar.write_text(f"{sha}  {archive.name}\n",encoding="utf-8")
 return archive,sidecar
if __name__=="__main__":
 for item in build():print(item)
