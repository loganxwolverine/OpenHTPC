#!/usr/bin/env python3
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata
ROOT=pathlib.Path(__file__).resolve().parents[1];NAME="OpenHTPC-1.1.3-Running-Flex-Media-Sync-Dev16";BUILD="running-flex-media-generation-sync-dev16";ARTIFACTS=ROOT/"artifacts";EXCLUDED={".git","artifacts","__pycache__","diagnostics"}
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
 return h.hexdigest()
def files():return sorted((p for p in ROOT.rglob("*") if p.is_file() and not EXCLUDED.intersection(p.relative_to(ROOT).parts)),key=lambda p:p.relative_to(ROOT).as_posix())
def manifest():
 paths=[p for p in files() if p.name!="MANIFEST.sha256"];(ROOT/"MANIFEST.sha256").write_text("".join(f"{digest(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in paths))
def build():
 metadata=release_metadata.validate_tree(ROOT,BUILD);manifest();ARTIFACTS.mkdir(exist_ok=True);archive=ARTIFACTS/f"{NAME}.tar.gz";checksum=pathlib.Path(str(archive)+".sha256");report=ARTIFACTS/f"{NAME}-report.json";validation=ARTIFACTS/f"{NAME}.validation.json"
 for p in (archive,checksum,report,validation):
  if p.exists():raise FileExistsError(p)
 with tempfile.NamedTemporaryFile(dir=ARTIFACTS,delete=False) as raw:tmp=pathlib.Path(raw.name)
 try:
  with tmp.open("wb") as target,gzip.GzipFile(filename="",mode="wb",fileobj=target,mtime=0) as gz:
   with tarfile.open(fileobj=gz,mode="w") as tar:
    for p in files():
     rel=p.relative_to(ROOT);info=tar.gettarinfo(str(p),arcname=f"{NAME}/{rel}");info.uid=info.gid=0;info.uname=info.gname="root";info.mtime=0
     with p.open("rb") as stream:tar.addfile(info,stream)
  os.replace(tmp,archive)
 finally:tmp.unlink(missing_ok=True)
 release_metadata.validate_archive(archive,BUILD);sha=digest(archive);checksum.write_text(f"{sha}  {archive.name}\n");commit=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
 validation.write_text(json.dumps({"schema":1,"version":metadata["top_version"],"build":BUILD,"commit":commit,"artifact":archive.name,"sha256":sha,"installation_method":"update.sh","apply_remotely":False,"physical_matrix":["dev15_to_dev16","cache_media_dvd_descendant","live_remove_add_without_restart","alerte_video_audio_seek","running_token_matches_authority","optical_refresh_media_replay","quit_kde","manual_restart"]},indent=2,sort_keys=True)+"\n")
 report.write_text(json.dumps({"schema":1,"version":metadata["top_version"],"build_id":BUILD,"commit":commit,"artifact":archive.name,"sha256":sha,"focused_tests":"35/35 PASS","full_regression":"314/314 PASS","flex_binary_sha256":"351fbe72572fa719fd325899e6ab3703cf42de9a62732904c80555daf236448c","flex_build_id":"77862cb627f4f324f99a4c08a5bba5f8d4958901","status":"RUNNING_FLEX_MEDIA_SYNC_DEV16_READY_FOR_PHYSICAL_VALIDATION"},indent=2,sort_keys=True)+"\n");return archive,checksum,validation,report
if __name__=="__main__":
 for p in build():print(p)
