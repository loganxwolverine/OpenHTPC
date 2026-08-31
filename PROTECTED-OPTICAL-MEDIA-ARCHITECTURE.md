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

The canonical optical state separates the Blu-ray media family from its exact
variant. Public libbluray disc information is the primary source for Blu-ray,
AACS and BD+ detection. Mounted, non-secret BDMV/AACS structure is a lower
priority fallback. The published `classification_source` and
`classification_confidence` explain the result. A disc may truthfully remain
`BLURAY_FAMILY` when standard versus UHD is not proven; this is not a globally
unknown media type.

Protection is independently classified as `UNPROTECTED`, `PROTECTED`, or
`UNKNOWN`. `aacs_detected` or `bdplus_detected` means `PROTECTED`, regardless of
the corresponding `handled` value. Handled status describes access capability,
not the presence of protection. An unprotected Blu-ray or UHD Blu-ray does not
require a key database; its action depends only on the
structural `libbluray` capability. A protected disc requires the external
protected-media capability to be `AVAILABLE`. Unknown protection is disabled
conservatively and never presented as playable.

UHD is claimed only from BDMV index version 0300 evidence. HEVC, 3840x2160,
BDXL/media capacity, disc labels and titles are not UHD classifiers. Without
that proof the exact variant remains unknown while the Blu-ray family stays
known.

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

`BLURAY_FAMILY` uses that same generic `bd://` backend when protection and
provider gating authorize an attempt. Protection, provider capability and the
recorded `OPEN_SUCCESS`/`OPEN_FAILED` result remain three separate facts.

## Development-branch plugin status

Protected optical support is currently experimental and integrated into this
development branch. It is not evidence that the future optional Blu-ray or UHD
plugins are installed. Doctor may therefore truthfully show protected optical
playback `ENABLED` while the Plugin Registry shows both optional plugins as
`NOT_INSTALLED`. Extraction is reserved for Plugin Framework P2; Dev5 does not
move components or fabricate plugin manifests.
