# OPENHTPC plugins

Plugin Framework P2 discovers declarative V2 manifests below
`plugins/available/<plugin-id>/plugin.json` and the matching user-owned XDG
location. Discovery never executes plugin code. The canonical schema and
ownership rules are documented in `PLUGIN_FRAMEWORK_P2_ARCHITECTURE.md`.

OPENHTPC ships no optional plugin enabled by default. Protected Optical Dev5
remains temporarily integrated into Core and is not represented as an
installed Blu-ray or UHD plugin.
