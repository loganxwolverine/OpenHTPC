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

Status: `P2 PHASE 11 STATIC ASSETS — CORE VALIDATION/RENDERING RETAINED`

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

Phase 6 transfers only the deterministic protected playback-decision
projection. The plugin consumes current canonical disc classification and the
Core-generated capability snapshot, with exact Core/plugin A/B equality and a
retained Core fallback. `AVAILABLE` still means ready to attempt; historical
`OPEN_SUCCESS`/`OPEN_FAILED` is not an input. Probing, snapshot generation,
classification, Flex rendering, action tokens, dispatcher/revalidation,
`bd://`, MPV and result recording remain Core-owned. Plugin decision is not
playback authority.

Phase 7 transfers only the declarative Blu-ray/UHD UI/menu contribution. It
combines validated presentation and playback-decision data and may return only
an allowlisted badge key and semantic `PLAY_CURRENT_OPTICAL_MEDIA` intent.
Core validates, resolves assets, creates generation-bound tokens, renders Flex
and revalidates in the dispatcher. Physical/software probing, canonical
classification, snapshot generation, `bd://`, MPV and protected-attempt
recording remain Core-owned. Plugin UI contribution is not UI execution.

Phase 8 transfers deterministic Blu-ray/UHD classification only. Core still
acquires and normalizes udev, libbluray, AACS/BD+, structural BDMV and INDX
facts; the plugin sees no location or I/O primitive. The selected classifier
must exactly match the retained Core result, after which Core alone publishes
canonical state. `0300` remains the only UHD index proof, and protection
detection remains separate from handled/accessibility state. KEYDB capability
does not affect media identity.

Phase 9 transfers only deterministic normalization of primitive libbluray
results already acquired by Core. The plugin receives bounded booleans and an
optional INDX header value; it receives no device path, handle, pointer, file
descriptor or callable. It preserves detected and handled AACS/BD+ facts as
independent values and normalizes the INDX version without classifying media.
Core still owns every libbluray call and BDMV/INDX read, the structural
fallback, validation and merge of the complete Phase 8 facts, and canonical
state publication. Plugin normalization is not libbluray probing.

Phase 10 transfers only deterministic normalization of already-acquired
structural BDMV/INDX and protection primitives. The plugin receives the INDX
header value, the existing conservative structural protection evidence and a
probe-completeness boolean; it receives no mountpoint, path, descriptor,
file object or callable. The current structural fallback does not acquire a
distinct BD+ mechanism fact, so Phase 10 does not fabricate one.

Core performs every filesystem operation and error handler, retains the
separate Phase 9 libbluray fragment, validates and merges both fragments into
the Phase 8 raw contract, and alone publishes canonical state. Plugin
structural normalization is not filesystem probing.

Phase 11 transfers ownership of the qualified Blu-ray and Ultra HD Blu-ray 4K
badge PNGs to `plugin.bluray` as exact byte copies. The manifest exposes only
the closed `BLURAY` and `UHD_BLURAY` keys. Core rejects absolute, traversing,
remote, unsupported, missing and symlink-escaping resources, verifies exact
SHA-256 equality with its retained fallback, reads the selected image and
continues to own all Flex layout and rendering.

Plugin asset ownership is not Flex rendering ownership. After Phase 11 no
meaningful media-state pure/declarative responsibility is currently known to
remain in Core. Probe acquisition, security enforcement, playback execution
and rendering orchestration remain separate architectural decisions rather
than automatic migration targets.
