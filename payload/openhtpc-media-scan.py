#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Incremental Source Scanner for OpenHTPC Media Foundation (DEV4).

Scans ONE configured local media source per invocation.
Implements a mandatory two-phase scan:
  Phase A: Complete candidate file enumeration without DB mutation.
  Phase B: Set-theoretic classification (NEW, CHANGED, UNCHANGED, RESTORED, MISSING).

Reuses DEV2 normalized media probe and DEV3 descriptor ingestion.
Does NOT infer titles, query TMDb, manage playback, or run on system startup.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Callable

_MEDIA_TYPES = None
_MEDIA_PROBE = None
_MEDIA_INGEST = None
_MEDIA_DB = None


def _load_media_types() -> Any:
    global _MEDIA_TYPES
    if _MEDIA_TYPES is not None:
        return _MEDIA_TYPES
    target = Path(__file__).resolve().parent / "openhtpc-media-types.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-types.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_types", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MEDIA_TYPES = mod
            return mod
    return None


def _load_media_probe() -> Any:
    global _MEDIA_PROBE
    if _MEDIA_PROBE is not None:
        return _MEDIA_PROBE
    target = Path(__file__).resolve().parent / "openhtpc-media-probe.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-probe.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_probe", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MEDIA_PROBE = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-probe component")


def _load_media_ingest() -> Any:
    global _MEDIA_INGEST
    if _MEDIA_INGEST is not None:
        return _MEDIA_INGEST
    target = Path(__file__).resolve().parent / "openhtpc-media-ingest.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-ingest.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_ingest", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MEDIA_INGEST = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-ingest component")


def _load_media_db() -> Any:
    global _MEDIA_DB
    if _MEDIA_DB is not None:
        return _MEDIA_DB
    target = Path(__file__).resolve().parent / "openhtpc-media-db.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-db.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_db", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MEDIA_DB = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-db component")


def compute_source_id(source_root: Path | str) -> str:
    """Compute canonical 16-hex OPENHTPC source_id from source root directory."""
    path = Path(source_root).resolve()
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


def load_user_config(home: Path | None = None, environ: Any = None) -> dict[str, Any]:
    """Load user configuration from authoritative path."""
    env = os.environ if environ is None else environ
    xdg_config = env.get("XDG_CONFIG_HOME")
    if home is not None:
        config_path = Path(home) / ".config/openhtpc/user-config.json"
    elif xdg_config and Path(xdg_config).is_absolute():
        config_path = Path(xdg_config) / "openhtpc/user-config.json"
    else:
        config_path = Path.home() / ".config/openhtpc/user-config.json"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": 1, "local_media_sources": []}


def get_configured_sources(home: Path | None = None, environ: Any = None) -> list[dict[str, Any]]:
    """Enumerate configured sources with their canonical paths and derived source IDs."""
    config = load_user_config(home, environ=environ)
    raw_sources = config.get("local_media_sources", [])
    if not isinstance(raw_sources, list):
        return []

    sources = []
    for raw in raw_sources:
        if not isinstance(raw, str) or not raw.strip():
            continue
        p = Path(raw)
        try:
            canonical = p.resolve(strict=True)
            exists = canonical.is_dir()
        except OSError:
            canonical = p.resolve()
            exists = False
        sid = compute_source_id(canonical)
        sources.append({
            "configured_path": raw,
            "canonical_path": canonical,
            "source_id": sid,
            "exists": exists,
        })
    return sources


def detect_overlapping_sources(sources: list[dict[str, Any]]) -> list[str]:
    """Detect if any configured sources are nested or overlap."""
    warnings = []
    for i, s1 in enumerate(sources):
        p1 = s1["canonical_path"]
        for j, s2 in enumerate(sources):
            if i >= j:
                continue
            p2 = s2["canonical_path"]
            if p1 == p2:
                warnings.append(f"DUPLICATE_SOURCE_CONFIGURED: {p1}")
            elif p1 in p2.parents or p2 in p1.parents:
                warnings.append(f"OVERLAPPING_SOURCE_DETECTED: {p1} and {p2}")
    return warnings


