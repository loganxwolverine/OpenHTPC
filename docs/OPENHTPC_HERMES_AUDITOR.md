# OPENHTPC Hermes / DeepSeek audit lane

## Role

Hermes Agent with DeepSeek through OpenRouter is an external contradictory reviewer for OPENHTPC. It starts in read-only audit mode. Its findings are evidence, not project authority.

Authority remains: code/tests/artifacts first, then verified current project state and qualification documents. AGY/Autopilot planning, Codex execution, CodeGraph mapping, software gates and Steve's physical qualification remain separate authorities.

## Verified service endpoint — 2026-10-09

- Unraid host: `Tower` / `192.168.1.10`.
- Container: `hermes-agent`, image `nousresearch/hermes-agent:latest`.
- Persistent data: `/mnt/user/appdata/hermes-agent` -> `/opt/data`.
- CLI: `/opt/hermes/hermes`, invoked as user `hermes` (UID/GID 10000).
- Model: `deepseek/deepseek-v4.1-flash` via `openrouter`, reasoning `high`.
- Port 8642 is not an approved control interface; a root HTTP request returning 404 is not control-plane validation.
- OpenRouter credentials stay inside the Hermes configuration. Never print or copy the complete API key.

Fedora reaches Unraid using the dedicated operator SSH identity. That private key is never copied into the Hermes container and is not Hermes authority.

## Read-only audit contract

Every initial audit uses a new identifiable snapshot of the current canonical worktree. The snapshot must record the verified branch, HEAD, `git status --short`, protected stash names, and a diff of local changes. `.git` is excluded so the snapshot cannot become Git authority.

The snapshot on Unraid is owned by root and exposed 0555 for directories / 0444 for files. Hermes runs as UID 10000. A write-attempt test must fail before an audit is accepted as isolated.

One-shot `-z` auto-bypasses approval prompts and is therefore NOT a safety boundary. Initial audits explicitly restrict Hermes to the `terminal` toolset and rely on OS permissions plus container isolation. No Docker socket, Fedora filesystem, OPENHTPC runtime path, SSH private key, deployment credential, or canonical repository is mounted into Hermes.

Reports are captured outside the read-only snapshot under `/mnt/user/appdata/hermes-agent/reports/`. A report must separate FACT / HYPOTHESIS / OPEN QUESTION and cite file:line evidence.

## Invocation pattern

Operator-side pattern (exact snapshot/report names vary):

```text
docker exec -u hermes hermes-agent \
  /opt/hermes/hermes \
  --in /opt/data/audits/<snapshot>/project \
  -t terminal \
  -m deepseek/deepseek-v4.1-flash \
  --provider openrouter \
  --reasoning high \
  -z '<bounded audit prompt>'
```

Stdout is captured by the Unraid operator into the report directory. The prompt must explicitly forbid modification, but safety does not depend on that instruction.

## First mission

Map the production lifecycle:

media selection -> playback policy/dispatcher -> MPV launch -> real MPV termination -> exact tracked child completion -> Flex restoration.

Then identify code paths that could leave KWin/Wayland alive while Flex is absent or hidden, producing a black screen with a mouse cursor. Require file/line evidence, distinguish facts from hypotheses, and make no modifications.

The first report must be compared with the project's existing diagnoses before Hermes receives any workspace-write development task.

## CodeGraph

CodeGraph access is NOT currently established for Hermes. Evaluate it only after the first plain-source audit. Prefer a read-only query surface or exported graph facts; do not give Hermes write/control access to the canonical Fedora repository merely to obtain graph context.

## First qualified audit run — 2026-10-09

Snapshot: `openhtpc-audit-20261009T100617Z-6cdaef7`.

Report on Unraid: `/mnt/user/appdata/hermes-agent/reports/openhtpc-audit-20261009T100617Z-6cdaef7-lifecycle-black-screen-audit.md`.

Invocation used only `-t terminal`, explicit model `deepseek/deepseek-v4.1-flash`, provider `openrouter`, reasoning `high`, and the read-only snapshot as `--in` workspace. Result: exit code 0, 184-line report, empty stderr. Post-run SHA-256 verification of every snapshot file passed.

The first report confirmed the inherited UI-session-lock hazard already observed in the project and identified additional items requiring independent validation, notably classic focus-based lifecycle for local MEDIA playback and failed-update recovery after Flex cleanup. No finding is automatically accepted as a code change; compare it with canonical source/tests first.

## CodeGraph feasibility — 2026-10-09

Hermes supports stdio MCP registration (`hermes mcp add --command ... --args ...`). The installed CodeGraph server supports MCP stdio, `--profile graph`, `--graph-only`, and one-shot `--run-tool`. Fedora and the Hermes container are both x86_64.

Preferred future connection: run a separate root-owned CodeGraph engine against the same read-only audit snapshot inside the Hermes/Unraid isolation boundary. Do NOT bridge Hermes directly to the canonical Fedora CodeGraph workspace. This keeps graph facts aligned with the immutable snapshot and preserves canonical-repository isolation. The connection has not yet been created or tested.

## Second contradictory audit — 2026-10-09

Snapshot: `openhtpc-audit-20261009T102153Z-6cdaef7-r2` (read-only, no `.git`). This snapshot contained the first lifecycle/update/waitpid fixes but intentionally preceded the later manual-search `QtCore` correction and signal/EINTR hardening.

