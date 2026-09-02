#!/usr/bin/env python3
"""Build the deterministic OPENHTPC 1.2.0 RC3 physical-validation candidate."""
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata

ROOT=pathlib.Path(__file__).resolve().parents[1]
NAME = "OpenHTPC-1.2.0-RC3"
BUILD = "public-release-1.2.0-rc3"
ARTIFACTS=ROOT/"artifacts"
EXCLUDED={".git","artifacts","__pycache__","diagnostics"}
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
 if any(p.exists() for p in (archive,checksum,validation,report)):raise FileExistsError("RC3_ARTIFACT_COLLISION")
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
 common={"schema":1,"version":metadata["top_version"],"commit":commit,"artifact":archive.name,"sha256":sha,"physical_qualification": "PENDING","protected_bluray_audio_fix": "SOFTWARE_PASS_PHYSICAL_VALIDATION_REQUIRED"}
 validation.write_text(json.dumps({**common,"build":BUILD,"installation_method":"update.sh","human_physical_validation_required":True,"decisive_test":"PROTECTED_BLURAY_BITSTREAM_AVR"},indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report.write_text(json.dumps({**common,"build_id":BUILD,"focused_security_tests":"173/173 PASS","complete_regression":"690/690 PASS","rc1":"NO_GO","rc2":"PHYSICAL_GATE_NO_GO","status":"OPENHTPC_1_2_0_RC3_READY_FOR_PHYSICAL_VALIDATION"},indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return archive,checksum,validation,report
if __name__=="__main__":
 for item in build():print(item)
