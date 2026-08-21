#!/usr/bin/env bash
set -Eeuo pipefail
readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x $ROOT/payload/install-openhtpc-fedora.sh ]]; then
    exec "$ROOT/payload/install-openhtpc-fedora.sh" "$@"
fi
exec "$ROOT/install-openhtpc-fedora.sh" "$@"
