#!/usr/bin/env bash
#
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.

set -Eeuo pipefail

readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ $# -eq 2 ]] || { printf 'Usage: %s ARCHIVE PRIVATE_SIGNING_KEY\n' "$0" >&2; exit 2; }
readonly ARCHIVE="$(realpath -- "$1")"
readonly SIGNING_KEY="$(realpath -- "$2")"
[[ -f $ARCHIVE ]] || { printf 'ARCHIVE_NOT_FOUND\n' >&2; exit 2; }
[[ -f $SIGNING_KEY ]] || { printf 'SIGNING_KEY_NOT_FOUND\n' >&2; exit 2; }
case "$SIGNING_KEY" in "$PROJECT_ROOT"|"$PROJECT_ROOT"/*) printf 'SIGNING_KEY_INSIDE_REPOSITORY_REFUSED\n' >&2; exit 3;; esac
readonly CHECKSUM="${ARCHIVE}.sha256"
readonly SIGNATURE="${ARCHIVE}.sig"
[[ ! -e $SIGNATURE ]] || { printf 'SIGNATURE_ALREADY_EXISTS\n' >&2; exit 4; }
(cd -- "$(dirname -- "$ARCHIVE")" && sha256sum -- "$(basename -- "$ARCHIVE")" >"$CHECKSUM")
ssh-keygen -Y sign -f "$SIGNING_KEY" -n openhtpc-release "$ARCHIVE"
[[ -s $SIGNATURE ]] || { printf 'SIGNATURE_NOT_CREATED\n' >&2; exit 5; }
printf 'OPENHTPC_RELEASE_SIGNED\n'
