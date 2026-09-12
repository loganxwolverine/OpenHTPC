#!/usr/bin/env python3
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Local Movie Identity Engine & Filename Clue Resolver for OpenHTPC (DEV5A).

Performs 100% offline filename/path clue extraction, deterministic movie candidate
scoring, candidate persistence, and transactional identity acceptance.

Core Rules:
- Filename is a clue, NEVER canonical identity.
- Clue extraction produces (title_clue, year_clue); it NEVER creates a WORK row.
- Candidate generation alone NEVER creates a WORK row.
- A WORK row is created or reused ONLY when an identity is accepted.
- MOVIE ONLY (work_type = 'MOVIE').
- Scale: strictly 0.0 .. 100.0 for match_confidence and match_candidates.score.
- Conservative auto-match: requires exact title match, reliable year clue, exact
  year agreement, top score >= 80.0, and margin over second candidate >= 20.0.
- Human authority is absolute: match_locked = 1 is immutable to automated changes.
- Provider namespace: tmdb_movie, imdb, fixture_movie (distinct from future tmdb_tv).
- Technical stream facts, availability status, and file fingerprints are NEVER mutated.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

_MEDIA_DB = None

TECHNICAL_TOKENS = frozenset({
    # Resolutions
    "2160p", "1080p", "1080i", "720p", "576p", "480p", "4k", "uhd", "fhd", "hd", "sd",
    # Video codecs and formats
    "x264", "x265", "h264", "h265", "hevc", "av1", "10bit", "10-bit", "xvid", "divx",
    # Source / Edition
    "bluray", "blu-ray", "bdrip", "brrip", "remux", "web-dl", "webdl", "webrip",
    "dvdrip", "dvd", "hdtv", "proper", "repack", "rerip",
    # Audio formats
    "dts", "dts-hd", "truehd", "atmos", "ddp", "ddp5.1", "ac3", "aac", "mp3", "flac"
})

GENERIC_NAMES = frozenset({
    "movie", "video", "film", "dvd", "disc", "cd", "feature", "main", "track",
    "title", "unknown", "sample", "trailer"
})

VALID_PROVIDER_NAMESPACES = frozenset({
    "tmdb_movie",
    "tmdb_tv",
    "imdb",
    "fixture_movie",
    "test_movie",
})


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


_TMDB_PROVIDER = None


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


class MovieClues:
    __slots__ = ("title_clue", "year_clue", "raw_stem")

    def __init__(self, title_clue: str, year_clue: int | None, raw_stem: str) -> None:
        self.title_clue = title_clue
        self.year_clue = year_clue
        self.raw_stem = raw_stem

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_clue": self.title_clue,
            "year_clue": self.year_clue,
            "raw_stem": self.raw_stem,
        }


