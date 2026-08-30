# OPENHTPC 1.1.3 RC2 — Candidate assembly record

Version: `1.1.3-rc2`  
Build: `public-release-1.1.3-rc2`

RC2 promotes the physically qualified Dev19 NVIDIA stabilization baseline. The
assembly changes public release identity, release documentation, artifact
metadata, and validation instructions; it adds no product feature or runtime
policy change after Dev19.

## Readiness audit

- Release identity is consistent across root/payload versions, JSON metadata,
  installer identity, runtime provenance input, and Flex product provenance.
- The existing update path preserves user configuration, MEDIA sources, TMDb
  credentials, confirmed disc associations, audio preferences, caches, and the
  valid Hardware Passport while regenerating the version-derived runtime.
- Dev16/RC1 MEDIA synchronization and qualified optical, audio, update, quit,
  and autostart behavior remain in the canonical regression suite.
- Dev17 capability provenance and safe passport rebuild, Dev18 native NVIDIA
  backend selection, and Dev19 MPEG-2 whitelist correction are represented in
  the changelog and qualification record.
- Intel and AMD VA-API architecture is unchanged.
- Known limitations, attribution, licenses, manifest coverage, and deterministic
  release packaging remain explicit.

Readiness verdict: **NO RC2 SOFTWARE BLOCKER FOUND**.

## Evidence boundary

- Dev19 targeted automation: 35/35 PASS.
- Dev19 full canonical automation: 355/355 PASS.
- Dev19 NVIDIA physical qualification: PASS, as recorded separately.
- RC2 targeted and full automation are required after assembly.
- RC2 physical qualification is pending and must be performed by a human on
  the NVIDIA, Ryzen AMD, and ZimaBoard 2 validators.

No RC2 physical PASS, tag, publication, GitHub release, or replacement of the
existing public RC1 release is claimed by this candidate record.
