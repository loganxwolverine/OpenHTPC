#!/usr/bin/env python3
"""Canonical secure TMDb credential lifecycle and bounded service diagnostics."""
from __future__ import annotations
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request

VALIDATION_URL = "https://api.themoviedb.org/3/authentication"
DISPLAY = {
    "NOT_CONFIGURED": "NON CONFIGURÉ",
    "VALID": "CONFIGURATION VALIDE",
    "AUTH_REJECTED": "CLÉ / JETON API REFUSÉ",
    "NETWORK_UNAVAILABLE": "RÉSEAU INDISPONIBLE",
    "SERVICE_UNAVAILABLE": "SERVICE TMDb INDISPONIBLE",
    "TIMEOUT": "DÉLAI DE CONNEXION DÉPASSÉ",
    "TESTING": "TEST EN COURS",
    "UNKNOWN": "ÉTAT INCONNU / NON TESTÉ",
}

def paths(home: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    root = home / ".config/openhtpc"
    return root / "secrets/tmdb-token", root / "tmdb-validation.json", root / "user-config.json"

def credential(home: pathlib.Path) -> str | None:
    target, _, _ = paths(home)
    try:
        value = target.read_text(encoding="utf-8").strip()
        if not value or target.stat().st_mode & 0o077:
            return None
        return value
    except OSError:
        return None

def masked(value: str | None) -> str:
    return "••••" + value[-4:] if value else ""

def _atomic_json(target: pathlib.Path, value: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def _write_credential(home: pathlib.Path, value: str) -> None:
    setup_path = pathlib.Path(__file__).with_name("openhtpc-initial-setup.py")
    spec = importlib.util.spec_from_file_location("openhtpc_tmdb_private", setup_path)
    setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
    setup.write_private(paths(home)[0], value)

def _set_configured(home: pathlib.Path, configured: bool) -> None:
    _, _, target = paths(home)
    try: data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): data = {"schema":1,"configuration_completed":True,"local_media_sources":[]}
    if not isinstance(data, dict): data = {"schema":1,"configuration_completed":True,"local_media_sources":[]}
    data["tmdb"] = {"configured": configured}; _atomic_json(target, data)

def record(home: pathlib.Path, state: str, detail: str) -> dict:
    data = {"schema":1,"state":state,"detail":detail,"tested_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _atomic_json(paths(home)[1], data); return data

def validate(candidate: str, opener=urllib.request.urlopen) -> dict:
    value = candidate.strip()
    if not value: return {"state":"AUTH_REJECTED","detail":"Clé ou jeton API refusé par TMDb"}
    is_v4 = value.startswith("ey")
    url = VALIDATION_URL if is_v4 else VALIDATION_URL + "?api_key=" + value
    headers = {"Accept":"application/json"}
    if is_v4: headers["Authorization"] = "Bearer " + value
    try:
        with opener(urllib.request.Request(url, headers=headers), timeout=8) as response:
            json.load(response)
        return {"state":"VALID","detail":"Connexion à TMDb réussie"}
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403): return {"state":"AUTH_REJECTED","detail":"Clé ou jeton API refusé par TMDb"}
        if 500 <= exc.code <= 599: return {"state":"SERVICE_UNAVAILABLE","detail":"Service TMDb momentanément indisponible"}
        return {"state":"SERVICE_UNAVAILABLE","detail":f"Réponse TMDb indisponible ({exc.code})"}
    except (TimeoutError, socket.timeout):
        return {"state":"TIMEOUT","detail":"Délai de connexion à TMDb dépassé"}
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return {"state":"TIMEOUT","detail":"Délai de connexion à TMDb dépassé"}
        return {"state":"NETWORK_UNAVAILABLE","detail":"Aucun chemin réseau utilisable vers TMDb"}
    except OSError:
        return {"state":"NETWORK_UNAVAILABLE","detail":"Aucun chemin réseau utilisable vers TMDb"}
    except (ValueError, json.JSONDecodeError):
        return {"state":"SERVICE_UNAVAILABLE","detail":"Réponse TMDb illisible"}

def status(home: pathlib.Path) -> dict:
    value = credential(home)
    if not value: return {"state":"NOT_CONFIGURED","label":DISPLAY["NOT_CONFIGURED"],"masked":"","detail":"Aucun accès API TMDb enregistré"}
    try: saved = json.loads(paths(home)[1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): saved = {}
    state = saved.get("state") if saved.get("state") in DISPLAY else "UNKNOWN"
    return {"state":state,"label":DISPLAY[state],"masked":masked(value),"detail":saved.get("detail") or "Accès API TMDb enregistré, non testé"}

def test_stored(home: pathlib.Path, opener=urllib.request.urlopen) -> dict:
    value = credential(home)
    if not value: return status(home)
    result = validate(value, opener); record(home, result["state"], result["detail"]); return status(home)

def replace(home: pathlib.Path, candidate: str, opener=urllib.request.urlopen) -> dict:
    result = validate(candidate, opener)
    if result["state"] != "VALID":
        record(home, result["state"], result["detail"]); return {**status(home), "candidate_state":result["state"], "candidate_detail":result["detail"], "committed":False}
    _write_credential(home, candidate.strip()); _set_configured(home, True); record(home, "VALID", result["detail"])
    return {**status(home), "candidate_state":"VALID", "committed":True}

def delete(home: pathlib.Path) -> dict:
    token, validation, _ = paths(home)
    try: token.unlink()
    except FileNotFoundError: pass
    try: validation.unlink()
    except FileNotFoundError: pass
    _set_configured(home, False); return status(home)

def _dialog(args: list[str], capture=False):
    return subprocess.run(["kdialog", *args], text=True, capture_output=capture, check=False)

def interactive(home: pathlib.Path, action: str) -> int:
    current = status(home)
    if action == "test": result = test_stored(home)
    elif action in {"configure","modify"}:
        entered = _dialog(["--title","OPENHTPC — TMDb","--password","Clé API v3 ou jeton d'accès v4 TMDb :"], True)
        if entered.returncode or not entered.stdout.strip(): return 0
        result = replace(home, entered.stdout.strip())
        if not result.get("committed"):
            _dialog(["--title","OPENHTPC — TMDb","--error",DISPLAY[result["candidate_state"]] + "\n" + result["candidate_detail"]]); return 2
    elif action == "delete":
        answer = _dialog(["--title","OPENHTPC — TMDb","--warningyesno","Supprimer l'accès API TMDb enregistré ?","--yes-label","SUPPRIMER","--no-label","ANNULER"])
        if answer.returncode: return 0
        result = delete(home)
    else: result = current
    _dialog(["--title","OPENHTPC — TMDb","--msgbox",result["label"] + "\n" + result["detail"]])
    return 0

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=("show","test","configure","modify","delete"));parser.add_argument("--home",type=pathlib.Path,default=pathlib.Path(os.environ.get("OPENHTPC_HOME",pathlib.Path.home())))
    args=parser.parse_args();return interactive(args.home,args.action)
if __name__ == "__main__": raise SystemExit(main())
