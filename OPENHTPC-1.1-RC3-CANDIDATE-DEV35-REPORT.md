# OPENHTPC 1.1 RC3 Candidate Dev35 Report

- Baseline: `1.1.0-dev34` / `fcd94395edf70e6bf37fdba1443ae05f16d12ca3`
- Version: `1.1.0-dev35`
- Build: `rc3-playback-ux-finalize-dev1`
- Scope: playback layout, immediate parent refresh, effective-mode OSD wording, global-mode DVD shortcut.
- Root cause layout: Flex did not classify the playback menus as bottom-dock
  system subpages, so its generic vertical centering placed the controls over
  the status sheet. Playback and DVD mode selectors now use the existing
  bottom action dock geometry.
- Root cause refresh: a child setting process regenerated the shared PNG while
  Flex only refreshed the current child texture; returning restored the
  already-loaded parent texture. The bounded `:applyback` action waits for the
  save/render operation, reloads the parent section and texture, then returns.
- Geometry contract at 1920x1080: status panel bottom `530 px`; action controls
  top `950 px`; safety gap `420 px` (required minimum `100 px`).
- Source of truth: `user-config.json`; the DVD control is a shortcut to the
  same global `presentation_mode`, not a disc override.
- OSD: only the effective result is shown (`Mode vidéo appliqué : PURE`);
  `PLAYBACK_POLICY` logs retain requested and resolved modes.
- Flex fork binary SHA256:
  `6b705d37076138b418465918b727bfeb5fe1b9432902c0c2fec2bb064bbcb6cf`.
- Flex source fingerprint:
  `4d8c5f2ede6a964c2339f8da53360f6e837ba39cca5dc107745d0d53e6f459e5`.
- Tests: 8/8 dev35 regressions PASS; 44/44 full workspace regression PASS;
  59/59 candidate validation PASS.
- Signing: `OFFICIAL_RELEASE_SIGNING_KEY_PENDING`
- Physical qualification: pending Steve final playback UX smoke; this report does not qualify RC3.
