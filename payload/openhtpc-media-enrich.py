#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""OpenHTPC Media Batch Enrichment Orchestrator (DEV6C1 / DEV6C1B).

Explicit-only batch metadata enrichment for Media Foundation.
Reuses existing qualified primitives without duplicating algorithms:
  - Filename clue extraction (openhtpc-media-match.py)
  - TMDb movie candidate search (openhtpc-media-provider-tmdb.py)
  - Candidate scoring & conservative auto-acceptance (openhtpc-media-match.py)
  - Work creation / external_ids linkage (openhtpc-media-match.py)
  - Work presentation refresh (openhtpc-media-presentation.py)
  - Poster caching (openhtpc-media-artwork.py)

Safety Invariants:
  - Source scoping is mandatory (--source-id or --source-root).
  - --plan is strict dry-run: read-only DB (mode=ro), 0 DB writes, 0 network, 0 cache writes.
  - USER_MATCHED and match_locked=1 identities are strictly immutable; never rematched.
  - Incremental retry policy (DEV6C1B): items with persisted candidates are preserved without repeated queries unless --refresh-candidates is explicitly requested.
  - Title without year: AUTO_ACCEPT is FORBIDDEN; candidate suggestions may be persisted.
  - Technical streams (video_streams, audio_streams, subtitle_streams), resources, and schema_info are never mutated.
  - ISO resources (resource_kind = 'ISO') are ignored (DEV6C_ISO_BEHAVIOR = IGNORE_OUT_OF_SCOPE).
  - Missing resources (availability_status = 'MISSING') are skipped without provider queries.
  - Resumable: transactions committed per item; failure is item-local.
  - Sequential execution only: no async, no threads.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any
import urllib.request

_MEDIA_DB = None
_TMDB_PROVIDER = None
_MEDIA_MATCH = None
_PRESENTATION = None
_ARTWORK = None


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


def set_media_db_module(mod: Any) -> None:
    """Dependency injection helper for testing."""
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
    raise RuntimeError("Cannot load openhtpc-media-provider-tmdb component")


def set_tmdb_provider_module(mod: Any) -> None:
    """Dependency injection helper for testing."""
    global _TMDB_PROVIDER
    _TMDB_PROVIDER = mod


def _load_media_match() -> Any:
    global _MEDIA_MATCH
    if _MEDIA_MATCH is not None:
        return _MEDIA_MATCH
    target = Path(__file__).resolve().parent / "openhtpc-media-match.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-match.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_match", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MEDIA_MATCH = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-match component")


def set_media_match_module(mod: Any) -> None:
    """Dependency injection helper for testing."""
    global _MEDIA_MATCH
    _MEDIA_MATCH = mod


def _load_presentation() -> Any:
    global _PRESENTATION
    if _PRESENTATION is not None:
        return _PRESENTATION
    target = Path(__file__).resolve().parent / "openhtpc-media-presentation.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-presentation.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_presentation", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _PRESENTATION = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-presentation component")


def set_presentation_module(mod: Any) -> None:
    """Dependency injection helper for testing."""
    global _PRESENTATION
    _PRESENTATION = mod


def _load_artwork() -> Any:
    global _ARTWORK
    if _ARTWORK is not None:
        return _ARTWORK
    target = Path(__file__).resolve().parent / "openhtpc-media-artwork.py"
    if not target.is_file():
        target = Path.home() / ".local/lib/openhtpc/openhtpc-media-artwork.py"
    if target.is_file():
        spec = importlib.util.spec_from_file_location("openhtpc_media_artwork", target)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _ARTWORK = mod
            return mod
    raise RuntimeError("Cannot load openhtpc-media-artwork component")


def set_artwork_module(mod: Any) -> None:
    """Dependency injection helper for testing."""
    global _ARTWORK
    _ARTWORK = mod


def compute_source_id(source_root: Path | str) -> str:
    """Compute canonical 16-hex OPENHTPC source_id from source root directory."""
    path = Path(source_root).resolve()
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


