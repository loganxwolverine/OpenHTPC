# OPENHTPC Optical Media Core O1 Dev2 — Canonical UI truth

Baseline: `23d4e2091c023f51fe54d81d5c7eb036d5d9fb23`, 1.1.3-dev1,
`optical-media-core-detection-dev1`.

Accepted physical truth: empty and DVD passed. Both protected standard BD and
UHD exposed only `UDEV_MMC_BD_MEDIA`, correctly yielding `BLURAY_FAMILY`,
`uhd_status=UNKNOWN`, no provider and non-playable. Detection is unchanged.

Root cause: Dev1 retained the compatibility `state` field but presentation
consumers still selected HOME labels/icons, submenu provider messages, disc-sheet
artwork and cinematic badges from it. The cinematic generic poster additionally
hardcoded the text `DVD`. This allowed presentation to be more specific than the
canonical detector and left DVD artwork on non-DVD media.

Fix: `openhtpc-optical.py` now owns one canonical presentation map. Session,
disc-sheet and disc-view consumers resolve `canonical_state` first. Legacy state
is consulted only when canonical state is absent for upgrade compatibility.
`BLURAY_FAMILY` renders `BLU-RAY / UHD`, an exact-type-undetermined message,
generic optical icon/artwork and no provider-specific claim.

Fallback poster labels are DVD, BLU-RAY, ULTRA HD BLU-RAY, BLU-RAY / UHD, or
MÉDIA OPTIQUE according only to canonical identity. TMDb pending/no-result keeps
that fallback; only a committed PASS poster replaces it. Metadata never changes
identity. Non-playable media no longer receives text claiming local playback is
available.

DVD detection, artwork, metadata, dispatcher, playback, CSS, eject and monitor
behavior are unchanged. AMD, Capability Engine, graphics/runtime, audio, MEDIA,
power, plugin execution and low-level optical classification are untouched.

Tests: 10/10 dedicated Dev2 PASS; 171/171 full regression PASS.

Status: OPTICAL_CORE_O1_DEV2_READY_FOR_PHYSICAL_VALIDATION
