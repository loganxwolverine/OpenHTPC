# OPENHTPC Plugin Framework P2 — Registry foundation

## Migration phases

- P2 Phase 1 established the current-tree registry foundation.
- P2 Phase 2 installs `plugin.bluray` as a disabled, read-only shadow. It may
  be loaded only by an explicit development invocation and reflects a bounded
  Core observation; it owns no production hook.
- P2 Phase 3 transfers the protected-optical Doctor projection only, with a
  Core fallback and mandatory direct A/B comparison.
- P2 Phase 4 transfers only the Blu-ray/UHD presentation descriptor mapping;
  Core retains rendering and asset resolution.
- P2 Phase 5 transfers only the protected-optical capability projection;
  Core retains probing and canonical snapshot generation.
- Later phases may progressively extract classification and other bounded
  responsibilities, only when each prior
  boundary is proven equivalent.

**SHADOW EQUIVALENCE IS REQUIRED BEFORE OWNERSHIP TRANSFER.** The phase count
and extraction order remain evidence-driven.

## Phase 1 registry scope

P2 Phase 1 establishes one declarative registry for the current qualified
OPENHTPC tree. It discovers and validates metadata, evaluates compatibility,
tracks explicit enablement, publishes a deterministic snapshot and supplies
generic Doctor states. Discovery never imports or executes plugin code,
installs packages, accesses the network or mutates Core runtime configuration.

The historical P1 commit `3b00a907e8a6933867b9dccc5498b06b6d74ee88`
was reference material only. P2 deliberately rewrites its schema, compatibility
model and Doctor integration for the current tree. Reused concepts are the XDG
ownership split, strict declarative validation, deterministic provider registry
and non-blocking optional-plugin failures.

## Ownership

Core owns discovery, validation, compatibility, enablement state, deterministic
registry publication, explicit hook contracts, dispatcher security and generic
Doctor reporting. A plugin will own its media/service implementation,
dependencies, bounded capability/UI contributions and media-specific
diagnostics. No plugin may replace MPV configuration or monkey-patch Core.

| Purpose | Canonical location |
|---|---|
| Project-installed plugins | `<install>/plugins/available/<plugin-id>/` |
| User-installed plugins | `~/.local/share/openhtpc/plugins/available/<plugin-id>/` |
| Explicit enabled set | `~/.config/openhtpc/plugins-enabled-v2.json` |
| Persistent plugin data | `~/.local/share/openhtpc/plugin-data/<plugin-id>/` |
| Plugin cache | `~/.cache/openhtpc/plugins/<plugin-id>/` |
| Runtime plugin state | `~/.local/state/openhtpc/plugins/<plugin-id>/` |
| Generated registry | `~/.local/state/openhtpc/plugin-registry-v2.json` |

Project registry code and project manifests are Core-managed. User plugins and
all XDG state are outside the Core managed-file cleanup, so unrelated updates
do not overwrite them. Phase 1 does not provide package import or uninstall.

## Canonical manifest V2

Each plugin directory contains exactly one `plugin.json` with this exact
schema:

```json
{
  "schema": "openhtpc-plugin-v2",
  "id": "plugin.example",
  "name": "Example Plugin",
  "version": "0.1.0",
  "plugin_api": 2,
  "openhtpc": {"minimum": "1.2.0", "maximum": null},
  "category": "media",
  "entrypoint": null,
  "capabilities": ["capability", "doctor"],
  "dependencies": {"plugins": [], "capabilities": []},
  "system_dependencies": ["example-runtime"],
  "enabled_by_default": false,
  "doctor": {"label": "Example Plugin", "capability": "example-ready"}
}
```

`plugin_api=2` is the only supported API in this phase. Categories are
`optical`, `media`, `service`, `presentation`, and `system`. Explicit hook
names are `capability`, `doctor`, `ui_menu`, `media_handler`, and `dispatcher`.
The entrypoint is optional metadata and is never loaded during discovery.
There are no shell-command or lifecycle-command fields.

IDs, versions, dependencies and every field are strictly validated. Plugin
directory name must equal plugin ID. Absolute paths, `..`, symlinked plugin
directories, symlinked entrypoints and resolved paths outside the plugin root
are rejected.

## States and Doctor

`INSTALLED` is the installation fact. Operational states are `DISABLED`,
`AVAILABLE`, `INCOMPATIBLE`, and `BROKEN`; an absent known optional plugin is
reported as `NOT_INSTALLED`. Invalid or incompatible optional plugins are
diagnostic and do not block Overall READY. Failure of the Core registry module
itself is a Core integrity failure and may block readiness.

With no manifest Doctor reports Blu-ray and UHD as `NOT_INSTALLED`. Phase 2
installs the combined `plugin.bluray` candidate, so Doctor truthfully reports
`Blu-ray/UHD DISABLED`. Physically qualified Protected Optical Dev5 remains
temporarily Core-integrated and can remain functional while this shadow is
disabled. This temporary overlap must end before production ownership moves.

## Phase 2 shadow contract

