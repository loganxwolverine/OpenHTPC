#!/usr/bin/env python3
"""OPENHTPC 1.1 Phase C2 Blind Visual Qualification Harness (Dev13)."""
from __future__ import annotations
import argparse
import datetime
import json
import os
import pathlib
import select
import socket
import subprocess
import sys
import time

STATE_DIR = pathlib.Path(os.environ.get("OPENHTPC_STATE_DIR", pathlib.Path.home() / ".local/state/openhtpc"))
INSTALL_DIR = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", pathlib.Path.home() / ".local/lib/openhtpc"))
SHADERS_DIR = INSTALL_DIR / "assets" / "shaders"
BENCHMARK_DIR = INSTALL_DIR / "assets" / "benchmark"
SESSION_LOG_PATH = STATE_DIR / "visual_review_session.json"
KEY_MAP_PATH = STATE_DIR / "blind_review_key.json"
AUX_CAPTURES_DIR = STATE_DIR / "auxiliary_captures"

# Fresh Authoritative Blind Mode Mapping (New randomized assignment, 5 viable DVD_PAL recipes)
BLIND_MODES = [
    {
        "mode_label": "MODE A",
        "recipe_id": "RECIPE_C2_DVD_RAVU_LITE",
        "name": "RAVU Lite AR r4",
        "shaders": ["ravu-lite-ar-r4.hook"],
        "key": "1"
    },
    {
        "mode_label": "MODE B",
        "recipe_id": "RECIPE_C2_DVD_CFL_LITE",
        "name": "CfL Prediction Lite",
        "shaders": ["CfL_Prediction_Lite.glsl"],
        "key": "2"
    },
    {
        "mode_label": "MODE C",
        "recipe_id": "RECIPE_0_PURE",
        "name": "PURE Baseline",
        "shaders": [],
        "key": "3"
    },
    {
        "mode_label": "MODE D",
        "recipe_id": "RECIPE_C2_DVD_KRIG_BILATERAL",
        "name": "KrigBilateral Chroma",
        "shaders": ["KrigBilateral.glsl"],
        "key": "4"
    },
    {
        "mode_label": "MODE E",
        "recipe_id": "RECIPE_C2_DVD_FSRCNNX_8",
        "name": "FSRCNNX 8-0-4-1",
        "shaders": ["FSRCNNX_x2_8-0-4-1.glsl"],
        "key": "5"
    }
]


