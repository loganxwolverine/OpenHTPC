# OPENHTPC Optical Media Core O1 Dev4

Baseline: O1 Dev3 final manifest commit `ca28058214b2cb8c1c2b800f501d796de914a6ca`.

The physical Dev3 bundle proved canonical generations 42–47 continued while
disc-sheet and Flex presentation stopped at generation 44. The HOME controller
performed complete rendering/configuration synchronously in its only optical
watch loop, so one non-returning regeneration prevented later generations from
being consumed. The controller now acknowledges generation changes in the live
state immediately and delegates complete regeneration to a bounded worker.
Workers are cancelled on newer generations and config publication verifies the
expected generation immediately before atomic replacement. A five-second
timeout publishes an explicit matching FALLBACK rather than retaining old
provenance.

`BLURAY_FAMILY` previously had no lsdvd `disc_id`, so no enrichment process was
started while the renderer nevertheless displayed PENDING. Titled family media
now uses a generation-scoped optical metadata cache and schedules the existing
generation-guarded TMDb worker. READY is not presented as a live search; only
STARTED/PENDING has RECHERCHE TMDb semantics. Optical identity remains
BLURAY_FAMILY for every result.

The validator now detects canonical/disc-sheet/Flex divergence after five
seconds as PRESENTATION_GENERATION_STALE, persists observer-status.json, and
replaces an older observer during apply. Capture resolves forensic engines with
absolute paths, discovers empty optical drives from canonical state/sysfs/lsblk,
captures general and filtered user journals, and records hashes/mtimes for the
sheet, sidecar, live state and Flex config.

Tests: 9/9 dedicated Dev4 PASS; 189/189 full regression PASS. Python compilation,
installer/update shell validation and release metadata validation PASS.

No classifier, playback, codec, audio, power, plugin execution or TMDb settings
management behavior was changed.
