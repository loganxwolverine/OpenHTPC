#!/usr/bin/env python3
"""OPENHTPC Basic session gates and deterministic Flex home generation."""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import tempfile
import hashlib
import fcntl
import importlib.util
import importlib.machinery
import re
import shlex
import sys
import time
from contextlib import contextmanager

_optical_spec = importlib.util.spec_from_file_location("openhtpc_optical_presentation", pathlib.Path(__file__).with_name("openhtpc-optical.py"))
_optical_model = importlib.util.module_from_spec(_optical_spec); _optical_spec.loader.exec_module(_optical_model)


def load_theme(install: pathlib.Path):
    import importlib.util
    path = install / "openhtpc-theme.py"
    if not path.is_file():
        path = pathlib.Path(__file__).with_name("openhtpc-theme.py")
    spec = importlib.util.spec_from_file_location("openhtpc_theme", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateError(RuntimeError):
    def __init__(self, gate: str, reason: str, message: str):
        super().__init__(message)
        self.gate = gate
        self.reason = reason


def load_object(path: pathlib.Path, gate: str, missing: str, invalid: str) -> dict:
    if not path.is_file():
        raise GateError(gate, missing, f"Fichier requis absent : {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(gate, invalid, f"Fichier JSON invalide : {path}") from exc
    if not isinstance(value, dict):
        raise GateError(gate, invalid, f"Objet JSON attendu : {path}")
    return value


def validate_profile(profile: dict) -> None:
    required = ("generator", "detected", "gpu_topology", "video_backend", "runtime", "runtime_profiles")
    if not all(isinstance(profile.get(key), dict) for key in required):
        raise GateError("hardware_profile", "PROFILE_INVALID", "Le profil matériel CURRENT est incomplet.")
    generator = profile["generator"]
    if generator.get("name") != "OPENHTPC Builder" or not generator.get("version"):
        raise GateError("hardware_profile", "PROFILE_INVALID", "Le profil ne provient pas du Builder OPENHTPC CURRENT.")


def validate_capability_provenance(profile: dict, snapshot: dict) -> None:
    if not snapshot:
        return
    source = profile.get("capability_source")
    if not isinstance(source, dict) or not all(source.get(key) for key in ("hardware_fingerprint", "runtime_fingerprint")):
        raise GateError("hardware_profile", "PASSPORT_REBUILD_REQUIRED", "Le Hardware Passport legacy doit être reconstruit.")
    if any(source.get(key) != snapshot.get(key) for key in ("hardware_fingerprint", "runtime_fingerprint")):
        raise GateError("hardware_profile", "PASSPORT_STALE", "Le Hardware Passport ne correspond pas aux capacités courantes.")
    runtime_source = profile.get("runtime", {}).get("generation_provenance", {}).get("capability_source")
    if runtime_source != source:
        raise GateError("runtime", "RUNTIME_STALE", "Le runtime ne correspond pas au Hardware Passport courant.")


def viability(profile: dict) -> dict:
    backend = profile["video_backend"]
    topology = profile["gpu_topology"]
    processing = topology.get("processing_gpu")
    failures = []
    if backend.get("status") != "observed":
        failures.append("backend vidéo non observé")
    if not backend.get("decode_api"):
        failures.append("API de décodage non observée")
    if not backend.get("render_api"):
        failures.append("API de rendu non observée")
    if not backend.get("render_node"):
        failures.append("render node absent")
    if not isinstance(processing, dict):
        failures.append("GPU de traitement non associé")
    if topology.get("offload_required") is True and topology.get("offload_validated") is not True:
        failures.append("chemin multi-GPU non validé")
    return {
        "status": "PASS" if not failures else "FAIL",
        "basis": "CURRENT observed backend and GPU topology",
        "failures": failures,
    }


def validate_runtime(profile: dict, home: pathlib.Path) -> None:
    runtime = profile["runtime"]
    profiles = profile["runtime_profiles"].get("profiles")
    pure = profiles.get("PURE") if isinstance(profiles, dict) else None
    if runtime.get("status") != "ready" or runtime.get("playback_validated") not in (False, True):
        raise GateError("runtime", "RUNTIME_NOT_READY", "Le runtime MPV CURRENT n'est pas prêt.")
    if not isinstance(pure, dict) or pure.get("generation_status") != "generated":
        raise GateError("runtime", "PURE_NOT_GENERATED", "Le profil PURE CURRENT n'est pas généré.")
    config = pure.get("config_path")
    if not isinstance(config, str) or not config:
        config = str(home / ".config/openhtpc/runtime/mpv/pure.conf")
    path = pathlib.Path(config)
    if not path.is_absolute():
        raise GateError("runtime", "RUNTIME_CONFIG_INVALID", "Le chemin du runtime PURE n'est pas absolu.")
    if not path.is_file():
        raise GateError("runtime", "RUNTIME_CONFIG_MISSING", f"Configuration PURE absente : {path}")


def validate_user_config(config: dict, credential: pathlib.Path) -> list[pathlib.Path]:
    if config.get("configuration_completed") is not True:
        raise GateError("initial_configuration", "CONFIGURATION_INCOMPLETE", "La configuration initiale n'est pas terminée.")
    sources = config.get("local_media_sources")
    tmdb = config.get("tmdb")
    if not isinstance(sources, list) or not isinstance(tmdb, dict) or not isinstance(tmdb.get("configured"), bool):
        raise GateError("initial_configuration", "CONFIGURATION_INVALID", "La configuration utilisateur est invalide.")
    paths = []
    for source in sources:
        if not isinstance(source, str) or not pathlib.Path(source).is_absolute():
            raise GateError("initial_configuration", "CONFIGURATION_INVALID", "Chaque source média doit être un chemin absolu.")
        paths.append(pathlib.Path(source))
    if tmdb["configured"]:
        try:
            mode = stat.S_IMODE(credential.stat().st_mode)
            present = credential.is_file() and credential.stat().st_size > 0
        except OSError:
            present, mode = False, 0
        if not present or mode & 0o077:
            raise GateError("initial_configuration", "TMDB_CREDENTIAL_INVALID", "La configuration TMDb privée est absente ou insuffisamment protégée.")
    return paths


def ini_value(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace(";", "—")


def normalized_disc_title(value: object) -> str:
    """Return a conservative couch label while retaining raw state elsewhere."""
    title = ini_value(str(value or "")).strip()
    title = re.sub(r"(?i)(?:[ _.-]+)(?:DVD|DISC|DISK)\s*[12]\s*$", "", title).strip()
    return title or "Disque identifié"


def optical_home_label(optical: dict) -> str:
    title = normalized_disc_title(
        optical.get("tmdb_title") or optical.get("disc_title") or
        optical.get("normalized_volume_label") or optical.get("volume_label")
    )
    prefix = _optical_model.presentation(optical)["home_prefix"]
    # Flex receives the complete title. It can use the available item width;
    # the disc sheet remains the authoritative full-title presentation.
    return f"{prefix} - {title}"


def dvd_home_label(optical: dict, limit: int | None = None) -> str:
    """Compatibility name for callers from older Basic RCs."""
    return optical_home_label({**optical, "state": "DVD"})


def observed_display_size(environment=None) -> tuple[int, int] | None:
    environment = os.environ if environment is None else environment
    override = environment.get("OPENHTPC_DISPLAY_SIZE")
    if override:
        try:
            width, height = (int(value) for value in override.lower().split("x", 1))
            return (width, height) if width > 0 and height > 0 else None
        except ValueError:
            return None
    try:
        home = pathlib.Path(environment.get("OPENHTPC_HOME", pathlib.Path.home())) if isinstance(environment, dict) else pathlib.Path.home()
        install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
        cap_path = install / "openhtpc-capabilities.py"
        if not cap_path.is_file():
            cap_path = pathlib.Path(__file__).with_name("openhtpc-capabilities.py")
        caps = sys.modules.get("openhtpc_capabilities")
        if caps is None and cap_path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_capabilities", cap_path)
                if spec and spec.loader:
                    caps = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(caps)
            except Exception:
                caps = None
        context = {"status": "UNAVAILABLE", "environment": {}}
        if caps is not None and hasattr(caps, "resolve_graphical_context"):
            try:
                context = caps.resolve_graphical_context(environment=environment if isinstance(environment, dict) else None, home=home, install=install)
            except Exception:
                pass
        if (
            context.get("status") != "RESOLVED"
            or not context.get("environment")
            or (hasattr(caps, "is_graphical_context_usable") and not caps.is_graphical_context_usable(context["environment"]))
        ):
            return None
        env = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
            env.pop(key, None)
        env.update(context["environment"])
        result = subprocess.run(["kscreen-doctor", "-j"], env=env, text=True, capture_output=True, timeout=5)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        sizes = []
        for output in data.get("outputs", []):
            if not output.get("enabled"):
                continue
            current = output.get("currentModeId")
            mode = next((item for item in output.get("modes", []) if item.get("id") == current), None)
            size = (mode or {}).get("size", {})
            if size.get("width") and size.get("height"):
                sizes.append((int(size["width"]), int(size["height"])))
        return max(sizes, key=lambda item: item[0] * item[1]) if sizes else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError, ValueError):
        return None


def flex_scale(size: tuple[int, int] | None) -> dict[str, int]:
    basis = min(size) if size else 1080
    return {
        "icon": max(165, min(280, round(basis * 0.17))),
        "title": max(42, min(72, round(basis * 0.049))),
        "clock": max(34, min(74, round(basis * 0.043))),
        "padding": max(16, min(32, round(basis * 0.018))),
    }


def _load_media_types():
    import importlib.util
    for base in (pathlib.Path(__file__).resolve().parent, pathlib.Path.home() / ".local/lib/openhtpc"):
        target = base / "openhtpc-media-types.py"
        if target.is_file():
            spec = importlib.util.spec_from_file_location("openhtpc_media_types", target)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None

_media_types = _load_media_types()
VIDEO_EXTENSIONS = _media_types.VIDEO_EXTENSIONS if _media_types is not None else {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}


def menu_name(prefix: str, value: object) -> str:
    return prefix + "_" + hashlib.blake2s(str(value).encode("utf-8"), digest_size=8).hexdigest()


def media_source_id(path: pathlib.Path) -> str:
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


def media_item_id(source_id: str, relative_path: pathlib.PurePath, item_type: str) -> str:
    value=f"media:{source_id}:{item_type}:{relative_path.as_posix()}"
    return hashlib.blake2s(value.encode("utf-8"),digest_size=12).hexdigest()


def media_action_token(generation: str, item_id: str) -> str:
    value = f"{generation}:{item_id}"
    return "mact_" + hashlib.blake2s(value.encode("utf-8"), digest_size=16).hexdigest()


def current_media_manifest(home: pathlib.Path) -> pathlib.Path:
    return home/".local/state/openhtpc/media-actions/current.json"


def active_media_generation(home: pathlib.Path) -> str | None:
    """Return the generation bound to the authoritative active MEDIA manifest."""
    model = load_optional_object(current_media_manifest(home))
    generation = model.get("manifest_generation")
    return generation if isinstance(generation, str) and generation else None


def write_media_model_state(home: pathlib.Path, generation: str, sources: list[dict], actions: dict[str, dict], target: pathlib.Path | None = None) -> pathlib.Path:
    target=target or current_media_manifest(home);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            # This file is the current UI model registry, not a media database.
            # Atomic replacement invalidates every token from the old model.
            data={"schema":1,"manifest_generation":generation,"sources":sources,"items":actions}
            json.dump(data,stream,ensure_ascii=False,sort_keys=True);stream.write("\n")
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return target


_POSTER_TOKEN_RE = re.compile(r"^/[A-Za-z0-9_-]+\.jpg$")
_MAX_POSTER_TOKEN_CHARS = 128
_MAX_POSTER_BYTES = 5_000_000


def _canonical_poster_path(poster_path: str, home: pathlib.Path) -> pathlib.Path | None:
    """Resolve canonical cache path for a validated TMDb movie poster token."""
    if not isinstance(poster_path, str) or len(poster_path) > _MAX_POSTER_TOKEN_CHARS or not _POSTER_TOKEN_RE.fullmatch(poster_path):
        return None
    material = f"tmdb_movie|poster|w500|{poster_path}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500" / f"{digest}.jpg"


def _project_work_poster(home: pathlib.Path, work_id: int, payload_json: str | None, uid: int) -> pathlib.Path | None:
    """Safely project a verified cached poster to an ephemeral short symlink in /tmp.

    Stale symlinks from previous presentations are unlinked.
    Non-symlink objects at the alias path are never blindly overwritten.
    Returns the short symlink Path if valid, or None (fallback to generic icon).
    """
    if type(work_id) is not int or work_id <= 0:
        return None
    alias_path = pathlib.Path(f"/tmp/ohtpc-{uid}-p{work_id}.jpg")

    def _cleanup_stale_alias() -> None:
        if alias_path.is_symlink():
            try:
                alias_path.unlink(missing_ok=True)
            except OSError:
                pass

    if payload_json is None:
        _cleanup_stale_alias()
        return None

    try:
        payload = json.loads(payload_json)
    except Exception:
        _cleanup_stale_alias()
        return None

    if not isinstance(payload, dict):
        _cleanup_stale_alias()
        return None

    token = payload.get("poster_path")
    canonical_target = _canonical_poster_path(token, home)
    if canonical_target is None:
        _cleanup_stale_alias()
        return None

    try:
        if canonical_target.is_symlink() or not canonical_target.is_file():
            _cleanup_stale_alias()
            return None
        st = canonical_target.stat()
        if not (0 < st.st_size <= _MAX_POSTER_BYTES):
            _cleanup_stale_alias()
            return None
    except OSError:
        _cleanup_stale_alias()
        return None

    # Defense against unsafe pre-existing non-symlink object at alias path
    if alias_path.exists(follow_symlinks=False) and not alias_path.is_symlink():
        return None

    # Atomic symlink update
    temp_alias = pathlib.Path(f"/tmp/.ohtpc-{uid}-p{work_id}-{os.getpid()}-{time.time_ns()}.tmp")
    try:
        temp_alias.symlink_to(canonical_target)
        os.replace(temp_alias, alias_path)
        return alias_path
    except OSError:
        try:
            if temp_alias.is_symlink() or temp_alias.exists(follow_symlinks=False):
                temp_alias.unlink(missing_ok=True)
        except OSError:
            pass
        _cleanup_stale_alias()
        return None


def _extract_year(release_date: Any, fallback_year: Any = None) -> str | None:
    """Extract 4-digit release year from date string or fallback year."""
    if isinstance(release_date, str) and release_date.strip():
        m = re.match(r"^\s*(\d{4})", release_date.strip())
        if m:
            return m.group(1)
    if fallback_year is not None and not isinstance(fallback_year, bool):
        try:
            y = int(fallback_year)
            if 1800 <= y <= 2100:
                return str(y)
        except (ValueError, TypeError):
            pass
    return None


def _format_runtime(runtime_minutes: Any) -> str | None:
    """Format movie runtime in minutes to compact French couch string (e.g. 109 -> '1 h 49')."""
    if runtime_minutes is None or isinstance(runtime_minutes, bool):
        return None
    try:
        minutes = int(runtime_minutes)
    except (ValueError, TypeError):
        return None
    if minutes <= 0:
        return None
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    rem = minutes % 60
    if rem > 0:
        return f"{hours} h {rem:02d}"
    return f"{hours} h"


def _format_genres(genres_json: Any) -> str | None:
    """Parse genres_json safely and format as comma-separated French string."""
    if not genres_json or not isinstance(genres_json, str):
        return None
    try:
        data = json.loads(genres_json)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    cleaned: list[str] = []
    for g in data:
        if isinstance(g, str) and g.strip():
            val = ini_value(g.strip()).strip()
            if val:
                cleaned.append(val)
        elif isinstance(g, dict) and isinstance(g.get("name"), str) and g["name"].strip():
            val = ini_value(g["name"].strip()).strip()
            if val:
                cleaned.append(val)
    if cleaned:
        return ", ".join(cleaned)
    return None


def _chunk_synopsis(overview: str, max_row_bytes: int = 120, max_rows: int = 2) -> list[str]:
    """Break untrusted overview into up to two Flex-safe, couch-readable rows."""
    cleaned = ini_value(overview).strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ["Aucun synopsis disponible."]

    words = cleaned.split(" ")
    rows: list[str] = []
    current_words: list[str] = []

    i = 0
    while i < len(words) and len(rows) < max_rows:
        word = words[i]
        test_line = " ".join(current_words + [word]) if current_words else word
        if len(test_line.encode("utf-8")) <= max_row_bytes:
            current_words.append(word)
            i += 1
        else:
            if current_words:
                rows.append(" ".join(current_words))
                current_words = []
            else:
                chars: list[str] = []
                for ch in word:
                    if len("".join(chars + [ch]).encode("utf-8")) <= max_row_bytes:
                        chars.append(ch)
                    else:
                        break
                part1 = "".join(chars)
                rows.append(part1)
                remaining_word = word[len(chars):]
                words[i] = remaining_word

    if current_words and len(rows) < max_rows:
        rows.append(" ".join(current_words))

    if i < len(words) and rows:
        last = rows[-1]
        ellipsis = "…"
        while last and len((last + ellipsis).encode("utf-8")) > max_row_bytes:
            last = last[:-1].rstrip()
        rows[-1] = last + ellipsis

    return rows if rows else ["Aucun synopsis disponible."]


def _chunk_synopsis_properties(overview: str, max_chunk_bytes: int = 135, max_chunks: int = 16) -> list[str]:
    """Split overview text into word-bounded chunks suitable for Synopsis1..N INI properties."""
    cleaned = ini_value(overview.replace("\n", " ").replace("\r", " ")).strip()
    if not cleaned:
        return ["Aucun synopsis disponible."]
    words = cleaned.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_bytes = 0
    for w in words:
        w_bytes = len(w.encode("utf-8"))
        if w_bytes > max_chunk_bytes:
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = []
                current_bytes = 0
            chunks.append(w[:max_chunk_bytes // 2])
            continue
        extra = 1 if current_words else 0
        if current_bytes + extra + w_bytes <= max_chunk_bytes:
            current_words.append(w)
            current_bytes += extra + w_bytes
        else:
            if current_words:
                chunks.append(" ".join(current_words))
            current_words = [w]
            current_bytes = w_bytes
        if len(chunks) >= max_chunks:
            break
    if current_words and len(chunks) < max_chunks:
        chunks.append(" ".join(current_words))
    return chunks if chunks else ["Aucun synopsis disponible."]


def _build_movie_detail_section(
    section_id: str,
    token: str,
    stem: str,
    ext: str,
    ident: dict[str, Any] | None,
    pres_info: dict[str, Any] | None,
    item_icon: pathlib.Path,
    entry_icon: pathlib.Path,
    res_menu: str,
) -> str:
    """Construct one hermetic native movie detail [MEDIA_D...] section."""
    lines: list[str] = [
        f"[{section_id}]",
        "Layout=MovieDetail",
    ]
    play_cmd = f"$HOME/.local/lib/openhtpc/openhtpc-play {token}"

    # Determine presentation validity
    is_unmatched = (ident is None) or (ident.get("work_id") is None) or (ident.get("identification_state") == "UNMATCHED")
    is_malformed = False
    if pres_info is not None:
        raw_payload = pres_info.get("payload_json")
        if raw_payload:
            try:
                parsed_payload = json.loads(raw_payload)
                if not isinstance(parsed_payload, dict):
                    is_malformed = True
            except Exception:
                is_malformed = True
        disp_title_val = pres_info.get("display_title")
        if disp_title_val is not None and not isinstance(disp_title_val, str):
            is_malformed = True
        overview_val = pres_info.get("overview")
        if overview_val is not None and not isinstance(overview_val, str):
            is_malformed = True

    # 1. Poster property
    lines.append(f"Poster={item_icon}")

    # 2. Title & Original Title properties
    disp_title = ""
    disp_orig = ""
    if not is_unmatched and not is_malformed and pres_info and isinstance(pres_info.get("display_title"), str) and pres_info["display_title"].strip():
        disp_title = ini_value(pres_info["display_title"]).strip()
        if isinstance(pres_info.get("display_original_title"), str):
            disp_orig = ini_value(pres_info["display_original_title"]).strip()
    elif not is_unmatched and ident and isinstance(ident.get("title"), str) and ident["title"].strip():
        disp_title = ini_value(ident["title"]).strip()
        if isinstance(ident.get("original_title"), str):
            disp_orig = ini_value(ident["original_title"]).strip()
    else:
        disp_title = ini_value(stem).strip() or "Vidéo"

    while len(f"Title={disp_title}".encode("utf-8")) > 155:
        disp_title = disp_title[:-1].rstrip()
    lines.append(f"Title={disp_title}")

    if disp_orig and disp_orig.casefold() != disp_title.casefold():
        while len(f"OriginalTitle={disp_orig}".encode("utf-8")) > 155:
            disp_orig = disp_orig[:-1].rstrip()
        lines.append(f"OriginalTitle={disp_orig}")

    # 3. Metadata property
    meta_parts: list[str] = []
    if not is_unmatched and not is_malformed:
        yr = None
        if pres_info and pres_info.get("release_date"):
            yr = _extract_year(pres_info["release_date"], ident.get("year") if ident else None)
        elif ident and ident.get("year"):
            yr = _extract_year(None, ident["year"])
        if yr:
            meta_parts.append(yr)

        if pres_info and pres_info.get("runtime_minutes") is not None:
            rt = _format_runtime(pres_info["runtime_minutes"])
            if rt:
                meta_parts.append(rt)

        if pres_info and pres_info.get("genres_json"):
            gn = _format_genres(pres_info["genres_json"])
            if gn:
                meta_parts.append(gn)

    if meta_parts:
        meta_label = " · ".join(meta_parts)
    else:
        tech_ext = ext[1:].upper() if ext else "FICHIER VIDÉO"
        if not is_unmatched and ident and ident.get("year"):
            meta_label = f"{ident['year']} · {tech_ext}"
        elif is_unmatched:
            meta_label = "Média local non identifié"
        else:
            meta_label = tech_ext

    while len(f"Metadata={meta_label}".encode("utf-8")) > 155:
        meta_label = meta_label[:-1].rstrip()
    lines.append(f"Metadata={meta_label}")

    # 4. Synopsis properties (Synopsis1..N)
    if is_unmatched:
        raw_synopsis = "Fichier local non identifié."
    elif is_malformed:
        raw_synopsis = "Présentation non disponible."
    elif pres_info is not None:
        overview = pres_info.get("overview")
        if isinstance(overview, str) and overview.strip():
            raw_synopsis = overview
        else:
            raw_synopsis = "Aucun synopsis disponible."
    elif ident and ident.get("work_id"):
        raw_synopsis = "Aucun synopsis disponible."
    else:
        raw_synopsis = "Présentation non disponible."

    synopsis_chunks = _chunk_synopsis_properties(raw_synopsis, max_chunk_bytes=135, max_chunks=16)
    for idx, chunk in enumerate(synopsis_chunks, 1):
        lines.append(f"Synopsis{idx}={chunk}")

    # 5. Exactly three focusable action entries:
    # Entry 1: LIRE LE FILM
    lines.append(bounded_flex_entry(1, "LIRE LE FILM", item_icon, play_cmd))

    # Entry 2: CHANGER L’IDENTIFICATION / IDENTIFIER LE FILM
    if is_unmatched:
        ident_label = "IDENTIFIER LE FILM"
    else:
        ident_label = "CHANGER L’IDENTIFICATION"
    lines.append(bounded_flex_entry(2, ident_label, entry_icon, f":submenu {res_menu}"))

    # Entry 3: RETOUR
    lines.append(bounded_flex_entry(3, "RETOUR", entry_icon, ":back"))

    return "\n".join(lines)


def media_menu_sections(home: pathlib.Path, sources: list[pathlib.Path], icon: pathlib.Path, generation: str = "test-generation", manifest_target: pathlib.Path | None = None) -> tuple[str, str]:
    """Build a bounded complete media graph before the persistent Flex starts."""
    sections: list[str] = []
    actions: dict[str, dict] = {}
    unmatched_entries: list[tuple[str, pathlib.Path, str]] = []
    unmatched_resources: list[tuple[int, str, str]] = []
    generated_detail_ids: set[str] = set()
    source_roots: dict[str, pathlib.Path] = {}
    visited: set[pathlib.Path] = set(); inventory=[]
    install = home / ".local/lib/openhtpc"
    picker_bin = install / "openhtpc-media-picker"
    remove_bin = install / "openhtpc-media-remove"
    add_icon = icon
    folder_icon = home / ".local/lib/openhtpc/assets/ui/folder.png"
    remove_icon = home / ".local/lib/openhtpc/flex/assets/icons/drive-empty.png"

    # Short icon symlinks for line buffer economy (libinih INI_MAX_LINE 200)
    uid = os.getuid()
    short_icon = pathlib.Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(icon)
        entry_icon = short_icon
    except OSError:
        entry_icon = icon

    short_remove_icon = pathlib.Path(f"/tmp/ohtpc-{uid}-d.png")
    try:
        if short_remove_icon.is_symlink() or short_remove_icon.is_file():
            short_remove_icon.unlink(missing_ok=True)
        short_remove_icon.symlink_to(remove_icon)
        effective_remove_icon = short_remove_icon
    except OSError:
        effective_remove_icon = remove_icon

    # Preload identity map from media.db if present (single read-only pass)
    media_db_path = home / ".local/share/openhtpc/media/media.db"
    identity_map: dict[tuple[str, str], dict[str, Any]] = {}
    work_posters: dict[int, pathlib.Path] = {}
    if media_db_path.is_file():
        pres_map: dict[int, dict[str, Any]] = {}
        try:
            import sqlite3
            with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                rows = db.execute(
                    """
                    SELECT r.source_id, r.relative_path, r.media_version_id,
                           mv.identification_state, mv.match_locked, mv.work_id,
                           w.title, w.year, w.original_title,
                           (SELECT COUNT(*) FROM match_candidates mc WHERE mc.media_version_id = mv.id AND mc.status != 'REJECTED') AS cand_count
                    FROM resources r
                    JOIN media_versions mv ON mv.id = r.media_version_id
                    LEFT JOIN works w ON w.id = mv.work_id
                    """
                ).fetchall()
                for r in rows:
                    identity_map[(r[0], r[1])] = {
                        "media_version_id": r[2],
                        "identification_state": r[3],
                        "match_locked": r[4],
                        "work_id": r[5],
                        "title": r[6],
                        "year": r[7],
                        "original_title": r[8],
                        "candidate_count": r[9] or 0,
                    }

                unmatched_resources = db.execute(
                    """
                    SELECT mv.id, r.source_id, r.relative_path
                    FROM media_versions mv
                    JOIN resources r ON r.media_version_id = mv.id
                    WHERE mv.identification_state = 'UNMATCHED'
                      AND r.resource_kind = 'FILE'
                      AND r.availability_status = 'AVAILABLE'
                      AND r.source_id IS NOT NULL
                      AND r.relative_path IS NOT NULL
                    ORDER BY mv.id, r.source_id, r.relative_path, r.id
                    """
                ).fetchall()

                # DEV6B2 / DEV6B3: Batch presentation lookup for fr-FR movie posters & details
                # Provenance chain: work_presentations -> provider_snapshots -> external_ids
                pres_rows = db.execute(
                    """
                    SELECT wp.work_id, ps.payload_json,
                           wp.display_title, wp.display_original_title,
                           wp.release_date, wp.runtime_minutes,
                           wp.overview, wp.genres_json
                    FROM work_presentations wp
                    JOIN provider_snapshots ps ON ps.id = wp.source_snapshot_id
                    JOIN external_ids e ON e.id = ps.external_id_id
                    WHERE wp.locale = 'fr-FR'
                      AND ps.snapshot_kind = 'MOVIE_DETAILS'
                      AND ps.locale = 'fr-FR'
                      AND e.provider = 'tmdb_movie'
                      AND e.work_id = wp.work_id
                    """
                ).fetchall()
                for r in pres_rows:
                    pres_map[r[0]] = {
                        "payload_json": r[1],
                        "display_title": r[2],
                        "display_original_title": r[3],
                        "release_date": r[4],
                        "runtime_minutes": r[5],
                        "overview": r[6],
                        "genres_json": r[7],
                    }
        except Exception:
            identity_map = {}
            pres_map = {}
            unmatched_resources = []

        distinct_work_ids = {info["work_id"] for info in identity_map.values() if info.get("work_id") is not None}
        for wid in distinct_work_ids:
            pres_info = pres_map.get(wid)
            payload_json = pres_info.get("payload_json") if pres_info else None
            poster_link = _project_work_poster(home, wid, payload_json, uid)
            if poster_link is not None:
                work_posters[wid] = poster_link

    # Load UI helper for resolver menu construction
    match_ui = None
    ui_script = install / "openhtpc-media-match-ui"
    if not ui_script.is_file():
        ui_script = pathlib.Path(__file__).resolve().parent / "openhtpc-media-match-ui"
    if ui_script.is_file():
        try:
            import importlib.machinery
            loader = importlib.machinery.SourceFileLoader("openhtpc_media_match_ui", str(ui_script))
            spec = importlib.util.spec_from_loader("openhtpc_media_match_ui", loader)
            if spec and spec.loader:
                match_ui = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(match_ui)
        except Exception:
            match_ui = None

    def section_for(folder: pathlib.Path, source_root: pathlib.Path, source_id: str, depth: int = 0) -> str | None:
        try: resolved = folder.resolve(strict=True)
        except OSError: return None
        if resolved in visited or len(visited) >= 64 or depth > 3: return None
        visited.add(resolved); name = menu_name("MEDIA", resolved)
        entries = [("RETOUR", icon, ":back")]
        try:
            with os.scandir(resolved) as scanner:
                items = sorted(list(scanner), key=lambda it: it.name.casefold())
        except OSError:
            items = []
        for item in items:
            try:
                if item.is_dir(follow_symlinks=True):
                    child_path = pathlib.Path(item.path)
                    target = section_for(child_path, source_root, source_id, depth + 1)
                    if target:
                        relative = child_path.relative_to(source_root)
                        item_id = media_item_id(source_id, relative, "directory")
                        token = media_action_token(generation, item_id)
                        actions[token] = {"page_id": name, "item_type": "directory", "source_id": source_id, "relative_path": relative.as_posix(), "semantic_id": item_id}
                        entries.append(("DOSSIER — " + ini_value(item.name), folder_icon, f":submenu {target}"))
                elif item.is_file(follow_symlinks=True):
                    ext = os.path.splitext(item.name)[1].casefold()
                    if ext in VIDEO_EXTENSIONS:
                        child_path = pathlib.Path(item.path)
                        relative = child_path.relative_to(source_root)
                        item_id = media_item_id(source_id, relative, "file")
                        token = media_action_token(generation, item_id)
                        detail_menu = f"MEDIA_D{item_id[:8]}"
                        actions[token] = {"page_id": detail_menu, "parent_page_id": name, "item_type": "file", "source_id": source_id, "relative_path": relative.as_posix(), "semantic_id": item_id}
                        stem = os.path.splitext(item.name)[0]
                        ident = identity_map.get((source_id, relative.as_posix()))
                        mv_id = ident.get("media_version_id") if ident else None
                        state = ident.get("identification_state") if ident else "UNMATCHED"
                        work_id = ident.get("work_id") if ident else None
                        title_source = stem
                        if state in ("AUTO_MATCHED", "USER_MATCHED") and work_id is not None:
                            presentation = pres_map.get(work_id)
                            title_source = (presentation.get("display_title") if presentation else None) or ident.get("title") or stem
                        title = ini_value(title_source)
                        if len(title) > 72: title = title[:69].rstrip() + "…"

                        item_icon = work_posters.get(work_id) if state in ("AUTO_MATCHED", "USER_MATCHED") and work_id is not None else None
                        if item_icon is None:
                            item_icon = entry_icon

                        if state == "AUTO_MATCHED":
                            context_title = "CONFIRMER / CHANGER L’IDENTIFICATION"
                        elif state == "USER_MATCHED":
                            context_title = "CHANGER L’IDENTIFICATION"
                        else:
                            context_title = "IDENTIFIER LE FILM"

                        res_menu = f"MEDIA_R{item_id[:8]}"
                        context_cmd = f":submenu {res_menu}"

                        res_secs = None
                        if match_ui and mv_id is not None and media_db_path.is_file():
                            try:
                                import sqlite3
                                with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                                    res_secs = match_ui.build_resolver_menu_sections(
                                        home=home,
                                        install=install,
                                        db=db,
                                        media_version_id=mv_id,
                                        res_section_id=res_menu,
                                        generation=generation,
                                        actions=actions,
                                        icon=entry_icon,
                                    )
                                    if res_secs:
                                        sections.extend(res_secs)
                            except Exception:
                                res_secs = None
                        if not res_secs:
                            token_suffix = item_id[:8]
                            search_helper_path = "$HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui"
                            ms_menu = f"MEDIA_MS_{token_suffix}"
                            ms_cmd = f":submenu {ms_menu}"
                            ms_launch_cmd = f":applyback {search_helper_path} --token {token}"
                            ms_e1 = bounded_flex_entry(1, "LANCER LA RECHERCHE", entry_icon, ms_launch_cmd)
                            ms_e2 = bounded_flex_entry(2, "RETOUR", entry_icon, ":back")
                            ms_sec = f"[{ms_menu}]\n{ms_e1}\n{ms_e2}"

                            r_e1 = bounded_flex_entry(1, "RECHERCHER MANUELLEMENT", entry_icon, ms_cmd)
                            r_e2 = bounded_flex_entry(2, "Aucune proposition disponible.", entry_icon, ":back")
                            r_e3 = bounded_flex_entry(3, "RETOUR", entry_icon, ":back")
                            res_sec = f"[{res_menu}]\n{r_e1}\n{r_e2}\n{r_e3}"

                            sections.append(res_sec)
                            sections.append(ms_sec)

                        detail_menu = f"MEDIA_D{item_id[:8]}"
                        detail_sec = _build_movie_detail_section(
                            section_id=detail_menu,
                            token=token,
                            stem=stem,
                            ext=ext,
                            ident=ident,
                            pres_info=pres_map.get(work_id) if work_id is not None else None,
                            item_icon=item_icon,
                            entry_icon=entry_icon,
                            res_menu=res_menu,
                        )
                        sections.append(detail_sec)
                        generated_detail_ids.add(detail_menu)

                        parent_cmd = f":submenu {detail_menu}"
                        label = f"{title}  ·  {ext[1:].upper()}"
                        entries.append((label, item_icon, parent_cmd, context_cmd, context_title))
            except OSError:
                continue
        if resolved == source_root.resolve():
            entries.append(("RETIRER CETTE SOURCE D'OPENHTPC", effective_remove_icon, f"$HOME/.local/lib/openhtpc/openhtpc-media-remove \"{str(source_root)}\""))
        body_entries = []
        for i, entry_tuple in enumerate(entries, 1):
            if len(entry_tuple) == 5:
                lbl, ico, cmd, c_cmd, c_title = entry_tuple
                body_entries.append(bounded_flex_entry(i, lbl, ico, cmd, c_cmd, c_title))
            else:
                lbl, ico, cmd = entry_tuple
                body_entries.append(bounded_flex_entry(i, lbl, ico, cmd))
        body = "\n".join(body_entries)
        sections.append(f"[{name}]\n{body}")
        return name

    roots = [("METTRE À JOUR LA MÉDIATHÈQUE", icon,
              f":fork {install / 'openhtpc-media-update-request'}")]
    if not sources:
        roots.append(("+ AJOUTER UNE SOURCE MÉDIA", add_icon, f"{picker_bin}"))
    else:
        for source in sources:
            try:canonical=source.resolve(strict=True)
            except OSError:canonical=None
            sid=media_source_id(canonical) if canonical is not None else media_source_id(source)
            target = section_for(canonical,canonical,sid) if canonical is not None and canonical.is_dir() else None
            if canonical is not None and canonical.is_dir():
                source_roots[sid] = canonical
            inventory.append({"source_id":sid,"configured_path":str(source),"canonical_path":str(canonical) if canonical is not None else None})
            label = ini_value(source.name or str(source)) + ("" if target else " — indisponible")
            source_cmd = f":submenu {target}" if target else ":fork true"
            context_cmd = f"$HOME/.local/lib/openhtpc/openhtpc-media-remove \"{str(source)}\""
            roots.append((label, folder_icon, source_cmd, context_cmd, "RETIRER LA SOURCE"))
        roots.append(("+ AJOUTER UNE SOURCE", add_icon, f"{picker_bin}"))

    # The unmatched view is sourced from the DB, independent of the bounded folder graph.
    unmatched_ids: set[int] = set()
    for mv_id, source_id, relative_path in unmatched_resources:
        if (type(mv_id) is not int or type(source_id) is not str
                or type(relative_path) is not str
                or mv_id in unmatched_ids or source_id not in source_roots):
            continue
        relative = pathlib.PurePosixPath(relative_path)
        if (relative.is_absolute() or not relative.parts
                or any(part in ("", ".", "..") for part in relative.parts)):
            continue
        root = source_roots[source_id]
        try:
            physical = root.joinpath(*relative.parts).resolve(strict=True)
            if root not in physical.parents or not physical.is_file():
                continue
        except (OSError, RuntimeError):
            continue
        ext = relative.suffix.casefold()
        if ext not in VIDEO_EXTENSIONS:
            continue

        item_id = media_item_id(source_id, relative, "file")
        token = media_action_token(generation, item_id)
        detail_menu = f"MEDIA_D{item_id[:8]}"
        res_menu = f"MEDIA_R{item_id[:8]}"
        if detail_menu not in generated_detail_ids:
            actions[token] = {"page_id": detail_menu, "parent_page_id": "MEDIA_UNMATCHED",
                              "item_type": "file", "source_id": source_id,
                              "relative_path": relative.as_posix(), "semantic_id": item_id}
            res_secs = None
            if match_ui:
                try:
                    import sqlite3
                    with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                        res_secs = match_ui.build_resolver_menu_sections(
                            home=home, install=install, db=db, media_version_id=mv_id,
                            res_section_id=res_menu, generation=generation,
                            actions=actions, icon=entry_icon,
                        )
                        if res_secs:
                            sections.extend(res_secs)
                except Exception:
                    res_secs = None
            if not res_secs:
                search_helper_path = "$HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui"
                ms_menu = f"MEDIA_MS_{item_id[:8]}"
                sections.append(f"[{res_menu}]\n" + "\n".join([
                    bounded_flex_entry(1, "RECHERCHER MANUELLEMENT", entry_icon, f":submenu {ms_menu}"),
                    bounded_flex_entry(2, "Aucune proposition disponible.", entry_icon, ":back"),
                    bounded_flex_entry(3, "RETOUR", entry_icon, ":back"),
                ]))
                sections.append(f"[{ms_menu}]\n" + "\n".join([
                    bounded_flex_entry(1, "LANCER LA RECHERCHE", entry_icon,
                                       f":applyback {search_helper_path} --token {token}"),
                    bounded_flex_entry(2, "RETOUR", entry_icon, ":back"),
                ]))
            sections.append(_build_movie_detail_section(
                section_id=detail_menu, token=token, stem=relative.stem, ext=ext,
                ident={"media_version_id": mv_id, "identification_state": "UNMATCHED",
                       "work_id": None},
                pres_info=None, item_icon=entry_icon, entry_icon=entry_icon,
                res_menu=res_menu,
            ))
            generated_detail_ids.add(detail_menu)

        title = ini_value(relative.stem)
        if len(title) > 72:
            title = title[:69].rstrip() + "…"
        unmatched_entries.append((f"{title}  ·  {ext[1:].upper()}", entry_icon,
                                  f":submenu {detail_menu}"))
        unmatched_ids.add(mv_id)

    if unmatched_entries:
        unmatched_body = "\n".join([
            bounded_flex_entry(1, "RETOUR", icon, ":back"),
            *(bounded_flex_entry(i, label, item_icon, command)
              for i, (label, item_icon, command) in enumerate(unmatched_entries, 2)),
        ])
        sections.append(f"[MEDIA_UNMATCHED]\n{unmatched_body}")
        roots.append((f"À identifier — {len(unmatched_entries)}", icon, ":submenu MEDIA_UNMATCHED"))

    roots.append(("RETOUR À OPENHTPC", icon, ":back"))
    root_entries = []
    for i, entry_tuple in enumerate(roots, 1):
        if len(entry_tuple) == 5:
            label, entry_icon_root, command, context_cmd, context_title = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon_root};{command};{context_cmd};{context_title}")
        else:
            label, entry_icon_root, command = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon_root};{command}")
    root_body = "\n".join(root_entries)

    write_media_model_state(home,generation,inventory,actions,manifest_target)
    return "MEDIA_ROOT", "\n\n".join([f"[MEDIA_ROOT]\n{root_body}", *reversed(sections)])


def bounded_flex_entry(
    index: int,
    label: str,
    icon: pathlib.Path,
    command: str,
    context_cmd: str | None = None,
    context_title: str | None = None,
    max_bytes: int = 198,
) -> str:
    """Serialize an Entry line that fits in Flex/inih's 200-byte input buffer."""
    prefix = f"Entry{index}="
    if context_cmd is not None and context_title is not None:
        suffix = f";{icon};{command};{context_cmd};{context_title}"
    else:
        suffix = f";{icon};{command}"
    budget = max_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
    if budget < 1:
        if context_cmd is not None and context_title is not None:
            suffix = f";{icon};{command}"
            budget = max_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
        if budget < 1:
            raise ValueError("Flex entry metadata exceeds parser line limit")
    encoded = label.encode("utf-8")
    if len(encoded) > budget:
        ellipsis = "…"
        media_suffix = ""
        if "  ·  " in label:
            head, tail = label.rsplit("  ·  ", 1)
            media_suffix = f"  ·  {tail}"
            encoded = head.encode("utf-8")
        reserved = len((ellipsis + media_suffix).encode("utf-8"))
        if budget < reserved:
            media_suffix = ""
            reserved = len(ellipsis.encode("utf-8"))
        encoded = encoded[:max(0, budget - reserved)]
        while True:
            try:
                label = encoded.decode("utf-8").rstrip() + ellipsis + media_suffix
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    line = prefix + label + suffix
    if len(line.encode("utf-8")) > max_bytes:
        raise ValueError("Flex entry exceeds parser line limit")
    return line


def protected_optical_menu_policy(home: pathlib.Path, install: pathlib.Path, optical: dict) -> tuple[str, dict, dict]:
    """Resolve protected-optical exposure through the production plugin authority."""
    neutral = {"owned": False, "visible": False, "enabled": False, "action_intent": "NONE"}
    try:
        core_path = install / "openhtpc-core.py"
        spec = importlib.util.spec_from_file_location("openhtpc_menu_p2_core", core_path)
        core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
        registry = core.plugin_status(home, install)
        snapshot = _optical_model.protected_capability(home)
        _, decision = core.protected_optical_playback_decision_projection(home, install, registry, optical, snapshot)
        _, presentation = core.optical_presentation_descriptor(home, install, registry, optical)
        authority, contribution = core.protected_optical_ui_contribution(home, install, registry, presentation, decision)
        return authority, contribution, decision
    except (OSError, ImportError, AttributeError, TypeError, ValueError, SystemExit):
        return "PLUGIN_UNAVAILABLE", neutral, {"playback_action": "DISABLED", "playback_reason": "PLUGIN_BROKEN", "protection": optical.get("protection", "UNKNOWN")}



def disc_menu_entries(optical: dict, install: pathlib.Path, icons: tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path], home: pathlib.Path | None = None) -> str:
    state = _optical_model.canonical_state(optical); media = _optical_model.presentation(optical); entries = []
    play_icon, tmdb_icon, eject_icon, back_icon = icons
    play_action = install / "assets/ui/media.png"
    media_play_icon = play_action if play_action.is_file() else play_icon
    eject_action = install / "assets/ui/eject.png"
    action_eject_icon = eject_action if eject_action.is_file() else eject_icon
    back_action = install / "assets/ui/system-back.png"
    action_back_icon = back_action if back_action.is_file() else back_icon
    video_action = install / "assets/ui/system-processing.png"
    if not video_action.is_file():
        video_action = install / "assets/ui/traitement_video.png"
    video_icon = video_action if video_action.is_file() else play_icon
    diag_action = install / "assets/ui/diagnostic.png"
    if not diag_action.is_file():
        diag_action = install / "assets/ui/system-diagnostics.png"
    diagnostic_icon = diag_action if diag_action.is_file() else play_icon
    decision = _optical_model.playback_decision(optical, _optical_model.protected_capability(home)) if home else _optical_model.playback_decision(optical, {})
    ui_authority, ui_contribution = "CORE_FALLBACK", {"visible": False, "enabled": False, "action_intent": "NONE"}
    if state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"} and home:
        ui_authority, ui_contribution, decision = protected_optical_menu_policy(home, install, optical)

    core_path = install / "openhtpc-core.py"
    policy = {"unplayable": False}
    if core_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location("openhtpc_menu_p2_core", core_path)
            core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
            policy = core.resolve_protected_optical_policy(home, install, optical, _optical_model.protected_capability(home) if home else {})
        except Exception:
            policy = {"unplayable": False}
    is_protected_unplayable = bool(policy.get("unplayable"))

    has_token = bool(home and (home / ".config/openhtpc/secrets/tmdb-token").is_file())
    cached_meta = {}
    if home:
        tmdb_path = install / "openhtpc-tmdb.py"
        if tmdb_path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_menu_tmdb", tmdb_path)
                tmdb_model = importlib.util.module_from_spec(spec); spec.loader.exec_module(tmdb_model)
                query = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
                cache_target = tmdb_model.cache_path(home, optical, query)
                if cache_target is not None: cached_meta = load_optional_object(cache_target)
            except (OSError, AttributeError, ImportError, ValueError):
                cached_meta = {}

    meta_status = cached_meta.get("status")
    recovery = install / "openhtpc-tmdb-recovery"
    if meta_status == "AMBIGUOUS":
        disc_id = str(optical.get("disc_id") or "")
        generation = int(optical.get("generation", 0) or 0)
        canonical = state
        query = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
        bind_script = install / "openhtpc-bind-disc"
        for cand in cached_meta.get("candidates", [])[:3]:
            cid = int(cand.get("tmdb_id") or cand.get("id", 0))
            ctitle = str(cand.get("title") or "Film").strip()
            cyear = str((cand.get("release_date") or "")[:4]).strip()
            runtime_val = cand.get("runtime")
            cdur = ""
            if runtime_val not in (None, "", [], {}):
                try:
                    r_val = float(runtime_val)
                    if r_val > 0:
                        mins = round(r_val / 60) if r_val > 300 else int(r_val)
                        cdur = f"{mins // 60} h {mins % 60:02d}" if mins >= 60 else f"{mins} min"
                except (ValueError, TypeError):
                    pass
            meta_bits = []
            if cyear: meta_bits.append(cyear)
            if cdur: meta_bits.append(cdur)
            meta_str = " • ".join(meta_bits)
            label = f"{ctitle}  ·  {meta_str}" if meta_str else ctitle
            identity_args = (f"--disc-id {shlex.quote(disc_id)}" if disc_id else
                             f"--generation {generation} --canonical-state {shlex.quote(canonical)} --title {shlex.quote(query)}")
            cmd = f":fork {bind_script} {identity_args} --tmdb-id {cid}"
            cand_icon = tmdb_icon
            p_file = cand.get("poster_file")
            if p_file and pathlib.Path(p_file).is_file():
                cand_icon = pathlib.Path(p_file)
            elif cand.get("poster_path") and home:
                p_path = cand.get("poster_path")
                pf = home / ".cache/openhtpc/tmdb" / (hashlib.sha256(p_path.encode()).hexdigest() + ".jpg")
                if pf.is_file() and pf.stat().st_size > 0:
                    cand_icon = pf
            entries.append((label, cand_icon, cmd))
        # Non-candidate dock actions
        if state == "DVD_VIDEO":
            device = shlex.quote(str(optical.get("device") or ""))
            entries.append(("LIRE LE DVD", media_play_icon,
                            f"env OPENHTPC_FLEX_RETAINED=1 {install/'openhtpc-play-dvd'} {device}"))
        elif is_protected_unplayable:
            entries.append(("DIAGNOSTIC", diagnostic_icon, ":submenu SYSTEM_MEDIA_OPTICAL"))
    elif is_protected_unplayable:
        device = shlex.quote(str(optical.get("device") or ""))
        entries.append(("DIAGNOSTIC", diagnostic_icon, ":submenu SYSTEM_MEDIA_OPTICAL"))
        entries.append(("ÉJECTER", action_eject_icon, f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {device}" if device else ":fork true"))
        entries.append(("RETOUR", action_back_icon, ":back"))
        return "\n".join(f"Entry{i}={ini_value(label)};{icon};{command}" for i, (label, icon, command) in enumerate(entries, 1))
    else:
        if state == "DVD_VIDEO":
            device = shlex.quote(str(optical.get("device") or ""))
            entries.append(("LIRE LE DVD", media_play_icon,
                            f"env OPENHTPC_FLEX_RETAINED=1 {install/'openhtpc-play-dvd'} {device}"))
        elif optical.get("state") == "INITIALIZING": entries.append(("INITIALISATION DU DISQUE…", media_play_icon, ":fork true"))
        elif state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
            pass
        else: entries.append(("AUCUN DISQUE DÉTECTÉ", media_play_icon, ":fork true"))

        if not has_token or meta_status == "NOT_CONFIGURED":
            entries.append(("CONFIGURER TMDb", tmdb_icon, f":fork {install/'openhtpc-configure-tmdb'}"))
        elif meta_status in {"UNAVAILABLE", "AUTH_ERROR", "AUTH_FAILED"}:
            entries.append(("RECONNECTER TMDb", tmdb_icon, f":fork {install/'openhtpc-configure-tmdb'}"))
        elif meta_status == "NO_RESULT":
            entries.append(("RECHERCHE MANUELLE", tmdb_icon, f":fork {recovery}"))

    if state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
        media_name = {"BLURAY_VIDEO":"BLU-RAY","UHD_BLURAY_VIDEO":"UHD BLU-RAY","BLURAY_FAMILY":"BLU-RAY / UHD"}[state]
        if ui_authority != "PLUGIN_P2" or not ui_contribution.get("visible"):
            pass
        elif ui_contribution.get("enabled") and ui_contribution.get("action_intent")=="PLAY_CURRENT_OPTICAL_MEDIA":
            device = shlex.quote(str(optical.get("device") or "")); generation = int(optical.get("generation", 0) or 0)
            token = _optical_model.playback_action_token(optical, _optical_model.protected_capability(home) if home else {})
            entries.append((f"LIRE LE {media_name}", media_play_icon,
                            f":tracked {install/'openhtpc-play-optical'} --device {device} --generation {generation} --action-token {token}"))
        elif not is_protected_unplayable:
            reason_labels = {
                "PROTECTION_UNKNOWN":"PROTECTION NON DÉTERMINÉE",
                "MEDIA_TYPE_INDETERMINATE":"TYPE ET PROTECTION NON DÉTERMINÉS",
                "STRUCTURAL_SUPPORT_NOT_AVAILABLE":"SUPPORT STRUCTUREL NON DISPONIBLE",
                "PROTECTED_SUPPORT_NOT_CONFIGURED":"SUPPORT PROTÉGÉ NON CONFIGURÉ",
                "PROTECTED_SUPPORT_NOT_AVAILABLE":"SUPPORT PROTÉGÉ NON DISPONIBLE",
                "PROTECTED_SUPPORT_BLOCKED":"SUPPORT PROTÉGÉ BLOQUÉ",
            }
            entries.append((f"{media_name} · {reason_labels.get(decision['playback_reason'],'LECTURE NON DISPONIBLE')}", media_play_icon, ":fork true"))

    if state == "DVD_VIDEO":
        presentation = "PURE"
        try:
            policy_path = install / "openhtpc-playback-policy.py"
            spec = importlib.util.spec_from_file_location("openhtpc_dvd_playback_policy", policy_path)
            policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
            presentation = policy.read_preferences(home or pathlib.Path.home())["presentation_mode"]
        except (OSError, AttributeError, ImportError, KeyError):
            pass
        label = "CINÉMA AUTO" if presentation == "CINEMA_AUTO" else "PURE"
        insert_at = next((index + 1 for index, item in enumerate(entries) if item[0] == "LIRE LE DVD"), len(entries))
        entries.insert(insert_at, (f"MODE VIDÉO : {label}", video_icon, ":submenu DVD_VIDEO_MODE"))

    device = shlex.quote(str(optical.get("device") or ""))
    entries.append(("ÉJECTER", action_eject_icon, f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {device}" if device else ":fork true"))
    entries.append(("RETOUR", action_back_icon, ":back"))
    return "\n".join(f"Entry{i}={ini_value(label)};{icon};{command}" for i, (label, icon, command) in enumerate(entries, 1))


def optical_navigation_event(previous: dict, current: dict) -> tuple[int, int]:
    """Return generation-scoped (auto-open, eject-home) requests for a live transition."""
    empty = {"DRIVE_PRESENT_NO_MEDIA", "NO_OPTICAL_DRIVE", "DETECTION_INDETERMINATE"}
    old = _optical_model.canonical_state(previous); new = _optical_model.canonical_state(current)
    generation = int(current.get("generation", 0) or 0)
    if generation <= int(previous.get("generation", 0) or 0):
        return (0, 0)
    if old in empty and new not in empty:
        return (generation, 0)
    if old not in empty and new in {"DRIVE_PRESENT_NO_MEDIA", "NO_OPTICAL_DRIVE"}:
        return (0, generation)
    return (0, 0)


def write_live_optical_state(home: pathlib.Path, optical: dict, icon: pathlib.Path,
                             auto_open_generation: int = 0, eject_home_generation: int = 0) -> pathlib.Path:
    state = optical.get("state"); canonical = _optical_model.canonical_state(optical)
    labels = {"NO_DRIVE":"LECTEUR · AUCUN LECTEUR", "EMPTY":"LECTEUR · Aucun disque",
              "INITIALIZING":"LECTEUR · Initialisation du disque…", "UNKNOWN_DISC":"LECTEUR · DISQUE INCONNU",
              "UNSUPPORTED_IN_V1":"LECTEUR · MÉDIA NON PRIS EN CHARGE"}
    label = optical_home_label(optical) if canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"} else labels.get(state, "LECTEUR · ÉTAT INCONNU")
    target = home / ".local/state/openhtpc/flex-optical-state"
    target.parent.mkdir(parents=True, exist_ok=True)
    generation = int(optical.get("generation", 0) or 0)
    auto_open_generation = generation if int(auto_open_generation or 0) == generation else 0
    eject_home_generation = generation if int(eject_home_generation or 0) == generation else 0
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            title = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
            stream.write(ini_value(label) + "\n" + str(icon) + "\n" + str(state or "UNKNOWN") + "\n" +
                         str(optical.get("device") or "") + "\n" + ini_value(title) + "\n" +
                         str(generation) + "\n" + str(auto_open_generation) + "\n" +
                         str(eject_home_generation) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def _c4_processing_entries(home: pathlib.Path, install: pathlib.Path, local_icon: pathlib.Path) -> str:
    """Generate dynamic [SYSTEM_PROCESSING] entries for C4 CINÉMA AUTO state machine."""
    # Read current video profile (never probes hardware)
    vp_path = home / ".config/openhtpc/video-profile.json"
    try:
        vp_data = json.loads(vp_path.read_text(encoding="utf-8")) if vp_path.exists() else {}
        active = vp_data.get("active_profile", "PURE")
        if active not in {"PURE", "CINEMA_AUTO"}:
            active = "PURE"
    except Exception:
        active = "PURE"

    map_path = home / ".local/state/openhtpc/performance_map.json"
    map_present = map_path.exists()
    map_stale = False
    if map_present:
        try:
            import importlib.util
            ca_path = install / "openhtpc-cinema-auto.py"
            if ca_path.exists():
                spec = importlib.util.spec_from_file_location("ca", ca_path)
                if spec and spec.loader:
                    ca = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(ca)
                    pmap = json.loads(map_path.read_text(encoding="utf-8"))
                    if pmap:
                        stale, _ = ca.is_map_stale(pmap)
                        map_stale = stale
        except Exception:
            pass

    cal_status_path = home / ".local/state/openhtpc/calibration-ui-status.json"
    last_failed = False
    if cal_status_path.exists():
        try:
            cst = json.loads(cal_status_path.read_text(encoding="utf-8"))
            last_failed = (cst.get("status") == "FAILED")
        except Exception:
            pass

    vp_cmd = install / "openhtpc-video-profile.py"
    cal_ui = install / "openhtpc-calibrate-ui"
    lines = []
    idx = 1

    if not map_present:
        if last_failed:
            # State H: Calibration failure
            lines.append(f"Entry{idx}=RÉESSAYER L'ANALYSE;{local_icon};{cal_ui}")
            idx += 1
        else:
            # State A: Fresh install / No calibration
            # Exactly ONE primary action (no conflicting USE AUTO / ANALYZE buttons)
            lines.append(f"Entry{idx}=CONFIGURER CINÉMA AUTO;{local_icon};{cal_ui}")
            idx += 1
    elif map_stale:
        # State G: Stale map
        lines.append(f"Entry{idx}=RECALIBRER;{local_icon};{cal_ui}")
        idx += 1
        if active == "CINEMA_AUTO":
            lines.append(f"Entry{idx}=UTILISER PURE;{local_icon};:fork {vp_cmd} set PURE")
            idx += 1
        else:
            lines.append(f"Entry{idx}=UTILISER CINÉMA AUTO;{local_icon};:fork {vp_cmd} set CINEMA_AUTO")
            idx += 1
    else:
        # State D/E/F: Map present and valid
        if active == "PURE":
            lines.append(f"Entry{idx}=UTILISER CINÉMA AUTO;{local_icon};:fork {vp_cmd} set CINEMA_AUTO")
            idx += 1
        else:
            lines.append(f"Entry{idx}=UTILISER PURE;{local_icon};:fork {vp_cmd} set PURE")
            idx += 1
        lines.append(f"Entry{idx}=RECALIBRER;{local_icon};{cal_ui}")
        idx += 1

    lines.append(f"Entry{idx}=RETOUR;{local_icon};:back")
    return os.linesep.join(lines)


def _playback_policy_sections(home: pathlib.Path, install: pathlib.Path, icons: dict[str, pathlib.Path]) -> tuple[str, str, str, str]:
    """Couch-native selectors backed by persistent user configuration."""
    if not isinstance(icons, dict):
        icons = {key: icons for key in ("video", "audio", "subtitles", "status", "about", "back")}
    policy_path = install / "openhtpc-playback-policy.py"
    setting = install / "openhtpc-playback-setting"
    video_icon, audio_icon = icons["video"], icons["audio"]
    subtitle_icon, status_icon = icons["subtitles"], icons["status"]
    about_icon, back_icon = icons["about"], icons["back"]
    try:
        spec = importlib.util.spec_from_file_location("openhtpc_playback_policy_menu", policy_path)
        policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
        prefs = policy.read_preferences(home)
    except (OSError, AttributeError, ImportError):
        prefs = {"presentation_mode":"PURE","audio_language_policy":"AUTO","audio_output_mode":"PCM","subtitle_policy":"AUTO"}
    presentation = "CINÉMA AUTO" if prefs["presentation_mode"] == "CINEMA_AUTO" else "PURE"
    audio = {"AUTO":"AUTO","FR":"FRANÇAIS","DEFAULT":"PISTE PAR DÉFAUT"}[prefs["audio_language_policy"]]
    subtitle = {"AUTO":"AUTO","OFF":"DÉSACTIVÉS","FR_FORCED":"FRANÇAIS FORCÉS","FR_FULL":"FRANÇAIS COMPLETS"}[prefs["subtitle_policy"]]
    root = os.linesep.join((
        f"Entry1=MODE VIDÉO;{video_icon};:submenu PLAYBACK_VIDEO",
        f"Entry2=LANGUE AUDIO;{audio_icon};:submenu PLAYBACK_AUDIO",
        f"Entry3=SOUS-TITRES;{subtitle_icon};:submenu PLAYBACK_SUBTITLES",
        f"Entry4=ÉTAT AUDIO;{status_icon};:submenu SYSTEM_AUDIO",
        f"Entry5=À PROPOS;{about_icon};:submenu SYSTEM_ABOUT",
        f"Entry6=RETOUR;{back_icon};:back",
    ))
    video = os.linesep.join((
        f"Entry1=PURE;{video_icon};:applyback {setting} presentation_mode PURE",
        f"Entry2=CINÉMA AUTO;{video_icon};:applyback {setting} presentation_mode CINEMA_AUTO",
        f"Entry3=RETOUR;{back_icon};:back",
    ))
    audio_menu = os.linesep.join((
        f"Entry1=AUTO;{audio_icon};:applyback {setting} audio_language_policy AUTO",
        f"Entry2=FRANÇAIS;{audio_icon};:applyback {setting} audio_language_policy FR",
        f"Entry3=PISTE PAR DÉFAUT;{audio_icon};:applyback {setting} audio_language_policy DEFAULT",
        f"Entry4=RETOUR;{back_icon};:back",
    ))
    subtitles = os.linesep.join((
        f"Entry1=AUTO;{subtitle_icon};:applyback {setting} subtitle_policy AUTO",
        f"Entry2=DÉSACTIVÉS;{subtitle_icon};:applyback {setting} subtitle_policy OFF",
        f"Entry3=FRANÇAIS FORCÉS;{subtitle_icon};:applyback {setting} subtitle_policy FR_FORCED",
        f"Entry4=FRANÇAIS COMPLETS;{subtitle_icon};:applyback {setting} subtitle_policy FR_FULL",
        f"Entry5=RETOUR;{back_icon};:back",
    ))
    return root, video, audio_menu, subtitles


def canonical_flex_config_path(home: pathlib.Path | None = None) -> pathlib.Path:
    """Canonical authoritative path for the active Flex appliance configuration."""
    if home is None:
        home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    env_override = os.environ.get("OPENHTPC_FLEX_CONFIG")
    if env_override:
        return pathlib.Path(env_override)
    return home / ".config/openhtpc/flex-v1.ini"


@contextmanager
def flex_publication_lock(home: pathlib.Path):
    """Serialize complete Flex generation/publication across HOME and CLI writers."""
    target = home / ".local/state/openhtpc/flex-publication.lock"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def write_flex_config(path: pathlib.Path, home: pathlib.Path, sources: list[pathlib.Path], install: pathlib.Path | None = None, expected_optical_generation: int | None = None, media_generation: str | None = None) -> bool:
    with flex_publication_lock(home):
        if expected_optical_generation is not None and media_generation is None:
            media_generation = active_media_generation(home)
        return _write_flex_config(path, home, sources, install, expected_optical_generation, media_generation)


def _write_flex_config(path: pathlib.Path, home: pathlib.Path, sources: list[pathlib.Path], install: pathlib.Path | None = None, expected_optical_generation: int | None = None, media_generation: str | None = None) -> bool:
    install = install or pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    font = install / "flex/assets/fonts/OpenSans-Regular.ttf"
    icon_dir = install / "assets/ui"
    optical_empty_icon = icon_dir / "optical-empty.png"
    dvd_icon = icon_dir / "optical-dvd.png"
    bluray_icon = icon_dir / "optical-bluray.png"
    uhd_icon = icon_dir / "optical-uhd.png"
    media_icon = icon_dir / "media.png"
    eject_icon = icon_dir / "eject.png"
    local_icon = optical_empty_icon
    browser = home / ".local/bin/openhtpc-media-browser"
    dvd_ui = install / "openhtpc-dvd-ui"
    eject = install / "openhtpc-eject-current"
    power = install / "openhtpc-power-menu"
    system = install / "openhtpc-system-page"
    quit_openhtpc = install / "openhtpc-quit"
    system_view = install / "openhtpc-system-view"
    disc_view = install / "openhtpc-disc-view.py"
    theme = load_theme(install)
    logo = theme.assets(install)["logo"]
    scale = flex_scale(observed_display_size())
    optical = load_optional_object(home / ".local/state/openhtpc/optical-current.json")
    if expected_optical_generation is not None and int(optical.get("generation", 0) or 0) != expected_optical_generation:
        return False
    if _optical_model.canonical_state(optical) == "DVD_VIDEO" and optical.get("disc_id") and not optical.get("tmdb_title"):
        cache_target = home / ".local/share/openhtpc/media-cache/dvd" / hashlib.sha256(str(optical["disc_id"]).encode()).hexdigest() / "metadata.json"
        cached_meta = load_optional_object(cache_target)
        if cached_meta.get("status") == "PASS" and cached_meta.get("title"):
            optical["tmdb_title"] = cached_meta.get("title")
    canonical = _optical_model.canonical_state(optical); media = _optical_model.presentation(optical)
    disc_state = optical_home_label(optical) if canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"} else {
        "NO_OPTICAL_DRIVE": "AUCUN LECTEUR", "DRIVE_PRESENT_NO_MEDIA": "Aucun disque",
        "DETECTION_INDETERMINATE": "ÉTAT INCONNU",
    }.get(canonical, "ÉTAT INCONNU")
    optical_icon = icon_dir / media["icon"]
    live_optical_state = write_live_optical_state(home, optical, optical_icon)
    live_activity_state = home / ".local/state/openhtpc/media/activity-state"
    ready = canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"}
    entries = [
        f"Entry1={ini_value(str(disc_state)) if ready else 'LECTEUR · ' + ini_value(str(disc_state))};{optical_icon};:submenu DISQUE",
        f"Entry2=ÉJECTER;{eject_icon};:fork env OPENHTPC_STAY_IN_FLEX=1 {eject}",
        f"Entry3=MÉDIA;{media_icon};:submenu MEDIA_ROOT",
        f"Entry4=SYSTÈME;{logo};:submenu SYSTEME",
    ]
    index = 5
    for plugin_entry in plugin_menu_entries(home, install):
        entries.append(f"Entry{index}={ini_value(plugin_entry['label'])};{local_icon};:replace {plugin_entry['command']}")
        index += 1
    power_icon = install / "assets/ui/power.png"
    entries.append(f"Entry{index}=ÉTEINDRE;{power_icon};:submenu ALIMENTATION")
    source_inventory = os.linesep.join(f"Source{number}={ini_value(str(source))}" for number, source in enumerate(sources, 1)) or "SourceCount=0"
    optical_generation = int(optical.get("generation", 0) or 0)
    ui_spec = importlib.util.spec_from_file_location("openhtpc_ui", install / "openhtpc-ui.py" if (install / "openhtpc-ui.py").is_file() else pathlib.Path(__file__).with_name("openhtpc-ui.py"))
    ui = importlib.util.module_from_spec(ui_spec); ui_spec.loader.exec_module(ui)
    state_hash = hashlib.sha256(json.dumps(optical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    ui_generation_id = ui.generation_id(optical)
    system_page_keys = ("overview", "codecs", "display", "audio", "media_optical", "metadata", "tmdb", "processing", "playback", "diagnostics", "technical", "about")
    system_pages = {name: home / f".cache/openhtpc/system-{name}.png" for name in system_page_keys}
    dashboard = home / ".cache/openhtpc/system-dashboard.png"
    system_model = {}
    system_page = install / "openhtpc-system-page"
    if system_page.is_file():
        loader = importlib.machinery.SourceFileLoader("openhtpc_system_live", str(system_page))
        spec = importlib.util.spec_from_loader("openhtpc_system_live", loader)
        system_live = importlib.util.module_from_spec(spec)
        loader.exec_module(system_live)
        system_model = system_live.status_model(home, install)
        management_path = install / "openhtpc-tmdb-management.py"
        if management_path.is_file():
            loader = importlib.machinery.SourceFileLoader("openhtpc_tmdb_management_ui", str(management_path))
            management_spec = importlib.util.spec_from_loader("openhtpc_tmdb_management_ui", loader)
            management = importlib.util.module_from_spec(management_spec); loader.exec_module(management)
            system_model["tmdb_management"] = management.status(home)
        ui.system_page_png(system_model, dashboard, font, "root")
        for key in system_page_keys:
            ui.system_page_png(system_model, system_pages[key], font, key)
    sys_ui_dir = install / "assets/ui"
    root_ui_dir = pathlib.Path(__file__).resolve().parent / "assets/ui"

    def resolve_sys_icon(name, fallback):
        for d in (sys_ui_dir, root_ui_dir):
            p = d / name
            if p.is_file():
                return p
        return fallback

    icon_overview = resolve_sys_icon("system-overview.png", resolve_sys_icon("vue_ensemble.png", logo))
    icon_codecs = resolve_sys_icon("system-video.png", resolve_sys_icon("compatibilite_video.png", media_icon))
    icon_display = resolve_sys_icon("system-display.png", resolve_sys_icon("affichage.png", logo))
    icon_audio = resolve_sys_icon("system-audio.png", resolve_sys_icon("audio.png", media_icon))
    icon_optical = resolve_sys_icon("system-media-optical.png", resolve_sys_icon("media_optique.png", media_icon))
    icon_processing = resolve_sys_icon("system-processing.png", resolve_sys_icon("traitement_video.png", logo))
    icon_diagnostic = resolve_sys_icon("system-diagnostics.png", resolve_sys_icon("diagnostic.png", logo))
    icon_metadata = resolve_sys_icon("system-media-optical.png", resolve_sys_icon("media_optique.png", media_icon))
    icon_back = resolve_sys_icon("system-back.png", resolve_sys_icon("retour.png", logo))
    playback_icons = {
        "video": resolve_sys_icon("playback-video.png", icon_codecs),
        "audio": resolve_sys_icon("playback-language.png", icon_audio),
        "subtitles": resolve_sys_icon("playback-subtitles.png", media_icon),
        "status": resolve_sys_icon("playback-audio-status.png", icon_audio),
        "about": resolve_sys_icon("playback-about.png", logo),
        "back": icon_back,
    }
    playback_root, playback_video, playback_audio, playback_subtitles = _playback_policy_sections(home, install, playback_icons)
    user_cfg = load_optional_object(home / ".config/openhtpc/user-config.json")
    try:
        audio_mode = user_cfg.get("audio_output_mode", "PCM")
    except (OSError, AttributeError):
        audio_mode = "PCM"
    if audio_mode not in {"PCM", "BITSTREAM"}: audio_mode = "PCM"

    refresh_matching = user_cfg.get("refresh_matching", "OFF") if isinstance(user_cfg, dict) else "OFF"
    refresh_setting_label = "AUTOMATIQUE" if refresh_matching == "AUTO" else "DÉSACTIVÉE"

    audio_target = user_cfg.get("audio_output_target")
    if not isinstance(audio_target, dict):
        audio_target = {"mode": "SYSTEM", "node_name": None, "bus_path": None, "edid_name": None, "display_label": "SYSTEM", "device_type": "UNKNOWN"}

    audio_mod = None
    try:
        import openhtpc_audio
        audio_mod = openhtpc_audio
    except ImportError:
        pass
    if audio_mod is None:
        for candidate in (
            install / "openhtpc-audio.py",
            pathlib.Path(__file__).resolve().parent / "openhtpc-audio.py",
            pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-audio.py",
        ):
            if candidate.is_file():
                try:
                    spec = importlib.util.spec_from_file_location("openhtpc_audio", candidate)
                    if spec and spec.loader:
                        audio_mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(audio_mod)
                        break
                except Exception:
                    pass

    discovered_outputs = []
    if audio_mod and hasattr(audio_mod, "discover_outputs"):
        try:
            discovered_outputs = audio_mod.discover_outputs()
        except Exception:
            discovered_outputs = []
    physical_outputs = [o for o in discovered_outputs if isinstance(o, dict) and not o.get("is_network")]
    kind_order = {"HDMI": 0, "USB": 1, "ANALOG": 2, "BLUETOOTH": 3, "UNKNOWN": 4}
    physical_outputs.sort(key=lambda o: (kind_order.get(o.get("device_type"), 4), str(o.get("display_label", "")).lower(), str(o.get("node_name", "")).lower()))

    routing = audio_mod.resolve_audio(audio_target, physical_outputs) if audio_mod and hasattr(audio_mod, "resolve_audio") else {
        "CONFIGURED": audio_target,
        "AVAILABLE": audio_target.get("mode") == "SYSTEM",
        "EFFECTIVE": audio_target if audio_target.get("mode") == "SYSTEM" else {"mode": "SYSTEM"},
    }

    t_mode = audio_target.get("mode", "SYSTEM")
    if t_mode == "SYSTEM":
        target_display_label = "Sortie système — Fedora"
    else:
        target_display_label = audio_target.get("display_label") or audio_target.get("edid_name") or audio_target.get("node_name") or "DEVICE"

    target_entries = []
    entry_idx = 1
    found_configured = False
    for o in physical_outputs:
        is_sel = (t_mode == "DEVICE" and routing.get("AVAILABLE") and routing.get("EFFECTIVE", {}).get("node_name") == o.get("node_name"))
        if is_sel:
            found_configured = True
        prefix = "• " if is_sel else ""
        label = (
            audio_target.get("display_label")
            if is_sel and audio_target.get("display_label")
            else o["display_label"]
        )
        target_entries.append(f"Entry{entry_idx}={prefix}{ini_value(label)};{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target {o['node_name']}")
        entry_idx += 1

    if t_mode == "DEVICE" and not found_configured:
        unavail_entry = f"Entry{entry_idx}=• {ini_value(target_display_label)} (Indisponible);{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target {audio_target.get('node_name', 'UNKNOWN')}"
        target_entries.insert(0, unavail_entry)
        target_entries = [f"Entry{i+1}=" + e.split("=", 1)[1] for i, e in enumerate(target_entries)]
        entry_idx = len(target_entries) + 1

    sys_sel = (t_mode == "SYSTEM")
    sys_prefix = "• " if sys_sel else ""
    target_entries.append(f"Entry{entry_idx}={sys_prefix}Sortie système — Fedora;{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target SYSTEM")
    entry_idx += 1
    target_entries.append(f"Entry{entry_idx}=RETOUR;{icon_back};:back")
    audio_output_target_section = os.linesep.join(target_entries)
    disc_sheet = home / ".cache/openhtpc/disc-sheet.png"
    if not disc_sheet_is_current(home,optical):
        for stale in (disc_sheet,home/".local/state/openhtpc/disc-sheet-state.json"):
            try: stale.unlink()
            except OSError: pass
        _optical_model.trace_event(home,"PRESENTATION_INVALIDATED",optical_generation=optical_generation,canonical_state=canonical,presentation_state="INVALIDATED",event_reason="GENERATION_PROVENANCE_MISMATCH")
    if disc_view.is_file():
        subprocess.run([str(disc_view), "--home", str(home), "--generation", str(optical_generation)], timeout=12, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not disc_sheet_is_current(home,optical): disc_sheet = theme.assets(install)["wallpaper"]
    counter_path = home / ".local/state/openhtpc/menu-generation"
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    with open(counter_path, "a+", encoding="utf-8") as counter:
        fcntl.flock(counter, fcntl.LOCK_EX); counter.seek(0)
        try: menu_generation = int(counter.read().strip() or "0") + 1
        except ValueError: menu_generation = 1
        counter.seek(0); counter.truncate(); counter.write(str(menu_generation)); counter.flush(); os.fsync(counter.fileno())
    media_generation=media_generation or f"{ui_generation_id}-{menu_generation}"
    manifest_candidate=path.with_name(path.name+".media-actions.json")
    _media_root, media_sections = media_menu_sections(home, sources, media_icon, media_generation,manifest_candidate)
    content = f"""# OPENHTPC menu_generation={menu_generation} ui_generation_id={ui_generation_id} media_generation={media_generation} optical_generation={optical_generation} state_hash={state_hash}
[General]
DefaultMenu=OPENHTPC
VSync=true
OnLaunch=Blank
WrapEntries=true
ResetOnBack=true
MouseSelect=true
InhibitOSScreensaver=true
LiveOpticalState={live_optical_state}
LiveActivityState={live_activity_state}

{theme.background_block(install, 52)}

[Layout]
MaxButtons=9
IconSize={scale['icon']}
IconSpacing=3%
VCenter=50%

{theme.title_block(font, scale['title'], scale['padding'])}

{theme.highlight_block()}

[Scroll Indicators]
Enabled=true
FillColor=#FFFFFF
OutlineSize=0
OutlineColor=#000000
Opacity=100%

[Clock]
Enabled=true
ShowDate=true
Alignment=Right
Font={font}
FontSize={scale['clock']}
FontColor=#FFFFFF
Shadows=false
Margin=4%
Opacity=100%
TimeFormat=24hr
DateFormat=Auto
IncludeWeekday=true

[Screensaver]
Enabled=false

[Hotkeys]
Hotkey1=#1B;:back
Hotkey2=#08;:back

[Gamepad]
Enabled=false
DeviceIndex=-1
LStickX-=:left
LStickX+=:right
LStickY-=:left
LStickY+=:right
ButtonA=:select
ButtonB=:back
ButtonDPadLeft=:left
ButtonDPadRight=:right
ButtonDPadUp=:left
ButtonDPadDown=:right

[OPENHTPC]
{os.linesep.join(entries)}

[SYSTEME]
BackgroundImage={dashboard}
Entry1=VUE D'ENSEMBLE;{icon_overview};:submenu SYSTEM_OVERVIEW
Entry2=COMPATIBILITÉ VIDÉO;{icon_codecs};:submenu SYSTEM_CODECS
Entry3=AFFICHAGE;{icon_display};:submenu SYSTEM_DISPLAY
Entry4=LECTURE;{icon_processing};:submenu SYSTEM_PLAYBACK
Entry5=AUDIO;{icon_audio};:submenu SYSTEM_AUDIO
Entry6=MÉDIAS & OPTIQUE;{icon_optical};:submenu SYSTEM_MEDIA_OPTICAL
Entry7=MÉTADONNÉES;{icon_metadata};:submenu SYSTEM_METADATA
Entry8=DIAGNOSTIC;{icon_diagnostic};:submenu SYSTEM_DIAGNOSTICS
Entry9=À PROPOS;{logo};:submenu SYSTEM_ABOUT
Entry10=RETOUR;{icon_back};:back

[SYSTEM_OVERVIEW]
BackgroundImage={system_pages['overview']}
Entry1=RETOUR;{local_icon};:back

[SYSTEM_CODECS]
BackgroundImage={system_pages['codecs']}
Entry1=RETOUR;{local_icon};:back

[SYSTEM_DISPLAY]
BackgroundImage={system_pages['display']}
Entry1=ADAPTATION DE FRÉQUENCE : {refresh_setting_label};{icon_display};:submenu DISPLAY_REFRESH_MATCHING
Entry2=RETOUR;{icon_back};:back

[DISPLAY_REFRESH_MATCHING]
BackgroundImage={system_pages['display']}
Entry1=AUTOMATIQUE;{icon_display};:applyback {install/'openhtpc-playback-setting'} refresh_matching AUTO
Entry2=DÉSACTIVÉE;{icon_display};:applyback {install/'openhtpc-playback-setting'} refresh_matching OFF
Entry3=RETOUR;{icon_back};:back

[SYSTEM_AUDIO]
BackgroundImage={system_pages['audio']}
Entry1=SORTIE AUDIO : {target_display_label};{icon_audio};:submenu AUDIO_OUTPUT_TARGET
Entry2=MODE AUDIO : {audio_mode};{playback_icons['audio']};:submenu AUDIO_OUTPUT_MODE
Entry3=RETOUR;{icon_back};:back

[AUDIO_OUTPUT_TARGET]
BackgroundImage={system_pages['audio']}
{audio_output_target_section}

[AUDIO_OUTPUT_MODE]
BackgroundImage={system_pages['audio']}
Entry1=PCM;{playback_icons['audio']};:applyback {install/'openhtpc-playback-setting'} audio_output_mode PCM
Entry2=BITSTREAM;{playback_icons['audio']};:applyback {install/'openhtpc-playback-setting'} audio_output_mode BITSTREAM
Entry3=RETOUR;{icon_back};:back

[SYSTEM_MEDIA_OPTICAL]
BackgroundImage={system_pages['media_optical']}
Entry1=RETOUR;{local_icon};:back

[SYSTEM_METADATA]
BackgroundImage={system_pages['metadata']}
Entry1=TMDb;{icon_metadata};:submenu SYSTEM_TMDB
Entry2=RETOUR;{icon_back};:back

[SYSTEM_TMDB]
BackgroundImage={system_pages['tmdb']}
{(f"Entry1=CONFIGURER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} configure\nEntry2=RETOUR;{icon_back};:back" if not system_model.get('tmdb_management',{}).get('masked') else f"Entry1=TESTER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} test\nEntry2=MODIFIER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} modify\nEntry3=SUPPRIMER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} delete\nEntry4=RETOUR;{icon_back};:back")}

[SYSTEM_PROCESSING]
BackgroundImage={system_pages['processing']}
{_c4_processing_entries(home, install, local_icon)}

[SYSTEM_PLAYBACK]
BackgroundImage={system_pages['playback']}
{playback_root}

[PLAYBACK_VIDEO]
BackgroundImage={system_pages['playback']}
{playback_video}

[PLAYBACK_AUDIO]
BackgroundImage={system_pages['playback']}
{playback_audio}

[PLAYBACK_SUBTITLES]
BackgroundImage={system_pages['playback']}
{playback_subtitles}

[SYSTEM_DIAGNOSTICS]
BackgroundImage={system_pages['diagnostics']}
Entry1=ACTUALISER LES CAPACITÉS;{local_icon};:fork {install/'openhtpc-system-action'} refresh
Entry2=CRÉER UN RAPPORT SUPPORT;{local_icon};:fork {install/'openhtpc-system-action'} support
Entry3=INFORMATIONS TECHNIQUES;{local_icon};:submenu SYSTEM_TECHNICAL
Entry4=RETOUR;{local_icon};:back

[SYSTEM_TECHNICAL]
BackgroundImage={system_pages['technical']}
Entry1=RETOUR;{local_icon};:back

[SYSTEM_ABOUT]
BackgroundImage={system_pages['about']}
Entry1=RETOUR;{icon_back};:back

[DISQUE]
BackgroundImage={disc_sheet}
{disc_menu_entries(optical, install, (media_icon, media_icon, eject_icon, icon_back), home)}

[DVD_VIDEO_MODE]
BackgroundImage={disc_sheet}
Entry1=PURE;{playback_icons['video']};:applyback {install/'openhtpc-playback-setting'} presentation_mode PURE
Entry2=CINÉMA AUTO;{playback_icons['video']};:applyback {install/'openhtpc-playback-setting'} presentation_mode CINEMA_AUTO
Entry3=RETOUR;{icon_back};:back

{media_sections}

[ALIMENTATION]
Entry1=QUITTER OPENHTPC;{install/'assets/ui/quit.png'};:fork {quit_openhtpc}
Entry2=ÉTEINDRE LE PC;{power_icon};systemctl poweroff
Entry3=RETOUR;{icon_back};:back

[MediaSidebar]
Entry1=MÉDIAS LOCAUX;{local_icon};{browser}
Entry2=LECTEUR DVD / BLU-RAY / UHD;{dvd_icon};{dvd_ui}

[Configured Media]
{source_inventory}
"""
    ui.validate_config_text(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush(); os.fsync(stream.fileno())
        latest = load_optional_object(home / ".local/state/openhtpc/optical-current.json")
        if expected_optical_generation is not None and int(latest.get("generation", 0) or 0) != expected_optical_generation:
            return False
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def menu_identity(path: pathlib.Path) -> int:
    try:
        first = path.open(encoding="utf-8").readline()
        return int(first.split("menu_generation=", 1)[1].split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def activate_media_manifest(config_path:pathlib.Path,home:pathlib.Path)->pathlib.Path:
    """Publish only the action manifest loaded by the authoritative Flex."""
    candidate=config_path.with_name(config_path.name+".media-actions.json")
    data=load_object(candidate,"media_actions","ACTION_MANIFEST_MISSING","ACTION_MANIFEST_INVALID")
    if data.get("schema")!=1 or not isinstance(data.get("items"),dict) or not isinstance(data.get("sources"),list):
        raise GateError("media_actions","ACTION_MANIFEST_INVALID","Le manifeste MEDIA candidat est invalide.")
    target=current_media_manifest(home);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(data,stream,ensure_ascii=False,sort_keys=True);stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return target


def publish_flex_config(path:pathlib.Path,home:pathlib.Path,sources:list[pathlib.Path],install:pathlib.Path|None=None)->bool:
    """Publish one MEDIA generation at the synchronous Flex action boundary."""
    with flex_publication_lock(home):
        return _publish_flex_config(path, home, sources, install)


def _publish_flex_config(path:pathlib.Path,home:pathlib.Path,sources:list[pathlib.Path],install:pathlib.Path|None=None)->bool:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+".publish.",dir=path.parent);os.close(fd);staged=pathlib.Path(name)
    candidate=path.with_name(path.name+".media-actions.json");staged_candidate=staged.with_name(staged.name+".media-actions.json")
    current=current_media_manifest(home);targets=(path,candidate,current)
    previous={target:(target.read_bytes() if target.is_file() else None) for target in targets}
    def replace_bytes(target:pathlib.Path,data:bytes)->None:
        target.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
        try:
            with os.fdopen(fd,"wb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o600);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    try:
        staged.unlink()
        if not _write_flex_config(staged,home,sources,install):return False
        model=load_object(staged_candidate,"media_actions","ACTION_MANIFEST_MISSING","ACTION_MANIFEST_INVALID")
        if model.get("schema")!=1 or not isinstance(model.get("items"),dict):raise GateError("media_actions","ACTION_MANIFEST_INVALID","Le manifeste MEDIA candidat est invalide.")
        replace_bytes(candidate,staged_candidate.read_bytes())
        activate_media_manifest(path,home)
        replace_bytes(path,staged.read_bytes())
        return True
    except Exception:
        for target,data in previous.items():
            if data is None:
                try:target.unlink()
                except OSError:pass
            else:replace_bytes(target,data)
        raise
    finally:
        for target in (staged,staged_candidate):
            try:target.unlink()
            except OSError:pass


def load_optional_object(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def disc_sheet_is_current(home: pathlib.Path, optical: dict) -> bool:
    provenance=load_optional_object(home/".local/state/openhtpc/disc-sheet-state.json")
    return (int(provenance.get("optical_generation",-1) or -1)==int(optical.get("generation",0) or 0) and
            provenance.get("canonical_state")==_optical_model.canonical_state(optical) and
            provenance.get("ui_state_hash")==optical.get("ui_state_hash") and
            (home/".cache/openhtpc/disc-sheet.png").is_file())

def publish_generation_fallback(home: pathlib.Path, install: pathlib.Path, optical: dict, reason: str) -> None:
    """Publish a truthful, generation-matching fallback after bounded worker failure."""
    generation = int(optical.get("generation", 0) or 0)
    target = home/".cache/openhtpc/disc-sheet.png"; target.parent.mkdir(parents=True,exist_ok=True)
    source = load_theme(install).assets(install)["wallpaper"]
    fd, temporary = tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    provenance={"schema":1,"optical_generation":generation,"canonical_state":_optical_model.canonical_state(optical),
                "ui_state_hash":optical.get("ui_state_hash"),"render_identity":f"fallback-{generation}",
                "metadata_status":"FALLBACK","presentation_state":"FALLBACK","error_reason":reason}
    _optical_model.atomic_json(home/".local/state/openhtpc/disc-sheet-state.json",provenance)
    _optical_model.trace_event(home,"PRESENTATION_FALLBACK",optical_generation=generation,
                               canonical_state=provenance["canonical_state"],presentation_state="FALLBACK",
                               render_generation=generation,metadata_job_state="FALLBACK",event_reason=reason)


def plugin_menu_entries(home: pathlib.Path, install: pathlib.Path) -> list[dict[str, str]]:
    core_path = install / "openhtpc-core.py"
    if not core_path.is_file():
        return []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("openhtpc_core", core_path)
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        plugins, errors = core.installed_plugins(home, install)
        if errors:
            return []
        result = []
        for plugin in sorted(plugins, key=lambda item: item["plugin_id"]):
            for entry in plugin["menu_entries"]:
                if isinstance(entry, dict) and isinstance(entry.get("label"), str) and isinstance(entry.get("command"), str):
                    command = entry["command"]
                    if command.startswith(str(install) + "/") and "\n" not in command and ";" not in command:
                        result.append({"label": entry["label"], "command": command})
        return result
    except (OSError, AttributeError, TypeError):
        return []


def evaluate(home: pathlib.Path) -> dict:
    root = home / ".config/openhtpc"
    profile = load_object(root / "profile.json", "hardware_profile", "PROFILE_MISSING", "PROFILE_INVALID")
    validate_profile(profile)
    snapshot_path = root / "runtime/capabilities.json"
    snapshot = load_object(snapshot_path, "capabilities", "CAPABILITIES_MISSING", "CAPABILITIES_INVALID") if snapshot_path.exists() else {}
    validate_capability_provenance(profile, snapshot)
    decision = viability(profile)
    if decision["status"] != "PASS":
        raise GateError("viability", "MACHINE_NOT_VIABLE", "; ".join(decision["failures"]))
    validate_runtime(profile, home)
    user = load_object(root / "user-config.json", "initial_configuration", "CONFIGURATION_MISSING", "CONFIGURATION_INVALID")
    sources = validate_user_config(user, root / "secrets/tmdb-token")
    return {"profile": profile, "viability": decision, "user_config": user, "sources": sources}
