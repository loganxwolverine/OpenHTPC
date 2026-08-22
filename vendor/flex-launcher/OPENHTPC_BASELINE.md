# Flex Launcher baseline for OPENHTPC V1

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC reference: `OpenHTPC-Packaging-Source-20260809-200819/vendor/flex-launcher/openhtpc.patch`
- Scope retained: launcher engine, keyboard and mouse navigation, menu system and
  the OPENHTPC MediaSidebar patch.

The source in this directory is the patched source baseline. Files named
`before-*`, build output, documentation, unrelated stock icons and historical
runtime configuration were deliberately not imported.

OPENHTPC additionally synchronizes `OnLaunch=Quit` handoffs: the replacement
process waits for the current SDL launcher to terminate, after the launcher has
committed a neutral black frame. This prevents overlapping Flex windows while
keeping the historical menu and input engine unchanged.

`../../flex/bin/flex-launcher` is built from this source for the Fedora V1
runtime. It has no runtime dependency on the historical source or installation.