Core owns the side-effect-free observation contract. Its input consists only
of the canonical optical state, protected-media capability snapshot, canonical
playback decision and last-attempt history. The output contains media family,
exact type, protection and mechanism, classification source, provider state,
playback state and last attempt.

The shadow adapter receives that already-normalized mapping and publishes
corresponding `observed_*` fields. It does not open state files, probe hardware,
inspect disc structure, call libbluray/libaacs, inspect KEYDB metadata, write a
snapshot, modify Doctor, register a handler/dispatcher, or launch playback.
Tests compare every claimed field across no-disc, DVD, Blu-ray/UHD, provider,
unknown-protection, history and eject scenarios.

Registry discovery remains data-only. The bounded loader first requires a
discovered, validated, API-compatible plugin and an in-root entrypoint. A
disabled plugin requires explicit shadow invocation; an ordinary load requires
enablement. Load failures are isolated as `BROKEN` results.

## Phase 3 Doctor projection ownership

The first transferred responsibility is the Protected Optical Doctor
projection. Core still reads and owns the canonical optical state, capability
snapshot and last-attempt history. It also remains the sole owner of the
generic health engine, row validation, blocking policy and Overall result.

When `plugin.bluray` is enabled, compatible and valid, Core asks its bounded
`doctor_rows` contract to turn those read-only facts into the existing ordered
diagnostic rows. Core accepts the contribution only when its labels, values,
ordering and blocking metadata exactly equal the temporary Core fallback.
Normal output therefore contains one projection, never both.

Disabled, missing, incompatible or broken plugins select `CORE_FALLBACK`.
Runtime failure or semantic mismatch marks the optional plugin `BROKEN`, keeps
Doctor operational and preserves the non-blocking optional-plugin policy.
`PLUGIN_P2` is selected only for an explicitly enabled equivalent plugin.

The fallback must remain until automated equivalence covers enabled, disabled
and broken states and at least one later physical validation confirms truthful
Doctor output after a more significant ownership migration. Probing,
classification, capability generation, UI, dispatcher and playback remain
Core-owned.

## Phase 4 presentation descriptor ownership

The second transferred responsibility is the deterministic conversion from
canonical current-disc classification into declarative presentation data:
ownership, presentation key, badge key, display label and media kind. DVD,
no-disc and ejected states are explicitly unowned. Historical playback attempt
state is not an input and can never create a current badge.

`BLURAY_VIDEO` selects the existing `BLURAY` badge, `BLURAY_FAMILY` selects
the same generic badge with its existing family label, and
`UHD_BLURAY_VIDEO` selects `UHD_BLURAY` with the physically qualified text
`ULTRA HD BLU-RAY 4K`. Protection, HEVC, resolution, HDR, volume label and
title do not influence the mapping.

Core validates a closed set of descriptor and badge keys, performs exact A/B
comparison, and selects `PLUGIN_P2` only for an enabled equivalent plugin.
Disabled, invalid, mismatched or broken contributions use `CORE_FALLBACK`.
Core alone resolves `BLURAY` and `UHD_BLURAY` to existing asset paths and
continues to own Pillow/Flex rendering, layout, generated pages and all asset
files. The plugin contains no paths or rendering primitives.

## Phase 5 capability projection ownership

The third transferred responsibility is the pure projection of the
Core-generated `optical.protected_media` snapshot into a bounded P2 capability
contribution. It reports the canonical capability ID, provider/availability
state, ready-to-attempt boolean, supported Blu-ray media kinds, dependency
states, external-key-database state and non-blocking metadata.

`AVAILABLE` means only `READY_TO_ATTEMPT`; it never predicts per-disc
decryption or `OPEN_SUCCESS`. Current media type, protection and historical
`OPEN_SUCCESS`/`OPEN_FAILED` are not inputs and cannot mutate machine
capability. Absent snapshots project conservatively as `NOT_AVAILABLE` and
malformed states as `BLOCKED`.

Core remains the only probe and snapshot authority. It continues to discover
and load libraries, inspect allowed KEYDB metadata and write the canonical
snapshot. The plugin receives the resulting dictionary only. Selection follows
the same disabled/enabled/BROKEN and exact A/B fallback policy as Doctor and
presentation, while all three contributions remain independently bounded.

## Phase 6 playback-decision projection ownership

The fourth transferred responsibility is the deterministic projection from
the current canonical optical state and Core-generated protected capability
snapshot to the existing playback decision fields. The contribution adds only
an `owned` fact: no disc and DVD are not owned by `plugin.bluray`; Blu-ray,
UHD Blu-ray and the conservative Blu-ray family are owned.

The contract preserves every existing action and reason, including the
unprotected structural path, conservative unknown-protection behavior and all
four provider states. `AVAILABLE` continues to mean ready to attempt, never
guaranteed decryption or playback success. Last-attempt history is not a
decision input and cannot enable an action after ejection.

An enabled contribution is selected only after validation and exact A/B
equality with the retained Core function. Disabled, invalid, mismatched or
broken contributions use `CORE_FALLBACK`. Core publishes the selected
projection without rewriting either canonical input.