class ReviewIPCClient:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock: socket.socket | None = None

    def connect(self, timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(self.socket_path):
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(self.socket_path)
                    self.sock.settimeout(2.0)
                    return True
                except (socket.error, OSError):
                    time.sleep(0.1)
            else:
                time.sleep(0.1)
        return False

    def command(self, args: list) -> dict | None:
        if not self.sock:
            return None
        payload = json.dumps({"command": args}) + "\n"
        try:
            self.sock.sendall(payload.encode("utf-8"))
            buf = b""
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
            if buf:
                lines = [l.strip() for l in buf.decode("utf-8", errors="ignore").split("\n") if l.strip()]
                for l in lines:
                    try:
                        parsed = json.loads(l)
                        if "data" in parsed or "error" in parsed:
                            return parsed
                    except Exception:
                        pass
        except Exception:
            return None
        return None

    def get_property(self, prop: str):
        res = self.command(["get_property", prop])
        if res and isinstance(res, dict):
            return res.get("data")
        return None

    def set_property(self, prop: str, val):
        return self.command(["set_property", prop, val])

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def persist_blind_mapping():
    """Persist the blind mapping to private state file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    mapping_data = {
        "schema_version": 2,
        "review_version": "1.1-c2-dev2",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "description": "Authoritative blind mode assignment for OPENHTPC Phase C2 real DVD evaluation",
        "modes": BLIND_MODES
    }
    KEY_MAP_PATH.write_text(json.dumps(mapping_data, indent=2) + "\n", encoding="utf-8")


def get_canonical_readahead_args() -> list[str]:
    """Retrieve canonical Phase C0 Adaptive Read-Ahead flags dynamically from policy engine."""
    readahead_script = INSTALL_DIR / "openhtpc-readahead.py"
    if not readahead_script.exists():
        readahead_script = pathlib.Path(__file__).resolve().parent / "openhtpc-readahead.py"

    if readahead_script.exists():
        try:
            res = subprocess.run([sys.executable, str(readahead_script), "--source=OPTICAL", "--json"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            if res.returncode == 0:
                data = json.loads(res.stdout.decode("utf-8"))
                opts = data.get("mpv_options", [])
                if opts and isinstance(opts, list):
                    return opts
        except Exception:
            pass

    # Fallback to qualified Phase C0 baseline
    return [
        "--cache=yes",
        "--demuxer-readahead-secs=12.0",
        "--demuxer-max-bytes=268435456",
        "--demuxer-max-back-bytes=67108864",
        "--demuxer-thread=yes",
        "--cache-pause=yes",
        "--cache-pause-initial=no",
        "--cache-pause-wait=1",
        "--cache-on-disk=no"
    ]


def detect_and_validate_dvd_device(explicit_device: str | None = None) -> tuple[bool, str, str]:
    """Verify optical device exists, media is present, and DVD-Video is readable.
    Returns: (is_valid, device_path, error_reason)
    """
    candidate_devices = [explicit_device] if explicit_device else ["/dev/dvd", "/dev/sr0", "/dev/cdrom"]
    candidate_devices = [d for d in candidate_devices if d and os.path.exists(d)]

    if not candidate_devices:
        return False, "", "AUCUN_LECTEUR_OPTIQUE"

    for dev in candidate_devices:
        try:
            res = subprocess.run(["lsdvd", "-q", dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3.0)
            if res.returncode == 0 and b"Title:" in res.stdout:
                return True, dev, ""
            elif res.returncode == 0 and b"Disc Title:" in res.stdout:
                return True, dev, ""
        except Exception:
            pass

    return False, candidate_devices[0], "AUCUN_DISQUE_DVD_VIDEO"


def generate_auxiliary_captures():
    """Generate exact-timestamp auxiliary PNG captures for the 5 viable modes."""
    AUX_CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    asset_path = BENCHMARK_DIR / "c1_dvd_pal.mpg"
    if not asset_path.exists():
        return

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"

    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-0"

    for mode in BLIND_MODES:
        out_png = AUX_CAPTURES_DIR / f"{mode['mode_label'].replace(' ', '_')}.png"
        ipc_sock = f"/tmp/openhtpc_aux_cap_{os.getpid()}_{int(time.time()*1000)%10000}.sock"
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)

        cmd = [
            "mpv",
            "--no-config",
            f"--include={pure_conf}",
            f"--input-ipc-server={ipc_sock}",
            "--ao=null",
            "--keep-open=no",
            "--no-terminal",
            "--fs",
            f"--start=5.0",
            "--pause"
        ]
        if mode["shaders"]:
            shader_paths = [str(SHADERS_DIR / s) for s in mode["shaders"] if (SHADERS_DIR / s).exists()]
            if shader_paths:
                cmd.append(f"--glsl-shaders={':'.join(shader_paths)}")

        cmd.append(str(asset_path))
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ipc = ReviewIPCClient(ipc_sock)
        if ipc.connect(timeout=4.0):
            time.sleep(0.5)
            ipc.command(["screenshot-to-file", str(out_png), "window"])
            time.sleep(0.5)
            ipc.command(["quit"])
            proc.wait(timeout=3.0)
            ipc.close()
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)


def run_visual_review_session(target_source: str | None = None, is_dvd: bool = False):
    """Launch the interactive blind visual review couch session."""
    persist_blind_mapping()

    readahead_args = get_canonical_readahead_args()

    pure_conf = pathlib.Path.home() / ".config/openhtpc/runtime/mpv/pure.conf"
    if not pure_conf.exists():
        pure_conf = INSTALL_DIR / "pure.conf"

    ipc_sock = f"/tmp/openhtpc_review_{os.getpid()}.sock"
    if os.path.exists(ipc_sock):
        os.unlink(ipc_sock)

    # Generate custom input.conf for live switching during review
    input_conf_path = STATE_DIR / "review_input.conf"
    input_lines = [
        "# OPENHTPC Blind Review Couch Keybindings",
        "1 script-message openhtpc-set-mode 0",
        "2 script-message openhtpc-set-mode 1",
        "3 script-message openhtpc-set-mode 2",
        "4 script-message openhtpc-set-mode 3",
        "5 script-message openhtpc-set-mode 4",
        "RIGHT script-message openhtpc-cycle-mode next",
        "LEFT script-message openhtpc-cycle-mode prev",
        "NEXT script-message openhtpc-cycle-mode next",
        "PREV script-message openhtpc-cycle-mode prev",
        "TAB script-message openhtpc-cycle-mode next",
        "ENTER seek 0 absolute",
        "SPACE cycle pause",
        "ESC quit",
        "q quit",
        "BS quit"
    ]
    input_conf_path.write_text("\n".join(input_lines) + "\n", encoding="utf-8")

    # Determine playback source and base MPV arguments
    if is_dvd:
        valid_dvd, dvd_dev, err = detect_and_validate_dvd_device(target_source)
        if not valid_dvd:
            print("[OPENHTPC] AUCUN DVD-VIDEO LISIBLE DÉTECTÉ.", file=sys.stderr)
            print("Statut : NO_DVD_PRESENT", file=sys.stderr)
            print("Insérez un DVD-Video dans le lecteur optique puis relancez openhtpc visual-review --dvd.", file=sys.stderr)
            sys.exit(1)

        source_label = f"DISQUE DVD PHYSIQUE ({dvd_dev})"
        mpv_base_cmd = [
            "mpv",
            "--no-config",
            f"--include={pure_conf}",
            *readahead_args,
            "--fullscreen=yes",
            "--force-window=immediate",
            "--border=no",
            "--terminal=no",
            "--cursor-autohide=1000",
            f"--input-ipc-server={ipc_sock}",
            f"--input-conf={input_conf_path}",
            f"--dvd-device={dvd_dev}",
            "dvd://longest"
        ]
    else:
        source_arg = target_source or str(BENCHMARK_DIR / "c1_dvd_pal.mpg")
        if not os.path.exists(source_arg):
            print(f"[OPENHTPC] Asset introuvable : {source_arg}", file=sys.stderr)
            sys.exit(1)
        source_label = "ASSET DVD_PAL QUALIFIÉ (720x576 @ 25 fps MPEG-2)"
        mpv_base_cmd = [
            "mpv",
            "--no-config",
            f"--include={pure_conf}",
            "--fullscreen=yes",
            "--force-window=immediate",
            "--border=no",
            "--terminal=no",
            "--cursor-autohide=1000",
            f"--input-ipc-server={ipc_sock}",
            f"--input-conf={input_conf_path}",
            "--loop-file=inf",
            source_arg
        ]

    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-0"

    print("============================================================")
    print("OPENHTPC 1.1 — BLIND VISUAL COUCH REVIEW (PHASE C2)")
    print("============================================================")
    print(f"Source de lecture :  {source_label}")
    print("Cible d'affichage :  3840x2160 Plein écran @ 60 Hz (gpu-next / Vulkan)")
    print("")
    print("Contrôles télécommande / clavier :")
    print("  [1]           -> MODE A")
    print("  [2]           -> MODE B")
    print("  [3]           -> MODE C")
    print("  [4]           -> MODE D")
    print("  [5]           -> MODE E")
    print("  [FLECHE D/G]  -> Mode Suivant / Précédent")
    print("  [ESPACE]      -> Pause / Reprise (changement de mode actif sur image fixe)")
    print("  [ENTRÉE]      -> Rejouer la séquence")
    print("  [ECHAP / Q]   -> Quitter la session d'évaluation")
    print("============================================================")
    print("Lancement de la session en plein écran...")

    start_time = time.time()
    proc = subprocess.Popen(mpv_base_cmd, env=env)

    ipc = ReviewIPCClient(ipc_sock)
    connected = ipc.connect(timeout=6.0)

    # Check for early failure
    if not connected or proc.poll() is not None:
        exit_code = proc.poll() if proc.poll() is not None else "TIMEOUT"
        print(f"[OPENHTPC] ERREUR: VISUAL_REVIEW_START_FAILED (code: {exit_code})", file=sys.stderr)
        if proc.poll() is None:
            proc.kill()
        sys.exit(1)

    # Start in MODE A
    current_mode_idx = 0
    switch_counts = {m["mode_label"]: 0 for m in BLIND_MODES}

    def apply_mode(idx: int):
        m = BLIND_MODES[idx]
        switch_counts[m["mode_label"]] += 1
        if m["shaders"]:
            spaths = [str(SHADERS_DIR / s) for s in m["shaders"] if (SHADERS_DIR / s).exists()]
            ipc.command(["change-list", "glsl-shaders", "set", ":".join(spaths)])
        else:
            ipc.command(["change-list", "glsl-shaders", "clr", ""])
        ipc.command(["show-text", f"{m['mode_label']}", 1500])

        # Redraw frame if currently paused so shader switch is immediately visible
        is_paused = ipc.get_property("pause")
        if is_paused:
            ipc.command(["seek", 0, "relative+exact"])

    time.sleep(1.0)
    apply_mode(current_mode_idx)

    # Monitor IPC events & telemetry quietly
    telemetry = {
        "session_start": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": source_label,
        "mode_telemetry": {
            m["mode_label"]: {
                "time_active_s": 0.0,
                "vo_drops": 0,
                "decoder_drops": 0,
                "delayed_frames": 0,
                "switch_count": 0
            } for m in BLIND_MODES
        }
    }

    last_check = time.time()
    try:
        while proc.poll() is None:
            r, _, _ = select.select([ipc.sock], [], [], 0.2)
            if r:
                try:
                    raw = ipc.sock.recv(4096)
                    if raw:
                        for line in raw.decode("utf-8", errors="ignore").split("\n"):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                msg = json.loads(line)
                                if msg.get("event") == "client-message":
                                    args = msg.get("args", [])
                                    if len(args) >= 2 and args[0] == "openhtpc-set-mode":
                                        target_idx = int(args[1]) % len(BLIND_MODES)
                                        current_mode_idx = target_idx
                                        apply_mode(current_mode_idx)
                                    elif len(args) >= 2 and args[0] == "openhtpc-cycle-mode":
                                        direction = args[1]
                                        if direction == "next":
                                            current_mode_idx = (current_mode_idx + 1) % len(BLIND_MODES)
                                        else:
                                            current_mode_idx = (current_mode_idx - 1) % len(BLIND_MODES)
                                        apply_mode(current_mode_idx)
                            except Exception:
                                pass
                except Exception:
                    pass

            now = time.time()
            elapsed = now - last_check
            last_check = now
            cur_label = BLIND_MODES[current_mode_idx]["mode_label"]
            telemetry["mode_telemetry"][cur_label]["time_active_s"] += elapsed
    except KeyboardInterrupt:
        pass
    finally:
        if ipc.sock:
            try:
                vo_d = ipc.get_property("frame-drop-count") or 0
                dec_d = ipc.get_property("decoder-frame-drop-count") or 0
                del_f = ipc.get_property("vo-delayed-frame-count") or 0
                cur_label = BLIND_MODES[current_mode_idx]["mode_label"]
                telemetry["mode_telemetry"][cur_label]["vo_drops"] = vo_d
                telemetry["mode_telemetry"][cur_label]["decoder_drops"] = dec_d
                telemetry["mode_telemetry"][cur_label]["delayed_frames"] = del_f
                for m in BLIND_MODES:
                    lbl = m["mode_label"]
                    telemetry["mode_telemetry"][lbl]["switch_count"] = switch_counts[lbl]
                ipc.command(["quit"])
            except Exception:
                pass
            ipc.close()
        proc.wait(timeout=3.0)
        if os.path.exists(ipc_sock):
            os.unlink(ipc_sock)

    telemetry["session_end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    SESSION_LOG_PATH.write_text(json.dumps(telemetry, indent=2) + "\n", encoding="utf-8")
    print("\n[OPENHTPC] Session d'évaluation visuelle terminée.")
    print(f"[OPENHTPC] Télémétrie enregistrée : {SESSION_LOG_PATH}")


def print_review_instructions():
    print("""
======================================================================
OPENHTPC 1.1 — PHASE C2 BLIND VISUAL QUALIFICATION PROTOCOL
======================================================================

5 modes de rendu sont comparés sous conditions canapé réelles (4K60 Plein écran) :
- MODE A
- MODE B
- MODE C
- MODE D
- MODE E

L'un de ces modes est PURE (référence native non transformée).
Les quatre autres sont les recettes d'amélioration d'image techniquement viables.

Consignes pour l'évaluateur (Steve) :
1. Insérez le DVD de test dans le lecteur optique.
2. Lancez la session de revue visuelle sur DVD réel :
     openhtpc visual-review --dvd

3. Naviguez entre les modes avec les touches 1, 2, 3, 4, 5 ou les flèches GAUCHE / DROITE.
4. Mettez en pause (ESPACE) sur un plan de cadrage représentatif (visage, texture, arrière-plan).
   Alternez entre les modes pour comparer directement les différences sur image fixe ou en mouvement.
5. Évaluez :
   - Naturel du visage et carnations
   - Précision des textures et détails fins
   - Absence d'artefacts (halos, ringing, shimmering, lissage excessif)
   - Stabilité en travelling / mouvement
   - Rendu du grain et des aplats sombres

6. Remplissez la grille d'évaluation pour chaque mode :
   - Note globale : [ PREFERRED | ACCEPTABLE | REJECTED ]
   - Classement : de 1 (meilleur) à 5 (moins bon)
   - Remarques qualitatives

Le décodage de la correspondance MODE A..E -> Recettes techniques
sera effectué uniquement après enregistrement de votre verdict visuel.
======================================================================
""")


def main():
    parser = argparse.ArgumentParser(description="OPENHTPC Phase C2 Blind Visual Qualification Harness")
    parser.add_argument("action", nargs="?", default="start", choices=["start", "info", "captures", "dvd"], help="Action to execute")
    parser.add_argument("--dvd", action="store_true", help="Play physical DVD from drive")
    parser.add_argument("--source", help="Custom source path or URI")
    parser.add_argument("--generate-captures", action="store_true", help="Generate auxiliary PNG captures")

    args = parser.parse_args()

    if args.action == "info":
        print_review_instructions()
    elif args.action == "captures" or args.generate_captures:
        print("[OPENHTPC] Génération des captures auxiliaires PNG...")
        generate_auxiliary_captures()
        print(f"[OPENHTPC] Captures générées dans : {AUX_CAPTURES_DIR}")
    elif args.action == "dvd" or args.dvd:
        run_visual_review_session(target_source=args.source, is_dvd=True)
    else:
        run_visual_review_session(target_source=args.source, is_dvd=False)


if __name__ == "__main__":
    main()
