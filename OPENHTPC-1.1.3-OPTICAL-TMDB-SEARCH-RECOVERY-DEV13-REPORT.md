# OPENHTPC Optical TMDb Search Recovery UX — Dev13

Baseline: `1.1.3-dev12`, `media-action-token-runtime-binding-dev12`, commit
`545d2cd`.

Dev13 adds recovery only when automatic enrichment has a genuine `NO_RESULT`.
The raw optical label remains canonical evidence. A separate search-only title
removes bounded suffixes (`16/9`, `16:9`, `4/3`, `4:3`, `PAL`, `NTSC`,
`WIDESCREEN`, `FULLSCREEN`, and trailing `DISC/DISK/DVD 1/2`). It never rewrites
movie wording or changes optical classification, badges, identity, or playback.

The recovery controller reuses the physically qualified `kdialog` input path for
title and optional year. Search failures remain distinguishable from network or
service failures. One or multiple manual results require explicit confirmation
before the existing `commit_binding` transaction writes the physical-disc cache.
Generation, canonical state, and disc ID are rechecked before search and commit.

The qualified Hancock ambiguity picker is unchanged: no manual-search entry was
added, candidate order and RETOUR position remain intact, and existing selection
and close behavior are preserved.

Tests: 71/71 focused PASS. Full regression: 292/292 PASS, single run, exit 0.
Flex source was unchanged; no Flex rebuild was required.

Deferred backlog: `TMDB_AMBIGUITY_MANUAL_SEARCH_ESCAPE`,
`UHD_CLASSIFICATION_EVIDENCE`, `TMDB_CINEMATIC_BACKDROP_UX`,
`DOCTOR_MEDIA_ACTION_RUNTIME_SEMANTICS`,
`MEDIA_PLAYBACK_DIAGNOSTIC_CURRENT_PAGE_SEMANTICS`,
`GLOBAL_STATUS_PROBLEME_SEMANTICS_REVIEW`, `NETWORK_CONNECTIVITY_STATUS_UI`,
and `POWER_NO_SUSPEND_POLICY_REVALIDATION`.

Status: OPTICAL_TMDB_SEARCH_RECOVERY_DEV13_READY_FOR_PHYSICAL_VALIDATION