class MovieCandidate:
    __slots__ = ("provider", "external_id", "title", "original_title", "year", "runtime_minutes")

    def __init__(
        self,
        provider: str,
        external_id: str | int,
        title: str,
        original_title: str | None = None,
        year: int | None = None,
        runtime_minutes: int | float | None = None,
    ) -> None:
        self.provider = str(provider).strip()
        self.external_id = str(external_id).strip()
        self.title = str(title).strip()
        self.original_title = str(original_title).strip() if original_title else None
        self.year = int(year) if year is not None else None
        self.runtime_minutes = float(runtime_minutes) if runtime_minutes is not None else None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MovieCandidate:
        return cls(
            provider=data.get("provider", "fixture_movie"),
            external_id=data.get("external_id") or data.get("id", ""),
            title=data.get("title", ""),
            original_title=data.get("original_title"),
            year=data.get("year"),
            runtime_minutes=data.get("runtime_minutes") or data.get("runtime"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "external_id": self.external_id,
            "title": self.title,
            "original_title": self.original_title,
            "year": self.year,
            "runtime_minutes": self.runtime_minutes,
        }


# ─── 1. Filename & Path Clue Extraction ──────────────────────────────────────

def extract_movie_clues(filename_or_path: str | Path) -> MovieClues:
    """Extract movie title and optional year clues from filename or relative path.

    Crucial Safeguards:
    - 4-digit numeric titles (e.g. '1917.mkv', '1984', '300') are protected.
    - A bare leading numeric token is NOT automatically treated as a year.
    - Parenthesized/bracketed 4-digit years '(YYYY)' are authoritative year clues.
    - Strips scene and technical tokens without damaging legitimate title words.
    """
    p = Path(filename_or_path)
    raw_stem = p.stem
    stem = raw_stem

    # Remove trailing release group: e.g. -SPARKS, -ROVERS
    stem = re.sub(r"-[A-Za-z0-9_]+$", "", stem)

    year_clue: int | None = None
    title_clue: str = ""

    # Strategy 1: Look for parenthesized or bracketed 4-digit year: (1999) or [1999]
    bracket_matches = list(re.finditer(r"[\(\[]\s*(188[89]|189\d|19\d{2}|20\d{2}|2100)\s*[\)\]]", stem))
    if bracket_matches:
        last_m = bracket_matches[-1]
        year_clue = int(last_m.group(1))
        # Title is everything before this bracket match
        before = stem[:last_m.start()].strip()
        before = re.sub(r"[._]", " ", before)
        before = re.sub(r"\s+", " ", before).strip()
        if before:
            title_clue = before

    # Strategy 2: Delimited tokens (e.g. Alien.Romulus.2024.2160p)
    if not year_clue:
        tokens = re.split(r"[._\s]+", stem)
        cleaned_tokens: list[str] = []
        for i, token in enumerate(tokens):
            tok_lower = token.lower()
            # Check for 4-digit year
            if re.fullmatch(r"(188[89]|189\d|19\d{2}|20\d{2}|2100)", token):
                # Safeguard: cannot be year if it is the only token or first token with no tokens before it
                if i > 0 and len(cleaned_tokens) > 0:
                    year_clue = int(token)
                    break
                else:
                    cleaned_tokens.append(token)
                    continue

            # Technical token encountered; cut off title here
            if tok_lower in TECHNICAL_TOKENS:
                break

            cleaned_tokens.append(token)

        if not title_clue and cleaned_tokens:
            title_clue = " ".join(cleaned_tokens).strip()

    # Final cleanup of trailing technical tokens from title_clue
    if title_clue:
        words = title_clue.split()
        while words and words[-1].lower() in TECHNICAL_TOKENS:
            words.pop()
        title_clue = " ".join(words).strip()
        title_clue = re.sub(r"\s+", " ", title_clue).strip()

    if not title_clue:
        title_clue = stem.strip()

    # Fallback to parent directory if filename has no year and parent contains '(YYYY)'
    if year_clue is None and len(p.parts) > 1:
        parent_name = p.parent.name
        parent_bracket = re.search(r"[\(\[]\s*(188[89]|189\d|19\d{2}|20\d{2}|2100)\s*[\)\]]", parent_name)
        if parent_bracket:
            year_clue = int(parent_bracket.group(1))
            # If filename was generic (e.g. movie.mkv), adopt parent title
            if title_clue.lower() in GENERIC_NAMES:
                parent_title = parent_name[:parent_bracket.start()].strip()
                parent_title = re.sub(r"[._]", " ", parent_title)
                parent_title = re.sub(r"\s+", " ", parent_title).strip()
                if parent_title:
                    title_clue = parent_title

    return MovieClues(title_clue=title_clue, year_clue=year_clue, raw_stem=raw_stem)


def create_provider_query(clues: MovieClues) -> dict[str, Any]:
    """Privacy boundary filter for metadata queries.

    Exposes ONLY normalized title clue, optional year clue, and media_type.
    NEVER exposes absolute paths, usernames, hostnames, IPs, source roots,
    technical stream facts, or internal database IDs.
    """
    return {
        "title_query": clues.title_clue,
        "year_query": clues.year_clue,
        "media_type": "movie",
    }


# ─── 2. Title Normalization & Candidate Scoring ──────────────────────────────

def normalize_title(text: str) -> str:
    """Comparison normalization for titles.

    Lowercases, strips punctuation, and collapses whitespace.
    Never use this string as the canonical title in the works table.
    """
    if not text:
        return ""
    s = text.casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score_candidate(
    candidate: MovieCandidate | dict[str, Any],
    title_clue: str,
    year_clue: int | None = None,
    duration_seconds: float | None = None,
) -> tuple[float, list[str]]:
    """Deterministic candidate scoring on a fixed 0.0 .. 100.0 scale.

    Score components:
    1. Title Matching (0 to 50 points):
       - Exact normalized match: +50.0
       - Prefix match: +35.0
       - Word-subset match: +25.0
       - Partial token match: +15.0
       - Base match: +5.0
    2. Year Matching (0 to 30 points, or penalty):
       - Exact year agreement: +30.0
       - 1 year difference: +15.0
       - Greater difference: -20.0
       - No year clue: 0.0
    3. Runtime Proximity (0 to 20 points, or penalty):
       - diff <= 5 min: +20.0
       - diff <= 12 min: +12.0
       - diff <= 20 min: +5.0
       - diff > 35 min: -15.0
    """
    if isinstance(candidate, dict):
        cand = MovieCandidate.from_dict(candidate)
    else:
        cand = candidate

    score = 0.0
    reasons: list[str] = []

    norm_clue = normalize_title(title_clue)
    cand_title_norm = normalize_title(cand.title)
    cand_orig_norm = normalize_title(cand.original_title) if cand.original_title else ""

    # 1. Title Matching
    if norm_clue and (norm_clue == cand_title_norm or (cand_orig_norm and norm_clue == cand_orig_norm)):
        score += 50.0
        reasons.append("title_exact")
    elif norm_clue and (cand_title_norm.startswith(norm_clue) or norm_clue.startswith(cand_title_norm)):
        score += 35.0
        reasons.append("title_prefix")
    elif norm_clue and all(w in cand_title_norm.split() for w in norm_clue.split()):
        score += 25.0
        reasons.append("title_subset")
    elif norm_clue and any(w in cand_title_norm.split() for w in norm_clue.split()):
        score += 15.0
        reasons.append("title_token_overlap")
    else:
        score += 5.0
        reasons.append("title_fallback")

    # 2. Year Matching
    if year_clue is not None and cand.year is not None:
        diff_year = abs(cand.year - year_clue)
        if diff_year == 0:
            score += 30.0
            reasons.append("year_exact")
        elif diff_year == 1:
            score += 15.0
            reasons.append("year_near")
        else:
            score -= 20.0
            reasons.append(f"year_mismatch_{cand.year}_vs_{year_clue}")
    elif year_clue is None:
        reasons.append("year_clue_absent")

    # 3. Runtime Proximity
    if duration_seconds is not None and cand.runtime_minutes is not None and cand.runtime_minutes > 0:
        file_minutes = duration_seconds / 60.0
        diff_minutes = abs(file_minutes - cand.runtime_minutes)
        if diff_minutes <= 5.0:
            score += 20.0
            reasons.append("runtime_within_5min")
        elif diff_minutes <= 12.0:
            score += 12.0
            reasons.append("runtime_within_12min")
        elif diff_minutes <= 20.0:
            score += 5.0
            reasons.append("runtime_within_20min")
        elif diff_minutes > 35.0:
            score -= 15.0
            reasons.append("runtime_mismatch_over_35min")

    final_score = max(0.0, min(100.0, round(score, 1)))
    return final_score, reasons


def evaluate_candidate_list(
    candidates: list[dict[str, Any] | MovieCandidate],
    title_clue: str,
    year_clue: int | None = None,
    duration_seconds: float | None = None,
) -> list[tuple[float, MovieCandidate, list[str]]]:
    """Score, filter low confidence (< 50.0), and sort candidates."""
    scored: list[tuple[float, MovieCandidate, list[str]]] = []
    for item in candidates:
        cand = MovieCandidate.from_dict(item) if isinstance(item, dict) else item
        score, reasons = score_candidate(cand, title_clue, year_clue, duration_seconds)
        if score >= 50.0:  # Discard LOW confidence (< 50.0)
            scored.append((score, cand, reasons))

    # Stable sort: score DESC, external_id ASC
    scored.sort(key=lambda x: (-x[0], x[1].external_id))
    return scored


def check_auto_match_eligibility(
    scored_candidates: list[tuple[float, MovieCandidate, list[str]]],
    title_clue: str,
    year_clue: int | None,
) -> tuple[bool, MovieCandidate | None, float, str]:
    """Determine if top candidate qualifies for AUTO_MATCH under strict policy.

    Eligibility Rules:
    1. At least 1 candidate present.
    2. Reliable year clue was extracted (year_clue is not None).
    3. Top score >= 80.0.
    4. Top score margin over second candidate >= 20.0 (or single candidate).
    5. Exact normalized title match.
    6. Candidate year exactly matches year clue.
    """
    if not scored_candidates:
        return False, None, 0.0, "NO_CANDIDATES"

    if year_clue is None:
        return False, None, scored_candidates[0][0], "NO_YEAR_CLUE_CONSERVATIVE_GATE"

    top_score, top_cand, top_reasons = scored_candidates[0]
    second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else -100.0

    if top_score < 80.0:
        return False, None, top_score, f"SCORE_BELOW_AUTO_THRESHOLD_{top_score}"

    if (top_score - second_score) < 20.0:
        return False, None, top_score, f"MARGIN_INSUFFICIENT_{top_score - second_score:.1f}"

    norm_clue = normalize_title(title_clue)
    cand_norm = normalize_title(top_cand.title)
    cand_orig_norm = normalize_title(top_cand.original_title) if top_cand.original_title else ""
    if norm_clue != cand_norm and (not cand_orig_norm or norm_clue != cand_orig_norm):
        return False, None, top_score, "TITLE_NOT_EXACT_MATCH"

    if top_cand.year != year_clue:
        return False, None, top_score, f"YEAR_MISMATCH_{top_cand.year}_vs_{year_clue}"

    return True, top_cand, top_score, "AUTO_TITLE_YEAR_EXACT"


# ─── 3. Database Operations & Transactional Acceptance ───────────────────────

def persist_candidates(
    db: sqlite3.Connection,
    media_version_id: int,
    scored_candidates: list[tuple[float, MovieCandidate, list[str]]],
    limit: int = 5,
) -> list[int]:
    """Persist at most top 5 candidates into match_candidates table.

    Transactionally replaces previous PENDING candidates for this media_version_id.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted_ids: list[int] = []

    # Clear prior pending candidates
    db.execute(
        "DELETE FROM match_candidates WHERE media_version_id = ? AND status = 'PENDING'",
        (media_version_id,),
    )

    top_slice = scored_candidates[:limit]
    for score, cand, reasons in top_slice:
        payload = json.dumps({
            "original_title": cand.original_title,
            "runtime_minutes": cand.runtime_minutes,
            "match_reasons": reasons,
        })
        cur = db.execute(
            """
            INSERT INTO match_candidates (
                media_version_id, provider, external_id, candidate_title,
                candidate_year, candidate_payload_json, score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                media_version_id,
                cand.provider,
                cand.external_id,
                cand.title,
                cand.year,
                payload,
                score,
                now_iso,
            ),
        )
        inserted_ids.append(cur.lastrowid)

    return inserted_ids


