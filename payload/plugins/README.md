# OPENHTPC plugins

Plugin Framework P2 discovers declarative V2 manifests below
`plugins/available/<plugin-id>/plugin.json` and the matching user-owned XDG
location. Discovery never executes plugin code. The canonical schema and
ownership rules are documented in `PLUGIN_FRAMEWORK_P2_ARCHITECTURE.md`.

OPENHTPC ships no optional plugin enabled by default. `plugin.bluray` is the
first-party Phase 2 candidate: it is installed disabled and its entrypoint is
a read-only shadow adapter. Qualified playback remains Core-owned, so Doctor
truthfully reports `Blu-ray/UHD DISABLED` while Core functionality may remain
available during this temporary overlap.
