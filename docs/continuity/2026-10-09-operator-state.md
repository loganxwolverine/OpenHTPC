# Checkpoint partagé — note opérateur

Capturé : 2026-10-09T10:56:00.902000+00:00
Source : .git/OPENHTPC_STATE.md. Note consignée, pas une réexécution des validations.

---

# OPENHTPC CURRENT OPERATOR STATE — 2026-10-09

## Authority

This local `.git/OPENHTPC_STATE.md` is an operator continuity note, not repository truth. Code/tests/artifacts remain authoritative. The tracked `OPENHTPC_CURRENT_STATE.json` currently describes the superseded Plugin Framework P2 / 1.2.0 workstream; its schema cannot represent Patina/1.3.1 and it must therefore be treated as STALE under `AGENTS.md`.

## Git

- Branch: `feature/magnificence-sd-auto`
- Committed HEAD: `6cdaef763c593215550c241e70e13c773ac799d0`
- Published tag: `v1.3.0`
- Release name: `OPENHTPC 1.3.0 — Patina`
- Current worktree: intentionally dirty for post-release 1.3.1 stabilization and Hermes coordination.
- No 1.3.1 commit, tag, push or release exists yet.

Protected stashes — NEVER apply/drop/modify without explicit authorization:
- `stash@{0}` pre-sync stale RTX experiment 2026-10-02
- `stash@{1}` RC7 T5 network deferred

## 1.3.1 stabilization scope currently in worktree

1. Manual TMDb search UI:
   - text-entry, confirmation and error windows explicitly request top-level visibility (`WindowStaysOnTopHint`, `raise_`, `activateWindow`);
   - text-entry timeout is caught and returns a bounded cancellation result;
   - confirmation/error functions import `QtCore` explicitly;
   - offscreen behavioral tests execute these paths.
2. Local MEDIA playback:
   - movie-detail `LIRE LE FILM` now launches `openhtpc-play` through `:tracked` exact-child lifecycle ownership instead of classic focus-based completion;
   - tokenized `openhtpc-play` already self-enables retained-Flex semantics and synchronously owns MPV until real termination.
3. Update recovery:
   - a previously RUNNING session is restored not only after successful update but also after a post-cleanup failure;
   - original failure status is preserved;
   - INT/TERM/HUP are converted to deterministic exit statuses so the EXIT recovery path can run.
4. Flex classic launch probe:
   - WNOHANG status is read only when `waitpid` returns the exact child;
   - EINTR is retried;
   - hard waitpid errors fail closed.
5. Tests:
   - old local-playback lifecycle test was found vacuous and replaced with a non-vacuous tracked-lifecycle assertion;
   - dedicated 1.3.1 behavioral updater/waitpid tests added.

## Validation evidence so far

Source/static:
- `git diff --check`: PASS after current edits.
- CMake Flex build from current source: PASS.

Targeted tests before the latest signal/EINTR hardening:
- 204/204 PASS across update, MEDIA detail/search, tracked lifecycle and movie-detail suites.

Latest behavioral additions:
- 5/5 PASS: updater SIGTERM recovery, missing-launcher truthfulness, failed-restart retry/failure, production `unix.c` WNOHANG/EINTR/hard-error harness, and generated local MEDIA tracked lifecycle.

Adjacent regression batch:
- 40 functional tests PASS;
- teardown isolation guard reported one real salon DVD log changing during the test window. This is live-runtime activity, not an assertion failure. Do not run host-state-sensitive full gates while the salon runtime is active.

Physical validation of 1.3.1: NOT_PERFORMED.
Installed 1.3.1 state: NOT_DEPLOYED.

## Live salon state during this note

A real DVD playback was observed active on `.229` while source tests were running. Do not stop/restart/deploy over it. The live installed product remains the Patina-era installation plus earlier manual-search hotfix state; repository source is ahead of installed state.

## Hermes / DeepSeek auditor

Hermes runs on Unraid `Tower` (`192.168.1.10`) in container `hermes-agent`, model `deepseek/deepseek-v4.1-flash` through OpenRouter. Never expose the private Fedora→Unraid SSH key or full OpenRouter credential to Hermes.

Role: external contradictory reviewer, initially read-only. It does not replace AGY/Autopilot, Codex CLI, CodeGraph, tests, Git authority or physical qualification.

First immutable snapshot:
- `openhtpc-audit-20261009T100617Z-6cdaef7`
- root-owned read-only tree, no `.git`, hermes UID 10000 cannot write
- first lifecycle/black-screen audit: 184 lines, exit 0, stderr empty
- report: `/mnt/user/appdata/hermes-agent/reports/openhtpc-audit-20261009T100617Z-6cdaef7-lifecycle-black-screen-audit.md`

Second immutable snapshot:
- `openhtpc-audit-20261009T102153Z-6cdaef7-r2`
- captured after initial lifecycle fixes but before the later QtCore import correction and signal/EINTR hardening
- second review independently detected the missing `QtCore` import, confirmed local MEDIA `:tracked`, update EXIT recovery and waitpid-status fixes, and recommended broader behavioral tests.

## CodeGraph

Canonical CodeGraph remains local on Fedora through Codex MCP. Operator-side graph-only reindex of the current worktree succeeded: 6174 nodes / 10608 edges over 225 files. Direct Hermes→CodeGraph MCP is NOT established yet. Preferred future design remains a CodeGraph instance over the same immutable Hermes audit snapshot, not access to the canonical Fedora repository.

## Immediate next action

1. Finish source/test qualification of the current 1.3.1 stabilization worktree.
2. Do not disturb active salon playback.
3. After live playback ends, deploy a bounded local candidate to `.229` and physically exercise:
   - manual-search title → year/confirmation → TMDb result/return;
   - local MEDIA playback → real MPV exit → Flex return;
   - DVD regression → real MPV exit → Flex return.
4. Only after source + physical gates are clean: request/receive explicit authorization before committing/tagging/pushing 1.3.1.

## Later 2026-10-09 coordination update

Hermes R3 static review: GO for bounded manual deployment/smoke after active DVD playback ends; not a release GO. R3 independently confirmed the post-R2 runtime fixes and found the Autopilot stale-state enforcement gap.

Autopilot gap fixed in current worktree: historical P2 state remains schema-readable, but `ensure_canonical_state_applicable()` rejects it under root VERSION 1.3.0. Canonical-state unit tests: 20/20 PASS. Offline doctor now fails closed with `canonical_state=True`, `canonical_state_applicable=False`.

Snapshot-local CodeGraph 0.20.1 has now executed successfully inside `hermes-agent` against R3 (226 files, 6068 nodes, 10626 edges, graph-only, telemetry off). Persistent Hermes MCP registration remains NOT_ESTABLISHED because the operator MCP-management command was blocked by external tool safety controls.
