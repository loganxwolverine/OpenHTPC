#!/usr/bin/env python3
"""Optional, failure-tolerant TMDb disc lookup with deterministic ambiguous candidate resolution and no credential logging."""
from __future__ import annotations
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import hashlib

GENERIC_MEDIA_LABELS = {
    "dvd", "dvd video", "dvd_video", "dvdvideo", "video ts", "video_ts", "videots",
    "disc", "disc 1", "disc 2", "disc_1", "disc_2", "disc1", "disc2", "disk",
    "movie", "unknown", "no label", "no_label", "nolabel",
    "cd", "cdrom", "dvd a", "dvd b", "dvd_a", "dvd_b", "optical", "disque"
}

ACCEPT_THRESHOLD = 50.0
MINIMUM_MARGIN_OVER_SECOND = 15.0

def _normalize_title(text: str) -> str:
    if not text: return ""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def clean_disc_title(query: str) -> str:
    if not query: return ""
    s = query.replace("_", " ").strip()
    s = re.sub(r"(?i)(?:[ _.-]+)(?:DVD|DISC|DISK)\s*[12]\s*$", "", s).strip()
    return s or query

def is_generic_query(query: str) -> bool:
    cleaned = (query or "").lower().strip()
    if not cleaned or cleaned in GENERIC_MEDIA_LABELS or cleaned.replace("_", " ") in GENERIC_MEDIA_LABELS or cleaned.replace(" ", "_") in GENERIC_MEDIA_LABELS:
        return True
    norm = _normalize_title(clean_disc_title(query))
    return not norm or norm in GENERIC_MEDIA_LABELS or norm.replace(" ", "") in GENERIC_MEDIA_LABELS

AUTHORITATIVE_CONFIDENCE = {"USER_CONFIRMED_MATCH", "AUTOMATIC_CONFIDENT_MATCH"}

def _cache_path(home: pathlib.Path, state: dict) -> pathlib.Path | None:
    disc_id = str(state.get("disc_id") or "").strip()
    if not disc_id:
        return None
    return home / ".local/share/openhtpc/media-cache/dvd" / hashlib.sha256(disc_id.encode()).hexdigest() / "metadata.json"

def _score_candidate(candidate: dict, norm_query: str, duration_seconds: float | None = None, year: int | None = None, is_single: bool = False) -> float:
    score = 0.0
    cand_title = _normalize_title(candidate.get("title") or "")
    cand_orig = _normalize_title(candidate.get("original_title") or "")

    # 1. Title Matching (0 to 50 points)
    if norm_query and (norm_query == cand_title or norm_query == cand_orig):
        score += 50.0
    elif norm_query and (cand_title.startswith(norm_query) or norm_query.startswith(cand_title)):
        score += 40.0
    elif norm_query and all(w in cand_title for w in norm_query.split()):
        score += 30.0
    elif norm_query and any(w in cand_title for w in norm_query.split()):
        score += 15.0
    else:
        score += 5.0

    if is_single:
        score += 20.0

    # 2. Runtime Proximity (0 to 40 points, or penalty if extreme mismatch)
    cand_runtime = candidate.get("runtime")
    if duration_seconds and isinstance(cand_runtime, (int, float)) and cand_runtime > 0:
        disc_minutes = duration_seconds / 60.0
        diff = abs(disc_minutes - float(cand_runtime))
        if diff <= 5.0:
            score += 40.0
        elif diff <= 12.0:
            score += 30.0
        elif diff <= 20.0:
            score += 15.0
        elif diff <= 35.0:
            score += 0.0
        else:
            score -= 30.0

    # 3. Year Matching (0 to 20 points)
    cand_date = candidate.get("release_date") or ""
    cand_year = None
    if len(cand_date) >= 4 and cand_date[:4].isdigit():
        cand_year = int(cand_date[:4])
    if year and cand_year:
        if cand_year == year:
            score += 20.0
        elif abs(cand_year - year) == 1:
            score += 10.0
        else:
            score -= 10.0

    # 4. Metadata Completeness / Vote baseline (0 to 10 points)
    if candidate.get("overview") and candidate.get("poster_path"):
        score += 5.0
    if (candidate.get("vote_count") or 0) > 20:
        score += 5.0

    return score