Plugin decision is not playback authority. Core still owns Flex/button
generation, action tokens, dispatcher enforcement and immediate canonical
revalidation, the `bd://` backend, MPV execution and last-attempt recording.
The plugin remains disabled by default, preserving the qualified normal path.

## Phase 7 declarative UI/menu contribution ownership

The fifth transferred responsibility combines only the already-validated
Phase 4 presentation descriptor and Phase 6 playback-decision projection into
declarative Blu-ray/UHD menu data. The bounded contract contains ownership,
item kind, visibility, display label, an allowlisted badge key, enabled state,
canonical disabled reason and an allowlisted semantic action intent.

The plugin does not classify media or derive provider eligibility again. DVD,
no-disc and ejected inputs remain unowned. Current Blu-ray, Blu-ray family and
UHD inputs preserve their qualified labels and badge keys; historical attempt
state is not an input. Malformed upstream contracts select the conservative
Core fallback without invoking plugin code.

The sole executable intent vocabulary is semantic data:
`PLAY_CURRENT_OPTICAL_MEDIA` or `NONE`. It contains no token, command,
dispatcher, URI or arguments. Core validates exact A/B equality and remains
the only authority for Flex rendering, asset-key resolution, generation-bound
tokens, dispatcher revalidation and playback execution.

Plugin UI contribution is not UI execution. `plugin.bluray` remains disabled
by default; invalid, mismatched or broken contributions retain the qualified
Core UI builder.

## Phase 8 deterministic classification ownership

Phase 8 separates optical classification into four explicit stages: Core
acquires physical facts, Core normalizes them into a closed data contract, the
selected classifier produces a validated result, and Core alone publishes the
canonical state.

The raw contract contains only Blu-ray evidence, normalized index version and
source, availability and boolean disc-info facts, AACS/BD+ detected and handled
facts, structural protection and probe completeness. It contains no device,
mountpoint, path, previous state, playback result, capability or key-database
fact. Core continues to perform udev, libbluray and filesystem access,
including all BDMV/INDX reads.

The plugin classifier deterministically returns ownership, canonical and
legacy state, media family, exact type, UHD status, protection mechanisms,
source and confidence. UHD requires normalized index version `0300`; codec,
resolution, HDR, labels and titles are outside the contract. Positive AACS or
BD+ detection remains protected regardless of handled state. libbluray facts
retain priority over the structural fallback.

Core validates raw facts before explicit plugin invocation and validates exact
A/B output equality before selection. Disabled, malformed, mismatched or
broken cases use the retained Core classifier. Canonical persistence, monitor
publication and generation remain exclusively Core-owned.

## Phase 9 libbluray primitive-fact normalization ownership

Phase 9 inserts a pure normalization boundary between Core libbluray
acquisition and the Phase 8 raw-fact merge. Core validates and supplies only
immutable primitive data: disc-info availability, Blu-ray detection, separate
AACS/BD+ detected and handled booleans, probe completion and an optional INDX
header value already read through the public libbluray file API.

The enabled plugin may translate those values into the closed libbluray fact
fragment. It does not return family, exact type, protection, source or
confidence; those remain Phase 8 classification outputs. It receives no live
handle, ctypes pointer, descriptor, device or mount path, callable, or object
capable of I/O. It performs no libbluray/libaacs/libbdplus call, filesystem
probe, BDMV/INDX read, KEYDB access, network access or execution.

Core retains exact normalization fallback and accepts plugin authority only
after output validation and exact A/B equality. Core then merges the fragment
with independently acquired structural facts, validates the complete Phase 8
contract and remains the sole canonical-state publisher. Plugin normalization
is not libbluray probing.

## Phase 10 structural BDMV/INDX fact normalization ownership

Phase 10 adds a second pure normalization boundary for values already read by
Core's mounted-disc fallback. The strict input contains only the acquired INDX
header value, the existing `PROTECTED`/`UNPROTECTED`/`UNKNOWN` structural
evidence and probe completeness. The output contains structure availability,
a normalized index version, the unchanged structural evidence and completion.
It contains no final media identity, UHD or protection classification.

No device, mountpoint, BDMV path, file descriptor, file object, pathlib
object, stat result, iterator or callable crosses the boundary. Core retains
all `open`/`read`/`stat` operations, mounted path handling, structural error
handling and fallback. Because the current fallback does not acquire a
distinct BD+ mechanism fact, the contract does not invent one.

Core keeps Phase 9 libbluray and Phase 10 structural fragments separate,
validates both, performs the Phase 8 raw-fact merge and source precedence, and
alone publishes canonical state. Disabled, invalid, mismatched or broken
contributions use the exact Core normalizer. Plugin structural normalization
is not filesystem probing.

## Protected Optical migration boundary

Protected Optical is the first P2 migration candidate. Phase 3 moves only its
Doctor presentation; no media behavior changes. Generic optical state, provider contract, dispatcher
security and Doctor hooks remain Core candidates. libbluray/AACS probing,
Blu-ray/UHD classification, `bd://` launch semantics, badges and media-specific
diagnostics are future plugin candidates. Migration must preserve the Dev5
physical qualification and keep the current canonical state, capability
snapshot, action token and last-attempt contracts stable.
