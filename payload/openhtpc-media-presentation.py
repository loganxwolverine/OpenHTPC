#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""OpenHTPC Media Presentation Refresh Core (DEV6A2).

Orchestrates atomic fetch and persistence of normalized Work presentation
metadata from external providers (TMDb).

Core Rules:
- MOVIE ONLY: Operates on works with external_ids where provider = 'tmdb_movie'.
- Pure callable: refresh_work_presentation(db, work_id, locale, home, opener, now).
- Identity immutability: NEVER alters works, external_ids, media_versions, resources, or sources.
- Atomic persistence: provider_snapshots and work_presentations are written within an explicit transaction.
- Non-destructive failure: provider error or DB rollback leaves existing presentation intact.
- Zero artwork download: image assets are not fetched or saved to disk.
- Zero automatic execution: refresh is explicit-only; never triggered by scanner or playback.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
import urllib.request

_MEDIA_DB = None
_TMDB_PROVIDER = None


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
    return None


def set_media_db_module(mod: Any) -> None:
    """Dependency injection helper for hermetic testing."""
    global _MEDIA_DB
    _MEDIA_DB = mod


def _load_tmdb_provider() -> Any:
    global _TMDB_PROVIDER
    if _TMDB_PROVIDER is not None:
        return _TMDB_PROVIDER
    target = Path(__file__).resolve().parent / "openhtpc-media-provider-tmdb.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-provider-tmdb.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_provider_tmdb", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _TMDB_PROVIDER = mod
            return mod
    return None


def set_tmdb_provider_module(mod: Any) -> None:
    """Dependency injection helper for hermetic testing."""
    global _TMDB_PROVIDER
    _TMDB_PROVIDER = mod


