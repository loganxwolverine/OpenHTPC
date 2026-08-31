<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.1.4-dev4 — Protected Blu-ray physical qualification report

## Qualified identity

- Version: `1.1.4-dev4`
- Build: `protected-optical-disc-classification-dev4`
- Qualification baseline commit: `b3199fb84a815fda0d0506f58dbbba51bfe9d4d9`
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

## Qualification boundary

- One real protected Blu-ray was validated.
- The physical AACS path was validated.
- The exact Blu-ray/UHD variant remained `UNKNOWN`; no exact variant is
  claimed for this disc.
- This result does not qualify universal Blu-ray compatibility.
- This result does not qualify protected UHD playback.
- The absence of libbdplus was non-blocking for this AACS-protected disc.
- DVD was not exercised by this physical validation. Its existing regression
  gate and previously qualified behavior are not broadened by this report.

## Conclusion

`PROTECTED_BLURAY_PHYSICAL_GATE=PASS`

`UHD_PHYSICAL_GATE=NOT_QUALIFIED`

`DVD_REGRESSION_GATE=NOT_RUN_IN_THIS_PHYSICAL_QUALIFICATION`
