<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.3.2 RC1 — Patina

Version: `1.3.2-rc1`
Build: `public-release-1.3.2-rc1`
Status: **Release Candidate — public installation/physical qualification pending (not published)**

OPENHTPC is a local-first couch interface for a Fedora KDE home-theater PC.
Flex Launcher provides the ten-foot interface and MPV provides playback. The
Hardware Passport, capabilities, media configuration and playback history stay
on the local machine; normal operation does not require a cloud service.

OPENHTPC 1.3.2 RC1 **Patina** is a stabilization-only candidate. It carries
forward the 1.3.1 Magnificence and media qualifications without changing image
recipes. This candidate adds the V11 DVD optical-generation publication and
menu-regeneration correction, plus a repaired synthetic test fixture for the
release tooling. A complete movie was watched successfully after the optical
fix on the .229 validator; that does not prove a clean public installation.

The preceding 1.3.1 version completed its physical gates on both Radeon RX 5700 XT and
Intel Arc A310 systems. The A310 retained its CLEAN + FSRCNNX-16 +
KrigBilateral + Vibrance Mild recipe and HDMI AC3 passthrough; the RX validator
confirmed the exact per-PCI codec view, PAL 50 Hz switching with restoration to
60 Hz, and safe PCM fallback on the available S/PDIF output.

The qualified Dev14 baseline passed on Fedora 44 KDE Plasma/Wayland with
Intel/ZimaBoard 2, AMD/Ryzen and NVIDIA/RTX 3050. RC2 adds only the protected
optical stabilization required after the RC1 and RC2 physical gates closed
NO-GO. RC4 added PipeWire HDMI HD passthrough sink preparation, RC5 added
effective PipeWire IEC958 SPA parameter verification, and RC6 recovered MEDIA
bitstream passthrough by sharing dynamic PipeWire IEC958 sink preparation with
local media playback. RC7 added automatic frame-rate matching, dynamic display
settings synchronization, and protected optical / local playback display resync
audio stability. RC8 introduced the Media Foundation persistent database,
normalized media probe, living-room movie matcher and resolver, cached poster
rendering, asynchronous library/identity/TMDb operations with live activity
feedback, and Unicode/CJK fallback rendering. OPENHTPC 1.2.0 promotes the
RC9-qualified behavior unchanged as the stable release: an authoritative library
summary, clearer unidentified-media review, mounted NAS/network source discovery,
and contextual first-use guidance from source selection through first analysis.

## Verify the download

Keep the archive and checksum sidecar together, then run from their directory:

```bash
sha256sum -c OpenHTPC-1.3.2-RC1.tar.gz.sha256
```

## Install

Extract `OpenHTPC-1.3.2-RC1.tar.gz`, enter the extracted directory and inspect
the installation first:

```bash
./install.sh --check
```

Install with the normal user account, not a root shell:

```bash
./install.sh
```

The supported release platform is Fedora 44 with KDE Plasma on Wayland. The
installer explains required system changes and requests consent before package
or repository mutations. It does not perform a general Fedora upgrade.

OPENHTPC is installed under `~/.local/lib/openhtpc`; public command links are
created under `~/.local/bin`. A managed KDE autostart entry starts the couch UI
at the next login. Initial setup performs local hardware discovery and creates
the Hardware Passport.

## Update

From the extracted OPENHTPC 1.3.2 RC1 directory:

```bash
./update.sh
```

Update preserves user configuration, MEDIA sources, the Hardware Passport,
recorded video validations and other persistent user state. It replaces only
managed product files according to the packaged manifest.

## Update the local media library

Run `~/.local/lib/openhtpc/openhtpc-media-library-update` to scan every
configured local source, enrich available movies, cache posters, and publish one
final Flex configuration. The command prints a JSON summary and returns a
nonzero status if any source or item failed or Flex publication was incomplete.
Unchanged files and previously matched identities keep their existing
incremental behavior.

## Public commands

```text
openhtpc start
openhtpc stop
openhtpc setup
openhtpc doctor
openhtpc doctor --json
openhtpc version
openhtpc plugins
openhtpc plugins --refresh
openhtpc plugin enable <plugin-id>
openhtpc plugin disable <plugin-id>
openhtpc capabilities
openhtpc capabilities --json
openhtpc capabilities --refresh
openhtpc capabilities --refresh --json
openhtpc rebuild-passport
openhtpc support-bundle
```

Additional expert video commands are listed by the command usage output.
There is no `openhtpc status` or `openhtpc update` command; use `./update.sh`.

## Blu-ray, UHD and protected media

`plugin.bluray` is an opt-in plugin. Enable it explicitly to expose Blu-ray/UHD
policy, presentation and play actions; DVD remains Core-owned. Generic device
access, security, rendering and bounded playback execution remain Core
services. If the plugin is absent, disabled or broken, Blu-ray/UHD play actions
are not exposed.

OPENHTPC does not provide, download, update, link to, parse, copy or modify a
user KEYDB. It detects presence/readability metadata only. Users may configure
their libaacs environment independently outside OPENHTPC. Protected optical
`AVAILABLE` means `READY_TO_ATTEMPT`, never guaranteed decryptability or
playback for every disc.

## Known limitations

- Run `openhtpc rebuild-passport` when protected-optical dependencies are
  added after Hardware Passport/runtime snapshot generation.
- UHD dropped frames observed on ZimaBoard 2 remain a deferred platform
  performance limitation.
- Plasma Login Manager on the qualified NVIDIA system required an external
  SDDM workaround; OPENHTPC does not require that login manager.

See [1.3.2 RC1 release notes](RELEASE-NOTES-OPENHTPC-1.3.2-RC1-FR-EN.md),
[preceding 1.3.1 release notes](RELEASE-NOTES-OPENHTPC-1.3.1-FR-EN.md),
[known limitations](KNOWN_LIMITATIONS.md),
[third-party notices](THIRD_PARTY_NOTICES.md) and
[asset provenance](assets/ASSET_PROVENANCE.md).

Project contributors and future work sessions should begin with the
[agent contract](AGENTS.md), the
[continuity checkpoint](docs/OPENHTPC_CONTINUITY.md), the
[global roadmap](OPENHTPC-ROADMAP.md), the
[actors and authority matrix](docs/OPENHTPC_ACTORS.md), and the
[reference-platform register](docs/OPENHTPC_REFERENCE_PLATFORMS.md).
GPU qualification follows the
[MPV/Magnificence protocol](docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md).

OPENHTPC was created as an original project by Steve Dehanne and is licensed
under Apache-2.0. Third-party components retain their respective licenses.
