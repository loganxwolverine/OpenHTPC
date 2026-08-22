# OPENHTPC 1.1 RC3 Candidate Dev34 Report

- Baseline: `1.1.0-dev33` / `da2c22974bf294ea4f2f1b3436b7e2d813b4f297`
- Version: `1.1.0-dev34`
- Build: `rc3-playback-ui-persistence-osd-fix-dev1`
- Scope: corrective playback layout, presentation-mode refresh, multiline OSD transport.
- Persistence root cause: user and legacy writes were correct; Flex retained a playback background rewritten on the same inode. The targeted refresh now atomically replaces that PNG.
- OSD root cause: dev33 supplied literal `\\N` sequences to MPV `osd-playing-msg`; MPV reported them as broken escapes. Dev34 supplies literal UTF-8 newlines in one argument.
- Tests: 7/7 dev34 regressions PASS; 36/36 targeted PASS; 36/36 full workspace regression PASS; 59/59 candidate validation PASS; MPV multiline transport smoke PASS.
- Playback contract: PURE requested/resolved PURE; CINEMA_AUTO requested/resolved PURE for the qualified local fallback fixture; log and OSD use the same decision object.
- Preserved: audio-language and subtitle selection engines, dev33 icons, media/optical/dispatcher/runtime subsystems.
- Signing: `OFFICIAL_RELEASE_SIGNING_KEY_PENDING`
- Physical qualification: pending Steve corrective smoke; this report does not qualify RC3.
