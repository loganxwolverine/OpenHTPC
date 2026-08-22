# OPENHTPC 1.1 RC3 Candidate Dev36 Report

- Baseline: `1.1.0-dev35` / `3ea68f6d28fb1062db83accd98e2271c074f215b`
- Version: `1.1.0-dev36`
- Build: `rc3-playback-ux-corrective-dev1`
- Root cause page: the dev35 targeted playback render omitted `available`, so
  the generic system fallback replaced the valid playback page.
- Correction: playback rendering is independent of capability availability;
  targeted models are explicitly available and remain policy-only/headless-safe.
- Root cause icons: the dev35 Flex rendering branch explicitly nulled icons for
  every system subpage.
- Correction: approved assets render inside the preserved bottom action cards.
- OSD: separate `Politique vidéo` and `Profil appliqué` lines, without arrow.
- Policy/logging/DVD shortcut/audio/subtitle engines: unchanged.
- Flex binary SHA256:
  `bbcda2469a563fa5869b9e6e6f7ea5412d785e595d70c1874593c89887c0051c`.
- Tests: 10/10 dev36 regressions PASS; 54/54 full workspace regression
  PASS; 59/59 candidate validation PASS.
- Signing: `OFFICIAL_RELEASE_SIGNING_KEY_PENDING`
- Physical qualification: pending Steve final RC3 smoke; this report does not
  qualify RC3.
