# OPENHTPC 1.2.0 RC2 — Candidate preparation record

Version: `1.2.0-rc2`  
Build: `public-release-1.2.0-rc2`

RC1 closed its physical release gate `NO-GO` because protected Blu-ray output
PCM while OPENHTPC was configured for bitstream. RC2 contains stabilization
only: shared playback-policy application, authoritative protected playback
context, expanded non-blocking attempt diagnostics, and disc-view exception
containment.

Physical validation closed RC2 `NO-GO`: BITSTREAM playback opened with image
and audio, but the AVR reported STEREO. PCM playback remained functional. The
fix status is `SOFTWARE_PASS_PHYSICAL_FAIL_STEREO`; no physical bitstream PASS
is claimed.

The UHD `OPEN_FAILED` reproduced outside OPENHTPC remains an external AACS
per-disc/environment limitation and is non-blocking for RC2. `AVAILABLE`
continues to mean `READY_TO_ATTEMPT`.
