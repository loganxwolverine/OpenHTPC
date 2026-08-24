# OPENHTPC 1.1.1 — Post-freeze backlog

This backlog is non-blocking for the physically qualified 1.1.1 RC3 Audio P0
candidate. Items must not be folded into the frozen artifact.

## AUDIO_CODEC_PHYSICAL_QUALIFICATION_MATRIX

Validate each runtime-supported passthrough codec with identified source media
and explicit AVR front-panel evidence.

| Codec | Status | Required evidence |
|---|---|---|
| AC3 / Dolby Digital | PASS | AVR identified Dolby Digital |
| E-AC3 | PENDING | AVR identifies Dolby Digital Plus or equivalent |
| DTS | PENDING | AVR identifies DTS |
| DTS-HD MA | PENDING | AVR identifies DTS-HD Master Audio |
| Dolby TrueHD | PENDING | AVR identifies Dolby TrueHD |

`MULTI IN` or another PCM indication is a failure for a BITSTREAM qualification
run and an expected result for the corresponding PCM control run.

## SYSTÈME → À PROPOS

- Reposition RETOUR in the lower action area.
- The approved back icon is already corrected.
- Non-blocking; do not reopen Audio P0 for this polish.

## Future independent work

- Plugin Framework V1 P2 — independent of Audio P0.
- Cinema Enhancement — not started by this release.
- Controlled OPENHTPC tone mapping strategy; no tone-mapping implementation is
  part of Audio P0.