class SourceLock:
    """Exclusive non-blocking file lock per source_id."""

    def __init__(self, source_id: str, *, home: Path | None = None, environ: Any = None) -> None:
        self.source_id = source_id
        env = os.environ if environ is None else environ
        xdg_state = env.get("XDG_STATE_HOME")
        if home is not None:
            base = Path(home) / ".local/state"
        elif xdg_state and Path(xdg_state).is_absolute():
            base = Path(xdg_state)
        else:
            base = Path.home() / ".local/state"
        self.lock_dir = base / "openhtpc/media"
        self.lock_path = self.lock_dir / f"scan-{source_id}.lock"
        self._fd: int | None = None

    def __enter__(self) -> SourceLock:
        self.lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            raise BlockingIOError(f"SCANNER_ALREADY_RUNNING: Scan lock active for source {self.source_id}") from exc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


class CandidateFile:
    __slots__ = ("relative_path", "absolute_path", "file_size", "mtime_ns")

    def __init__(self, relative_path: str, absolute_path: Path, file_size: int, mtime_ns: int) -> None:
        self.relative_path = relative_path
        self.absolute_path = absolute_path
        self.file_size = file_size
        self.mtime_ns = mtime_ns


def is_supported_media_extension(name: str) -> bool:
    """Case-insensitive check against authoritative VIDEO_EXTENSIONS."""
    mt = _load_media_types()
    if mt is not None and hasattr(mt, "is_candidate_media_file"):
        return mt.is_candidate_media_file(name)
    # Fallback to standard set
    ext = os.path.splitext(name)[1].casefold()
    return ext in {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}


def enumerate_source_candidates(source_root: Path) -> tuple[dict[str, CandidateFile], str | None]:
    """Phase A: Completely enumerate candidate media files within source root.

    Symlink policy:
      - Directory symlinks are NEVER followed.
      - Media file symlinks are permitted only if their resolved target lies within source_root.
      - Hidden files (starting with '.') are ignored.

    Returns (candidates_dict, error_string_or_none).
    """
    candidates: dict[str, CandidateFile] = {}
    root_resolved = source_root.resolve()

    def _walk(current_dir: Path) -> str | None:
        try:
            with os.scandir(current_dir) as scanner:
                entries = sorted(list(scanner), key=lambda it: it.name.casefold())
        except OSError as exc:
            return f"TRAVERSAL_ERROR: {current_dir}: {exc}"

        for entry in entries:
            # Skip hidden files and directories
            if entry.name.startswith("."):
                continue

            try:
                # 1. Directory handling (never follow directory symlinks)
                if entry.is_dir(follow_symlinks=False):
                    err = _walk(Path(entry.path))
                    if err:
                        return err
                    continue

                # 2. File handling
                if entry.is_file(follow_symlinks=False):
                    if is_supported_media_extension(entry.name):
                        st = entry.stat(follow_symlinks=False)
                        entry_path = Path(entry.path)
                        rel = entry_path.relative_to(root_resolved).as_posix()
                        candidates[rel] = CandidateFile(
                            relative_path=rel,
                            absolute_path=entry_path,
                            file_size=st.st_size,
                            mtime_ns=st.st_mtime_ns,
                        )
                    continue

                # 3. Symlink handling
                if entry.is_symlink():
                    try:
                        resolved_target = Path(entry.path).resolve(strict=True)
                    except OSError:
                        # Broken symlink, ignore safely
                        continue

                    # Directory symlinks are strictly rejected
                    if resolved_target.is_dir():
                        continue

                    # File symlink: verify target is within source root
                    if resolved_target.is_file():
                        try:
                            resolved_target.relative_to(root_resolved)
                            target_inside = True
                        except ValueError:
                            target_inside = False

                        if target_inside and is_supported_media_extension(entry.name):
                            st = resolved_target.stat()
                            entry_path = Path(entry.path)
                            rel = entry_path.relative_to(root_resolved).as_posix()
                            candidates[rel] = CandidateFile(
                                relative_path=rel,
                                absolute_path=entry_path,
                                file_size=st.st_size,
                                mtime_ns=st.st_mtime_ns,
                            )
                        # Symlinks resolving outside source root are ignored safely
            except OSError:
                # File-level stat errors ignore entry without failing directory
                continue

        return None

    error = _walk(root_resolved)
    return candidates, error


