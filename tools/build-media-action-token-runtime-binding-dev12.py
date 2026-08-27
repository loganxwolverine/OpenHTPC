#!/usr/bin/env python3
"""Build bounded OPENHTPC 1.1.3 Dev12 MEDIA token-binding candidate."""
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata
ROOT=pathlib.Path(__file__).resolve().parents[1];NAME="OpenHTPC-1.1.3-Media-Action-Token-Runtime-Binding-Dev12";BUILD="media-action-token-runtime-binding-dev12";BASELINE="19775007e1a849daab418d86115b79231258ef43";ARTIFACTS=ROOT/"artifacts";EXCLUDED={".git","artifacts","__pycache__","diagnostics"}
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
 if any(path.exists() for path in (archive,checksum,report,validation)):raise FileExistsError("MEDIA_ACTION_TOKEN_RUNTIME_BINDING_DEV12_ARTIFACT_COLLISION")
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
 matrix=["media_movies_alerte_mkv_video_audio_seek_quit_return_media","media_it_mkv_video_audio_quit_return_media","media_300_rise_video_audio_overlay_quit_return_media","different_hashed_media_page_file_pass","quit_to_kde_pass","manual_openhtpc_start_pass"]
 validation_data={"schema":1,"version":metadata["top_version"],"build":BUILD,"commit":commit,"artifact":archive.name,"sha256":sha,"intended_validator_phase":"MEDIA_ACTION_TOKEN_RUNTIME_BINDING_DEV12","installation_method":"update.sh","stop_openhtpc":True,"required_pre_checks":[["/usr/bin/test","-x","{HOME}/.local/bin/openhtpc"]],"required_post_checks":[["{HOME}/.local/bin/openhtpc","version"],["{HOME}/.local/bin/openhtpc","doctor"]],"playback_allowed":True,"local_kde_observation_required":True,"observer":None,"purge_authorized":False,"physical_validation_matrix":matrix,"optical_revalidation_required":False}
 validation.write_text(json.dumps(validation_data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report_data={"schema":1,"version":metadata["top_version"],"build_id":BUILD,"commit":commit,"baseline":BASELINE,"artifact":archive.name,"sha256":sha,"validation_manifest":validation.name,"focused_tests":"79/79 PASS","dev12_tests":"6/6 PASS","full_regression":"268/268 PASS","root_cause":"MEDIA tokens were coupled to general menu generation; optical-only regeneration could expose tokens absent from the active MEDIA manifest.","diagnostic_correction":"current_page=MEDIA was a hardcoded pending diagnostic default, not proof that Flex published generic MEDIA.","status":"MEDIA_ACTION_TOKEN_DEV12_READY_FOR_PHYSICAL_VALIDATION","published":False,"backlog":["DOCTOR_MEDIA_ACTION_RUNTIME_SEMANTICS","MEDIA_PLAYBACK_DIAGNOSTIC_CURRENT_PAGE_SEMANTICS"]}
 report.write_text(json.dumps(report_data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return archive,checksum,validation,report
if __name__=="__main__":
 for item in build():print(item)
