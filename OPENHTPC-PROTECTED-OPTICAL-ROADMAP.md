# OPENHTPC protected optical roadmap

## UHD optical playback performance / dropped output frames

Status: `KNOWN_LIMITATION — DEFER / OBSERVE`

Physical context: ZimaBoard 2, external USB optical drive, real protected UHD
4K media and HEVC Main10. Playback opened successfully and produced video and
audio, but important dropped output frames were observed.

Dev5 records the limitation without changing cache, video synchronization,
display refresh, Vulkan, VA-API, tone mapping, HDR, USB behavior or MPV
options. No ZimaBoard-specific workaround is introduced. If the same problem
is reproduced on AMD or NVIDIA, raise its priority and open a dedicated
performance project.

Dev5 physical qualification confirms protected UHD opening, video, audio,
quit/return and the dedicated UHD badge. It does not qualify playback fluidity
as PASS and does not claim universal UHD compatibility.

## Protected optical → plugin migration

Status: `P2 PHASE 5 CAPABILITY PROJECTION — CORE PROBE/SNAPSHOT RETAINED`

Protected optical support remains integrated into the development branch.
The first-party `plugin.bluray` manifest now exists as a disabled read-only
shadow, so the Plugin Registry truthfully reports `Blu-ray/UHD DISABLED` even
when the Core-integrated protected-optical capability is `ENABLED`.

Core ownership should remain limited to canonical optical device detection,
generic optical state, the generic provider contract, dispatcher security and
generic Doctor/plugin-framework hooks. A future optical/Blu-ray/UHD plugin
should own libbluray-specific probing, AACS provider integration, Blu-ray/UHD
classification, `bd://` launch semantics, media-specific presentation assets
and diagnostics.

Stable boundaries to preserve are the canonical optical state, capability
snapshot/provider statuses, generation-bound action token, dispatcher request
contract, last-attempt record and Doctor/plugin registry interfaces. The Dev5
audit moved no file and did not start Plugin Framework P2.

P2 Phase 1 established the registry and stable hook vocabulary. Phase 2 added
the bounded observation/equivalence adapter. Phase 3 transfers the first and
only responsibility so far: media-specific Doctor row projection. Core keeps
the canonical facts, generic health aggregation and an exact fallback.

Probing, classification, capability generation, UI, dispatcher and playback
remain Core-owned. The fallback remains until automated enabled/disabled/BROKEN
equivalence is complete and a later, more significant migration receives at
least one physical validation confirming truthful Doctor output.

Phase 4 additionally transfers only the Blu-ray/UHD presentation descriptor
mapping. Core still owns Flex rendering, asset files, safe badge-key-to-path
resolution and the exact fallback. The frozen physical invariant is:
`UHD_BLURAY` displays `ULTRA HD BLU-RAY 4K`. Hardware probing, libbluray and
libaacs probing, canonical classification, canonical capability generation, playback
decision, dispatcher, `bd://` backend and MPV remain Core-owned.

Phase 5 transfers only the deterministic protected-optical capability
projection. The plugin consumes the canonical Core-generated snapshot and is
not a second probe engine. Hardware probing, libbluray/libaacs/libbdplus
probing, KEYDB metadata detection, snapshot generation, classification,
playback decision, Flex rendering/assets, dispatcher, `bd://` and MPV remain
Core-owned. `AVAILABLE` continues to mean ready to attempt, not guaranteed
per-disc success.
