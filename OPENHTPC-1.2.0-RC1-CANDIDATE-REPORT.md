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

RC1 physical qualification is **PENDING**. No tag, publication or RC1 physical
PASS is claimed by this assembly record.
