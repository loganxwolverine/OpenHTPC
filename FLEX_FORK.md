# Flex Launcher provenance

The distributed `payload/flex/bin/flex-launcher` is the dev37 OPENHTPC Flex
binary recorded by `payload/flex/BUILD-METADATA.json`.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC adaptation: `openhtpc-1.1-final-ui-dev37`
- Binary SHA256: `b2e101c87a1c5c3d468e5706163ffe6408ed1b5802ac62dacbcb3a06b4945042`
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

Flex Launcher is distributed under The Unlicense. NanoSVG/NanoSVGRast notices
for code incorporated into the binary are provided separately. This candidate
does not rebuild or alter the qualified dev27 binary.
