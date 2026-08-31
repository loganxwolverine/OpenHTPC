# OPENHTPC Plugin Framework P2 — Registry foundation

## Phase 1 scope

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

Doctor continues to report Blu-ray and UHD as `NOT_INSTALLED`: physically
qualified Protected Optical Dev5 remains temporarily Core-integrated. An
integrated capability being available does not fabricate a plugin installation.

## Protected Optical migration boundary

Protected Optical is the first intended P2 migration candidate, but Phase 1
moves no implementation. Generic optical state, provider contract, dispatcher
security and Doctor hooks remain Core candidates. libbluray/AACS probing,
Blu-ray/UHD classification, `bd://` launch semantics, badges and media-specific
diagnostics are future plugin candidates. Migration must preserve the Dev5
physical qualification and keep the current canonical state, capability
snapshot, action token and last-attempt contracts stable.
