#!/usr/bin/env bash
set -Eeuo pipefail
readonly INSTALL_DIR="${HOME}/.local/lib/openhtpc"
readonly BIN_DIR="${HOME}/.local/bin"
purge=false
case ${1:-} in "") ;; --purge-config) purge=true ;; *) printf 'Usage: ./uninstall.sh [--purge-config]\n' >&2; exit 2;; esac
remove_link() { [[ -L $1 && $(readlink -- "$1") == "$2" ]] && rm -- "$1" || true; }
for command in openhtpc openhtpc-builder openhtpc-player-test openhtpc-session-start openhtpc-media-browser; do
    target=$INSTALL_DIR/$command
    case $command in openhtpc-builder) target=$INSTALL_DIR/openhtpc-builder.sh;; openhtpc-player-test) target=$INSTALL_DIR/openhtpc-player-test.sh;; esac
    remove_link "$BIN_DIR/$command" "$target"
done
autostart="$HOME/.config/autostart/openhtpc.desktop"
if [[ -f $autostart ]] && grep -Fq 'X-OPENHTPC-Managed=true' "$autostart"; then rm -- "$autostart"; fi
if [[ -f $INSTALL_DIR/VERSION ]] && grep -Eq '^(4\.0\.0-basic-v1-rc[0-9]+|1\.0\.0|1\.1\.0-dev[1-9]|1\.1\.0-dev1[0-9]|1\.1\.0-dev2[0-9])$' "$INSTALL_DIR/VERSION"; then rm -rf -- "$INSTALL_DIR"; fi





if $purge; then
    printf '[OPENHTPC] La configuration OPENHTPC va être supprimée; les dossiers média ne seront jamais touchés.\n'
    rm -rf -- "$HOME/.config/openhtpc" "$HOME/.cache/openhtpc" "$HOME/.local/state/openhtpc" "$HOME/.local/share/openhtpc"
else
    printf '[OPENHTPC] Configuration utilisateur conservée. Utilisez --purge-config pour la supprimer explicitement.\n'
fi
printf '[OPENHTPC] Désinstallation terminée. Vos médias n’ont pas été modifiés.\n'
