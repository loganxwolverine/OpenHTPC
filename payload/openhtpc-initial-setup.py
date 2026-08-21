#!/usr/bin/env python3
"""Small KDE/terminal initial configuration assistant for OPENHTPC V1."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import subprocess
import sys
import tempfile


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


def save(home: pathlib.Path, sources: list[str], tmdb_value: str | None) -> pathlib.Path:
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
    configured = bool(tmdb_value and tmdb_value.strip())
    if configured:
        write_private(credential, tmdb_value or "")
    config = {
        "schema": 1,
        "configuration_completed": True,
        "local_media_sources": normalized,
        "tmdb": {"configured": configured},
    }
    target = root / "user-config.json"
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def kd(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kdialog", *args], text=True, capture_output=capture, check=False)


def graphical(home: pathlib.Path) -> tuple[list[str], str | None] | None:
    if kd(["--title", "OPENHTPC", "--yesno", "Configurer maintenant OPENHTPC V1 ?"]).returncode:
        return None
    sources = []
    while True:
        prompt="Ajouter un dossier média local ?" if not sources else "Dossiers actuels :\n"+"\n".join(sources)+"\n\nAjouter un autre dossier média ?"
        if kd(["--title", "OPENHTPC — Médias locaux", "--yesno", prompt, "--yes-label", "AJOUTER UN DOSSIER", "--no-label", "CONTINUER"]).returncode: break
        result = kd(["--title", "OPENHTPC — Médias locaux", "--getexistingdirectory", str(home)], capture=True)
        if result.returncode:
            continue
        selected = result.stdout.strip()
        if selected and selected not in sources:
            sources.append(selected)
    token = None
    benefit = "TMDb est facultatif.\n\nConnectez-le pour enrichir les fiches avec affiches, synopsis, année, genres et acteurs.\n\nVous pourrez aussi le configurer plus tard depuis OPENHTPC."
    if kd(["--title", "TMDb — Métadonnées enrichies", "--yesno", benefit, "--yes-label", "CONFIGURER", "--no-label", "PLUS TARD"]).returncode == 0:
        result = kd(["--title", "OPENHTPC — TMDb", "--password", "Clé TMDb privée (facultative) :"], capture=True)
        if result.returncode == 0 and result.stdout.strip():
            token = result.stdout.strip()
    summary = "Aucune source média" if not sources else "Sources média :\n" + "\n".join(sources)
    if kd(["--title", "OPENHTPC", "--yesno", summary + "\n\nEnregistrer cette configuration ?"]).returncode:
        return None
    return sources, token


def terminal(home: pathlib.Path) -> tuple[list[str], str | None] | None:
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
    token = getpass.getpass("Clé TMDb facultative (vide = plus tard) : ").strip() or None
    return sources, token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=pathlib.Path, default=pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home())))
    parser.add_argument("--media-source", action="append", default=[])
    parser.add_argument("--no-media-sources", action="store_true")
    parser.add_argument("--tmdb-from-stdin", action="store_true")
    parser.add_argument("--default-empty", action="store_true")
    args = parser.parse_args()
    if args.default_empty:
        selected = ([], None)
    elif args.non_interactive:
        if args.media_source and args.no_media_sources:
            parser.error("--media-source et --no-media-sources sont incompatibles")
        token = sys.stdin.read() if args.tmdb_from_stdin else None
        selected = (args.media_source, token)
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
