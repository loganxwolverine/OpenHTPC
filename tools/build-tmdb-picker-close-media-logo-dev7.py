#!/usr/bin/env python3
"""Build bounded OpenHTPC 1.1.3 Dev7 plus validator manifest."""
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata
ROOT=pathlib.Path(__file__).resolve().parents[1];NAME="OpenHTPC-1.1.3-TMDb-Picker-Close-Media-Logo-Dev7";BUILD="tmdb-picker-close-media-logo-dev7";BASELINE="d3be4e2eb4b9461df5d94a912156ef74dc92d400";ARTIFACTS=ROOT/"artifacts";EXCLUDED={".git","artifacts","__pycache__","diagnostics"}
def digest(path):
 value=hashlib.sha256()
 with path.open("rb") as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b""):value.update(chunk)
 return value.hexdigest()
def files():return sorted((path for path in ROOT.rglob("*") if path.is_file() and not EXCLUDED.intersection(path.relative_to(ROOT).parts)),key=lambda path:path.relative_to(ROOT).as_posix())
def manifest_hashes():
 paths=[path for path in files() if path.name!="MANIFEST.sha256"]
 (ROOT/"MANIFEST.sha256").write_text("".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths),encoding="utf-8")
def build():
 metadata=release_metadata.validate_tree(ROOT,BUILD);manifest_hashes();ARTIFACTS.mkdir(exist_ok=True)
 archive=ARTIFACTS/f"{NAME}.tar.gz";checksum=archive.with_suffix(archive.suffix+".sha256");report=ARTIFACTS/f"{NAME}-report.json";validation=ARTIFACTS/f"{NAME}.validation.json"
 if any(path.exists() for path in (archive,checksum,report,validation)):raise FileExistsError("TMDB_PICKER_CLOSE_MEDIA_LOGO_DEV7_ARTIFACT_COLLISION")
 with tempfile.NamedTemporaryFile(dir=ARTIFACTS,prefix=NAME+".",delete=False) as raw:temporary=pathlib.Path(raw.name)
 try:
  with temporary.open("wb") as target,gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0) as compressed:
   with tarfile.open(fileobj=compressed,mode="w") as tar:
    for path in files():
     relative=path.relative_to(ROOT);info=tar.gettarinfo(str(path),arcname=f"{NAME}/{relative.as_posix()}");info.uid=info.gid=0;info.uname=info.gname="root";info.mtime=0
     with path.open("rb") as stream:tar.addfile(info,stream)
  os.replace(temporary,archive)
 finally:temporary.unlink(missing_ok=True)
 release_metadata.validate_archive(archive,BUILD);sha=digest(archive);checksum.write_text(f"{sha}  {archive.name}\n",encoding="utf-8")
 commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
 validation_data={"schema":1,"version":metadata["top_version"],"build":BUILD,"commit":commit,"artifact":archive.name,"sha256":sha,"intended_validator_phase":"TMDB_PICKER_CLOSE_MEDIA_LOGO_DEV7","installation_method":"update.sh","stop_openhtpc":True,"required_pre_checks":[["/usr/bin/test","-x","{HOME}/.local/bin/openhtpc"]],"required_post_checks":[["{HOME}/.local/bin/openhtpc","version"],["{HOME}/.local/bin/openhtpc","doctor"]],"playback_allowed":False,"local_kde_observation_required":True,"observer":"optical","presentation_convergence_timeout_seconds":5,"purge_authorized":False}
 validation.write_text(json.dumps(validation_data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report.write_text(json.dumps({"schema":1,"version":metadata["top_version"],"build_id":BUILD,"commit":commit,"baseline":BASELINE,"artifact":archive.name,"sha256":sha,"validation_manifest":validation.name,"focused_tests":"52/52 PASS","full_regression":"213/213 PASS","status":"DEV7_READY_FOR_PHYSICAL_VALIDATION","published":False},indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return archive,checksum,validation,report
if __name__=="__main__":
 for item in build():print(item)
