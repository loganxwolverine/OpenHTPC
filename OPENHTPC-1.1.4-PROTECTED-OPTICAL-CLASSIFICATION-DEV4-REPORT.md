# OPENHTPC 1.1.4 Dev4 — Physical Blu-ray classification

## Dev3 diagnosis

`CURRENT_TYPE_CLASSIFICATION_SOURCE=udev ID_CDROM_MEDIA_BD* plus a mounted BDMV/index.bdmv header`

`CURRENT_PROTECTION_CLASSIFICATION_SOURCE=mounted filesystem AACS/BDMV paths only`

`WHY_REAL_BLURAY_CAN_REMAIN_UNKNOWN=a commercial Blu-ray can be identified as BD by udev while exposing no mountpoint or readable BDMV/AACS paths; Dev3 then knows only BLURAY_FAMILY and has no protection evidence`

Dev3 did not query libbluray disc information. Labels, `blkid` filesystem type,
codec and resolution were deliberately not sufficient classifiers.

## Dev4 implementation

Fedora's installed libbluray 1.4.0 header exposes `BLURAY_DISC_INFO` through
`bd_get_disc_info()`, including `bluray_detected`, `aacs_detected`,
`aacs_handled`, `bdplus_detected` and `bdplus_handled`. Dev4 publishes those
public facts in canonical optical state and records `LIBBLURAY` as the primary
source. Mounted non-secret disc structure remains the deterministic fallback.

An AACS or BD+ detected flag always yields `PROTECTED`; handled status remains
separate diagnostic evidence. A reliable Blu-ray result with neither mechanism
yields `UNPROTECTED`. Contradictory evidence resolves conservatively toward a
detected protection mechanism.

Exact UHD classification still requires BDMV `INDX0300`. HEVC, 3840x2160 and
labels never upgrade the type. A known Blu-ray with unknown exact variant is
published as `BLURAY_FAMILY` with partial confidence, and the existing generic
`bd://` backend may be attempted only after the unchanged protection/provider
gate authorizes it.

The implementation performs no direct key-database content access and adds no
network acquisition. DVD, TMDb, protected backend and GPU runtime sources are
unchanged from Dev3.
