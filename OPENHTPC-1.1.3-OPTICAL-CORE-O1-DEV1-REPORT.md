# OPENHTPC Optical Media Core O1 — Dev1

Baseline: `0027c25ea866c47e3afe9775f6a5908bdbbbbeeb`, 1.1.2-dev5,
`amd-codec-release-metadata-consistency-dev5`.

Architecture: the existing optical monitor and `openhtpc-optical.py` remain the
single authority. The qualified legacy `state` field remains for existing DVD
consumers; `canonical_state` is the O1 medium identity. Detection, provider and
playability are separate fields.

Evidence: `/sys/class/block/*/device/type == 5` discovers drives dynamically.
`udevadm` MMC-derived `ID_CDROM_MEDIA*` properties establish media presence and
physical family. `lsdvd` remains the qualified DVD-Video proof. BD-Video needs
BD media evidence and a recognized unencrypted `BDMV/index.bdmv` header.
`INDX0100/0200` means Blu-ray Video; `INDX0300` is the UHD application-format
version and is required for UHD. Missing/unreadable/unrecognized headers yield
truthful `BLURAY_FAMILY` with `uhd_status=UNKNOWN`. Capacity, BDXL, labels, drive
capability, keys and decryption are excluded.

Research basis: Linux kernel CD-ROM ioctl documentation confirms that legacy
disc-status classification is CD-oriented and insufficient for BD/UHD; systemd
`cdrom_id` derives `ID_CDROM_MEDIA_BD*` from MMC profiles; the Blu-ray Disc
Association identifies UHD BD-ROM as application format version 3.0; and
libbluray's upstream history explicitly associates version-0300 BDMV parsing and
UHD extension data. Sources:

- https://docs.kernel.org/userspace-api/ioctl/cdrom.html
- https://cgit.freedesktop.org/systemd/systemd/tree/src/udev/cdrom_id/cdrom_id.c
- https://us.blu-raydisc.com/tech-specifications/uhd-bd-rom/
- https://www.mail-archive.com/libbluray-devel@videolan.org/thrd3.html

Playback: DVD retains provider `core` and its existing behavior. Blu-ray maps to
`plugin:bluray`; UHD maps to `plugin:uhd`. Both are non-playable and
`PLUGIN_REQUIRED` when absent. No plugin code is executed and P2 is untouched.

UI: DVD is unchanged. Blu-ray/UHD cards state detection, unavailable playback
and the required plugin; no dead installer action was added. TMDb is never used
by detection.

Transitions covered deterministically: no drive, empty, insert DVD/BD/UHD,
ambiguous BD, eject and device removal. Atomic publication removes stale disc
identity. Physical hotplug/card observation remains for Steve.

Safety: collector is read-only, title-free, keyless and performs no playback,
decryption, mount, rip, network lookup, sudo or package operation.

Tests: 13/13 dedicated O1 PASS; 161/161 full regression PASS.

Backlog retained: `SYSTEM_METADATA_TMDB_MANAGEMENT` and
`POWER_NO_SUSPEND_POLICY_REVALIDATION`. No power or TMDb settings changes.

Status: OPTICAL_CORE_O1_READY_FOR_PHYSICAL_VALIDATION
