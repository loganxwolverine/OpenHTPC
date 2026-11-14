#!/usr/bin/env python3
"""Validate all managed package sources before any update changes.

Fail closed for malformed manifest entries, absent source files or symlink
escapes. Does not install, change system state or follow external resources.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import pathlib
import sys


def verify_manifest(root: pathlib.Path) -> int:
    package = root.parent
    manifest = package / "MANIFEST.sha256"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("missing or unsafe SHA256 manifest")
    seen = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("malformed SHA256 manifest")
        digest, name = match.groups()
        rel = pathlib.PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or name != rel.as_posix() or "\\" in name:
            raise ValueError("unsafe SHA256 path")
        if name in seen:
            raise ValueError("duplicate SHA256 entry")
        seen.add(name)
        path = package.joinpath(*rel.parts)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(package) or not resolved.is_file():
            raise ValueError("SHA256 source outside package")
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b""):
                h.update(chunk)
        if h.hexdigest() != digest:
            raise ValueError("SHA256 mismatch: " + name)
    if len(seen) < 600:
        raise ValueError("incomplete SHA256 manifest")
    return len(seen)


def validate(root: pathlib.Path) -> int:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("invalid payload directory")
    for name in ("managed-files.txt", "version.json", "flex/BUILD-METADATA.json",
                 "openhtpc-preflight-payload.py"):
        path = root/name
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("required source absent or outside package: "+name)
    lines = (root/"managed-files.txt").read_text(encoding="utf-8").splitlines()
    seen = set()
    for raw in lines:
        name = raw.strip()
        if not name or name.startswith("#") or name==".openhtpc-managed-files":
            continue
        entry = pathlib.PurePosixPath(name)
        if (entry.is_absolute() or ".." in entry.parts or
                name != entry.as_posix() or chr(92) in name):
            raise ValueError("unsafe managed source: "+name)
        if name in seen:
            raise ValueError("duplicate managed source: "+name)
        seen.add(name)
        path = root.joinpath(*entry.parts)
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("missing managed source: "+name) from exc
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("managed source outside package or not file: "+name)
    if len(seen)<200:
        raise ValueError("incomplete managed source manifest")
    verify_manifest(root)
    return len(seen)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--payload",type=pathlib.Path,required=True)
    args=parser.parse_args()
    try:
        count=validate(args.payload)
    except (OSError,ValueError,RuntimeError) as exc:
        print("OPENHTPC_PAYLOAD_PREFLIGHT_REJECT: "+str(exc),file=sys.stderr)
        return 41
    print("OPENHTPC_PAYLOAD_PREFLIGHT_PASS "+str(count))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