def _fetch_movie_details(movie_id: int, token: str, is_v4: bool, opener=urllib.request.urlopen) -> dict:
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"} if is_v4 else {"Accept": "application/json"}
    api_param = "" if is_v4 else f"api_key={token}&"
    details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?{api_param}language=fr-FR&append_to_response=credits"
    request = urllib.request.Request(details_url, headers=headers)
    with opener(request, timeout=8) as response:
        return json.load(response)

def lookup(home: pathlib.Path, query: str, opener=urllib.request.urlopen, duration_seconds: float | None = None, year: int | None = None) -> dict:
    token_path = home / ".config/openhtpc/secrets/tmdb-token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return {"status": "NOT_CONFIGURED"}
    if not token or not query:
        return {"status": "NOT_CONFIGURED"}

    clean_query = clean_disc_title(query)
    if is_generic_query(clean_query):
        return {"status": "NO_RESULT", "query": query}

    is_v4 = token.startswith("ey")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"} if is_v4 else {"Accept": "application/json"}
    api_param = "" if is_v4 else f"api_key={token}&"
    url = f"https://api.themoviedb.org/3/search/movie?{api_param}language=fr-FR&query=" + urllib.parse.quote(clean_query)
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener(request, timeout=8) as response:
            values = json.load(response).get("results", [])
        if not values or not isinstance(values, list):
            return {"status": "NO_RESULT", "query": query}

        norm_query = _normalize_title(clean_query)
        scored_candidates = []
        for idx, item in enumerate(values[:5], 1):
            if not isinstance(item, dict):
                continue
            movie_id = int(item.get("id") or idx)
            details = {}
            if item.get("id") and duration_seconds and len(scored_candidates) < 4:
                try:
                    details = _fetch_movie_details(movie_id, token, is_v4, opener)
                except Exception:
                    details = {}

            merged = dict(item)
            merged.setdefault("id", movie_id)
            if details:
                merged.update(runtime=details.get("runtime"), tagline=details.get("tagline"),
                              genres=[g.get("name") for g in details.get("genres", []) if isinstance(g, dict) and g.get("name")])
                crew = (details.get("credits") or {}).get("crew") or []
                cast = (details.get("credits") or {}).get("cast") or []
                merged.update(director=next((p.get("name") for p in crew if p.get("job") == "Director"), None),
                              writers=[p.get("name") for p in crew if p.get("job") in {"Writer", "Screenplay"} and p.get("name")][:3],
                              cast=[p.get("name") for p in cast if p.get("name")][:5])

            score = _score_candidate(merged, norm_query, duration_seconds, year, is_single=(len(values) == 1))
            scored_candidates.append((score, merged))

        if not scored_candidates:
            return {"status": "NO_RESULT", "query": query}

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_score, top_candidate = scored_candidates[0]
        second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else -100.0

        if top_score >= ACCEPT_THRESHOLD and (top_score - second_score) >= MINIMUM_MARGIN_OVER_SECOND:
            movie_id = int(top_candidate.get("id") or 1)
            if top_candidate.get("id") and not top_candidate.get("director"):
                try:
                    details = _fetch_movie_details(movie_id, token, is_v4, opener)
                    crew = (details.get("credits") or {}).get("crew") or []
                    cast = (details.get("credits") or {}).get("cast") or []
                    top_candidate.update(tagline=details.get("tagline"), runtime=details.get("runtime"),
                                         genres=[g.get("name") for g in details.get("genres", []) if isinstance(g, dict) and g.get("name")],
                                         director=next((p.get("name") for p in crew if p.get("job") == "Director"), None),
                                         writers=[p.get("name") for p in crew if p.get("job") in {"Writer", "Screenplay"} and p.get("name")][:3],
                                         cast=[p.get("name") for p in cast if p.get("name")][:5])
                except Exception:
                    pass
            return {
                "status": "PASS",
                "confidence": "AUTOMATIC_CONFIDENT_MATCH",
                "tmdb_id": movie_id,
                "title": top_candidate.get("title"),
                "release_date": top_candidate.get("release_date"),
                "poster_path": top_candidate.get("poster_path"),
                "overview": top_candidate.get("overview"),
                "tagline": top_candidate.get("tagline"),
                "runtime": top_candidate.get("runtime"),
                "genres": top_candidate.get("genres", []),
                "director": top_candidate.get("director"),
                "writers": top_candidate.get("writers", []),
                "cast": top_candidate.get("cast", []),
                "score": top_score
            }

        plausible = [c for s, c in scored_candidates if s >= 35.0]
        if len(plausible) >= 2 or (len(plausible) == 1 and top_score < ACCEPT_THRESHOLD):
            candidates_list = []
            for s, c in scored_candidates[:3]:
                candidates_list.append({
                    "tmdb_id": int(c["id"]),
                    "title": c.get("title"),
                    "release_date": c.get("release_date"),
                    "original_title": c.get("original_title"),
                    "poster_path": c.get("poster_path"),
                    "overview": c.get("overview"),
                    "runtime": c.get("runtime"),
                    "score": s
                })
            return {
                "status": "AMBIGUOUS",
                "query": query,
                "candidates": candidates_list
            }

        if top_score >= 40.0:
            movie_id = int(top_candidate["id"])
            if not top_candidate.get("director"):
                try:
                    details = _fetch_movie_details(movie_id, token, is_v4, opener)
                    crew = (details.get("credits") or {}).get("crew") or []
                    cast = (details.get("credits") or {}).get("cast") or []
                    top_candidate.update(tagline=details.get("tagline"), runtime=details.get("runtime"),
                                         genres=[g.get("name") for g in details.get("genres", []) if isinstance(g, dict) and g.get("name")],
                                         director=next((p.get("name") for p in crew if p.get("job") == "Director"), None),
                                         writers=[p.get("name") for p in crew if p.get("job") in {"Writer", "Screenplay"} and p.get("name")][:3],
                                         cast=[p.get("name") for p in cast if p.get("name")][:5])
                except Exception:
                    pass
            return {
                "status": "PASS",
                "confidence": "AUTOMATIC_CONFIDENT_MATCH",
                "tmdb_id": movie_id,
                "title": top_candidate.get("title"),
                "release_date": top_candidate.get("release_date"),
                "poster_path": top_candidate.get("poster_path"),
                "overview": top_candidate.get("overview"),
                "tagline": top_candidate.get("tagline"),
                "runtime": top_candidate.get("runtime"),
                "genres": top_candidate.get("genres", []),
                "director": top_candidate.get("director"),
                "writers": top_candidate.get("writers", []),
                "cast": top_candidate.get("cast", []),
                "score": top_score
            }

        return {"status": "NO_RESULT", "query": query}

    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"status": "AUTH_FAILED"}
        return {"status": "UNAVAILABLE"}
    except Exception:
        return {"status": "UNAVAILABLE"}

