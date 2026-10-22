<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.3.2 RC3 — Patina

Version: `1.3.2-rc3`
Build: `public-release-1.3.2-rc3`
Status: **Release Candidate 3 in preparation — final build and physical qualification pending; not published**

OPENHTPC is a local-first couch interface for a Fedora KDE home-theater PC.
Flex Launcher provides the ten-foot interface and MPV provides playback. The
Hardware Passport, capabilities, media configuration and playback history stay
on the local machine; normal operation does not require a cloud service.

OPENHTPC 1.3.2 RC3 **Patina** builds on the published RC2 prerelease. This
candidate integrates a discreet HOME network-link/local-IP indicator, gamepad
navigation in Flex HOME and MEDIA, and a managed native SDL2 MPV gamepad mapping
for local films and DVD playback, including playback transport, seek, volume
and the MPV Stats overlay/pages.

It retains RC2 optical-generation refresh and HOME session protections, the
managed installation/removal policy, and the previous Magnificence GPU recipes.
The HOME/IP and Flex gamepad changes were physically exercised on the former
GEEKOM validator. The final combined RC3 package is not yet qualified on a
clean Fedora 44 KDE installation or across different gamepad models.

The preceding 1.3.1 version completed its physical gates on both Radeon RX 5700 XT and
Intel Arc A310 systems. The A310 retained its CLEAN + FSRCNNX-16 +
KrigBilateral + Vibrance Mild recipe and HDMI AC3 passthrough; the RX validator
confirmed the exact per-PCI codec view, PAL 50 Hz switching with restoration to
60 Hz, and safe PCM fallback on the available S/PDIF output.

Historical platform and media qualification is detailed in CHANGELOG.md,
the previous release notes and the reference-platform documentation. RC3's
full software regression, exact-commit artifact build, clean installation,
RC2-to-RC3 upgrade and physical validation are still pending.

## Verify the download

Keep the archive and checksum sidecar together, then run from their directory:

```bash
sha256sum -c OpenHTPC-1.3.2-RC3.tar.gz.sha256
```

## Install

Extract `OpenHTPC-1.3.2-RC3.tar.gz`, enter the extracted directory and inspect
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

From the extracted OPENHTPC 1.3.2 RC3 directory:

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

## RC3 qualification boundaries

The checksums and installation instructions above will apply to a real RC3
artifact once built and verified; no such RC3 archive has been released yet.
Source tests and prototype physical observations do not prove a final package
install, support for every gamepad, DVD, or audio output. SDL2 mappings depend
on the controller; MPV Stats pages depend on the installed MPV scripts.
Interactive DVD menus are not included.

## Known limitations

- Run `openhtpc rebuild-passport` when protected-optical dependencies are
  added after Hardware Passport/runtime snapshot generation.
- UHD dropped frames observed on ZimaBoard 2 remain a deferred platform
  performance limitation.
- Plasma Login Manager on the qualified NVIDIA system required an external
  SDDM workaround; OPENHTPC does not require that login manager.

See [1.3.2 RC3 release notes](RELEASE-NOTES-OPENHTPC-1.3.2-RC3-FR-EN.md),
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
