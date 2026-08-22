# Flex Launcher provenance

The distributed `payload/flex/bin/flex-launcher` is the dev36 OPENHTPC Flex
binary recorded by `payload/flex/BUILD-METADATA.json`.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC adaptation: `openhtpc-1.1-playback-ux-dev36`
- Binary SHA256: `bbcda2469a563fa5869b9e6e6f7ea5412d785e595d70c1874593c89887c0051c`
- Target: Fedora 44 x86_64

The OPENHTPC adaptation retains the launcher/menu/input engine and includes the
OPENHTPC MediaSidebar integration, synchronized `OnLaunch=Quit` handoff and a
neutral black committed frame before replacement-process startup. These changes
avoid overlapping Flex windows while preserving the single-Flex lifecycle.
Dev35 adds bottom-dock geometry for playback menus and a synchronous,
single-process preference apply-and-return action that reloads the parent view.
Dev36 preserves that geometry and restores the approved entry artwork inside
the six playback action cards.

Flex Launcher is distributed under The Unlicense. NanoSVG/NanoSVGRast notices
for code incorporated into the binary are provided separately. This candidate
does not rebuild or alter the qualified dev27 binary.