def commit_binding(home: pathlib.Path, state: dict, tmdb_id: int, opener=urllib.request.urlopen) -> dict:
    target = _cache_path(home, state)
    if target is None:
        return {"status": "NOT_CONFIGURED"}
    token_path = home / ".config/openhtpc/secrets/tmdb-token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return {"status": "NOT_CONFIGURED"}
    if not token or not tmdb_id:
        return {"status": "NOT_CONFIGURED"}
    is_v4 = token.startswith("ey")
    try:
        details = _fetch_movie_details(int(tmdb_id), token, is_v4, opener)
        crew = (details.get("credits") or {}).get("crew") or []
        cast = (details.get("credits") or {}).get("cast") or []
        result = {
            "status": "PASS",
            "confidence": "USER_CONFIRMED_MATCH",
            "tmdb_id": int(tmdb_id),
            "title": details.get("title"),
            "release_date": details.get("release_date"),
            "poster_path": details.get("poster_path"),
            "overview": details.get("overview"),
            "tagline": details.get("tagline"),
            "runtime": details.get("runtime"),
            "genres": [g.get("name") for g in details.get("genres", []) if isinstance(g, dict) and g.get("name")],
            "director": next((p.get("name") for p in crew if p.get("job") == "Director"), None),
            "writers": [p.get("name") for p in crew if p.get("job") in {"Writer", "Screenplay"} and p.get("name")][:3],
            "cast": [p.get("name") for p in cast if p.get("name")][:5]
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        poster(home, result, opener)
        return result
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"status": "AUTH_FAILED"}
        return {"status": "UNAVAILABLE"}
    except Exception:
        return {"status": "UNAVAILABLE"}