The second review exited 0 and independently classified the primary local MEDIA `:tracked` conversion, failed-update EXIT recovery, and WNOHANG status-ownership fix as structurally sound. It also independently found the reachable missing-`QtCore` regression in the confirmation/error windows. The canonical worktree had the same defect independently identified and then corrected; offscreen tests now execute those real window helpers instead of mocking them.

The review also identified two useful hardening items: update interruption by INT/TERM/HUP should flow through recovery, and the waitpid change should have an executed C harness rather than source-text-only coverage. Both items are now implemented in the uncommitted 1.3.1 worktree with behavioral tests. Findings remain advisory until canonical tests/physical validation pass.

## CodeGraph operator-side evidence

Before any direct Hermes MCP connection, Fedora CodeGraph was reindexed against the current canonical worktree in graph-only mode with telemetry disabled. The index contained 6174 nodes and 10608 edges over 225 files, and `codegraph_symbol_search` returned current 1.3.1 test symbols. This proves CodeGraph can provide fresh structural context, but it is still operator-mediated evidence, not a Hermes connector.

Direct Hermes -> CodeGraph MCP remains `NOT_ESTABLISHED`. The preferred design is unchanged: a dedicated CodeGraph instance indexing the same immutable audit snapshot. Until that boundary is implemented and tested, Hermes receives no control path to Fedora CodeGraph.

## Promotion rule for Hermes

Hermes remains READ_ONLY. Workspace-write eligibility requires multiple successful contradictory reviews, canonical verification of its findings, and an explicit separate writable workspace with no deployment/Git-push authority. No such promotion has been granted as of 2026-10-09.

## R3 review and snapshot-local CodeGraph — 2026-10-09

R3 snapshot: `openhtpc-audit-20261009T104338Z-6cdaef7-r3`. The root-owned read-only write test again failed for UID 10000. The R3 Hermes review classified the manual-search fixes, local MEDIA tracked lifecycle, updater signal/EXIT recovery, and unix.c WNOHANG/EINTR handling as CLOSED for bounded physical-smoke purposes. It also identified a coordination contradiction: Autopilot still enforced the stale 1.2.0/P2 state despite the new AGENTS stale-state rule.

That contradiction is now corrected in the canonical uncommitted worktree: Autopilot parses the historical P2 state but rejects it as `CANONICAL_STATE_STALE` when the root VERSION is outside the 1.2.0 line. The offline doctor now reports `canonical_state=True`, `canonical_state_applicable=False` and fails closed on the current 1.3.0 worktree.

CodeGraph 0.20.1 was copied into the persistent Hermes data area as root-owned executable and successfully executed inside `hermes-agent` as UID 10000 against R3 with `CODEGRAPH_TELEMETRY=off`, `--graph-only`, and profile `graph`. It indexed 226 files, 6068 nodes and 10626 edges, with its data directory under `/opt/data/.codegraph`, outside the immutable project snapshot. A one-shot `codegraph_symbol_search` succeeded.

Persistent Hermes MCP registration was NOT completed: the operator command to inspect/register Hermes MCP configuration was blocked by the external tool safety control. Do not describe the direct connector as established. Current status is: snapshot-local CodeGraph execution PROVEN; persistent Hermes MCP registration NOT_ESTABLISHED.


## Final 1.3.1 stabilization audit — 2026-10-10

Snapshot `openhtpc-audit-20261010T133100Z-6cdaef7-131-final-r2`: 539 hashes and root ownership verified before audit; UID10000 write attempt denied; no .git. Direct Python CLI, terminal-only, DeepSeek v4.1 flash/OpenRouter/high. Exit 0, empty stderr; all source hashes verified again afterwards.

Original report preserved on Unraid and copied to `docs/audits/2026-10-10-131-hermes-final.md`. Operator dispositions, the independently reproduced standalone DVD lock-inheritance defect, its minimal FD-close fix and the 125/125 post-audit gate are recorded in `docs/continuity/2026-10-10-131-reprise-qualification.md`. R2 remains the immutable pre-fix snapshot; the fix is independently tested and must not be claimed as already reviewed by Hermes. No write promotion, physical qualification, release authority or persistent CodeGraph MCP connection is established by this review.

## Final delta review after `.67` qualification — 2026-10-10

Snapshot `openhtpc-audit-20261010T170140Z-6cdaef7-131-final-delta`: archive SHA-256 `901291b719c955157b08f36addf6433af6332152aa48a386472bc772ea123b27`, no `.git`, root-owned 0555/0444, UID10000 write denied. Tree digest `dac3d2bfdef58a8799c8aa3ef47ce32ed5c06bd7d7f157b778b633447051b5d0` matched before and after. Terminal-only DeepSeek v4.1 flash/OpenRouter/high audit exited 0 with empty stderr.

Report: `/mnt/user/appdata/hermes-agent/reports/openhtpc-audit-20261010T170140Z-6cdaef7-131-final-delta.md`, copied to `docs/audits/2026-10-10-131-hermes-final-delta.md`. The reviewer found the requested final deltas structurally coherent, identified the missing VC-1 profile projection (independently fixed and tested afterward), and flagged that the old repository payload Flex binary does not represent the modified source. Canonical verification established that the `.67` installed validator binary is rebuilt, metadata-matched and contains the fix; future snapshots/artifacts must rebuild rather than reuse the stale payload. Full dispositions are in the continuity checkpoint. Hermes remains read-only and gains no release or physical authority.
