# Flex Launcher provenance

The distributed `payload/flex/bin/flex-launcher` is the Dev16 OPENHTPC Flex
binary recorded by `payload/flex/BUILD-METADATA.json`.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC adaptation: `openhtpc-running-flex-media-generation-sync-dev16`
- Binary SHA256: `351fbe72572fa719fd325899e6ab3703cf42de9a62732904c80555daf236448c`
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
for code incorporated into the binary are provided separately. Dev16 rebuilds
the shipped ELF from the recorded vendor source and records its exact hash and
build ID in `payload/flex/BUILD-METADATA.json`.
