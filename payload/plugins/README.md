# OPENHTPC plugins

Optional plugins are JSON manifests discovered from this directory and from
`~/.local/share/openhtpc/plugins`. A manifest declares exactly: `plugin_id`,
`plugin_version`, `capability`, `dependencies`, `hardware_requirements`,
`menu_entries`, and the `install`, `verify`, `remove`, `doctor` lifecycle entry
points. OPENHTPC Basic ships no optional plugin enabled by default.
