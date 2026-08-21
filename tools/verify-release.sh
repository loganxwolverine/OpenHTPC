#!/usr/bin/env bash
#
# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.

set -Eeuo pipefail

invalid(){ printf 'OPENHTPC_RELEASE_SIGNATURE_INVALID\n'; exit 1; }
[[ $# -eq 4 ]] || invalid
readonly ARCHIVE="$1" CHECKSUM="$2" SIGNATURE="$3" PUBLIC_KEY="$4"
[[ -f $ARCHIVE && -f $CHECKSUM && -f $SIGNATURE && -f $PUBLIC_KEY ]] || invalid
expected="$(awk 'NR==1 && $1 ~ /^[0-9a-f]{64}$/ {print $1}' "$CHECKSUM")"
actual="$(sha256sum -- "$ARCHIVE" | awk '{print $1}')"
[[ -n $expected && $actual == "$expected" ]] || invalid
readonly TEMP_DIR="$(mktemp -d -t openhtpc-verify.XXXXXX)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
printf 'openhtpc-release %s\n' "$(tr -d '\r\n' <"$PUBLIC_KEY")" >"$TEMP_DIR/allowed_signers"
ssh-keygen -Y verify -f "$TEMP_DIR/allowed_signers" -I openhtpc-release -n openhtpc-release -s "$SIGNATURE" <"$ARCHIVE" >/dev/null 2>&1 || invalid
printf 'OPENHTPC_RELEASE_SIGNATURE_VALID\n'
