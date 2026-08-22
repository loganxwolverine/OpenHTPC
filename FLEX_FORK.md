# Flex Launcher provenance

The distributed `payload/flex/bin/flex-launcher` is the dev35 OPENHTPC Flex
binary recorded by `payload/flex/BUILD-METADATA.json`.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC adaptation: `openhtpc-1.1-playback-ux-dev35`
- Binary SHA256: `6b705d37076138b418465918b727bfeb5fe1b9432902c0c2fec2bb064bbcb6cf`
- Target: Fedora 44 x86_64

The OPENHTPC adaptation retains the launcher/menu/input engine and includes the
OPENHTPC MediaSidebar integration, synchronized `OnLaunch=Quit` handoff and a
neutral black committed frame before replacement-process startup. These changes
avoid overlapping Flex windows while preserving the single-Flex lifecycle.
Dev35 adds bottom-dock geometry for playback menus and a synchronous,
single-process preference apply-and-return action that reloads the parent view.

Flex Launcher is distributed under The Unlicense. NanoSVG/NanoSVGRast notices
for code incorporated into the binary are provided separately. This candidate
does not rebuild or alter the qualified dev27 binary.
