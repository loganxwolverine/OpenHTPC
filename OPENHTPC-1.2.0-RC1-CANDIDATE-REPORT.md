<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.2.0 RC1 — Candidate assembly record

Version: `1.2.0-rc1`
Build: `public-release-1.2.0-rc1`

RC1 promotes the physically qualified Dev14 Plugin Framework P2 production
cutover. The promotion changes release identity, documentation and packaging
metadata only; it introduces no functional change after the qualified commit
`e47ebe11c39b493746a1e38f258d462be0c86ea2`.

## Qualified origin

- Dev14 artifact: `OpenHTPC-1.2.0-Plugin-Framework-P2-Production-Cutover-UI-Gating-Dev14.tar.gz`
- Dev14 SHA-256: `94e030482c46b041ea0d791e261d0fea11e6c545270f036ef99543e324a65194`
- Intel / ZimaBoard 2: PASS
- AMD / Ryzen: PASS
- NVIDIA / RTX 3050: PASS
- Core/Flex/MEDIA, disabled-plugin UI gating, protected Blu-ray, protected UHD
  Blu-ray and DVD: PASS

## Release boundary

`plugin.bluray` is the opt-in owner of Blu-ray/UHD policy and presentation;
generic I/O, security, rendering and execution services remain in Core. DVD
remains Core-owned. Protected optical `AVAILABLE` means `READY_TO_ATTEMPT`, not
guaranteed success for every disc.

RC1 physical qualification is **NO-GO**. Protected Blu-ray produced PCM while
OPENHTPC was configured for bitstream, although local MKV and physical DVD
controls passed. The future `1.2.0-rc2` candidate is stabilization-only and is
not prepared or qualified. No tag, publication or physical bitstream PASS is
claimed by this record.

The RC1 UHD `OPEN_FAILED` is reclassified as an external AACS per-disc or
environment limitation after direct MPV reproduced the libaacs refusal outside
OPENHTPC. Structural UHD classification (`INDX0300`) and action gating passed;
`AVAILABLE` remains `READY_TO_ATTEMPT`, not a per-disc opening guarantee.

## Packaging hygiene audit

The packaged README now derives its active identity from the RC1 release
metadata and documents only current installation, update and public-command
contracts.

`payload/openhtpc-ui.py` retains a historical `1.1.2-dev1` fallback in the
low-level About-page renderer. It is not reachable through the normal RC1
product path: `openhtpc-system-page` reads installed `version.json`, falls back
to installed `VERSION`, and `openhtpc-system-model.py` always supplies
`model.technical.version`; session and SYSTÈME-action About rendering consume
that complete model. Partial action models render playback/audio pages only.
Direct invocation with a malformed model could expose the literal, so it is
recorded as non-blocking technical debt. No functional payload file was changed
for this packaging correction.
