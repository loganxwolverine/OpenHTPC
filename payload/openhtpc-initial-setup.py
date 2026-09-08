#!/usr/bin/env python3
"""Small KDE/terminal initial configuration assistant for OPENHTPC V1."""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any


def write_private(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value.strip() + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_audio_module() -> Any:
    try:
        import openhtpc_audio
        return openhtpc_audio
    except ImportError:
        pass
    for loc in (
        pathlib.Path(__file__).resolve().parent / "openhtpc-audio.py",
        pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", "")) / "openhtpc-audio.py",
        pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-audio.py",
    ):
        if loc.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_audio", loc)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception:
                pass
    return None


def _load_playback_policy() -> Any:
    if "openhtpc_playback_policy" in sys.modules:
        return sys.modules["openhtpc_playback_policy"]
    try:
        import openhtpc_playback_policy
        return openhtpc_playback_policy
    except ImportError:
        pass
    for loc in (
        pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", "")) / "openhtpc-playback-policy.py",
        pathlib.Path(__file__).resolve().parent / "openhtpc-playback-policy.py",
        pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-playback-policy.py",
    ):
        if loc.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_playback_policy", loc)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception:
                pass
    return None


def default_system_descriptor() -> dict:
    mod = _load_audio_module()
    if mod and hasattr(mod, "system_descriptor"):
        return mod.system_descriptor()
    return {
        "mode": "SYSTEM",
        "node_name": None,
        "bus_path": None,
        "edid_name": None,
        "display_label": "SYSTEM",
        "device_type": "UNKNOWN",
    }


def discover_audio_choices() -> tuple[Any, list[dict]]:
    mod = _load_audio_module()
    outputs = []
    if mod and hasattr(mod, "discover_outputs"):
        try:
            outputs = mod.discover_outputs()
        except Exception:
            outputs = []
    outputs = [o for o in outputs if isinstance(o, dict) and not o.get("is_network")]
    kind_order = {"HDMI": 0, "USB": 1, "ANALOG": 2, "BLUETOOTH": 3, "UNKNOWN": 4}
    outputs.sort(key=lambda o: (kind_order.get(o.get("device_type"), 4), str(o.get("display_label", "")).lower(), str(o.get("node_name", "")).lower()))
    return mod, outputs


def save(
    home: pathlib.Path,
    sources: list[str],
    tmdb_value: str | None,
    audio_target: dict | None = None,
    audio_mode: str | None = None,
) -> pathlib.Path:
    normalized = []
    for raw in sources:
        path = pathlib.Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"Dossier média inexistant : {raw}")
        text = str(path)
        if text not in normalized:
            normalized.append(text)
    root = home / ".config/openhtpc"
    root.mkdir(parents=True, exist_ok=True)
    credential = root / "secrets/tmdb-token"
    try:
        previous = json.loads((root / "user-config.json").read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, json.JSONDecodeError):
        previous = {}

    if tmdb_value is not None:
        configured = bool(tmdb_value.strip())
        if configured:
            write_private(credential, tmdb_value)
        if isinstance(previous.get("tmdb"), dict):
            tmdb_config = {**previous["tmdb"], "configured": configured}
        else:
            tmdb_config = {"configured": configured}
    else:
        # tmdb_value is None means no new TMDb value provided.
        # Preserve existing tmdb configuration exactly as is.
        if isinstance(previous.get("tmdb"), dict):
            tmdb_config = dict(previous["tmdb"])
        else:
            tmdb_config = {"configured": False}

    config = {
        **previous,
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": normalized,
        "tmdb": tmdb_config,
    }
    target_path = root / "user-config.json"
    fd, temporary = tempfile.mkstemp(prefix=target_path.name + ".", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    # Delegate audio persistence exclusively to canonical policy APIs
    policy = _load_playback_policy()
    target_to_write = audio_target
    if target_to_write is None:
        if isinstance(previous.get("audio_output_target"), dict):
            target_to_write = previous["audio_output_target"]
        else:
            target_to_write = default_system_descriptor()

    mode_to_write = audio_mode
    if mode_to_write not in {"PCM", "BITSTREAM"}:
        if previous.get("audio_output_mode") in {"PCM", "BITSTREAM"}:
            mode_to_write = previous["audio_output_mode"]
        else:
            mode_to_write = "PCM"

    if policy and hasattr(policy, "write_audio_output_target"):
        policy.write_audio_output_target(home, target_to_write)
    else:
        print("[OPENHTPC] AVERTISSEMENT : write_audio_output_target indisponible; persistance cible audio ignorée.", file=sys.stderr)

    if policy and hasattr(policy, "write_preference"):
        policy.write_preference(home, "audio_output_mode", mode_to_write)
    else:
        print("[OPENHTPC] AVERTISSEMENT : write_preference indisponible; persistance mode audio ignorée.", file=sys.stderr)

    return target_path


def kd(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kdialog", *args], text=True, capture_output=capture, check=False)


def terminal_audio_setup(home: pathlib.Path | None = None) -> tuple[dict, str]:
    mod, outputs = discover_audio_choices()
    sys_desc = default_system_descriptor()

    existing_mode = "PCM"
    if home:
        try:
            prev = json.loads((home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"))
            if prev.get("audio_output_mode") in ("PCM", "BITSTREAM"):
                existing_mode = prev["audio_output_mode"]
        except Exception:
            pass

    if not mod or not outputs:
        print("\nAucune sortie physique détectée, utilisation de la sortie système Fedora.")
        chosen_target = sys_desc
    else:
        rec = mod.recommend_output(outputs, interactive=True)
        rec_node = rec.get("node_name") if isinstance(rec, dict) and rec.get("mode") == "DEVICE" else None

        print("\nConfiguration audio OPENHTPC\n")
        print("Sorties détectées :")
        choices = []
        for idx, o in enumerate(outputs, 1):
            is_rec = bool(rec_node and o.get("node_name") == rec_node)
            rec_str = " (Recommandé)" if is_rec else ""
            label = o.get("display_label") or o.get("node_name")
            print(f"{idx}. {label}{rec_str}")
            choices.append(mod.device_descriptor(o))

        fedora_idx = len(choices) + 1
        print(f"{fedora_idx}. Utiliser la sortie audio définie par Fedora")
        choices.append(sys_desc)

        default_choice = fedora_idx
        prompt_str = f"Choisissez la sortie utilisée par OPENHTPC [{default_choice}] : "
        raw_choice = input(prompt_str).strip()
        if not raw_choice:
            selected_idx = default_choice
        else:
            try:
                val = int(raw_choice)
                if 1 <= val <= len(choices):
                    selected_idx = val
                else:
                    selected_idx = default_choice
            except ValueError:
                selected_idx = default_choice

        chosen_target = choices[selected_idx - 1]

    print("\nMode audio :")
    print("1. PCM")
    print("2. BITSTREAM")
    default_mode_choice = "2" if existing_mode == "BITSTREAM" else "1"
    raw_mode = input(f"Choisissez le mode audio [{default_mode_choice}] : ").strip()
    if not raw_mode:
        chosen_mode = existing_mode
    elif raw_mode == "2" or raw_mode.upper() == "BITSTREAM":
        chosen_mode = "BITSTREAM"
    elif raw_mode == "1" or raw_mode.upper() == "PCM":
        chosen_mode = "PCM"
    else:
        chosen_mode = existing_mode

    return chosen_target, chosen_mode


def graphical_audio_setup(home: pathlib.Path | None = None) -> tuple[dict, str]:
    mod, outputs = discover_audio_choices()
    sys_desc = default_system_descriptor()

    existing_mode = "PCM"
    if home:
        try:
            prev = json.loads((home / ".config/openhtpc/user-config.json").read_text(encoding="utf-8"))
            if prev.get("audio_output_mode") in ("PCM", "BITSTREAM"):
                existing_mode = prev["audio_output_mode"]
        except Exception:
            pass

    if not mod or not outputs:
        chosen_target = sys_desc
    else:
        rec = mod.recommend_output(outputs, interactive=True)
        rec_node = rec.get("node_name") if isinstance(rec, dict) and rec.get("mode") == "DEVICE" else None

        radiolist_items = []
        choice_map = {}

        radiolist_items.extend(["SYSTEM", "Utiliser la sortie audio définie par Fedora", "on"])
        choice_map["SYSTEM"] = sys_desc

        for idx, o in enumerate(outputs, 1):
            tag = str(idx)
            is_rec = bool(rec_node and o.get("node_name") == rec_node)
            rec_str = " (Recommandé)" if is_rec else ""
            label = f"{o.get('display_label') or o.get('node_name')}{rec_str}"
            radiolist_items.extend([tag, label, "off"])
            choice_map[tag] = mod.device_descriptor(o)

        res = kd([
            "--title", "OPENHTPC — Configuration audio",
            "--radiolist", "Choisissez la sortie utilisée par OPENHTPC :",
            *radiolist_items
        ], capture=True)
        if res.returncode == 0 and res.stdout.strip() in choice_map:
            chosen_target = choice_map[res.stdout.strip()]
        else:
            chosen_target = sys_desc

    mode_items = [
        "PCM", "PCM (stéréo / multicanal décodé)", "on" if existing_mode == "PCM" else "off",
        "BITSTREAM", "BITSTREAM (HDMI passthrough Dolby / DTS vers ampli)", "on" if existing_mode == "BITSTREAM" else "off",
    ]
    mode_res = kd([
        "--title", "OPENHTPC — Mode audio",
        "--radiolist", "Choisissez le mode audio :",
        *mode_items,
    ], capture=True)
    if mode_res.returncode == 0 and mode_res.stdout.strip() in ("2", "BITSTREAM"):
        chosen_mode = "BITSTREAM"
    elif mode_res.returncode == 0 and mode_res.stdout.strip() in ("1", "PCM"):
        chosen_mode = "PCM"
    else:
        chosen_mode = existing_mode

    return chosen_target, chosen_mode


def graphical(home: pathlib.Path) -> tuple[list[str], str | None, dict, str] | None:
    if kd(["--title", "OPENHTPC", "--yesno", "Configurer maintenant OPENHTPC V1 ?"]).returncode:
        return None
    sources = []
    while True:
        prompt = "Ajouter un dossier média local ?" if not sources else "Dossiers actuels :\n" + "\n".join(sources) + "\n\nAjouter un autre dossier média ?"
        if kd(["--title", "OPENHTPC — Médias locaux", "--yesno", prompt, "--yes-label", "AJOUTER UN DOSSIER", "--no-label", "CONTINUER"]).returncode:
            break
        result = kd(["--title", "OPENHTPC — Médias locaux", "--getexistingdirectory", str(home)], capture=True)
        if result.returncode:
            continue
        selected = result.stdout.strip()
        if selected and selected not in sources:
            sources.append(selected)
    token = None
    benefit = "TMDb est facultatif.\n\nConnectez-le pour enrichir les fiches avec affiches, synopsis, année, genres et acteurs.\n\nVous pourrez aussi le configurer plus tard depuis OPENHTPC."
    if kd(["--title", "TMDb — Métadonnées enrichies", "--yesno", benefit, "--yes-label", "CONFIGURER", "--no-label", "PLUS TARD"]).returncode == 0:
        result = kd(["--title", "OPENHTPC — TMDb", "--password", "Clé API v3 ou jeton d'accès v4 TMDb (facultatif) :"], capture=True)
        if result.returncode == 0 and result.stdout.strip():
            token = result.stdout.strip()
    audio_target, audio_mode = graphical_audio_setup(home)
    target_label = audio_target.get("display_label") if audio_target.get("mode") == "DEVICE" else "Sortie système Fedora"
    summary_parts = []
    summary_parts.append("Aucune source média" if not sources else "Sources média :\n" + "\n".join(sources))
    summary_parts.append(f"Sortie audio : {target_label}\nMode audio : {audio_mode}")
    summary = "\n\n".join(summary_parts)
    if kd(["--title", "OPENHTPC", "--yesno", summary + "\n\nEnregistrer cette configuration ?"]).returncode:
        return None
    return sources, token, audio_target, audio_mode


def terminal(home: pathlib.Path) -> tuple[list[str], str | None, dict, str] | None:
    if not sys.stdin.isatty():
        return None
    print("OPENHTPC V1 — configuration initiale")
    sources = []
    while True:
        raw = input("Dossier média (vide pour continuer) : ").strip()
        if not raw:
            break
        path = pathlib.Path(raw).expanduser()
        if path.is_dir():
            sources.append(str(path.resolve()))
        else:
            print("Dossier inexistant.", file=sys.stderr)
    token = getpass.getpass("Clé API v3 ou jeton d'accès v4 TMDb (facultatif) : ").strip() or None
    audio_target, audio_mode = terminal_audio_setup(home)
    return sources, token, audio_target, audio_mode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=pathlib.Path, default=pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())))
    parser.add_argument("--media-source", action="append", default=[])
    parser.add_argument("--no-media-sources", action="store_true")
    parser.add_argument("--tmdb-from-stdin", action="store_true")
    parser.add_argument("--default-empty", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    if args.default_empty:
        selected = ([], None, default_system_descriptor(), None)
    elif args.non_interactive:
        if args.media_source and args.no_media_sources:
            parser.error("--media-source et --no-media-sources sont incompatibles")
        token = sys.stdin.read() if args.tmdb_from_stdin else None
        selected = (args.media_source, token, default_system_descriptor(), None)
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        selected = graphical(args.home)
    else:
        selected = terminal(args.home)
    if selected is None:
        print("[OPENHTPC] Configuration initiale requise; Flex ne sera pas lancé.", file=sys.stderr)
        return 3
    try:
        path = save(args.home, *selected)
    except (OSError, ValueError) as exc:
        print(f"[OPENHTPC] Configuration refusée : {exc}", file=sys.stderr)
        return 2
    print(f"[OPENHTPC] Configuration utilisateur enregistrée : {path}")

    # Installation audio summary (RC7 T7.3 J)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    saved_target = cfg.get("audio_output_target", {})
    saved_mode = cfg.get("audio_output_mode", "PCM")
    t_mode = saved_target.get("mode", "SYSTEM")
    t_label = saved_target.get("display_label") or saved_target.get("edid_name") or saved_target.get("node_name") or "Sortie système Fedora"
    mod = _load_audio_module()
    if t_mode == "DEVICE":
        outputs = []
        if mod and hasattr(mod, "discover_outputs"):
            try:
                outputs = mod.discover_outputs()
            except Exception:
                outputs = []
        resolved = mod.resolve_audio(saved_target, outputs) if mod and hasattr(mod, "resolve_audio") else {"AVAILABLE": False}
        if resolved.get("AVAILABLE"):
            print(f"\nInstallation OPENHTPC terminée.\n\nAudio :\nSortie OPENHTPC : {t_label}\nMode : {saved_mode}")
        else:
            print(f"\nInstallation OPENHTPC terminée.\n\nAudio :\nSortie configurée : {t_label}\nÉtat : actuellement indisponible\nOPENHTPC utilisera temporairement la sortie système Fedora.\nMode : {saved_mode}")
    else:
        print(f"\nInstallation OPENHTPC terminée.\n\nAudio :\nSortie OPENHTPC : Sortie système Fedora\nMode : {saved_mode}")

    install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", pathlib.Path(__file__).resolve().parent))
    engine = install / "openhtpc-capabilities.py"
    if engine.is_file():
        subprocess.run([str(engine), "--refresh"], env={**os.environ, "OPENHTPC_HOME": str(args.home), "OPENHTPC_INSTALL_DIR": str(install)}, timeout=45, check=False)
    disc_view = install / "openhtpc-disc-view.py"
    if disc_view.is_file() and (args.home / ".config/openhtpc/secrets/tmdb-token").is_file():
        subprocess.run([str(disc_view), "--home", str(args.home), "--enrich"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
