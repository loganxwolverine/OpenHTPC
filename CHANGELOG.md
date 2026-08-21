# Changelog

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev31

- Refined only the generic DVD, BLU-RAY and UHD badge family and the DVD media
  sheet banner using original OPENHTPC primitives and generic descriptive text.
- No optical detection, playback, metadata or other functional code changed.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev30

- Replaced the generic optical icon on QUITTER OPENHTPC with an original
  OPENHTPC door-and-exit-arrow symbol.
- Assigned the approved POWER symbol to ÉTEINDRE LE PC and a dedicated return
  arrow to RETOUR.
- Refined the MEDIA folder silhouette and generic DVD/BLU-RAY/UHD disc badges.
- No functional runtime behavior changed from the physically qualified dev29
  baseline.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev29

- Prevented Flex/inih from truncating MEDIA action tokens when a displayed
  filename makes an INI entry exceed the parser's 200-byte input buffer.
- Kept full media paths exclusively in the action manifest; only the displayed
  label is shortened to fit the proven parser boundary.
- Added regression coverage for the physically failing dotted release name,
  long names, spaces, apostrophes, parentheses, release-group hyphens and UTF-8.

## OPENHTPC 1.1 Public Candidate R2 — 1.1.0-dev28

- Derived the public runtime strictly from physically qualified Media Sources
  dev27 (`core-media-sources-dev4`).
- Added qualified graphical management for zero to multiple filesystem media
  sources, including non-destructive removal and duplicate feedback.
- Simplified the HOME label to `MÉDIA`.
- Added original OPENHTPC POWER, folder and generic DVD/BLU-RAY/UHD artwork.
- Added manifest-based update convergence for obsolete managed files while
  preserving unknown and user-persistent files.
- Retained the qualified five-file benchmark set byte-for-byte and kept
  `filmgrain.glsl` excluded from public distribution.

## OPENHTPC 1.1 Public Candidate R1 — derived from 1.1.0-dev23

Changes since OPENHTPC Basic V1.0.0 Gold Master:

- Added the canonical System and Capability Engine UI integration.
- Added adaptive optical read-ahead with the qualified 12-second target and
  bounded forward/backward memory policy.
- Added local video render benchmarking and the versioned synthetic benchmark
  asset set.
- Added the qualified DVD visual recipe catalogue and real-disc blind-review
  outcomes.
- Added local auto-calibration with signature/event-driven staleness and
  observed-stability criteria.
- Added PURE and CINÉMA AUTO runtime/UI integration, including explicit couch
  recalibration and reliable KDE desktop restoration on quit.
- Added appliance idle/suspend inhibition while OPENHTPC owns the session.
- Added public licensing, third-party notices, provenance documentation and
  original replacement UI artwork for this distribution candidate.

R1 did not claim final `1.1.0` status.

## OPENHTPC Basic V1.0.0 Gold Master

- First qualified OPENHTPC Basic public baseline.
