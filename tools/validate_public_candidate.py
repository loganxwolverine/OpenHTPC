#!/usr/bin/env python3
"""Deterministic validation for OPENHTPC Public Candidate R2.

Copyright 2026 OPENHTPC contributors
Licensed under the Apache License, Version 2.0.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"

EXPECTED_BENCHMARKS = {
    "c1_dvd_pal.mpg": "c21adee7eb3ffc147038cf1e3336c265b8faaf1fd67c3ea6de5d92b659f87e93",
    "c1_hd60.mp4": "a9c123c4c39108ec3dfa7c2ef5a819780f7ec99863736eb2d06191bce365ecc1",
    "c1_fhd24.mp4": "23d72798749662fabfd9b4b96817a2934bfe08e14091a2457f491f535e2224b5",
    "c1_fhd60.mp4": "67ebaafea177001c5e743b67a5ba8e97d95f1c5a3e32856125ec33b1aa104a57",
    "c1_uhd24_main10.mp4": "d69da63473850b14f9dfbd28c1b55ab1acd649455678347042f1689594e4914e",
}

REQUIRED_DOCS = (
    "LICENSE", "NOTICE", "README.md", "KNOWN_LIMITATIONS.md", "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md", "FLEX_FORK.md", "assets/ASSET_PROVENANCE.md",
    "third_party/licenses/OFL-1.1.txt", "third_party/licenses/NanoSVG-zlib.txt",
    "third_party/licenses/Flex-Launcher-UNLICENSE.txt",
    "third_party/licenses/LGPL-3.0.txt", "third_party/licenses/MIT.txt",
    "third_party/licenses/BSD-2-Clause.txt",
)

def digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

results: list[tuple[str, bool, str]] = []

def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, bool(condition), detail))

metadata = json.loads((PAYLOAD / "version.json").read_text())
check("candidate_version", metadata.get("version") == "1.1.0-dev31", str(metadata.get("version")))
check("candidate_build", metadata.get("build_id") == "public-release-optical-badge-polish-dev1", str(metadata.get("build_id")))
check("required_docs", all((ROOT / p).is_file() for p in REQUIRED_DOCS))
check("filmgrain_removed", not any(ROOT.rglob("filmgrain.glsl")))
check("benchmark_manifest", (PAYLOAD / "assets/benchmark/manifest.json").is_file())
for name, expected in EXPECTED_BENCHMARKS.items():
    path = PAYLOAD / "assets/benchmark" / name
    check(f"benchmark:{name}", path.is_file() and digest(path) == expected, expected)

ui = sorted((PAYLOAD / "assets/ui").glob("*.png"))
check("ui_asset_count", len(ui) == 26, str(len(ui)))
for path in ui:
    with Image.open(path) as image:
        check(f"ui_rgba:{path.name}", image.mode == "RGBA" and image.getpixel((0, 0))[3] == 0)

text_files = []
for path in ROOT.rglob("*"):
    if path.is_file() and path.suffix.lower() not in {".png", ".ttf", ".mpg", ".mp4"} and path.name != "MANIFEST.sha256":
        try:
            text_files.append((path, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            pass
combined = "\n".join(text for _, text in text_files)
private_home = "/" + "home" + "/" + "steve"
check("no_private_home", private_home not in combined)
check("no_private_ips", not re.search(r"192\.168\.1\.(?:10|132|229)\b", combined))
check("no_unreleased_later_dev", not re.search(r"1\.1\.0-dev(?:3[2-9]|[4-9][0-9])\b", combined, re.I))
check("no_secret_values", not re.search(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY|https?://[^\s/:]+:[^\s/@]+@", combined))

reference_text = "\n".join(text for path, text in text_files if path.name != "legacy-managed-files-dev27.txt")
references = set(re.findall(r"assets/ui/([A-Za-z0-9_.-]+\.png)", reference_text))
missing = sorted(name for name in references if not (PAYLOAD / "assets/ui" / name).is_file())
check("ui_references_resolve", not missing, ",".join(missing))
check("media_sources_runtime", all((PAYLOAD / name).is_file() for name in (
    "openhtpc-media-sources", "openhtpc-media-picker", "openhtpc-media-remove",
    "openhtpc-media-sources-action")))
session_text = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
check("home_media_label", "Entry3=MÉDIA;" in session_text and "MÉDIA · Films stockés localement" not in session_text)
check("power_asset_reference", "assets/ui/power.png" in session_text)
check("folder_asset_reference", "assets/ui/folder.png" in session_text)
check("managed_update_contract", (PAYLOAD / "managed-files.txt").is_file() and
      (PAYLOAD / "openhtpc-update-managed-files").is_file())
catalogue_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (
    PAYLOAD / "assets/shaders/catalog.json", PAYLOAD / "assets/c3_calibration_catalog.json"))
check("filmgrain_unreferenced", "filmgrain.glsl" not in catalogue_text)

flex_meta = json.loads((PAYLOAD / "flex/BUILD-METADATA.json").read_text())
flex_binary = PAYLOAD / "flex/bin/flex-launcher"
check("flex_binary", flex_binary.is_file() and digest(flex_binary) == flex_meta.get("binary_sha256"))
check("flex_revision", "94a7a273fe8124df51e63058816526b66bbc9538" in flex_meta.get("source_revision", ""))

passed = sum(ok for _, ok, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" [{detail}]" if detail else ""))
print(f"TOTAL {passed}/{len(results)} PASS")
raise SystemExit(0 if passed == len(results) else 1)
