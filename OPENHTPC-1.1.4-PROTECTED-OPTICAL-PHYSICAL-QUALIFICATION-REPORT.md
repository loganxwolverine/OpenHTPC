<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.1.4-dev5 — Protected optical qualification consolidation

## Qualified identity

- Version: `1.1.4-dev5`
- Build: `protected-optical-qualification-ux-dev5`
- Qualified software commit: `6ce9f79da3053707d7936f4d44140ac5ff44e40c`
- Platform: ZimaBoard 2
- Operating environment: Fedora KDE Wayland

## Physical protected Blu-ray evidence

One real protected Blu-ray produced the following canonical state:

```text
Optical media family       BLURAY
Optical exact type         UNKNOWN
Optical protection         PROTECTED
Protection mechanism       AACS
Classification source      LIBBLURAY

Protected optical media    AVAILABLE
libbluray                   AVAILABLE
libaacs                     AVAILABLE
libbdplus                   NOT_AVAILABLE
External key database      DETECTED
Protected optical playback ENABLED
```

Observed playback behavior:

- Playback button visible/enabled: **PASS**
- MPV launch: **PASS**
- Video: **PASS**
- Audio: **PASS**
- Quit playback: **PASS**
- Return to OPENHTPC: **PASS**

## Doctor after playback

```text
Last protected disc attempt OPEN_SUCCESS
UI instances                1
Optical monitor instances   1
Appliance state             RUNNING
Overall                     READY
```

## DVD regression evidence

- Detection: **PASS**
- Play button: **PASS**
- Launch: **PASS**
- Video: **PASS**
- Audio: **PASS**
- Stable playback: **PASS**
- Quit: **PASS**
- Return to OPENHTPC: **PASS**
- Doctor Overall: **READY**

## Protected UHD Blu-ray 4K evidence

A real commercial protected UHD Blu-ray 4K was physically opened on the same
ZimaBoard 2 / Fedora KDE Wayland system.

- UHD physical detection: **PASS**
- Optical exact type: `UHD_BLURAY`
- Optical protection: `PROTECTED`
- Protection mechanism: `AACS`
- Classification source: `LIBBLURAY`
- Dedicated `ULTRA HD BLU-RAY 4K` badge: **PASS**
- Playback button: **ENABLED**
- MPV launch: **PASS**
- Video: **PASS**
- Audio: **PASS**
- Playback: **FUNCTIONAL**
- Quit: **PASS**
- Return to OPENHTPC: **PASS**
- Last protected disc attempt: `OPEN_SUCCESS`
- Doctor Overall: **READY**

Important dropped output frames were observed during UHD playback on this
configuration. UHD fluidity and performance are therefore not qualified as
PASS; investigation is deferred to the roadmap.

## Current state after UHD ejection

- Current optical classification removed: **PASS**
- No stale current Blu-ray/UHD/protection state: **PASS**
- Last protected disc attempt preserved as `OPEN_SUCCESS`: **PASS**
- Doctor Overall: **READY**

The current-disc state and last-attempt history remained separate.

## Qualification boundary

- One real protected Blu-ray was validated.
- The physical AACS path was validated.
- The exact Blu-ray/UHD variant remained `UNKNOWN`; no exact variant is
  claimed for this disc.
- This result does not qualify universal Blu-ray compatibility.
- Protected UHD opening, video, audio and return were validated for one real
  disc and this specific system; this is not a universal compatibility claim.
- Protected UHD performance remains a known limitation and is not qualified.
- The absence of libbdplus was non-blocking for this AACS-protected disc.
- DVD regression was physically exercised and passed.

## Conclusion

`PROTECTED_BLURAY_PHYSICAL_GATE=PASS`

`DVD_REGRESSION_GATE=PASS`

`DEV5_PHYSICAL_UHD_BADGE_GATE=PASS`

`CURRENT_DISC_CLEAR_ON_EJECT=PASS`

`PROTECTED_UHD_OPEN_GATE=PASS`

`PROTECTED_UHD_VIDEO_GATE=PASS`

`PROTECTED_UHD_AUDIO_GATE=PASS`

`PROTECTED_UHD_RETURN_GATE=PASS`

`PROTECTED_UHD_PERFORMANCE_GATE=KNOWN_LIMITATION_DEFERRED`

`DEV5_STATUS=PHYSICALLY_QUALIFIED`
