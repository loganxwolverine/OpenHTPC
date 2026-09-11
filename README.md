<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.2.0 RC7

Version: `1.2.0-rc7`
Build: `public-release-1.2.0-rc7`
Status: **Release Candidate / prerelease — physical validation pending**

OPENHTPC is a local-first couch interface for a Fedora KDE home-theater PC.
Flex Launcher provides the ten-foot interface and MPV provides playback. The
Hardware Passport, capabilities, media configuration and playback history stay
on the local machine; normal operation does not require a cloud service.

The qualified Dev14 baseline passed on Fedora 44 KDE Plasma/Wayland with
Intel/ZimaBoard 2, AMD/Ryzen and NVIDIA/RTX 3050. RC2 adds only the protected
optical stabilization required after the RC1 and RC2 physical gates closed
NO-GO. RC4 added PipeWire HDMI HD passthrough sink preparation, RC5 added
effective PipeWire IEC958 SPA parameter verification, and RC6 recovered MEDIA
bitstream passthrough by sharing dynamic PipeWire IEC958 sink preparation with
local media playback. RC7 adds automatic frame-rate matching, dynamic display
settings synchronization, and protected optical / local playback display resync
audio stability.

## Verify the download

Keep the archive and checksum sidecar together, then run from their directory:

```bash
sha256sum -c OpenHTPC-1.2.0-RC7.tar.gz.sha256
```

## Install

Extract `OpenHTPC-1.2.0-RC7.tar.gz`, enter the extracted directory and inspect
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

From the extracted RC5 directory:

```bash
./update.sh
```

Update preserves user configuration, MEDIA sources, the Hardware Passport,
recorded video validations and other persistent user state. It replaces only
managed product files according to the packaged manifest.

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

See [RC3 release notes](RELEASE-NOTES-OPENHTPC-1.2.0-RC3-FR-EN.md),
[known limitations](KNOWN_LIMITATIONS.md),
[third-party notices](THIRD_PARTY_NOTICES.md) and
[asset provenance](assets/ASSET_PROVENANCE.md).

OPENHTPC was created as an original project by Steve Dehanne and is licensed
under Apache-2.0. Third-party components retain their respective licenses.
