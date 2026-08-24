# Changelog

## OPENHTPC AMD codec consistency candidate — 1.1.2-dev3

- Keep the qualified Dev2 RPM Fusion Free remediation and accept MPEG-2
  software fallback when the current freeworld VAAPI driver omits MPEG-2.
- Make `media_stack.observed_capabilities` authoritative inside `profile.json`
  and atomically synchronize all existing GPU-topology compatibility mirrors.
- Record VAAPI capability gains and losses individually without fabricating
  playback validation.

## OPENHTPC AMD Base validation candidate — 1.1.2-dev1

- Remove the historical Intel-only runtime-generation veto.
- Generate PURE/REFERENCE candidates only when the existing observed Vulkan,
  VAAPI, render-node, direct-display and MPV capability gates all pass.
- Keep AMD physical validation pending and preserve unvalidated-offload safety.

## OPENHTPC 1.1 audio final semantic corrective — 1.1.1-rc3

- Make requested PCM deterministically report passthrough as inactive,
  immediately and without requiring playback observation.
- Preserve BITSTREAM observation semantics and all forensic history.

## OPENHTPC 1.1 audio corrective — 1.1.1-rc2

- Preserve the physically validated PCM/BITSTREAM MPV and PipeWire policy.
- Refresh the AUDIO page and mode label synchronously after couch selection.
- Capture isolated MPV runtime evidence for DVD and publish the same bounded
  `AUDIO_POLICY_OBSERVED` state as local MEDIA playback.
- Place the AUDIO mode selector in the qualified lower system-page dock.
- Reuse existing lsdvd audio-format metadata when it identifies the DVD codec.

## OPENHTPC 1.1 maintenance candidate — 1.1.1-rc1

- Add one persistent PCM/BITSTREAM output policy, with safe PCM migration and
  codec-bounded MPV passthrough for AC3, E-AC3, DTS/DTS-HD and TrueHD.
- Remove audio-mode and HDR-capability questions from fresh installation.
- Record requested and observed audio policy without treating channel count or
  configured `audio-spdif` as proof of active passthrough.
- Include bounded audio policy, MPV observation and default PipeWire sink data
  in the support bundle.

## OPENHTPC 1.1 RC3 final corrective — 1.1.0-dev38

- Resolve DVD `FR_FULL` from qualified `lsdvd` language inventory through MPV's
  documented DVD language selector, without assuming lsdvd-to-MPV track IDs.
- Refresh an already-loaded DVD detail menu after the global presentation mode
  changes from SYSTÈME → LECTURE.
- Preserve dev37 UI geometry, artwork, OSD, audio and presentation semantics.

## OPENHTPC 1.1 RC3 final UI and optical artwork — 1.1.0-dev37

- Separates the approved playback dock icons vertically from their labels.
- Shows only the active user video-mode preference in the startup OSD.
- Integrates deterministic UI derivatives of Steve's optical-media artwork.
- Leaves playback, DVD detection and all media policies unchanged.

## OPENHTPC 1.1 RC3 playback UX corrective — 1.1.0-dev36

- Keeps LECTURE available when system capabilities are partial or unavailable.
- Restores the approved six first-party icons inside the lower action dock.
- Explains requested policy and resolved profile on separate OSD lines.
- Preserves the global DVD mode shortcut and qualified playback policy.

## OPENHTPC 1.1 RC3 playback UX candidate — 1.1.0-dev35

- Places all playback controls in the real Flex bottom dock below status.
- Applies each playback preference synchronously and reloads its parent view.
- Shows only the effective applied presentation mode in the startup OSD.
- Adds a DVD-sheet shortcut to the same global presentation preference.

## OPENHTPC 1.1 RC3 corrective candidate — 1.1.0-dev34

- Separates the LECTURE status card from its bottom action zone.
- Makes presentation-mode page refresh observable without restarting Flex.
- Sends the startup OSD as literal multiline UTF-8 in one argument.
- Preserves the dev33 icons and qualified audio/subtitle engines.

## OPENHTPC 1.1 RC3 development candidate — 1.1.0-dev33

- Separates the LECTURE page into an informational active-preferences zone and
  a bottom action row with distinct first-party icons.
- Refreshes the active-preferences page immediately after a saved selection.
- Shows the resolved playback policy in a top-left MPV OSD for five seconds.
- Backlog: `FUTURE_MEDIA_LANGUAGE_PREFERENCE` will generalize the currently
  qualified French media-language policy after RC3, without changing dev33.

## Previous candidate — 1.1.0-dev32

- Added persistent couch-native presentation, audio-language and subtitle
  preferences under SYSTÈME → LECTURE.
- Wired qualified PURE/CINÉMA AUTO intent and deterministic language policy
  through local/DVD playback, MPV arguments, temporary OSD and structured logs.
- Added the À PROPOS screen and explicit first-party project provenance.
- Added opt-in OpenSSH Ed25519 release-signing and public verification tools.
- Preserved RC2 runtime, MEDIA dispatcher, DVD, C3/C4 and updater semantics.

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
