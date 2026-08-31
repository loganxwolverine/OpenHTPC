# OPENHTPC agent guidance

Authority precedence is: code/tests/artifacts; current qualification and
architecture documents; current roadmap/state documents; historical
conversation only as background.

Always inspect Git status first and work only on the authorized branch. Unless
a human explicitly authorizes it, never push, tag, release, merge, rebase,
delete branches, destructively reset, discard work, or mutate remote refs.
Never claim a test passed unless that exact test was executed successfully.
Software tests never establish physical optical qualification.

OPENHTPC does not provide, download, update, link to, parse, copy, or modify a
user KEYDB. Metadata-only presence detection is permitted where the current
architecture requires it. `AVAILABLE` means `READY_TO_ATTEMPT`, never
guaranteed per-disc decryptability.

The P2 Phase 12 boundary is frozen. `plugin.bluray` owns Blu-ray/UHD Doctor,
presentation, capability, decision, declarative UI, classification, pure
libbluray/structural normalization, and static assets. Core intentionally owns
device/library/filesystem acquisition, KEYDB metadata acquisition, raw-fact
merge and canonical publication, resource validation/rendering, tokens,
dispatcher/revalidation, bounded playback execution, MPV launch, and attempt
recording. Do not cross these I/O, security, rendering, or execution boundaries
without explicit authorization and qualification planning.

New OPENHTPC source files, where applicable, use:

    Copyright 2026 Steve Dehanne
    SPDX-License-Identifier: Apache-2.0

    Part of the OPENHTPC project.
    Original project by Steve Dehanne.

When invoked by OPENHTPC Autopilot, obey only the bounded plan, do not expand
scope, commit, or push, return the required structured report, and stop on any
safety or policy ambiguity.
