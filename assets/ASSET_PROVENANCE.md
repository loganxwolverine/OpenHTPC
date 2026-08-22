# Asset provenance

## OPENHTPC branding

`payload/assets/branding/openhtpc-logo.png` and
`payload/assets/branding/openhtpc-wallpaper.png` are artwork created
specifically for the OPENHTPC project and retained unchanged through qualified dev27. They
are project branding, not third-party logos.

## Original public-candidate UI artwork

Every PNG under `payload/assets/ui/` in this candidate was regenerated for
OPENHTPC from simple geometric primitives by
`assets/ui-source/generate_ui_assets.py`. The artwork does not copy an icon
pack and contains no official DVD, Blu-ray or UHD logo. Optical variants use
generic disc/drive geometry, color/ring distinctions and plain descriptive
text (`DVD`, `BLU-RAY`, `UHD`) only; they do not reproduce trademark logo
typography. Public Candidate R2 also adds an original POWER symbol and an
immediately recognizable folder silhouette generated from primitives. Dev30
adds an original door-and-outgoing-arrow `quit.png`, assigns the existing
project POWER symbol to PC shutdown, refines the project return arrow, and
strengthens the generic folder and optical disc/badge silhouettes. All are
deterministically drawn by the same generator from rectangles, polygons,
ellipses, arcs and lines.

Dev31 changes only the generic optical identification family. Its DVD,
BLU-RAY and UHD badges combine an original disc outline, a dark rounded media
capsule, a small geometric disc medallion, OPENHTPC palette accents and generic
text rendered with the already licensed Open Sans font. They do not trace,
copy or reproduce DVD-Video, Blu-ray Disc or Ultra HD Blu-ray trademarks.

Dev33 adds five original playback-control icons generated from primitives:
screen/play symbol, speaker plus `FR`, generic subtitle bubble, audio-level
bars and an information symbol. They visually distinguish actions without
copying an icon pack, trademark or official closed-caption logo.

## Project-provided optical-media artwork — dev37

The following source masters were provided for OPENHTPC by Steve Dehanne in
`openhtpc/assets/systeme/` on the project NAS. They are not redistributed or
modified as masters:

- `Dvd_logo.jpg` — SHA256
  `77924fff80e273b7ac09dc2c0cf6b1aae5e6036c45f1aa01807a16764da848d7`
- `bluray_logo.jpg` — SHA256
  `b58ed1513beff775341131aada124d26914dcef0a58a612b86569c577dcfaac8`
- `bluray_UH_4K_logo.jpg` — SHA256
  `32e9e104dc162bb830d77db34896c99a2bdfe78ae3c5f61b49b040a88db2286c`

`assets/ui-source/derive_optical_media.py` reproducibly crops those masters,
preserves their aspect ratios, applies Lanczos downscaling, and places the
result on an RGBA canvas. It produces `dvd-media.png`, `bluray-media.png`,
`uhd-bluray-media.png` and their matching `*-badge.png` variants.

Project-provided optical-media artwork. Created for OPENHTPC by Steve Dehanne.
These are descriptive project media identifiers, not official DVD Forum,
Blu-ray Disc Association, or Ultra HD Blu-ray logos. OPENHTPC claims no
official affiliation with those trademark holders.

These replacement PNGs and their generator are OPENHTPC project artwork/code:

Copyright 2026 OPENHTPC contributors

Licensed under the Apache License, Version 2.0.

Historical UI PNGs with uncertain provenance are not distributed in this
candidate.

## Third-party graphical components retained

- `payload/flex/assets/icons/drive-empty.png` and `dvd.png` match the retained
  Flex Launcher upstream tree and are distributed under the Flex upstream
  Unlicense.
- `payload/flex/assets/fonts/OpenSans-Regular.ttf` is Open Sans under the SIL
  Open Font License 1.1. See `third_party/licenses/OFL-1.1.txt`.

## Synthetic benchmark assets

The five files under `payload/assets/benchmark/` are synthetic video test
patterns generated for OPENHTPC using FFmpeg test sources. These files contain
no third-party film or television footage. Exact characteristics and SHA256
hashes are recorded in `payload/assets/benchmark/manifest.json`.
