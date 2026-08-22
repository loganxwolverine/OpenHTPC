# OPENHTPC 1.1 RC3 Candidate Dev37 Report

- Baseline: `1.1.0-dev36` / `49a4ca6c48d30ac943d9cf8daec6f32a933e8b15`
- Version: `1.1.0-dev37`
- Build: `rc3-final-ui-optical-artwork-dev1`
- Scope: vertical icon/label spacing, requested-mode OSD wording, and
  deterministic derivatives of Steve's optical-media artwork.
- Playback policy, resolved-profile logic, audio/subtitle engines, DVD
  playback/detection, dispatchers and Media Sources are unchanged.
- OSD logs retain requested and resolved presentation modes.
- Steve masters: three JPEG 1408×768 files detected on the NAS; SHA256 values
  and deterministic crop/downscale method are recorded in asset provenance.
- Derived artwork: three 1024 px media PNGs and three 512×256 badge PNGs,
  RGBA with transparent canvas margin and preserved aspect ratios.
- Flex binary SHA256:
  `b2e101c87a1c5c3d468e5706163ffe6408ed1b5802ac62dacbcb3a06b4945042`.
- Tests: 10/10 dev37 targeted PASS; 64/64 relevant workspace regression
  PASS; 65/65 candidate validation PASS.
- Signing: `OFFICIAL_RELEASE_SIGNING_KEY_PENDING`
- Physical qualification: pending Steve final UI smoke; this report does not
  qualify RC3.
