#!/usr/bin/env bash
set -Eeuo pipefail
readonly INSTALL_DIR="${HOME}/.local/lib/openhtpc"
readonly BIN_DIR="${HOME}/.local/bin"
purge=false
case ${1:-} in "") ;; --purge-config) purge=true ;; *) printf 'Usage: ./uninstall.sh [--purge-config]\n' >&2; exit 2;; esac
remove_link() { [[ -L $1 && $(readlink -- "$1") == "$2" ]] && rm -- "$1" || true; }
for command in openhtpc openhtpc-builder openhtpc-player-test openhtpc-session-start openhtpc-media-browser openhtpc-validator; do
    target=$INSTALL_DIR/$command
    case $command in openhtpc-builder) target=$INSTALL_DIR/openhtpc-builder.sh;; openhtpc-player-test) target=$INSTALL_DIR/openhtpc-player-test.sh;; esac
    remove_link "$BIN_DIR/$command" "$target"
done
autostart="$HOME/.config/autostart/openhtpc.desktop"
if [[ -L $autostart ]]; then :
elif [[ -f $autostart ]] && grep -Fq 'X-OPENHTPC-Managed=true' "$autostart"; then rm -- "$autostart"; fi
app_desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/openhtpc.desktop"
if [[ -L $app_desktop ]]; then :
elif [[ -f $app_desktop ]] && grep -Fq 'X-OPENHTPC-Managed=true' "$app_desktop"; then rm -- "$app_desktop"; fi
# Legacy releases have an explicit set of known closed-layout versions.
if [[ -f $INSTALL_DIR/VERSION && ! -L $INSTALL_DIR ]] && grep -Eq '^(4\.0\.0-basic-v1-rc[0-9]+|1\.0\.0|1\.1\.0-dev[1-9]|1\.1\.0-dev1[0-9]|1\.1\.0-dev2[0-9]|1\.1\.0-dev3[0-9]|1\.2\.0-dev[0-9]+)$' "$INSTALL_DIR/VERSION"; then
    rm -rf -- "$INSTALL_DIR"
elif [[ -d $INSTALL_DIR && ! -L $INSTALL_DIR && -f $INSTALL_DIR/VERSION && ! -L $INSTALL_DIR/VERSION ]] && grep -Eq '^1\.3\.[0-9]+(-rc[0-9]+)?$' "$INSTALL_DIR/VERSION"; then
    # 1.3.x uses a managed-file manifest: remove the declared product files
    # only. Empty directories are then removed bottom-up. Unknown user files
    # survive, including custom plugins. Never traverse symbolic-link parents.
    python3 - "$INSTALL_DIR" <<'PY_MANAGED'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
manifest = root / ".openhtpc-managed-files"
if not manifest.is_file() or manifest.is_symlink():
    raise SystemExit("OPENHTPC_UNINSTALL_MANIFEST_MISSING: refusing unsafe cleanup")
root = root.resolve(strict=True)
entries = set()
for line in manifest.read_text(encoding="utf-8").splitlines():
    value = line.strip()
    if not value or value.startswith("#"):
        continue
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise SystemExit("OPENHTPC_UNINSTALL_MANIFEST_UNSAFE")
    entries.add(path)
if not {pathlib.PurePosixPath("VERSION"),
        pathlib.PurePosixPath(".openhtpc-managed-files"),
        pathlib.PurePosixPath("openhtpc")}.issubset(entries):
    raise SystemExit("OPENHTPC_UNINSTALL_MANIFEST_INCOMPLETE")
# Preflight the entire manifest before unlinking anything. No partial
# deletion is allowed when a later entry is unsafe.
targets = []
parents = set()
for relative in sorted(entries, key=lambda p: (-len(p.parts), p.as_posix())):
    target = root.joinpath(*relative.parts)
    parent = target.parent
    resolved_parent = parent.resolve(strict=False)
    if resolved_parent != root and root not in resolved_parent.parents:
        raise SystemExit("OPENHTPC_UNINSTALL_MANAGED_PATH_ESCAPES_ROOT")
    if target.is_dir() and not target.is_symlink():
        raise SystemExit("OPENHTPC_UNINSTALL_MANAGED_PATH_IS_DIRECTORY")
    targets.append(target)
    while parent != root:
        parents.add(parent)
        parent = parent.parent
for target in targets:
    if target.is_symlink() or target.is_file():
        target.unlink()
for parent in sorted(parents, key=lambda p: -len(p.parts)):
    try:
        parent.rmdir()
    except OSError:
        pass
try:
    root.rmdir()
except OSError:
    print("[OPENHTPC] Unmanaged files preserved in " + str(root))
PY_MANAGED
fi





if $purge; then
    printf '[OPENHTPC] La configuration OPENHTPC va être supprimée; les dossiers média ne seront jamais touchés.\n'
    rm -rf -- "$HOME/.config/openhtpc" "$HOME/.cache/openhtpc" "$HOME/.local/state/openhtpc" "$HOME/.local/share/openhtpc"
else
    printf '[OPENHTPC] Configuration utilisateur conservée. Utilisez --purge-config pour la supprimer explicitement.\n'
fi
printf '[OPENHTPC] Désinstallation terminée. Vos médias n’ont pas été modifiés.\n'
