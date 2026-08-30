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