def scan_source(
    source_id: str | None = None,
    source_root: str | Path | None = None,
    db_path: str | Path | None = None,
    home: str | Path | None = None,
    probe_func: Callable[..., dict[str, Any]] | None = None,
    ffprobe_bin: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Execute complete incremental source scan for exactly one configured source.

    Returns structured ScanResult dictionary.
    """
    start_time = time.monotonic()
    home_path = Path(home).resolve() if home is not None else None
    
    # 1. Resolve source from authoritative configuration
    all_sources = get_configured_sources(home_path)
    warnings = detect_overlapping_sources(all_sources)

    target_source: dict[str, Any] | None = None
    if source_id:
        target_source = next((s for s in all_sources if s["source_id"] == source_id), None)
        if not target_source:
            return {
                "ok": False,
                "error": "SOURCE_NOT_CONFIGURED",
                "message": f"Source id '{source_id}' is not configured in user-config.json",
                "outcome": "SOURCE_UNAVAILABLE",
            }
    elif source_root:
        try:
            req_root = Path(source_root).resolve(strict=False)
        except OSError:
            req_root = Path(source_root)
        target_source = next((s for s in all_sources if s["canonical_path"] == req_root or Path(s["configured_path"]).resolve() == req_root), None)
        if not target_source:
            return {
                "ok": False,
                "error": "SOURCE_NOT_CONFIGURED",
                "message": f"Source root '{source_root}' is not configured in user-config.json",
                "outcome": "SOURCE_UNAVAILABLE",
            }
    else:
        return {
            "ok": False,
            "error": "MISSING_SOURCE_ARGUMENT",
            "message": "Either source_id or source_root must be specified",
            "outcome": "SOURCE_UNAVAILABLE",
        }

    sid = target_source["source_id"]
    s_root = target_source["canonical_path"]

    # 2. Acquire concurrency lock
    try:
        lock = SourceLock(sid, home=home_path)
    except Exception as exc:
        return {
            "ok": False,
            "error": "LOCK_INITIALIZATION_FAILED",
            "message": str(exc),
            "outcome": "SOURCE_UNAVAILABLE",
        }

    try:
        with lock:
            # 3. Source Availability Check
            try:
                if not s_root.exists() or not s_root.is_dir():
                    return {
                        "ok": False,
                        "source_id": sid,
                        "source_root": str(s_root),
                        "outcome": "SOURCE_UNAVAILABLE",
                        "message": f"Source root does not exist or is not a directory: {s_root}",
                        "enumerated": 0,
                        "new": 0,
                        "changed": 0,
                        "unchanged": 0,
                        "restored": 0,
                        "missing": 0,
                        "failed": 0,
                        "probe_calls": 0,
                    }
                # Check root directory accessibility
                with os.scandir(s_root):
                    pass
            except OSError as exc:
                return {
                    "ok": False,
                    "source_id": sid,
                    "source_root": str(s_root),
                    "outcome": "SOURCE_UNAVAILABLE",
                    "message": f"Source root I/O error: {exc}",
                    "enumerated": 0,
                    "new": 0,
                    "changed": 0,
                    "unchanged": 0,
                    "restored": 0,
                    "missing": 0,
                    "failed": 0,
                    "probe_calls": 0,
                }

            # 4. Phase A: Total Candidate Enumeration
            candidates, traversal_error = enumerate_source_candidates(s_root)
            if traversal_error:
                return {
                    "ok": False,
                    "source_id": sid,
                    "source_root": str(s_root),
                    "outcome": "PARTIAL_ERROR",
                    "message": traversal_error,
                    "enumerated": len(candidates),
                    "new": 0,
                    "changed": 0,
                    "unchanged": 0,
                    "restored": 0,
                    "missing": 0,
                    "failed": 0,
                    "probe_calls": 0,
                }

            # 5. Connect to Media DB
            media_db = _load_media_db()
            media_ingest = _load_media_ingest()
            target_db_path = Path(db_path) if db_path is not None else media_db.database_path(home=home_path)

            if not target_db_path.is_file():
                media_db.initialize(target_db_path)

            # Query known DB resources for this source
            db_records: dict[str, dict[str, Any]] = {}
            with closing(media_db.connect(target_db_path)) as db:
                rows = db.execute(
                    """
                    SELECT id, media_version_id, relative_path, file_size, mtime_ns, availability_status
                    FROM resources
                    WHERE resource_kind = 'FILE' AND source_id = ?
                    """,
                    (sid,),
                ).fetchall()
                for row in rows:
                    db_records[row[2]] = {
                        "id": row[0],
                        "media_version_id": row[1],
                        "relative_path": row[2],
                        "file_size": row[3],
                        "mtime_ns": row[4],
                        "availability_status": row[5],
                    }

            # 6. Strict Suspicious Empty Guard
            if len(db_records) > 0 and len(candidates) == 0:
                return {
                    "ok": False,
                    "source_id": sid,
                    "source_root": str(s_root),
                    "outcome": "SUSPICIOUS_EMPTY",
                    "message": "Source returned 0 eligible media files but database contains existing records. Refusing to mark records MISSING.",
                    "enumerated": 0,
                    "new": 0,
                    "changed": 0,
                    "unchanged": 0,
                    "restored": 0,
                    "missing": 0,
                    "failed": 0,
                    "probe_calls": 0,
                    "warnings": warnings,
                    "elapsed_seconds": round(time.monotonic() - start_time, 3),
                }

            # 7. Phase B: Set-Theoretic Classification & Dispatch
            enumerated_paths = set(candidates.keys())
            db_paths = set(db_records.keys())

            new_paths = enumerated_paths - db_paths
            existing_paths = enumerated_paths & db_paths
            absent_paths = db_paths - enumerated_paths

            count_new = 0
            count_changed = 0
            count_unchanged = 0
            count_restored = 0
            count_missing = 0
            count_failed = 0
            probe_calls = 0

            now_iso = datetime.now(timezone.utc).isoformat()

            # Process Existing Files (Unchanged or Changed)
            for rel in sorted(existing_paths):
                cand = candidates[rel]
                rec = db_records[rel]
                fingerprint_matched = (cand.file_size == rec["file_size"] and cand.mtime_ns == rec["mtime_ns"])

                if fingerprint_matched:
                    # Fingerprint unchanged: DO NOT probe, DO NOT rewrite stream facts
                    if rec["availability_status"] == "AVAILABLE":
                        count_unchanged += 1
                    else:
                        # Restored with same fingerprint
                        with closing(media_db.connect(target_db_path)) as db:
                            with db:
                                db.execute(
                                    "UPDATE resources SET availability_status = 'AVAILABLE', last_seen_at = ? WHERE id = ?",
                                    (now_iso, rec["id"]),
                                )
                        count_restored += 1
                else:
                    # Fingerprint changed: size or mtime differs -> trigger DEV3 ingestion
                    probe_calls += 1
                    ingest_result = media_ingest.ingest_file(
                        file_path=cand.absolute_path,
                        source_root=s_root,
                        db_path=target_db_path,
                        ffprobe_bin=ffprobe_bin,
                        timeout=timeout,
                        probe_func=probe_func,
                    )

                    if ingest_result.get("ok"):
                        if rec["availability_status"] in ("MISSING", "UNKNOWN"):
                            count_restored += 1
                        else:
                            count_changed += 1
                    else:
                        # Re-probe/ingest failed: preserve old technical truth, but mark presence AVAILABLE
                        count_failed += 1
                        with closing(media_db.connect(target_db_path)) as db:
                            with db:
                                db.execute(
                                    "UPDATE resources SET availability_status = 'AVAILABLE', last_seen_at = ? WHERE id = ?",
                                    (now_iso, rec["id"]),
                                )

            # Process New Files
            for rel in sorted(new_paths):
                cand = candidates[rel]
                probe_calls += 1
                ingest_result = media_ingest.ingest_file(
                    file_path=cand.absolute_path,
                    source_root=s_root,
                    db_path=target_db_path,
                    ffprobe_bin=ffprobe_bin,
                    timeout=timeout,
                    probe_func=probe_func,
                )

                if ingest_result.get("ok"):
                    count_new += 1
                else:
                    # New file failed probe: no incomplete DB rows created
                    count_failed += 1

            # Process Absent Files (Mark MISSING, never delete)
            for rel in sorted(absent_paths):
                rec = db_records[rel]
                if rec["availability_status"] != "MISSING":
                    with closing(media_db.connect(target_db_path)) as db:
                        with db:
                            db.execute(
                                "UPDATE resources SET availability_status = 'MISSING' WHERE id = ?",
                                (rec["id"],),
                            )
                    count_missing += 1

            outcome = "PARTIAL" if count_failed > 0 else "COMPLETE"
            elapsed = time.monotonic() - start_time

            return {
                "ok": True,
                "source_id": sid,
                "source_root": str(s_root),
                "outcome": outcome,
                "enumerated": len(candidates),
                "new": count_new,
                "changed": count_changed,
                "unchanged": count_unchanged,
                "restored": count_restored,
                "missing": count_missing,
                "failed": count_failed,
                "probe_calls": probe_calls,
                "warnings": warnings,
                "elapsed_seconds": round(elapsed, 3),
            }

    except BlockingIOError as exc:
        return {
            "ok": False,
            "error": "SCANNER_ALREADY_RUNNING",
            "source_id": sid,
            "message": str(exc),
            "outcome": "SOURCE_UNAVAILABLE",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenHTPC Media Foundation Incremental Source Scanner (DEV4)")
    parser.add_argument("--home", type=Path, default=None, help="User home directory for config/state")
    parser.add_argument("--db", type=Path, default=None, help="Explicit media.db database path")
    
    subparsers = parser.add_subparsers(dest="action", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan one configured media source")
    src_group = scan_parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--source-id", dest="source_id", help="Canonical source identifier to scan")
    src_group.add_argument("--source-root", dest="source_root", help="Configured source root directory path")
    scan_parser.add_argument("--json", action="store_true", help="Output JSON format (default: JSON)")

    list_parser = subparsers.add_parser("list-sources", help="List configured media sources and their IDs")
    list_parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args(argv)

    home = args.home if args.home else Path(os.environ.get("OPENHTPC_HOME", Path.home())).resolve()

    if args.action == "list-sources":
        sources = get_configured_sources(home)
        out = [
            {
                "source_id": s["source_id"],
                "configured_path": s["configured_path"],
                "canonical_path": str(s["canonical_path"]),
                "exists": s["exists"],
            }
            for s in sources
        ]
        print(json.dumps(out, indent=2))
        return 0

    if args.action == "scan":
        result = scan_source(
            source_id=args.source_id,
            source_root=args.source_root,
            db_path=args.db,
            home=home,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") and result.get("outcome") in ("COMPLETE", "PARTIAL") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