def connect_db(
    db_path: Path | str | None = None,
    *,
    read_only: bool = False,
    home: Path | None = None,
) -> sqlite3.Connection:
    """Open SQLite database connection obeying read-only/read-write contract."""
    media_db = _load_media_db()
    resolved = Path(db_path) if db_path is not None else media_db.database_path(home=home)
    if not resolved.is_file():
        raise FileNotFoundError(f"Database file not found: {resolved}")
    if resolved.is_symlink() or resolved.parent.is_symlink():
        raise ValueError("Database directory/file must not be a symlink")

    if read_only:
        db = sqlite3.connect(resolved.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA busy_timeout = 5000")
        db.execute("PRAGMA foreign_keys = ON")
        return db
    else:
        return media_db.connect(resolved)


def get_source_items(
    db: sqlite3.Connection,
    source_id: str,
    *,
    media_version_ids: list[int] | None = None,
    limit: int | None = None,
) -> tuple[bool, str | None, list[dict[str, Any]], dict[str, int]]:
    """Select source-scoped items using Schema 3 foreign keys.

    Enforces:
      - Mandatory source scoping: only resources with resource_kind='FILE', source_id=?
      - Availability: availability_status='AVAILABLE'
      - ISO items (resource_kind='ISO') are completely excluded.
      - Explicit media_version_ids must belong to source_id; cross-source rejects.
      - Deterministic ordering: media_version_id ASC.
      - Limit applies strictly to selected media_version items.
    """
    # 1. Inspect all file media_versions for this source
    rows = db.execute(
        """
        SELECT mv.id AS media_version_id,
               mv.work_id,
               mv.identification_state,
               mv.match_confidence,
               mv.match_method,
               mv.match_locked,
               mv.duration_seconds,
               r.id AS resource_id,
               r.relative_path,
               r.canonical_path,
               r.availability_status
        FROM media_versions mv
        JOIN resources r ON r.media_version_id = mv.id
        WHERE r.source_id = ?
          AND r.resource_kind = 'FILE'
        ORDER BY mv.id ASC, (CASE WHEN r.availability_status = 'AVAILABLE' THEN 0 ELSE 1 END) ASC
        """,
        (source_id,),
    ).fetchall()

    # Deduplicate by media_version_id while preserving ascending order
    all_source_items: list[dict[str, Any]] = []
    seen_mv_ids: set[int] = set()
    for row in rows:
        mv_id = row[0]
        if mv_id in seen_mv_ids:
            continue
        seen_mv_ids.add(mv_id)
        all_source_items.append({
            "media_version_id": mv_id,
            "work_id": row[1],
            "identification_state": row[2],
            "match_confidence": row[3],
            "match_method": row[4],
            "match_locked": int(row[5]) if row[5] is not None else 0,
            "duration_seconds": row[6],
            "resource_id": row[7],
            "relative_path": row[8],
            "canonical_path": row[9],
            "availability_status": row[10],
        })

    # Summary counts for the entire source
    source_stats = {
        "total_media": len(all_source_items),
        "available_media": sum(1 for item in all_source_items if item["availability_status"] == "AVAILABLE"),
        "missing_media": sum(1 for item in all_source_items if item["availability_status"] == "MISSING"),
        "unmatched": sum(1 for item in all_source_items if item["identification_state"] == "UNMATCHED" and item["availability_status"] == "AVAILABLE"),
        "already_identified": sum(1 for item in all_source_items if item["identification_state"] in ("AUTO_MATCHED", "USER_MATCHED")),
        "user_matched": sum(1 for item in all_source_items if item["identification_state"] == "USER_MATCHED"),
        "auto_matched": sum(1 for item in all_source_items if item["identification_state"] == "AUTO_MATCHED"),
    }

    # 2. Validate explicit media_version_ids if supplied
    if media_version_ids is not None and len(media_version_ids) > 0:
        requested_set = set(media_version_ids)
        for req_id in requested_set:
            if req_id not in seen_mv_ids:
                return (
                    False,
                    f"CROSS_SOURCE_REJECTION: media_version_id {req_id} does not belong to source {source_id}",
                    [],
                    source_stats,
                )
        selected_items = [item for item in all_source_items if item["media_version_id"] in requested_set]
    else:
        selected_items = list(all_source_items)

    # 3. Apply limit deterministically
    if limit is not None and limit > 0:
        selected_items = selected_items[:limit]

    return True, None, selected_items, source_stats


def plan_source(
    db: sqlite3.Connection,
    source_id: str,
    *,
    media_version_ids: list[int] | None = None,
    limit: int | None = None,
    refresh_candidates: bool = False,
    locale: str = "fr-FR",
    home: Path | None = None,
) -> dict[str, Any]:
    """Execute hard read-only dry-run plan.

    0 DB writes, 0 provider network calls, 0 artwork downloads/writes.
    Deterministic ordering by media_version_id ASC.
    """
    media_match = _load_media_match()
    artwork_mod = _load_artwork()

    ok, err_msg, items, stats = get_source_items(
        db,
        source_id,
        media_version_ids=media_version_ids,
        limit=limit,
    )
    if not ok:
        return {
            "ok": False,
            "outcome": "REJECTED",
            "source_id": source_id,
            "error": "CROSS_SOURCE_MEDIA_VERSION_ID",
            "message": err_msg,
        }

    title_and_year = 0
    title_without_year = 0
    parse_failure = 0

    plan_items: list[dict[str, Any]] = []

    for item in items:
        rel_path = item["relative_path"]
        clues = media_match.extract_movie_clues(rel_path)
        clean_title = clues.title_clue
        extracted_year = clues.year_clue
        proj_query = media_match.create_provider_query(clues)

        avail_status = item.get("availability_status", "AVAILABLE")
        ident_state = item["identification_state"]
        is_locked = item["match_locked"] == 1

        if avail_status != "AVAILABLE":
            search_eligibility = "MISSING_SKIPPED"
            eligibility_reason = "RESOURCE_MISSING"
        elif is_locked:
            search_eligibility = "ALREADY_IDENTIFIED"
            eligibility_reason = "IDENTITY_LOCKED"
        elif ident_state == "USER_MATCHED":
            search_eligibility = "ALREADY_IDENTIFIED"
            eligibility_reason = "ALREADY_USER_MATCHED"
        elif ident_state == "AUTO_MATCHED":
            search_eligibility = "ALREADY_IDENTIFIED"
            eligibility_reason = "ALREADY_AUTO_MATCHED"
        elif not clean_title:
            parse_failure += 1
            search_eligibility = "PARSE_FAILURE"
            eligibility_reason = "PARSE_FAILURE"
        else:
            media_db = _load_media_db()
            current_sig = media_db.compute_query_signature(
                provider="tmdb_movie",
                media_type="movie",
                locale=locale,
                title=clean_title,
                year=extracted_year,
            )
            search_state = media_db.get_media_version_search(
                db, item["media_version_id"], provider="tmdb_movie"
            )

            if refresh_candidates:
                search_eligibility = "REFRESH_REQUESTED"
                eligibility_reason = "REFRESH_REQUESTED"
            elif search_state is None:
                search_eligibility = "NEVER_SEARCHED"
                if extracted_year is None:
                    title_without_year += 1
                    eligibility_reason = "NO_YEAR_CLUE_CONSERVATIVE_GATE"
                else:
                    title_and_year += 1
                    eligibility_reason = "ELIGIBLE_FOR_AUTO_MATCH"
            elif search_state["query_signature"] != current_sig:
                search_eligibility = "QUERY_CHANGED"
                eligibility_reason = "QUERY_CHANGED"
            elif search_state["search_status"] == "CANDIDATES":
                search_eligibility = "CANDIDATES_CURRENT"
                eligibility_reason = "CANDIDATES_ALREADY_PERSISTED"
            elif search_state["search_status"] == "NO_RESULT":
                search_eligibility = "NO_RESULT_CURRENT"
                eligibility_reason = "NO_RESULTS_PERSISTED"
            elif search_state["search_status"] == "FAILED":
                search_eligibility = "FAILED_RETRY"
                eligibility_reason = "FAILED_RETRY"
            else:
                search_eligibility = "NEVER_SEARCHED"
                eligibility_reason = "NEVER_SEARCHED"

        plan_items.append({
            "media_version_id": item["media_version_id"],
            "relative_path": rel_path,
            "clean_title": clean_title,
            "extracted_year": extracted_year,
            "projected_query": proj_query,
            "eligibility_reason": eligibility_reason,
            "search_eligibility": search_eligibility,
            "identification_state": ident_state,
            "work_id": item["work_id"],
        })

    return {
        "ok": True,
        "outcome": "PLAN_READY",
        "source_id": source_id,
        "mode": "PLAN",
        "total_media": stats["total_media"],
        "unmatched": stats["unmatched"],
        "already_identified": stats["already_identified"],
        "user_matched": stats["user_matched"],
        "auto_matched": stats["auto_matched"],
        "title_and_year": title_and_year,
        "title_without_year": title_without_year,
        "parse_failure": parse_failure,
        "considered": len(plan_items),
        "searched": 0,
        "auto_matched_new": 0,
        "unresolved": stats["unmatched"],
        "no_result": 0,
        "provider_failed": 0,
        "presentation_refreshed": 0,
        "presentation_failed": 0,
        "posters_cached": 0,
        "posters_cache_hit": 0,
        "posters_missing": 0,
        "poster_failed": 0,
        "already_complete": 0,
        "refresh_candidates": refresh_candidates,
        "never_searched": sum(1 for it in plan_items if it["search_eligibility"] == "NEVER_SEARCHED"),
        "candidates_current": sum(1 for it in plan_items if it["search_eligibility"] == "CANDIDATES_CURRENT"),
        "candidates_present": sum(1 for it in plan_items if it["search_eligibility"] in ("CANDIDATES_PRESENT", "CANDIDATES_CURRENT")),
        "no_result_current": sum(1 for it in plan_items if it["search_eligibility"] == "NO_RESULT_CURRENT"),
        "failed_retry": sum(1 for it in plan_items if it["search_eligibility"] == "FAILED_RETRY"),
        "query_changed": sum(1 for it in plan_items if it["search_eligibility"] == "QUERY_CHANGED"),
        "refresh_requested": sum(1 for it in plan_items if it["search_eligibility"] == "REFRESH_REQUESTED"),
        "missing_skipped": sum(1 for it in plan_items if it["search_eligibility"] == "MISSING_SKIPPED"),
        "items": plan_items,
    }


def enrich_source(
    db: sqlite3.Connection,
    source_id: str,
    *,
    media_version_ids: list[int] | None = None,
    limit: int | None = None,
    refresh_candidates: bool = False,
    locale: str = "fr-FR",
    home: Path | None = None,
    opener: Any = None,
    rate_limit_sleep: float = 0.0,
) -> dict[str, Any]:
    """Execute sequential batch enrichment phases.

    Phase 1: select source-scoped items
    Phase 2: clue extraction, provider search, score, bounded candidate persistence
    Phase 3: auto-match eligibility & transactional acceptance
    Phase 4: ensure fr-FR presentation if missing
    Phase 5: ensure local poster cache
    Phase 6: emit structured report
    """
    media_match = _load_media_match()
    tmdb_provider = _load_tmdb_provider()
    media_pres = _load_presentation()
    artwork_mod = _load_artwork()

    ok, err_msg, items, stats = get_source_items(
        db,
        source_id,
        media_version_ids=media_version_ids,
        limit=limit,
    )
    if not ok:
        return {
            "ok": False,
            "outcome": "REJECTED",
            "source_id": source_id,
            "error": "CROSS_SOURCE_MEDIA_VERSION_ID",
            "message": err_msg,
        }

    outcome = "COMPLETE"
    considered = len(items)
    searched = 0
    auto_matched_count = 0
    unresolved = 0
    no_result = 0
    provider_failed = 0
    presentation_refreshed = 0
    presentation_failed = 0
    posters_cached = 0
    posters_cache_hit = 0
    posters_missing = 0
    poster_failed = 0
    already_complete = 0

    item_reports: list[dict[str, Any]] = []

    for item in items:
        item_id = item["media_version_id"]
        rel_path = item["relative_path"]
        ident_state = item["identification_state"]
        work_id = item["work_id"]
        is_locked = item["match_locked"] == 1
        duration_sec = item["duration_seconds"]
        avail_status = item.get("availability_status", "AVAILABLE")

        clues = media_match.extract_movie_clues(rel_path)
        clean_title = clues.title_clue
        extracted_year = clues.year_clue

        search_status = "SKIPPED"
        match_status = ident_state
        external_id = None
        presentation_status = "SKIPPED"
        poster_status = "SKIPPED"
        failure_reason = None

        if avail_status != "AVAILABLE":
            item_reports.append({
                "media_version_id": item_id,
                "relative_path": rel_path,
                "clean_title": clean_title,
                "extracted_year": extracted_year,
                "search_status": "SKIPPED",
                "match_status": ident_state,
                "work_id": work_id,
                "external_id": external_id,
                "presentation_status": "SKIPPED",
                "poster_status": "SKIPPED",
                "failure_reason": "RESOURCE_MISSING",
            })
            continue

        # Resolve existing external_id if work exists
        if work_id is not None:
            ext_row = db.execute(
                "SELECT external_id FROM external_ids WHERE work_id = ? AND provider = 'tmdb_movie'",
                (work_id,),
            ).fetchone()
            if ext_row is not None:
                external_id = ext_row[0]

        # ─── PHASES 2 & 3: Match / Auto-Accept ───────────────────────────────
        if is_locked or ident_state in ("USER_MATCHED", "AUTO_MATCHED"):
            # Identity is immutable; search is strictly skipped
            search_status = "SKIPPED"
            match_status = ident_state
        else:
            # Item is UNMATCHED and unlocked
            if not clean_title:
                unresolved += 1
                search_status = "PARSE_FAILURE"
                match_status = "UNMATCHED"
                failure_reason = "PARSE_FAILURE"
            else:
                media_db = _load_media_db()
                current_sig = media_db.compute_query_signature(
                    provider="tmdb_movie",
                    media_type="movie",
                    locale=locale,
                    title=clean_title,
                    year=extracted_year,
                )
                search_state = media_db.get_media_version_search(
                    db, item_id, provider="tmdb_movie"
                )

                should_search = False
                if refresh_candidates:
                    should_search = True
                elif search_state is None:
                    should_search = True
                elif search_state["query_signature"] != current_sig:
                    should_search = True
                elif search_state["search_status"] == "FAILED":
                    should_search = True
                elif search_state["search_status"] == "CANDIDATES":
                    should_search = False
                    unresolved += 1
                    search_status = "CANDIDATES_PRESERVED"
                    match_status = "UNMATCHED"
                    failure_reason = "CANDIDATES_ALREADY_PERSISTED"
                elif search_state["search_status"] == "NO_RESULT":
                    should_search = False
                    unresolved += 1
                    search_status = "NO_RESULTS_PRESERVED"
                    match_status = "UNMATCHED"
                    failure_reason = "NO_RESULTS"
                else:
                    should_search = True

                if should_search:
                    searched += 1
                    if rate_limit_sleep > 0.0:
                        time.sleep(rate_limit_sleep)

                    search_res = tmdb_provider.search_movies(
                        title=clean_title,
                        year=extracted_year,
                        language=locale,
                        home=home,
                        opener=opener or urllib.request.urlopen,
                    )

                    if search_res.status == tmdb_provider.STATUS_OK_NO_RESULTS:
                        no_result += 1
                        unresolved += 1
                        search_status = "NO_RESULTS"
                        match_status = "UNMATCHED"
                        failure_reason = "NO_RESULTS"
                        # Clear stale pending candidates
                        db.execute(
                            "DELETE FROM match_candidates WHERE media_version_id = ? AND status = 'PENDING'",
                            (item_id,),
                        )
                        media_db.upsert_media_version_search(
                            db,
                            media_version_id=item_id,
                            provider="tmdb_movie",
                            query_signature=current_sig,
                            search_status="NO_RESULT",
                            failure_reason="NO_RESULTS",
                            query_title=clean_title,
                            query_year=extracted_year,
                            query_locale=locale,
                            query_media_type="movie",
                        )
                        db.commit()
                    elif search_res.status != tmdb_provider.STATUS_OK:
                        provider_failed += 1
                        unresolved += 1
                        search_status = "PROVIDER_FAILED"
                        match_status = "UNMATCHED"
                        failure_reason = search_res.error_code or search_res.status
                        outcome = "PARTIAL"
                        # Preserve prior usable candidate set across transient failure
                        media_db.upsert_media_version_search(
                            db,
                            media_version_id=item_id,
                            provider="tmdb_movie",
                            query_signature=current_sig,
                            search_status="FAILED",
                            failure_reason=failure_reason[:200] if failure_reason else None,
                            query_title=clean_title,
                            query_year=extracted_year,
                            query_locale=locale,
                            query_media_type="movie",
                        )
                        db.commit()
                    else:
                        # Search succeeded with candidates
                        search_status = "OK"
                        scored = media_match.evaluate_candidate_list(
                            candidates=search_res.candidates,
                            title_clue=clean_title,
                            year_clue=extracted_year,
                            duration_seconds=duration_sec,
                        )
                        # Persist top 5 candidates
                        media_match.persist_candidates(db, item_id, scored, limit=5)
                        media_db.upsert_media_version_search(
                            db,
                            media_version_id=item_id,
                            provider="tmdb_movie",
                            query_signature=current_sig,
                            search_status="CANDIDATES",
                            failure_reason=None,
                            query_title=clean_title,
                            query_year=extracted_year,
                            query_locale=locale,
                            query_media_type="movie",
                        )

                        if extracted_year is None:
                            # Section 7: Yearless items — AUTO_ACCEPT is FORBIDDEN
                            unresolved += 1
                            match_status = "UNMATCHED"
                            failure_reason = "NO_YEAR_CLUE_CONSERVATIVE_GATE"
                            db.commit()
                        else:
                            is_eligible, top_cand, top_score, reason = media_match.check_auto_match_eligibility(
                                scored_candidates=scored,
                                title_clue=clean_title,
                                year_clue=extracted_year,
                            )

                            if not is_eligible:
                                unresolved += 1
                                match_status = "UNMATCHED"
                                failure_reason = reason
                                db.commit()
                            else:
                                # Eligible for conservative auto-match
                                accept_res = media_match.accept_candidate(
                                    db,
                                    item_id,
                                    top_cand,
                                    score=top_score,
                                    mode="AUTO",
                                    method=reason,
                                )
                                if not accept_res.get("ok"):
                                    unresolved += 1
                                    match_status = "UNMATCHED"
                                    failure_reason = accept_res.get("error")
                                    outcome = "PARTIAL"
                                    db.commit()
                                else:
                                    auto_matched_count += 1
                                    match_status = "AUTO_MATCHED"
                                    work_id = accept_res["work_id"]
                                    external_id = accept_res["external_id"]
                                    db.commit()

        # ─── PHASE 4: Presentation ──────────────────────────────────────────
        pres_existed_before = False
        if work_id is not None:
            pres_row = db.execute(
                "SELECT id FROM work_presentations WHERE work_id = ? AND locale = ?",
                (work_id, locale),
            ).fetchone()
            if pres_row is not None:
                pres_existed_before = True
                presentation_status = "ALREADY_PRESENT"
            else:
                if rate_limit_sleep > 0.0:
                    time.sleep(rate_limit_sleep)
                pres_res = media_pres.refresh_work_presentation(
                    db,
                    work_id,
                    locale=locale,
                    home=home,
                    opener=opener,
                )
                if pres_res.get("ok"):
                    presentation_refreshed += 1
                    presentation_status = "REFRESHED"
                    db.commit()
                else:
                    presentation_failed += 1
                    presentation_status = "FAILED"
                    if not failure_reason:
                        failure_reason = pres_res.get("error_code") or pres_res.get("status")
                    outcome = "PARTIAL"
        else:
            presentation_status = "NOT_APPLICABLE"

        # ─── PHASE 5: Artwork (Poster Cache) ─────────────────────────────────
        poster_hit_before = False
        if work_id is not None and presentation_status in ("ALREADY_PRESENT", "REFRESHED"):
            poster_res = artwork_mod.ensure_work_poster(
                db,
                work_id,
                locale=locale,
                home=home,
                opener=opener,
            )
            p_status = poster_res.get("status")
            if p_status == "OK_CACHE_HIT":
                posters_cache_hit += 1
                poster_status = "CACHE_HIT"
                poster_hit_before = True
            elif p_status == "OK_DOWNLOADED":
                posters_cached += 1
                poster_status = "DOWNLOADED"
            elif p_status in ("NO_POSTER", "NO_PRESENTATION"):
                posters_missing += 1
                poster_status = "MISSING"
            else:
                poster_failed += 1
                poster_status = "FAILED"
                if not failure_reason:
                    failure_reason = p_status
                outcome = "PARTIAL"
        else:
            poster_status = "NOT_APPLICABLE"

        # Check already_complete condition:
        if ident_state in ("USER_MATCHED", "AUTO_MATCHED") and pres_existed_before and poster_hit_before:
            already_complete += 1

        item_reports.append({
            "media_version_id": item_id,
            "relative_path": rel_path,
            "clean_title": clean_title,
            "extracted_year": extracted_year,
            "search_status": search_status,
            "match_status": match_status,
            "work_id": work_id,
            "external_id": external_id,
            "presentation_status": presentation_status,
            "poster_status": poster_status,
            "failure_reason": failure_reason,
        })

    return {
        "ok": True,
        "outcome": outcome,
        "source_id": source_id,
        "mode": "EXECUTE",
        "considered": considered,
        "searched": searched,
        "auto_matched": auto_matched_count,
        "unresolved": unresolved,
        "no_result": no_result,
        "provider_failed": provider_failed,
        "presentation_refreshed": presentation_refreshed,
        "presentation_failed": presentation_failed,
        "posters_cached": posters_cached,
        "posters_cache_hit": posters_cache_hit,
        "posters_missing": posters_missing,
        "poster_failed": poster_failed,
        "already_complete": already_complete,
        "refresh_candidates": refresh_candidates,
        "candidates_preserved": sum(1 for it in item_reports if it.get("search_status") == "CANDIDATES_PRESERVED"),
        "no_results_preserved": sum(1 for it in item_reports if it.get("search_status") == "NO_RESULTS_PRESERVED"),
        "missing_skipped": sum(1 for it in item_reports if it.get("search_status") == "SKIPPED" and it.get("failure_reason") == "RESOURCE_MISSING"),
        "items": item_reports,
    }


def run_batch_enrichment(
    source_id: str | None = None,
    source_root: Path | str | None = None,
    *,
    plan: bool = False,
    media_version_ids: list[int] | None = None,
    limit: int | None = None,
    refresh_candidates: bool = False,
    locale: str = "fr-FR",
    home: Path | None = None,
    db_path: Path | str | None = None,
    db: sqlite3.Connection | None = None,
    opener: Any = None,
    rate_limit_sleep: float = 0.0,
) -> dict[str, Any]:
    """Top-level entrypoint for batch enrichment orchestration."""
    # 1. Source scoping resolution
    if not source_id and not source_root:
        return {
            "ok": False,
            "outcome": "REJECTED",
            "error": "SOURCE_SCOPE_REQUIRED",
            "message": "Either --source-id or --source-root must be specified",
        }

    canonical_source_id: str
    if source_root:
        computed = compute_source_id(source_root)
        if source_id and source_id != computed:
            return {
                "ok": False,
                "outcome": "REJECTED",
                "error": "SOURCE_ID_ROOT_MISMATCH",
                "message": f"Source id '{source_id}' does not match source root '{source_root}' ({computed})",
            }
        canonical_source_id = computed
    else:
        assert source_id is not None
        canonical_source_id = source_id

    # 2. Database connection & phase execution
    if db is not None:
        if plan:
            return plan_source(
                db,
                canonical_source_id,
                media_version_ids=media_version_ids,
                limit=limit,
                refresh_candidates=refresh_candidates,
                locale=locale,
                home=home,
            )
        else:
            return enrich_source(
                db,
                canonical_source_id,
                media_version_ids=media_version_ids,
                limit=limit,
                refresh_candidates=refresh_candidates,
                locale=locale,
                home=home,
                opener=opener,
                rate_limit_sleep=rate_limit_sleep,
            )

    if plan:
        with closing(connect_db(db_path, read_only=True, home=home)) as ro_db:
            return plan_source(
                ro_db,
                canonical_source_id,
                media_version_ids=media_version_ids,
                limit=limit,
                refresh_candidates=refresh_candidates,
                locale=locale,
                home=home,
            )
    else:
        with closing(connect_db(db_path, read_only=False, home=home)) as rw_db:
            return enrich_source(
                rw_db,
                canonical_source_id,
                media_version_ids=media_version_ids,
                limit=limit,
                refresh_candidates=refresh_candidates,
                locale=locale,
                home=home,
                opener=opener,
                rate_limit_sleep=rate_limit_sleep,
            )


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="openhtpc-media-enrich",
        description="Explicit Media Batch Enrichment Orchestrator for OPENHTPC.",
    )
    src_group = parser.add_argument_group("Source Scope (Mandatory)")
    src_group.add_argument(
        "--source-id",
        dest="source_id",
        help="Canonical 16-hex OPENHTPC source_id to scope enrichment",
    )
    src_group.add_argument(
        "--source-root",
        dest="source_root",
        help="Path to media directory; computes canonical source_id",
    )

    op_group = parser.add_argument_group("Operation Controls")
    op_group.add_argument(
        "--plan",
        dest="plan",
        action="store_true",
        help="Dry-run plan mode: strictly read-only SQLite, 0 network, 0 DB writes",
    )
    op_group.add_argument(
        "--refresh-candidates",
        dest="refresh_candidates",
        action="store_true",
        help="Re-query provider search for unresolved items with existing candidates",
    )
    op_group.add_argument(
        "--limit",
        dest="limit",
        type=int,
        help="Limit number of selected media_version items to process",
    )
    op_group.add_argument(
        "--media-version-id",
        dest="media_version_ids",
        type=int,
        action="append",
        help="Explicit media_version_id to process (repeatable)",
    )

    env_group = parser.add_argument_group("Environment & Output")
    env_group.add_argument(
        "--db",
        dest="db",
        help="Custom path to media.db (default: canonical XDG location)",
    )
    env_group.add_argument(
        "--home",
        dest="home",
        help="Custom home directory for XDG isolation",
    )
    env_group.add_argument(
        "--locale",
        dest="locale",
        default="fr-FR",
        help="Presentation locale (default: fr-FR)",
    )
    env_group.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output machine-readable JSON summary",
    )
    env_group.add_argument(
        "--rate-limit-sleep",
        dest="rate_limit_sleep",
        type=float,
        default=0.0,
        help="Delay in seconds between provider requests (default: 0.0)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    home_path = Path(args.home).resolve() if args.home else None

    result = run_batch_enrichment(
        source_id=args.source_id,
        source_root=args.source_root,
        plan=args.plan,
        media_version_ids=args.media_version_ids,
        limit=args.limit,
        refresh_candidates=args.refresh_candidates,
        locale=args.locale,
        home=home_path,
        db_path=args.db,
        rate_limit_sleep=args.rate_limit_sleep,
    )

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") and result.get("outcome") in ("COMPLETE", "PARTIAL", "PLAN_READY") else 1


if __name__ == "__main__":
    sys.exit(main())
