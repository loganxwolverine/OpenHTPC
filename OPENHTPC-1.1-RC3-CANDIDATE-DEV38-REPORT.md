# OPENHTPC 1.1 RC3 Candidate Dev38 Report

- Baseline: `1.1.0-dev37` / `c56d3ab9ab51dfae5ab5f926c81bf8b15612bd75`
- Version: `1.1.0-dev38`
- Build: `rc3-final-dvd-policy-refresh-corrective-dev1`
- Scope: DVD `FR_FULL` resolution and global presentation-mode refresh on the
  already-loaded DVD detail menu only.
- DVD selection uses qualified `physical_edition.subtitles` as eligibility
  evidence and MPV's documented `--slang=fr,fra,fre` DVD selection. It does not
  derive an MPV `sid` from lsdvd ordering.
- The single preference remains `user-config.json/presentation_mode`; no DVD,
  disc or session override is introduced.
- Root cause (DVD): the optical player invoked the generic policy resolver with
  neither a media probe nor the already-qualified optical inventory, so
  `FR_FULL` saw an empty stream list and emitted `--sid=no`.
- Root cause (detail): Flex `:applyback` reloaded only the selector's parent.
  A SYSTÈME update rewrote the canonical config but left the preloaded `DISQUE`
  menu object stale until another optical refresh.
- Tests: 9/9 dev38 targeted PASS; 73/73 checkout regression PASS; 564/564
  frozen workspace regression PASS; 65/65 candidate validation PASS.
- Signing: `OFFICIAL_RELEASE_SIGNING_KEY_PENDING`.
- Physical qualification: pending Steve's final short couch smoke; this report
  does not qualify RC3.