def accept_candidate(
    db: sqlite3.Connection,
    media_version_id: int,
    candidate: MovieCandidate | dict[str, Any],
    score: float,
    mode: str = "USER",
    method: str | None = None,
) -> dict[str, Any]:
    """Transactionally accept an identity candidate for media_version_id.

    1. Checks match_locked: if locked and mode is AUTO, rejects immediately.
    2. Looks up existing external_ids(provider, external_id) -> reuses work_id.
    3. If not found, creates ONE works row (work_type='MOVIE') and external_ids link.
    4. Updates media_versions(work_id, identification_state, match_confidence, match_method, match_locked).
    5. Sets candidate status='ACCEPTED' and supersedes other pending candidates.
    6. Ensures technical resources, video/audio/subtitle streams are NOT touched.
    """
    if isinstance(candidate, dict):
        cand = MovieCandidate.from_dict(candidate)
    else:
        cand = candidate

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Check current media_version
    cur = db.execute(
        "SELECT work_id, identification_state, match_locked FROM media_versions WHERE id = ?",
        (media_version_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"MEDIA_VERSION_NOT_FOUND: {media_version_id}")

    current_work_id, current_state, match_locked = row
    if match_locked == 1 and mode == "AUTO":
        return {
            "ok": False,
            "error": "IDENTITY_LOCKED",
            "message": "media_version is locked by human authority; automated acceptance rejected.",
            "media_version_id": media_version_id,
            "work_id": current_work_id,
        }

    # 2. Duplicate WORK Prevention: Check if this external ID already has a WORK
    cur = db.execute(
        "SELECT work_id FROM external_ids WHERE provider = ? AND external_id = ?",
        (cand.provider, cand.external_id),
    )
    ext_row = cur.fetchone()

    if ext_row is not None:
        work_id = ext_row[0]
        work_reused = True
    else:
        # Create new WORK
        norm_title = normalize_title(cand.title)
        cur = db.execute(
            """
            INSERT INTO works (
                work_type, title, original_title, normalized_title, year, created_at, updated_at
            ) VALUES ('MOVIE', ?, ?, ?, ?, ?, ?)
            """,
            (
                cand.title,
                cand.original_title,
                norm_title,
                cand.year,
                now_iso,
                now_iso,
            ),
        )
        work_id = cur.lastrowid
        work_reused = False

        # Link external ID
        db.execute(
            """
            INSERT INTO external_ids (
                work_id, provider, external_id, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                work_id,
                cand.provider,
                cand.external_id,
                str(score),
                now_iso,
            ),
        )

    # 3. Update media_version
    ident_state = "USER_MATCHED" if mode == "USER" else "AUTO_MATCHED"
    new_locked = 1 if mode == "USER" else 0
    resolved_method = method or ("USER_CONFIRMATION" if mode == "USER" else "AUTO_TITLE_YEAR_EXACT")

    db.execute(
        """
        UPDATE media_versions
        SET work_id = ?,
            identification_state = ?,
            match_confidence = ?,
            match_method = ?,
            match_locked = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            work_id,
            ident_state,
            score,
            resolved_method,
            new_locked,
            now_iso,
            media_version_id,
        ),
    )

    # 4. Update candidate statuses
    db.execute(
        """
        UPDATE match_candidates
        SET status = 'ACCEPTED'
        WHERE media_version_id = ? AND provider = ? AND external_id = ?
        """,
        (media_version_id, cand.provider, cand.external_id),
    )
    db.execute(
        """
        UPDATE match_candidates
        SET status = 'SUPERSEDED'
        WHERE media_version_id = ? AND status = 'PENDING'
        """,
        (media_version_id,),
    )

    return {
        "ok": True,
        "media_version_id": media_version_id,
        "work_id": work_id,
        "work_reused": work_reused,
        "identification_state": ident_state,
        "match_locked": new_locked,
        "match_confidence": score,
        "match_method": resolved_method,
        "provider": cand.provider,
        "external_id": cand.external_id,
        "title": cand.title,
        "year": cand.year,
    }


