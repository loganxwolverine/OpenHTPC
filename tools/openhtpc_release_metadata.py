#!/usr/bin/env python3
"""Propagate and validate OPENHTPC release metadata from the root VERSION."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import tarfile
import tempfile
from typing import Any

INSTALLER_PATTERN = re.compile(r'(?m)^readonly OPENHTPC_VERSION="([^"]+)"$')


def canonical_version(root: pathlib.Path) -> str:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("RELEASE_METADATA_CANONICAL_VERSION_INVALID")
    return version


def read_tree(root: pathlib.Path) -> dict[str, str]:
    metadata = json.loads((root / "payload/version.json").read_text(encoding="utf-8"))
    installer = (root / "payload/install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    match = INSTALLER_PATTERN.search(installer)
    if not match:
        raise ValueError("RELEASE_METADATA_INSTALLER_VERSION_MISSING")
    return {
        "top_version": canonical_version(root),
        "payload_version": (root / "payload/VERSION").read_text(encoding="utf-8").strip(),
        "json_version": str(metadata.get("version") or ""),
        "installer_version": match.group(1),
        "build_id": str(metadata.get("build_id") or ""),
    }


def validate_tree(root: pathlib.Path, expected_build_id: str) -> dict[str, str]:
    values = read_tree(root)
    versions = {values[key] for key in ("top_version", "payload_version", "json_version", "installer_version")}
    if len(versions) != 1:
        raise ValueError("RELEASE_METADATA_VERSION_MISMATCH " + json.dumps(values, sort_keys=True))
    if values["build_id"] != expected_build_id:
        raise ValueError(f"RELEASE_METADATA_BUILD_ID_MISMATCH expected={expected_build_id} actual={values['build_id']}")
    return values


def propagate(root: pathlib.Path, build_id: str) -> dict[str, str]:
    version = canonical_version(root)
    (root / "payload/VERSION").write_text(version + "\n", encoding="utf-8")
    json_path = root / "payload/version.json"
    metadata: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    metadata["version"] = version
    metadata["build_id"] = build_id
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    installer_path = root / "payload/install-openhtpc-fedora.sh"
    installer = installer_path.read_text(encoding="utf-8")
    updated, count = INSTALLER_PATTERN.subn(f'readonly OPENHTPC_VERSION="{version}"', installer)
    if count != 1:
        raise ValueError("RELEASE_METADATA_INSTALLER_VERSION_AMBIGUOUS")
    installer_path.write_text(updated, encoding="utf-8")
    return validate_tree(root, build_id)


def validate_installed_layout(install: pathlib.Path, expected_version: str, expected_build_id: str) -> None:
    version = (install / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((install / "version.json").read_text(encoding="utf-8"))
    if version != expected_version or metadata.get("version") != expected_version:
        raise ValueError("INSTALLED_RELEASE_VERSION_MISMATCH")
    if metadata.get("build_id") != expected_build_id:
        raise ValueError("INSTALLED_RELEASE_BUILD_ID_MISMATCH")


def validate_archive(archive: pathlib.Path, expected_build_id: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="openhtpc-metadata-") as raw:
        destination = pathlib.Path(raw)
        with tarfile.open(archive, "r:gz") as source:
            members = {member.name: member for member in source.getmembers() if member.isfile()}
            roots = {name.split("/", 1)[0] for name in members if "/" in name}
            if len(roots) != 1:
                raise ValueError("RELEASE_ARCHIVE_LAYOUT_INVALID")
            root_name = next(iter(roots)); extracted = destination / root_name
            for relative in ("VERSION", "payload/VERSION", "payload/version.json", "payload/install-openhtpc-fedora.sh"):
                member = members.get(f"{root_name}/{relative}")
                if member is None:
                    raise ValueError(f"RELEASE_ARCHIVE_METADATA_MISSING {relative}")
                stream = source.extractfile(member)
                if stream is None:
                    raise ValueError(f"RELEASE_ARCHIVE_METADATA_UNREADABLE {relative}")
                target = extracted / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.read())
        values = validate_tree(extracted, expected_build_id)
        validate_installed_layout(extracted / "payload", values["top_version"], expected_build_id)
        return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--propagate", action="store_true")
    parser.add_argument("--archive", type=pathlib.Path)
    args = parser.parse_args()
    values = propagate(args.root, args.build_id) if args.propagate else validate_tree(args.root, args.build_id)
    if args.archive:
        values = validate_archive(args.archive, args.build_id)
    print(json.dumps(values, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
