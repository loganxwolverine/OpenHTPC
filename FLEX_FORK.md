# Flex Launcher provenance

The distributed `payload/flex/bin/flex-launcher` is the qualified dev27 OPENHTPC Flex
binary recorded by `payload/flex/BUILD-METADATA.json`.

- Upstream: `complexlogic/flex-launcher`
- Upstream commit: `94a7a273fe8124df51e63058816526b66bbc9538`
- OPENHTPC adaptation: `openhtpc-1.1-media-sources-dev4`
- Binary SHA256: `695e4b806c593410cb2d0630ba019efd4fc1c23beae806c75bbdf479952efd9f`
- Target: Fedora 44 x86_64

The OPENHTPC adaptation retains the launcher/menu/input engine and includes the
OPENHTPC MediaSidebar integration, synchronized `OnLaunch=Quit` handoff and a
neutral black committed frame before replacement-process startup. These changes
avoid overlapping Flex windows while preserving the single-Flex lifecycle.

Flex Launcher is distributed under The Unlicense. NanoSVG/NanoSVGRast notices
for code incorporated into the binary are provided separately. This candidate
does not rebuild or alter the qualified dev27 binary.
