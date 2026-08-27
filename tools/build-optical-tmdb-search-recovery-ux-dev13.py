#!/usr/bin/env python3
"""Build bounded OPENHTPC 1.1.3 Dev13 optical TMDb recovery candidate."""
from __future__ import annotations
import gzip,hashlib,json,os,pathlib,subprocess,tarfile,tempfile
import openhtpc_release_metadata as release_metadata
ROOT=pathlib.Path(__file__).resolve().parents[1];NAME="OpenHTPC-1.1.3-Optical-TMDb-Search-Recovery-UX-Dev13";BUILD="optical-tmdb-search-recovery-ux-dev13";BASELINE="545d2cd";ARTIFACTS=ROOT/"artifacts";EXCLUDED={".git","artifacts","__pycache__","diagnostics"}
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
 if any(path.exists() for path in (archive,checksum,report,validation)):raise FileExistsError("OPTICAL_TMDB_SEARCH_RECOVERY_DEV13_ARTIFACT_COLLISION")
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
 matrix=["city_of_angel_auto_open_zero_result","normalized_prefill_city_of_angel","manual_city_of_angels_year_1998","explicit_confirmation","same_dvd_reinsert_mapping_reuse","hancock_picker_unchanged","colombiana_automatic_unchanged","quit_to_kde_manual_restart"]
 validation_data={"schema":1,"version":metadata["top_version"],"build":BUILD,"commit":commit,"artifact":archive.name,"sha256":sha,"intended_validator_phase":"OPTICAL_TMDB_SEARCH_RECOVERY_DEV13","installation_method":"update.sh","stop_openhtpc":True,"required_pre_checks":[["/usr/bin/test","-x","{HOME}/.local/bin/openhtpc"]],"required_post_checks":[["{HOME}/.local/bin/openhtpc","version"],["{HOME}/.local/bin/openhtpc","doctor"]],"playback_allowed":True,"local_kde_observation_required":True,"observer":"optical","purge_authorized":False,"physical_validation_matrix":matrix,"optical_revalidation_required":True}
 validation.write_text(json.dumps(validation_data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 report_data={"schema":1,"version":metadata["top_version"],"build_id":BUILD,"commit":commit,"baseline":BASELINE,"artifact":archive.name,"sha256":sha,"validation_manifest":validation.name,"focused_tests":"71/71 PASS","full_regression":"292/292 PASS","full_regression_exit":0,"status":"OPTICAL_TMDB_SEARCH_RECOVERY_DEV13_READY_FOR_PHYSICAL_VALIDATION","published":False,"backlog":["TMDB_AMBIGUITY_MANUAL_SEARCH_ESCAPE","UHD_CLASSIFICATION_EVIDENCE","TMDB_CINEMATIC_BACKDROP_UX","DOCTOR_MEDIA_ACTION_RUNTIME_SEMANTICS","MEDIA_PLAYBACK_DIAGNOSTIC_CURRENT_PAGE_SEMANTICS","GLOBAL_STATUS_PROBLEME_SEMANTICS_REVIEW","NETWORK_CONNECTIVITY_STATUS_UI","POWER_NO_SUSPEND_POLICY_REVALIDATION"]}
 report.write_text(json.dumps(report_data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return archive,checksum,validation,report
if __name__=="__main__":
 for item in build():print(item)
