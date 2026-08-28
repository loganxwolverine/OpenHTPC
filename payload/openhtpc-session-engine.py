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
        result = subprocess.run(["kscreen-doctor", "-j"], text=True, capture_output=True, timeout=5)
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


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}


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


def media_menu_sections(home: pathlib.Path, sources: list[pathlib.Path], icon: pathlib.Path, generation: str = "test-generation", manifest_target: pathlib.Path | None = None) -> tuple[str, str]:
    """Build a bounded complete media graph before the persistent Flex starts."""
    sections: list[str] = []
    actions: dict[str, dict] = {}
    visited: set[pathlib.Path] = set(); inventory=[]
    install = home / ".local/lib/openhtpc"
    picker_bin = install / "openhtpc-media-picker"
    remove_bin = install / "openhtpc-media-remove"
    add_icon = icon
    folder_icon = home / ".local/lib/openhtpc/assets/ui/folder.png"
    remove_icon = home / ".local/lib/openhtpc/flex/assets/icons/drive-empty.png"

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
                        actions[token] = {"page_id": name, "item_type": "file", "source_id": source_id, "relative_path": relative.as_posix(), "semantic_id": item_id}
                        command = f"$HOME/.local/lib/openhtpc/openhtpc-play {token}"
                        stem = os.path.splitext(item.name)[0]
                        title = ini_value(stem)
                        if len(title) > 72: title = title[:69].rstrip() + "…"
                        entries.append((f"{title}  ·  {ext[1:].upper()}", icon, command))
            except OSError:
                continue
        if resolved == source_root.resolve():
            entries.append(("RETIRER CETTE SOURCE D'OPENHTPC", remove_icon, f"{remove_bin} \"{str(source_root)}\""))
        body = "\n".join(bounded_flex_entry(i, label, entry_icon, command) for i, (label, entry_icon, command) in enumerate(entries, 1))
        sections.append(f"[{name}]\n{body}")
        return name

    roots = []
    if not sources:
        roots.append(("+ AJOUTER UNE SOURCE MÉDIA", add_icon, f"{picker_bin}"))
    else:
        for source in sources:
            try:canonical=source.resolve(strict=True)
            except OSError:canonical=None
            sid=media_source_id(canonical) if canonical is not None else media_source_id(source)
            target = section_for(canonical,canonical,sid) if canonical is not None and canonical.is_dir() else None
            inventory.append({"source_id":sid,"configured_path":str(source),"canonical_path":str(canonical) if canonical is not None else None})
            label = ini_value(source.name or str(source)) + ("" if target else " — indisponible")
            source_cmd = f":submenu {target}" if target else ":fork true"
            context_cmd = f"{remove_bin} \"{str(source)}\""
            roots.append((label, folder_icon, source_cmd, context_cmd, "RETIRER LA SOURCE"))
        roots.append(("+ AJOUTER UNE SOURCE", add_icon, f"{picker_bin}"))

    roots.append(("RETOUR À OPENHTPC", icon, ":back"))
    root_entries = []
    for i, entry_tuple in enumerate(roots, 1):
        if len(entry_tuple) == 5:
            label, entry_icon, command, context_cmd, context_title = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon};{command};{context_cmd};{context_title}")
        else:
            label, entry_icon, command = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon};{command}")
    root_body = "\n".join(root_entries)

    write_media_model_state(home,generation,inventory,actions,manifest_target)
    return "MEDIA_ROOT", "\n\n".join([f"[MEDIA_ROOT]\n{root_body}", *reversed(sections)])


def bounded_flex_entry(index: int, label: str, icon: pathlib.Path, command: str, max_bytes: int = 198) -> str:
    """Serialize an Entry line that fits in Flex/inih's 200-byte input buffer."""
    prefix = f"Entry{index}="
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



def disc_menu_entries(optical: dict, install: pathlib.Path, icons: tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path], home: pathlib.Path | None = None) -> str:
    state = _optical_model.canonical_state(optical); media = _optical_model.presentation(optical); entries = []
    play_icon, tmdb_icon, eject_icon, back_icon = icons
    dvd_icon = install / "assets/ui/optical-dvd.png"
    media_play_icon = dvd_icon if (state == "DVD_VIDEO" and dvd_icon.is_file()) else play_icon

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
        video_icon = install / "assets/ui/playback-video.png"
        insert_at = next((index + 1 for index, item in enumerate(entries) if item[0] == "LIRE LE DVD"), len(entries))
        entries.insert(insert_at, (f"MODE VIDÉO : {label}", video_icon, ":submenu DVD_VIDEO_MODE"))

    device = shlex.quote(str(optical.get("device") or ""))
    entries.append(("ÉJECTER", eject_icon, f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {device}" if device else ":fork true"))
    entries.append(("RETOUR", back_icon, ":back"))
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


def write_flex_config(path: pathlib.Path, home: pathlib.Path, sources: list[pathlib.Path], install: pathlib.Path | None = None, expected_optical_generation: int | None = None, media_generation: str | None = None) -> bool:
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
    try:
        audio_mode = load_optional_object(home / ".config/openhtpc/user-config.json").get("audio_output_mode", "PCM")
    except (OSError, AttributeError):
        audio_mode = "PCM"
    if audio_mode not in {"PCM", "BITSTREAM"}: audio_mode = "PCM"
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
    content = f"""# OPENHTPC menu_generation={menu_generation} ui_generation_id={ui_generation_id} optical_generation={optical_generation} state_hash={state_hash}
[General]
DefaultMenu=OPENHTPC
VSync=true
OnLaunch=Blank
WrapEntries=true
ResetOnBack=true
MouseSelect=true
InhibitOSScreensaver=true
LiveOpticalState={live_optical_state}

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
Entry1=RETOUR;{local_icon};:back

[SYSTEM_AUDIO]
BackgroundImage={system_pages['audio']}
Entry1=MODE AUDIO : {audio_mode};{playback_icons['audio']};:submenu AUDIO_OUTPUT_MODE
Entry2=RETOUR;{icon_back};:back

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
{disc_menu_entries(optical, install, (optical_icon, media_icon, eject_icon, logo), home)}

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
        if not write_flex_config(staged,home,sources,install):return False
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
    decision = viability(profile)
    if decision["status"] != "PASS":
        raise GateError("viability", "MACHINE_NOT_VIABLE", "; ".join(decision["failures"]))
    validate_runtime(profile, home)
    user = load_object(root / "user-config.json", "initial_configuration", "CONFIGURATION_MISSING", "CONFIGURATION_INVALID")
    sources = validate_user_config(user, root / "secrets/tmdb-token")
    return {"profile": profile, "viability": decision, "user_config": user, "sources": sources}
