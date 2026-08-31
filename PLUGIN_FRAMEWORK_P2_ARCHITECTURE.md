# OPENHTPC Plugin Framework P2 — Registry foundation

## Migration phases

- P2 Phase 1 established the current-tree registry foundation.
- P2 Phase 2 installs `plugin.bluray` as a disabled, read-only shadow. It may
  be loaded only by an explicit development invocation and reflects a bounded
  Core observation; it owns no production hook.
- A future Phase 3 may transfer one bounded responsibility with a Core
  fallback and direct A/B comparison.
- Later phases may progressively extract diagnostics, classification,
  presentation and finally dispatcher/backend ownership, only when each prior
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

## Protected Optical migration boundary

Protected Optical is the first P2 migration candidate, but Phases 1 and 2 move
no production implementation. Generic optical state, provider contract, dispatcher
security and Doctor hooks remain Core candidates. libbluray/AACS probing,
Blu-ray/UHD classification, `bd://` launch semantics, badges and media-specific
diagnostics are future plugin candidates. Migration must preserve the Dev5
physical qualification and keep the current canonical state, capability
snapshot, action token and last-attempt contracts stable.