def refresh_work_presentation(
    db: sqlite3.Connection,
    work_id: int | str,
    locale: str = "fr-FR",
    home: Path | None = None,
    opener: Any = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Refresh normalized presentation for a work from its TMDb movie identity.

    - Validates work_id exists in works.
    - Resolves external ID where provider = 'tmdb_movie'.
    - Rejects if 0 rows (PRESENTATION_NO_TMDB_ID) or >1 rows (PRESENTATION_AMBIGUOUS_TMDB_ID).
    - Fetches movie details via get_movie_details().
    - On provider failure, returns error dict without mutating database.
    - On provider success, persists provider_snapshots and work_presentations in single transaction.
    - Identity immutability: works, external_ids, media_versions, resources are NOT mutated.
    - Artwork policy: zero artwork download, retains poster_path and backdrop_path in returned dict.
    """
    if work_id is None or isinstance(work_id, bool):
        return {
            "ok": False,
            "error_code": "PRESENTATION_INVALID_WORK_ID",
            "error_detail": f"Invalid work_id: {work_id!r}",
        }
    try:
        wid = int(work_id)
        if wid <= 0:
            return {
                "ok": False,
                "error_code": "PRESENTATION_INVALID_WORK_ID",
                "error_detail": f"Invalid work_id: {work_id!r}",
            }
    except (ValueError, TypeError):
        return {
            "ok": False,
            "error_code": "PRESENTATION_INVALID_WORK_ID",
            "error_detail": f"Invalid work_id: {work_id!r}",
        }

    work_row = db.execute("SELECT id, title FROM works WHERE id = ?", (wid,)).fetchone()
    if work_row is None:
        return {
            "ok": False,
            "error_code": "PRESENTATION_WORK_NOT_FOUND",
            "error_detail": f"Work {wid} not found",
        }

    # Strict tmdb_movie lookup only - NO fallback, NO legacy provider names
    ext_rows = db.execute(
        "SELECT id, external_id FROM external_ids WHERE work_id = ? AND provider = 'tmdb_movie'",
        (wid,),
    ).fetchall()

    if len(ext_rows) == 0:
        return {
            "ok": False,
            "error_code": "PRESENTATION_NO_TMDB_ID",
            "error_detail": f"Work {wid} has no external_ids with provider='tmdb_movie'",
        }
    elif len(ext_rows) > 1:
        return {
            "ok": False,
            "error_code": "PRESENTATION_AMBIGUOUS_TMDB_ID",
            "error_detail": f"Work {wid} has multiple conflicting external_ids with provider='tmdb_movie' ({len(ext_rows)} found)",
        }

    ext_id_pk, tmdb_movie_id = ext_rows[0]

    tmdb_mod = _load_tmdb_provider()
    if tmdb_mod is None:
        return {
            "ok": False,
            "error_code": "TMDB_PROVIDER_MISSING",
            "error_detail": "openhtpc-media-provider-tmdb module could not be loaded",
        }

    media_db = _load_media_db()
    if media_db is None:
        return {
            "ok": False,
            "error_code": "MEDIA_DB_MISSING",
            "error_detail": "openhtpc-media-db module could not be loaded",
        }

    details_res = tmdb_mod.get_movie_details(
        tmdb_id=tmdb_movie_id,
        language=locale,
        home=home,
        opener=opener or urllib.request.urlopen,
    )

    if details_res.status != tmdb_mod.STATUS_OK or details_res.movie is None:
        return {
            "ok": False,
            "status": details_res.status,
            "error_code": details_res.error_code or details_res.status,
            "error_detail": details_res.error_detail,
            "http_status": details_res.http_status,
        }

    movie = details_res.movie
    fetched_at = now or datetime.now(timezone.utc).isoformat()

    in_tx = db.in_transaction
    sp_name = "openhtpc_presentation_refresh"

    if not in_tx:
        db.execute("BEGIN IMMEDIATE")
    else:
        db.execute(f"SAVEPOINT {sp_name}")

    try:
        snap_res = media_db.upsert_provider_snapshot(
            db,
            external_id_id=ext_id_pk,
            snapshot_kind="MOVIE_DETAILS",
            locale=locale,
            payload_json=movie.raw_payload,
            fetched_at=fetched_at,
        )
        if not snap_res.get("ok"):
            raise RuntimeError(f"Failed to upsert provider_snapshot: {snap_res.get('message') or snap_res.get('error')}")

        snapshot_id = snap_res["id"]

        pres_res = media_db.upsert_work_presentation(
            db,
            work_id=wid,
            locale=locale,
            display_title=movie.title,
            display_original_title=movie.original_title,
            release_date=movie.release_date,
            runtime_minutes=movie.runtime_minutes,
            overview=movie.overview,
            genres=movie.genres,
            source_snapshot_id=snapshot_id,
        )
        if not pres_res.get("ok"):
            raise RuntimeError(f"Failed to upsert work_presentation: {pres_res.get('message') or pres_res.get('error')}")

        presentation_id = pres_res["id"]

        if not in_tx:
            db.commit()
        else:
            db.execute(f"RELEASE SAVEPOINT {sp_name}")

    except Exception as exc:
        if not in_tx:
            db.rollback()
        else:
            try:
                db.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                db.execute(f"RELEASE SAVEPOINT {sp_name}")
            except Exception:
                pass
        return {
            "ok": False,
            "error_code": "PRESENTATION_PERSISTENCE_FAILED",
            "error_detail": f"Database transaction failed: {exc}",
        }

    return {
        "ok": True,
        "work_id": wid,
        "locale": locale,
        "snapshot_id": snapshot_id,
        "presentation_id": presentation_id,
        "display_title": movie.title,
        "display_original_title": movie.original_title,
        "release_date": movie.release_date,
        "runtime_minutes": movie.runtime_minutes,
        "overview": movie.overview,
        "genres": movie.genres,
        "poster_path": movie.poster_path,
        "backdrop_path": movie.backdrop_path,
        "is_update": pres_res.get("is_update", False),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenHTPC Media Presentation Refresh (DEV6A2)")
    subparsers = parser.add_subparsers(dest="action", required=True)

    refresh_p = subparsers.add_parser("refresh", help="Refresh work presentation from provider")
    refresh_p.add_argument("--work-id", type=int, required=True, help="Work ID in media.db")
    refresh_p.add_argument("--locale", default="fr-FR", help="Locale / language (default: fr-FR)")
    refresh_p.add_argument("--db", type=Path, default=None, help="Path to media.db")
    refresh_p.add_argument("--home", type=Path, default=None, help="OpenHTPC user home directory")

    args = parser.parse_args(argv)

    if args.action == "refresh":
        media_db = _load_media_db()
        if media_db is None:
            print(json.dumps({"ok": False, "error_code": "MEDIA_DB_MISSING", "error_detail": "openhtpc-media-db component not found"}, indent=2))
            return 1

        db_path = args.db or media_db.database_path(home=args.home)
        if not db_path.is_file():
            print(json.dumps({"ok": False, "error_code": "DB_NOT_FOUND", "error_detail": f"Database file not found: {db_path}"}, indent=2))
            return 1

        with closing(media_db.connect(db_path)) as db:
            res = refresh_work_presentation(
                db=db,
                work_id=args.work_id,
                locale=args.locale,
                home=args.home,
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
