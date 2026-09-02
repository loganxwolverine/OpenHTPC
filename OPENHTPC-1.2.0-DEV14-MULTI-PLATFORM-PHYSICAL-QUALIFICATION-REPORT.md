<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.2.0-dev14 — Multi-platform physical qualification

## Qualified identity

- Version: `1.2.0-dev14`
- Build: `plugin-framework-p2-production-cutover-ui-gating-dev14`
- Qualified commit: `e47ebe11c39b493746a1e38f258d462be0c86ea2`
- Artifact: `OpenHTPC-1.2.0-Plugin-Framework-P2-Production-Cutover-UI-Gating-Dev14.tar.gz`
- SHA-256: `94e030482c46b041ea0d791e261d0fea11e6c545270f036ef99543e324a65194`

The tested artifact is a **qualified candidate for a separate RC-preparation
step**. It is not an RC, and this qualification creates no RC artifact or tag.

## Qualification matrix

| Scope | Intel / ZimaBoard 2 | AMD / Ryzen | NVIDIA / RTX 3050 |
|---|---:|---:|---:|
| Core / Flex / MEDIA | PASS | PASS | PASS |
| `plugin.bluray` disabled UI gating | PASS | PASS | PASS |
| Protected Blu-ray | PASS | PASS | PASS |
| Protected UHD Blu-ray | PASS | PASS | PASS |
| DVD | PASS | PASS | PASS |

**MULTI-PLATFORM PHYSICAL QUALIFICATION = PASS**

## Intel / ZimaBoard 2

Core, Flex and MEDIA passed. With a real Blu-ray and `plugin.bluray` disabled,
disc detection remained operational while the Blu-ray badge and `LIRE LE
BLU-RAY` action were absent; no automatic launch, popup or error occurred and
Flex remained functional. Disabled, broken, absent and available plugin states
were all physically qualified.

With the plugin available, protected Blu-ray detection, badge, action, launch,
image, audio, MPV quit and Flex return passed. Classification, libbluray
normalization and structural normalization authorities were `PLUGIN_P2`; the
protected attempt was `OPEN_SUCCESS`.

Protected UHD passed with exact badge `ULTRA HD BLU-RAY 4K`, canonical state
`UHD_BLURAY_VIDEO`, structural proof `INDX0300`, `uhd_status=CONFIRMED`, all
three `PLUGIN_P2` authorities, `OPEN_SUCCESS`, image/audio, quit and Flex
return. DVD detection, presentation, playback, image/audio, seek and return
passed with canonical state `DVD_VIDEO`, Core playback provider and
`uhd_status=NOT_APPLICABLE`.

## AMD / Ryzen

Migration from RC2 to Dev14 and Core/Flex/MEDIA passed. With a real Blu-ray and
the plugin disabled, detection passed with no badge, action or popup; Flex
remained functional. The decision was `playable=false`, provider
`plugin:bluray`, status `PLUGIN_REQUIRED`, with Overall `READY`.

After activation, protected Blu-ray passed with exact type `BLURAY`, AACS,
`aacs_handled=true`, `PLUGIN_P2` authorities, `OPEN_SUCCESS`, image/audio,
quit/return and Overall `READY`. Protected UHD passed with exact type
`UHD_BLURAY`, canonical state `UHD_BLURAY_VIDEO`, `INDX0300`, confirmed UHD,
`PLUGIN_P2` authorities and `OPEN_SUCCESS`. DVD passed with `DVD_VIDEO`,
`CORE_FALLBACK`, `playable=true`, Core provider, `AVAILABLE`,
`NOT_APPLICABLE`; `plugin.bluray` remained available and Overall was `READY`.

## NVIDIA / RTX 3050

The validator used an Intel Core i7-7700, Intel HD 630 plus NVIDIA RTX 3050,
Fedora KDE Wayland, RTX 3050 display ownership and NVIDIA driver 610.57.04.
Migration from RC2 passed. Fullscreen, 4K scaling, navigation, MEDIA and local
file image/audio/seek/quit/return passed without error. One UI instance, one
optical monitor, runtime ownership and Overall `READY` were observed.

With the plugin disabled, real Blu-ray detection passed while badge, play
action and autolaunch remained absent. Flex stayed functional with canonical
state `BLURAY_VIDEO`, `CORE_FALLBACK`, `playable=false`, provider
`plugin:bluray`, `PLUGIN_REQUIRED`, empty providers and Overall `READY`.

With the plugin available, protected Blu-ray passed with exact type `BLURAY`,
`aacs_handled=true`, `INDX0200`, `PLUGIN_P2` authorities and `OPEN_SUCCESS`.
Protected UHD passed with exact type `UHD_BLURAY`, `UHD_BLURAY_VIDEO`,
`INDX0300`, confirmed UHD, `PLUGIN_P2` authorities and `OPEN_SUCCESS`. Both
passed image/audio and quit/return. DVD passed with the same Core-owned facts
recorded on Ryzen, while `plugin.bluray` remained available. Overall was
`READY` throughout.

## History, operational requirement and deferred limitation

Dev13 exposed the real disabled-plugin UI-gating defect during physical
qualification. Dev14 fixed it, and the matrix above physically closes that
regression across Intel, AMD and NVIDIA.

On Ryzen and NVIDIA, libaacs and external AACS configuration were added after
the initial Hardware Passport/runtime snapshot. Live detection immediately
reported libbluray and libaacs available, external key database detected and
protected optical support available, but `capabilities.json` retained its
earlier snapshot until `openhtpc rebuild-passport` was run. The rebuild made
protected optical media and libaacs available, external key database detected,
protected playback enabled and Overall ready while preserving prior video
validations. This is a real, non-blocking operational requirement and possible
future UX/runtime debt; it is not corrected by Dev14 documentation closure.

UHD dropped frames observed on ZimaBoard 2 remain a deferred platform and
performance limitation. They do not reopen Dev14 qualification.

OPENHTPC does not provide, download, update, link to, parse, copy or modify a
user KEYDB. It detects presence/readability metadata only. `AVAILABLE` means
`READY_TO_ATTEMPT`, never guaranteed decryptability or playback for every disc.
