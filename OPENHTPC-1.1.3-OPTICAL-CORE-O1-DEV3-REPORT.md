# OPENHTPC Optical Media Core O1 Dev3 — Lifecycle and validator

Baseline: `050546def871242b5a2781785e0d31d2651b42cb`, 1.1.3-dev2,
`optical-media-ui-truth-dev2`.

Physical Dev2 accepted empty-drive, DVD and media-aware family artwork. It
failed because the sole monitor published INITIALIZING before a blocking DVD
probe on BD media, while HOME accepted a persistent disc-sheet PNG without
generation provenance after render timeout/failure.

Dev3 publishes stable detection directly and skips lsdvd for MMC-confirmed BD.
Eject advances the canonical generation, clears disc identity, records a hard
invalidation event and prevents old sheets from being reused. Rendered sheets
are staged, rechecked against CURRENT generation, then atomically committed with
a sidecar containing canonical state, UI hash, render identity and metadata
status. HOME accepts only an exact sidecar match.

TMDb enrichment is optional and guarded before cache commit and after render.
Late results are discarded and traced as TMDB_RESULT_DISCARDED_STALE_GENERATION.
The canonical fallback remains ready independently of metadata status.

Lifecycle events are retained as a bounded 512-line JSONL trace without keys or
metadata payloads. Events include insert/eject, canonical change, presentation
invalidation/readiness, render, TMDb start/result and stale-result discard.

The isolated validator uses ~/OPENHTPC-VALIDATOR/{inbox,releases,current,logs,
outbox,state}. apply-latest verifies manifest, SHA, archive metadata, uses exactly
the declared update.sh, never purges or starts graphics, executes post-checks and
starts the read-only optical observer. capture snapshots current state first,
redacts secrets, and creates one archive plus SHA. The observer captures objective
initialization timeout, stale eject presentation, backwards generation and
duplicate monitor failures. Subjective visual issues remain manual capture.

Detection evidence, Dev2 artwork mapping, DVD behavior and all frozen systems
remain unchanged.

Tests: 9/9 Dev3 dedicated PASS; 180/180 full regression PASS.

Status: OPTICAL_CORE_O1_DEV3_READY_FOR_ONE_COMMAND_PHYSICAL_VALIDATION
