# OPENHTPC Protected Optical Media

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.

## Responsibility boundary

OPENHTPC provides optical integration and a read-only capability model. The
external mechanisms that may be required for protected optical media remain
outside the project and under the user's responsibility, including their legal
use. OPENHTPC provides no AACS key, no `KEYDB.cfg`, no key download, and no key
database update mechanism.

Phase 1 detects loadable `libbluray`, `libaacs`, and optional `libbdplus`
libraries. It also checks metadata for an existing user-provided
`$XDG_CONFIG_HOME/aacs/KEYDB.cfg`, falling back to
`~/.config/aacs/KEYDB.cfg`. The file is never opened, parsed, copied, created,
or modified, and its contents are never exposed.

The canonical capability snapshot records `PROTECTED_OPTICAL_SUPPORT` as
`NOT_AVAILABLE`, `NOT_CONFIGURED`, `AVAILABLE`, or `BLOCKED`. `libbdplus` is
reported independently because it is not required by every disc. Doctor treats
missing optional support as non-blocking. Phase 1 does not connect this state to
playback, MPV, a dispatcher, or the interface's Play action.

The small `status()`, `available()`, and
`can_open_protected_optical_media()` functions form the future generic provider
boundary. They deliberately expose no acquisition or decryption operation.

## Phase 2 playback gating

The canonical optical state classifies the disc as `UNPROTECTED`, `PROTECTED`,
or `UNKNOWN` from mounted-disc filesystem metadata. An unprotected Blu-ray or
UHD Blu-ray does not require a key database; its action depends only on the
structural `libbluray` capability. A protected disc requires the external
protected-media capability to be `AVAILABLE`. Unknown protection is disabled
conservatively and never presented as playable.

The Flex Play action is derived from the current optical generation and the
current capability snapshot. A capability refresh changes the presentation
signature and therefore triggers the existing menu-regeneration cycle. The
optical dispatcher independently rechecks device, generation, media type,
protection, and capability before accepting an action. Phase 2 stops after
authorization and does not invoke libbluray, libaacs, MPV, or any decryption
mechanism.

## Phase 3 system backend

Provider `AVAILABLE` means only that OPENHTPC may attempt to open a protected
disc. It is not evidence that the current disc is accessible. After the Dev2
dispatcher checks generation, action token, device, media identity, protection,
and current capability again, the backend passes the canonical device to MPV's
normal libbluray integration. System libbluray delegates protected access to
the already-installed system libraries and the user's external configuration.

`OPEN_SUCCESS` records that the backend actually opened media streams.
`OPEN_FAILED` records a clean failure for that disc and session. This runtime
result is informational, remains separate from the machine capability, and
does not change `PROTECTED_OPTICAL_SUPPORT` from `AVAILABLE`. Unprotected
Blu-ray and UHD Blu-ray use the same libbluray path without requiring libaacs
or an external key database. OPENHTPC still never reads, parses, copies,
changes, supplies, or acquires key material.
