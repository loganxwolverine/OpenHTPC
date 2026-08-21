#!/usr/bin/env bash
set -Eeuo pipefail
readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly INSTALL_DIR="${OPENHTPC_INSTALL_DIR:-$HOME/.local/lib/openhtpc}"
readonly INSTALLED_MANIFEST="$INSTALL_DIR/.openhtpc-managed-files"
readonly TARGET_MANIFEST="$ROOT/payload/managed-files.txt"
readonly LEGACY_DEV27_MANIFEST="$ROOT/legacy-managed-files-dev27.txt"
printf '[OPENHTPC] Mise à jour ciblée : configuration, Hardware Passport et dépendances existantes seront conservés.\n'
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
exec "$ROOT/install.sh" "$@"
