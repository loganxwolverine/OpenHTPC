# OPENHTPC 1.1 Public Candidate

This package is Public Candidate R2, version `1.1.0-dev31`, build
`public-release-optical-badge-polish-dev1`. It is an optical-badge-only visual
polish iteration derived from the stable dev30 functional baseline.
It is not the final `1.1.0` release.

The public RC2 tag `v1.1.0-rc2` identifies this qualified candidate and is
derived from the technical runtime baseline `1.1.0-dev31`; the runtime version
is intentionally not renamed. RC2 is physically qualified and frozen.

OPENHTPC is a local-first couch interface for a Fedora KDE home-theater PC. Its
Core manages playback, capabilities and appliance lifecycle; the Hardware
Passport records user-confirmed hardware choices; optional plugins extend the
system without changing Core capability truth. Flex Launcher provides the
ten-foot interface and MPV provides playback.

## Qualified platform and video modes

The currently qualified platform is Fedora 44 KDE Plasma on Wayland. Other
platforms are not claimed as validated.

`PURE` is the default presentation and uses the qualified native MPV path.
`CINÉMA AUTO` combines content scope, the project Recipe Catalogue and the
current local Performance Map. It selects the highest-quality project-qualified
presentation that is technically stable on the local hardware. It does not
mean that a shader is always enabled; PURE is a valid CINÉMA AUTO result.

Calibration is local, signature-driven and based on observed playback
stability. It uses no cloud or AI service. The Hardware Passport and Performance
Map remain user-local. `openhtpc doctor` reports product health; an unknown or
unsupported capability is not automatically a product failure.

Appliance mode inhibits desktop idle/suspend while OPENHTPC owns the couch
session. Explicit quit restores the KDE Plasma desktop lifecycle.

## Verify the download

Keep the archive and its `.sha256` file together, then run:

```bash
sha256sum -c OpenHTPC-1.1-PublicR2-Dev31.tar.gz.sha256
```

## Install

Extract the archive, enter the extracted directory and inspect first:

```bash
./install.sh --check
```

Install with the normal user account, not a root shell:

```bash
./install.sh
```

The installer accepts only Fedora 44 with KDE Plasma. It may propose specific
missing packages, RPM Fusion repositories and `libdvdcss`. Every system or
repository mutation is explained and requires interactive consent before
`sudo`/DNF is invoked. OPENHTPC never performs a general Fedora upgrade.

The installation lives under `~/.local/lib/openhtpc`; commands are linked under
`~/.local/bin`. Reconnect the session or add that directory to `PATH` if it is
not already present. OPENHTPC installs a managed KDE autostart entry and starts
on the next login. First installation runs local hardware discovery and initial
setup; updates preserve the existing Hardware Passport when present.

## Update and uninstall

From the extracted candidate directory:

```bash
./update.sh
./uninstall.sh
./uninstall.sh --purge-config
```

Update preserves user configuration, configured media sources, Hardware
Passport, Performance Map, runtime and system dependencies. A versioned
managed-file manifest removes only files proven to have belonged to the prior
OPENHTPC installation and absent from the target payload. Unknown files and
all user-persistent paths are outside this cleanup contract.

Normal uninstall removes the managed product, command links and autostart entry
while preserving user configuration. `--purge-config` also removes OPENHTPC
configuration, cache, state and shared data. Neither mode removes media files,
Fedora packages, RPM Fusion repositories or `libdvdcss`.

## Graphical Media Sources

The MÉDIA page supports zero to multiple configured filesystem sources. From
the couch UI you can add a source, open it, navigate folders and files, or use
RIGHT on a source to expose the non-destructive removal action. Removal only
updates OPENHTPC configuration: it never deletes, moves or modifies media.
Duplicate additions produce an explicit `SOURCE DÉJÀ AJOUTÉE` result.

Sources must already be accessible as local filesystem paths. An existing CIFS
or NFS mount can be selected through the picker, but OPENHTPC does not configure
or mount SMB/NFS shares itself. SMB/NFS service integration remains future
plugin work.

## Public commands in dev31

```text
openhtpc start
openhtpc stop
openhtpc setup
openhtpc doctor
openhtpc doctor --json
openhtpc version
openhtpc plugins
openhtpc capabilities
openhtpc capabilities --json
openhtpc capabilities --refresh
openhtpc support-bundle
```

There is no `openhtpc status` or `openhtpc update` command in this baseline.

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md),
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[assets/ASSET_PROVENANCE.md](assets/ASSET_PROVENANCE.md) before distribution.

## Candidate status

This package preserves the qualified dev27 Media Sources behavior while adding
public packaging, managed-update hygiene and provenance-safe UI polish. The
RC2 candidate completed physical validation and is frozen. This status does
not constitute a final `1.1.0` release announcement.
