#!/usr/bin/env python3
"""Execute one explicitly approved, registry-bounded Fedora transaction."""
from __future__ import annotations
import argparse,json,pathlib,shutil,subprocess,sys

DVD_PACKAGE_REGISTRY=frozenset({"lsdvd","util-linux","udisks2","libdvdnav"})

def install_argv(dnf:str,packages:list[str])->list[str]:
 unknown=[value for value in packages if value not in DVD_PACKAGE_REGISTRY]
 if not packages or unknown: raise ValueError("PACKAGE_NOT_APPROVED:"+",".join(unknown))
 return [dnf,"install","--assumeyes",*packages]

def execute(dnf:str,packages:list[str],runner=subprocess.run)->int:
 argv=install_argv(dnf,packages)
 print("DNF action: install packages="+json.dumps(packages,ensure_ascii=False)+" assumeyes=yes",flush=True)
 print("DNF executable: "+dnf,flush=True)
 result=runner(argv,check=False)
 return int(result.returncode)

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--dnf",required=True);parser.add_argument("packages",nargs="+");args=parser.parse_args()
 dnf=shutil.which(args.dnf) if "/" not in args.dnf else args.dnf
 if not dnf or not pathlib.Path(dnf).is_file(): print("DNF_EXECUTABLE_NOT_FOUND",file=sys.stderr);return 2
 try:return execute(dnf,args.packages)
 except ValueError as exc:print(str(exc),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