def disc_metadata(home: pathlib.Path, state: dict, title: str, enrich: bool=False, opener=urllib.request.urlopen) -> dict:
    has_token = (home / ".config/openhtpc/secrets/tmdb-token").is_file()
    disc_id = str(state.get("disc_id") or "").strip()
    if not disc_id:
        return {"status": "NOT_CONFIGURED" if not has_token else "PENDING", "query": ""}

    target = _cache_path(home, state)
    if target is None:
        return {"status": "NOT_CONFIGURED" if not has_token else "PENDING", "query": ""}

    cached = None
    try:
        cached = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = None

    if isinstance(cached, dict):
        status = cached.get("status")
        confidence = cached.get("confidence")

        # 1. Authoritative PASS matches are always reused directly
        if status == "PASS" and confidence in AUTHORITATIVE_CONFIDENCE and cached.get("title"):
            return cached

        # 2. Stable AMBIGUOUS matches with candidate list are reused directly
        if status == "AMBIGUOUS" and cached.get("candidates"):
            return cached

        # 3. If not enrich: return valid non-pending/non-unconfigured cached state if available
        if not enrich:
            if status == "PASS" and cached.get("title"):
                return cached
            if status in {"AMBIGUOUS", "NO_RESULT", "AUTH_FAILED", "UNAVAILABLE"}:
                return cached
            return {"status": "NOT_CONFIGURED" if not has_token else "PENDING", "query": title}

    if not enrich:
        return {"status": "NOT_CONFIGURED" if not has_token else "PENDING", "query": title}

    dur = state.get("duration") or state.get("physical_edition", {}).get("duration")
    dur_sec = None
    if dur is not None:
        try: dur_sec = float(dur)
        except (ValueError, TypeError): pass

    data = lookup(home, title, opener, duration_seconds=dur_sec)
    data["query"] = title
    if data.get("status") in {"PASS", "AMBIGUOUS", "NO_RESULT", "AUTH_FAILED", "UNAVAILABLE"}:
        if data.get("status") == "PASS":
            poster(home, data, opener)
        elif data.get("status") == "AMBIGUOUS":
            for cand in data.get("candidates", [])[:3]:
                if cand.get("poster_path"):
                    p_file = poster(home, {"status": "PASS", "poster_path": cand["poster_path"]}, opener)
                    if p_file: cand["poster_file"] = str(p_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    return data

def poster(home: pathlib.Path, metadata: dict, opener=urllib.request.urlopen) -> pathlib.Path | None:
    remote = metadata.get("poster_path")
    if metadata.get("status") != "PASS" or not isinstance(remote, str) or not remote.startswith("/"):
        return None
    target = home / ".cache/openhtpc/tmdb" / (hashlib.sha256(remote.encode()).hexdigest() + ".jpg")
    if target.is_file() and target.stat().st_size:
        return target
    request = urllib.request.Request("https://image.tmdb.org/t/p/w500" + remote)
    try:
        with opener(request, timeout=8) as response:
            data = response.read(5_000_001)
        if not data or len(data) > 5_000_000 or not data.startswith(b"\xff\xd8"):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.chmod(0o600)
        temporary.replace(target)
        return target
    except (OSError, ValueError):
        return None