def evaluate_media_version(
    db: sqlite3.Connection,
    media_version_id: int,
    candidate_list: list[dict[str, Any] | MovieCandidate],
    auto_accept: bool = True,
) -> dict[str, Any]:
    """Complete evaluation pipeline for a media_version against input candidates."""
    # 1. Fetch media_version and associated resource
    cur = db.execute(
        """
        SELECT mv.work_id, mv.identification_state, mv.match_locked, mv.duration_seconds,
               r.relative_path, r.canonical_path
        FROM media_versions mv
        LEFT JOIN resources r ON r.media_version_id = mv.id
        WHERE mv.id = ?
        LIMIT 1
        """,
        (media_version_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {"ok": False, "error": f"MEDIA_VERSION_NOT_FOUND: {media_version_id}"}

    work_id, ident_state, match_locked, duration_sec, rel_path, can_path = row

    if match_locked == 1:
        return {
            "ok": True,
            "status": "LOCKED",
            "message": "media_version is locked by user; evaluation skipped.",
            "media_version_id": media_version_id,
            "work_id": work_id,
            "identification_state": ident_state,
            "match_locked": 1,
        }

    # Extract clues from relative path or filename
    path_to_parse = rel_path or can_path or f"movie_{media_version_id}"
    clues = extract_movie_clues(path_to_parse)

    # Optional update of provisional clues on media_version
    now_iso = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        UPDATE media_versions
        SET provisional_title = ?, provisional_year = ?, updated_at = ?
        WHERE id = ? AND work_id IS NULL
        """,
        (clues.title_clue, clues.year_clue, now_iso, media_version_id),
    )

    # Score and filter candidates
    scored = evaluate_candidate_list(candidate_list, clues.title_clue, clues.year_clue, duration_sec)

    # Persist top 5 candidates
    persist_candidates(db, media_version_id, scored, limit=5)

    # Check auto-match eligibility
    is_eligible, top_cand, top_score, auto_reason = check_auto_match_eligibility(
        scored, clues.title_clue, clues.year_clue
    )

    if auto_accept and is_eligible and top_cand is not None:
        accept_res = accept_candidate(
            db,
            media_version_id,
            top_cand,
            score=top_score,
            mode="AUTO",
            method=auto_reason,
        )
        return {
            "ok": True,
            "status": "AUTO_MATCHED",
            "clues": clues.to_dict(),
            "acceptance": accept_res,
            "candidates_stored": min(len(scored), 5),
        }

    return {
        "ok": True,
        "status": "UNMATCHED",
        "reason": auto_reason,
        "clues": clues.to_dict(),
        "candidates_stored": min(len(scored), 5),
        "top_score": top_score,
    }


def lookup_media_version(
    db: sqlite3.Connection,
    media_version_id: int,
    provider_name: str = "tmdb_movie",
    auto_accept: bool = True,
    language: str | None = None,
    home: Path | None = None,
    opener=None,
) -> dict[str, Any]:
    """Query metadata provider for media_version and evaluate candidates.

    Guarantees:
    - If match_locked = 1, short-circuits BEFORE network request.
    - On provider error/failure, leaves DB completely untouched (non-destructive).
    - On provider success, hands candidates to evaluate_media_version().
    """
    # 1. Fetch media_version and associated resource
    cur = db.execute(
        """
        SELECT mv.work_id, mv.identification_state, mv.match_locked, mv.duration_seconds,
               r.relative_path, r.canonical_path
        FROM media_versions mv
        LEFT JOIN resources r ON r.media_version_id = mv.id
        WHERE mv.id = ?
        LIMIT 1
        """,
        (media_version_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {"ok": False, "error": f"MEDIA_VERSION_NOT_FOUND: {media_version_id}"}

    work_id, ident_state, match_locked, duration_sec, rel_path, can_path = row

    # 2. Lock check: short-circuit before network call!
    if match_locked == 1:
        return {
            "ok": True,
            "status": "LOCKED",
            "message": "media_version is locked by user; lookup skipped.",
            "media_version_id": media_version_id,
            "work_id": work_id,
            "identification_state": ident_state,
            "match_locked": 1,
        }

    # 3. Clue extraction & privacy boundary query
    path_to_parse = rel_path or can_path or f"movie_{media_version_id}"
    clues = extract_movie_clues(path_to_parse)
    provider_query = create_provider_query(clues)

    # 4. Dispatch to provider
    if provider_name == "tmdb_movie":
        provider_mod = _load_tmdb_provider()
        if provider_mod is None:
            return {
                "ok": False,
                "error": "PROVIDER_NOT_AVAILABLE",
                "detail": "openhtpc-media-provider-tmdb component not found",
                "media_version_id": media_version_id,
            }

        search_kwargs: dict[str, Any] = {}
        if opener is not None:
            search_kwargs["opener"] = opener
        if language is not None:
            search_kwargs["language"] = language
        if home is not None:
            search_kwargs["home"] = home

        pres = provider_mod.search_movies(
            title=provider_query["title_query"],
            year=provider_query["year_query"],
            **search_kwargs,
        )

        if pres.status in (provider_mod.STATUS_OK, provider_mod.STATUS_OK_NO_RESULTS):
            eval_res = evaluate_media_version(
                db,
                media_version_id,
                pres.candidates,
                auto_accept=auto_accept,
            )
            return {
                "ok": True,
                "provider": provider_name,
                "provider_status": pres.status,
                "evaluation": eval_res,
            }
        else:
            # Provider failure: non-destructive! Zero database mutation!
            return {
                "ok": False,
                "provider": provider_name,
                "provider_status": pres.status,
                "error": pres.error_code,
                "detail": pres.error_detail,
                "media_version_id": media_version_id,
            }

    return {
        "ok": False,
        "error": "UNSUPPORTED_PROVIDER",
        "detail": f"Provider '{provider_name}' not supported",
        "media_version_id": media_version_id,
    }


def get_media_version_status(db: sqlite3.Connection, media_version_id: int) -> dict[str, Any]:
    """Retrieve identity status and work details for a media_version."""
    cur = db.execute(
        """
        SELECT mv.id, mv.work_id, mv.identification_state, mv.match_confidence,
               mv.match_method, mv.match_locked, mv.provisional_title, mv.provisional_year,
               w.title, w.year, w.work_type, w.original_title,
               r.id, r.relative_path, r.availability_status
        FROM media_versions mv
        LEFT JOIN works w ON w.id = mv.work_id
        LEFT JOIN resources r ON r.media_version_id = mv.id
        WHERE mv.id = ?
        """,
        (media_version_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {"ok": False, "error": f"MEDIA_VERSION_NOT_FOUND: {media_version_id}"}

    (
        mv_id, w_id, ident_state, confidence, method, locked, prov_title, prov_year,
        w_title, w_year, w_type, w_orig_title, r_id, r_path, r_avail
    ) = row

    # Count pending candidates
    cand_count = db.execute(
        "SELECT COUNT(*) FROM match_candidates WHERE media_version_id = ? AND status = 'PENDING'",
        (media_version_id,),
    ).fetchone()[0]

    return {
        "ok": True,
        "media_version_id": mv_id,
        "work_id": w_id,
        "identification_state": ident_state,
        "match_confidence": confidence,
        "match_method": method,
        "match_locked": locked,
        "provisional_title": prov_title,
        "provisional_year": prov_year,
        "work": {
            "id": w_id,
            "title": w_title,
            "year": w_year,
            "work_type": w_type,
            "original_title": w_orig_title,
        } if w_id is not None else None,
        "resource": {
            "id": r_id,
            "relative_path": r_path,
            "availability_status": r_avail,
        } if r_id is not None else None,
        "pending_candidates_count": cand_count,
    }


def get_candidates(db: sqlite3.Connection, media_version_id: int) -> list[dict[str, Any]]:
    """List match_candidates for a media_version."""
    rows = db.execute(
        """
        SELECT id, provider, external_id, candidate_title, candidate_year,
               candidate_payload_json, score, status, created_at
        FROM match_candidates
        WHERE media_version_id = ?
        ORDER BY score DESC, id ASC
        """,
        (media_version_id,),
    ).fetchall()

    results = []
    for r in rows:
        payload = {}
        try:
            payload = json.loads(r[5])
        except (json.JSONDecodeError, TypeError):
            pass
        results.append({
            "id": r[0],
            "provider": r[1],
            "external_id": r[2],
            "candidate_title": r[3],
            "candidate_year": r[4],
            "payload": payload,
            "score": r[6],
            "status": r[7],
            "created_at": r[8],
        })
    return results


# ─── 4. CLI Interface ────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenHTPC Local Movie Identity Engine (DEV5A)")
    parser.add_argument("--db", type=Path, default=None, help="Explicit media.db database path")
    parser.add_argument("--home", type=Path, default=None, help="OpenHTPC user home directory")

    subparsers = parser.add_subparsers(dest="action", required=True)

    # clues <path>
    clues_p = subparsers.add_parser("clues", help="Extract title and year clues from filename or path")
    clues_p.add_argument("path", help="Filename or path to parse")

    # evaluate --media-version-id <id> --candidates <json-file-or-string>
    eval_p = subparsers.add_parser("evaluate", help="Score candidates and evaluate media_version")
    eval_p.add_argument("--media-version-id", type=int, required=True, help="Media version ID to evaluate")
    eval_p.add_argument("--candidates", required=True, help="Path to JSON file or raw JSON string of candidates")
    eval_p.add_argument("--no-auto-accept", action="store_true", help="Do not automatically accept top match")

    # candidates --media-version-id <id>
    cand_p = subparsers.add_parser("candidates", help="List stored candidates for media_version")
    cand_p.add_argument("--media-version-id", type=int, required=True, help="Media version ID")

    # accept --media-version-id <id> --candidate-id <id>
    accept_p = subparsers.add_parser("accept", help="User acceptance of candidate")
    accept_p.add_argument("--media-version-id", type=int, required=True, help="Media version ID")
    accept_p.add_argument("--candidate-id", type=int, required=True, help="ID in match_candidates table")

    # status --media-version-id <id>
    status_p = subparsers.add_parser("status", help="Show identity status for media_version")
    status_p.add_argument("--media-version-id", type=int, required=True, help="Media version ID")

    # lookup --media-version-id <id> [--provider tmdb_movie] [--no-auto-accept] [--language <lang>]
    lookup_p = subparsers.add_parser("lookup", help="Query metadata provider for media_version and evaluate")
    lookup_p.add_argument("--media-version-id", type=int, required=True, help="Media version ID to lookup")
    lookup_p.add_argument("--provider", default="tmdb_movie", choices=["tmdb_movie"], help="Metadata provider")
    lookup_p.add_argument("--no-auto-accept", action="store_true", help="Do not automatically accept top match")
    lookup_p.add_argument("--language", default=None, help="Query language (defaults to provider default)")

    args = parser.parse_args(argv)

    if args.action == "clues":
        clues = extract_movie_clues(args.path)
        print(json.dumps(clues.to_dict(), indent=2))
        return 0

    # For actions requiring database
    media_db = _load_media_db()
    if media_db is None:
        print("ERROR: openhtpc-media-db component not found", file=sys.stderr)
        return 2

    home_path = args.home if args.home else Path(os.environ.get("OPENHTPC_HOME", Path.home())).resolve()
    db_file = Path(args.db) if args.db else media_db.database_path(home=home_path)

    if not db_file.is_file():
        print(f"ERROR: Database file not found: {db_file}", file=sys.stderr)
        return 1

    with closing(media_db.connect(db_file)) as db:
        if args.action == "status":
            st = get_media_version_status(db, args.media_version_id)
            print(json.dumps(st, indent=2))
            return 0 if st.get("ok") else 1

        if args.action == "candidates":
            cands = get_candidates(db, args.media_version_id)
            print(json.dumps(cands, indent=2))
            return 0

        if args.action == "lookup":
            with db:
                res = lookup_media_version(
                    db,
                    args.media_version_id,
                    provider_name=args.provider,
                    auto_accept=not args.no_auto_accept,
                    language=args.language,
                    home=home_path,
                )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1

        if args.action == "evaluate":
            raw_cands = args.candidates.strip()
            if os.path.isfile(raw_cands):
                candidate_data = json.loads(Path(raw_cands).read_text(encoding="utf-8"))
            else:
                candidate_data = json.loads(raw_cands)

            if not isinstance(candidate_data, list):
                candidate_data = [candidate_data]

            with db:
                res = evaluate_media_version(
                    db,
                    args.media_version_id,
                    candidate_data,
                    auto_accept=not args.no_auto_accept,
                )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1

        if args.action == "accept":
            # Lookup candidate from match_candidates
            cur = db.execute(
                """
                SELECT provider, external_id, candidate_title, candidate_year,
                       candidate_payload_json, score
                FROM match_candidates
                WHERE id = ? AND media_version_id = ?
                """,
                (args.candidate_id, args.media_version_id),
            )
            row = cur.fetchone()
            if row is None:
                print(f"ERROR: Candidate {args.candidate_id} not found for media_version {args.media_version_id}", file=sys.stderr)
                return 1

            provider, external_id, title, year, payload_json, score = row
            orig_title = None
            runtime_min = None
            try:
                p_data = json.loads(payload_json)
                orig_title = p_data.get("original_title")
                runtime_min = p_data.get("runtime_minutes")
            except (json.JSONDecodeError, TypeError):
                pass

            cand = MovieCandidate(
                provider=provider,
                external_id=external_id,
                title=title,
                original_title=orig_title,
                year=year,
                runtime_minutes=runtime_min,
            )

            with db:
                res = accept_candidate(
                    db,
                    args.media_version_id,
                    cand,
                    score=score,
                    mode="USER",
                    method="USER_CONFIRMATION",
                )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
