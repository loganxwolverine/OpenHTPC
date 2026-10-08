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

# Refuse an in-place update while an authoritative DVD playback lock is held.
# Tracked playback can inherit the UI session lock; stopping Flex underneath it
# would strand the appliance on a black Plasma surface until playback exits.
dvd_lock="$HOME/.local/state/openhtpc/play-dvd.lock"
mkdir -p "$(dirname "$dvd_lock")"
exec 7>"$dvd_lock"
if ! flock -n 7; then
    printf '[OPENHTPC] ERREUR : une lecture DVD est en cours. Arrêtez la lecture avant de mettre OPENHTPC à jour.\n' >&2
    exit 4
fi
flock -u 7
exec 7>&-

# Remember whether the appliance session was running before update cleanup.
# A successful in-place update must restore the same user-visible state instead
# of leaving Plasma in appliance mode with no Flex window.
was_running=0
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
    printf '[OPENHTPC] Session active avant mise à jour : OPENHTPC relancé automatiquement.\n'
fi
