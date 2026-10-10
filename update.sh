#!/usr/bin/env bash
set -Eeuo pipefail
readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INSTALL_DIR="${OPENHTPC_INSTALL_DIR:-$HOME/.local/lib/openhtpc}"
readonly INSTALLED_MANIFEST="$INSTALL_DIR/.openhtpc-managed-files"
readonly TARGET_MANIFEST="$ROOT/payload/managed-files.txt"
readonly LEGACY_DEV27_MANIFEST="$ROOT/legacy-managed-files-dev27.txt"
printf '[OPENHTPC] Mise à jour ciblée : configuration, Hardware Passport et dépendances existantes seront conservés.\n'

# A dry-run must be genuinely non-mutating: do not stop a live OPENHTPC session
# before delegating --check to the installer.
for arg in "$@"; do
    if [[ $arg == "--check" ]]; then
        export OPENHTPC_UPDATE_MODE=1
        exec "$ROOT/install.sh" "$@"
    fi
done

# Refuse an in-place update while any authoritative playback is active, and
# hold the same lock for the whole update so a new playback cannot start after
# this preflight.  Keep the legacy DVD lock as a transition guard for older
# installed dispatchers which do not yet know playback-active.lock.
playback_lock="$HOME/.local/state/openhtpc/playback-active.lock"
dvd_lock="$HOME/.local/state/openhtpc/play-dvd.lock"
mkdir -p "$(dirname "$playback_lock")"
exec 7>"$playback_lock"
if ! flock -n 7; then
    printf '[OPENHTPC] ERREUR : une lecture est en cours. Arrêtez la lecture avant de mettre OPENHTPC à jour.\n' >&2
    exit 4
fi
exec 8>"$dvd_lock"
if ! flock -n 8; then
    printf '[OPENHTPC] ERREUR : une lecture DVD est en cours. Arrêtez la lecture avant de mettre OPENHTPC à jour.\n' >&2
    exit 4
fi
# File descriptors 7 and 8 intentionally remain locked until update.sh exits.

# Remember whether the appliance session was running before update cleanup.
# A successful in-place update must restore the same user-visible state instead
# of leaving Plasma in appliance mode with no Flex window.
was_running=0
restart_required=0
runtime_state="$HOME/.local/state/openhtpc/runtime-session.json"
if [[ -r $runtime_state ]] && python3 - "$runtime_state" <<'PY_STATE'
import json, pathlib, sys
try:
    data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
raise SystemExit(0 if data.get("state") == "RUNNING" else 1)
PY_STATE
then
    was_running=1
fi

restore_preupdate_session_on_exit() {
    local rc=$?
    if (( rc != 0 && was_running && restart_required )); then
        trap - EXIT
        if [[ -x $INSTALL_DIR/openhtpc ]]; then
            if "$INSTALL_DIR/openhtpc" start; then
                printf '[OPENHTPC] Échec de mise à jour : session OPENHTPC précédente restaurée.\n' >&2
            else
                printf '[OPENHTPC] ERREUR : échec de mise à jour et impossible de restaurer automatiquement OPENHTPC.\n' >&2
            fi
        else
            printf '[OPENHTPC] ERREUR : échec de mise à jour et lanceur OPENHTPC indisponible pour restauration.\n' >&2
        fi
        exit "$rc"
    fi
}
trap restore_preupdate_session_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# From this point onward, a failed mutation must attempt to restore the session
# that was active before cleanup.
if (( was_running )); then
    restart_required=1
fi

if [[ -x $ROOT/payload/openhtpc-runtime.py ]]; then
    if ! OPENHTPC_INSTALL_DIR="${OPENHTPC_INSTALL_DIR:-$HOME/.local/lib/openhtpc}" \
        "$ROOT/payload/openhtpc-runtime.py" cleanup-legacy >/dev/null; then
        printf '[OPENHTPC] ERREUR : impossible de stabiliser les anciens processus OPENHTPC.\n' >&2
        exit 1
    fi
fi
if [[ -d $INSTALL_DIR ]]; then
    previous_manifest=$INSTALLED_MANIFEST
    if [[ ! -f $previous_manifest ]]; then
        previous_manifest=$LEGACY_DEV27_MANIFEST
    fi
    [[ -r $previous_manifest && -r $TARGET_MANIFEST ]] || {
        printf '[OPENHTPC] ERREUR : manifeste de fichiers gérés absent; nettoyage refusé.\n' >&2
        exit 1
    }
    python3 "$ROOT/payload/openhtpc-update-managed-files" \
        --install-dir "$INSTALL_DIR" --previous "$previous_manifest" --target "$TARGET_MANIFEST"
fi
# RC23 invalidates only RC22's obsolete standalone MEDIA UI artifacts.
# User configuration, media roots and playback history remain untouched.
rm -f -- "$HOME/.config/openhtpc/media-browser.ini" \
    "$HOME/.config/openhtpc/media-browser-paths.json" \
    "$HOME/.local/state/openhtpc/media-model.json"
export OPENHTPC_UPDATE_MODE=1
"$ROOT/install.sh" "$@"

if (( was_running )); then
    "$INSTALL_DIR/openhtpc" start
    restart_required=0
    printf '[OPENHTPC] Session active avant mise à jour : OPENHTPC relancé automatiquement.\n'
fi
