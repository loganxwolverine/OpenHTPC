# Flex Launcher provenance

The tracked `payload/flex/bin/flex-launcher` is a historical repository
payload. It is not authoritative for new RC8 artifact builds. Its tracked
`BUILD-METADATA.json` is also historical and is not artifact provenance.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- Target: Fedora 44 x86_64

The OPENHTPC adaptation retains the launcher/menu/input engine and includes the
OPENHTPC MediaSidebar integration, synchronized `OnLaunch=Quit` handoff and a
neutral black committed frame before replacement-process startup. These changes
avoid overlapping Flex windows while preserving the single-Flex lifecycle.
Dev35 adds bottom-dock geometry for playback menus and a synchronous,
single-process preference apply-and-return action that reloads the parent view.
Dev36 preserves that geometry and restores the approved entry artwork inside
the six playback action cards.
Dev37 vertically separates those icons from their labels while keeping the
approved bottom dock bounds unchanged.
Dev16 adds generation-driven invalidation of every cached MEDIA descendant
after a committed live source mutation. The authoritative Flex process is
retained; stale or removed MEDIA sections cannot remain selectable.

Flex Launcher is distributed under The Unlicense. NanoSVG/NanoSVGRast notices
for code incorporated into the binary are provided separately.

The active RC8 `openhtpc-devctl build` path exports the exact Git commit,
compiles Flex from that exported vendor source in a fresh temporary directory,
and replaces the staging copy of the executable. It generates staged
`payload/flex/BUILD-METADATA.json` from that exact staged ELF and source,
regenerates the staged manifest, creates the archive, and independently verifies
the archive. The embedded Flex ELF build ID is separate from the OPENHTPC
artifact build ID, development tranche, and workstream.
