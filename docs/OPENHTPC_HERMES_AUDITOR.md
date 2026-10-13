# OPENHTPC Hermes / DeepSeek audit and engineering lanes

## Role

Hermes Agent with DeepSeek through OpenRouter has two distinct OPENHTPC roles:

1. external contradictory reviewer in the technically read-only audit lane;
2. second operational engineer in a dedicated writable clone with no authority
   over the canonical repository.

Its findings and changes remain evidence for review, not project authority.

Authority remains: code/tests/artifacts first, then verified current project state and qualification documents. AGY/Autopilot planning, Codex execution, CodeGraph mapping, software gates and Steve's physical qualification remain separate authorities.

## Verified service endpoint — 2026-10-11
- Active host: openhtpc-control / 192.168.1.79, Fedora 44.
- Container hermes-agent, exact source image preserved; Hermes Agent 0.21.6, upstream 818c13be.
- Data: /home/steve/.local/share/hermes-agent -> /opt/data.
- Restart unless-stopped; Docker enabled at boot.
- Operator CLI: hermes, invoking /opt/hermes/hermes as UID/GID10000.
- Model deepseek/deepseek-v4.1-flash, openrouter, reasoning high: migrated-host real invocation PASS.
- Port 8642 retained on 192.168.1.79; not an approved operator control interface.
- Source Unraid .10 stopped, restart no, no autostart; image/data kept as rollback backup.
- Credentials remain private; never print complete keys.

The dedicated operator SSH identity stays outside Hermes. The preexisting Hermes HD DVD identity for .67 is preserved in the normal gateway for its separately authorized missions, and masked in OPENHTPC audit invocations. Audit authority is unchanged.
Full proof: [migration checkpoint](continuity/2026-10-11-hermes-migration-79.md).

## Operational engineering contract

The engineering lane is additive and does not modify the audit wrapper or the
persistent gateway. `openhtpc-hermes-engineer` creates a standalone clone under
`~/.local/state/openhtpc-hermes-engineering/tasks/`, reproduces the current tracked
diff and safe non-ignored untracked files, freezes that exact dirty snapshot in a
local baseline commit, removes every Git remote, and writes
an `openhtpc-hermes-handoff-v1` manifest. Secret-like untracked paths fail
closed instead of being copied.

The one-shot engineering container:

- runs as the invoking host UID/GID;
- mounts only the task clone and its dedicated HOME read/write;
- mounts the canonical `.agents/skills/` directory read-only at the same project
  path, so current and future project skills are shared rather than duplicated;
- mounts the root-owned CodeGraph binary read-only;
- does not mount the canonical repository, Docker socket, host SSH directory,
  runtime configuration or deployment credentials;
- drops all Linux capabilities and enables `no-new-privileges`;
- uses a local derived image containing pytest, Ninja, Meson, SDL2/SDL2_image/
  SDL2_ttf and inih development files;
- trusts the task checkout; `.hermes/skills/` resolves into the shared read-only
  `.agents/skills/` mount;
- registers a task-local CodeGraph MCP indexed from `/workspace` with telemetry
  disabled and graph-only mode.

Before the run, a network-disabled helper that sees only the active Hermes
`.env` copies only `OPENROUTER_API_KEY` into a task-local 0600 env file, then
reassigns that file to the invoking UID/GID. The engineering container never
receives the other Hermes/provider/platform credentials.

Hermes may edit, test, compile and make local commits in that clone. Push,
canonical merge/rebase/reset, deployment, release, physical operations and any
protected-stash operation remain forbidden without a separate explicit mandate.

Commands on `.79`:

~~~sh
openhtpc-hermes-engineer build
openhtpc-hermes-engineer prepare TASK 'Objective and bounded scope'
openhtpc-hermes-engineer run TASK 'Read the handoff, perform the task, test, report.'
openhtpc-hermes-engineer status TASK
openhtpc-hermes-engineer export TASK
~~~

`export` produces a tracked binary patch relative to the isolated baseline (not
relative to the dirty canonical HEAD), the exact Git status and a NUL-safe
untracked-path manifest. Codex or Steve reviews these artifacts before any
canonical application. No automatic import path exists.

## Read-only audit contract

Every initial audit uses a new identifiable snapshot of the current canonical worktree. The snapshot must record the verified branch, HEAD, `git status --short`, protected stash names, and a diff of local changes. `.git` is excluded so the snapshot cannot become Git authority.

The snapshot in the active .79 data volume is owned by root and exposed 0555 for directories / 0444 for files. Hermes runs as UID 10000. A write-attempt test must fail before an audit is accepted as isolated.

One-shot `-z` auto-bypasses approval prompts and is therefore NOT a safety boundary. Initial audits explicitly restrict Hermes to the `terminal` toolset and rely on OS permissions plus container isolation. No Docker socket, Fedora filesystem, OPENHTPC runtime path, SSH private key, deployment credential, or canonical repository is mounted into Hermes. Since 2026-10-13 the canonical repository is nevertheless reachable from the *gateway* through a separate read-only forced-command channel (documented below): nothing is mounted and no write, Git or deployment authority is granted, but the sentence above must no longer be read as "Hermes has no access to the canonical repository".

Reports are captured outside the read-only snapshot under `/opt/data/reports/` (host: /home/steve/.local/share/hermes-agent/reports/). A report must separate FACT / HYPOTHESIS / OPEN QUESTION and cite file:line evidence.

## Read-only canonical channel — 2026-10-13

The **gateway** (not the audit one-shot) holds a dedicated read-only channel to the canonical
repository on `.79`, authorized by Steve on 2026-10-13. It exists so that verification and
base-pulling measure the **real** state instead of a possibly stale audit copy — the failure mode
it was created to remove.

- Identity: dedicated key `~/.ssh/hermes_readonly_ed25519`, alias `canonical` -> `steve@192.168.1.79`,
  forced command `/usr/local/bin/openhtpc-readonly.sh` with
  `restrict,no-port-forwarding,no-agent-forwarding,no-pty,no-user-rc`.
- Operations, exact and exhaustive: `status`, `digest`, `export`, `bundle`, `artifacts` — all
  read to stdout and write nothing anywhere — plus `put <continuity|audits> <name>.md`, which
  creates a **new** `.md` file in `docs/continuity/` or `docs/audits/` only; it refuses to
  overwrite an existing file and refuses any other path or extension.
- No Git authority: no `commit`, `push`, `fetch` or `merge`, and no mutable `.git`. Git runs with
  `--no-optional-locks`; a read was verified to leave the index untouched (an ordinary
  `git status` does rewrite it, which is why the flag is mandatory).
- Refusals reproduced: `push`, `fetch`, `commit` and argument injection (`bundle --all`,
  `artifacts;id`) are rejected — the whitelist accepts no arguments.
- Exercised against the canonical repository on 2026-10-13: `bundle` produced a complete-history
  bundle of 51 references (`git bundle verify`: "records a complete history", stashes included);
  `artifacts` streamed the 1.3.1 packages, whose SHA-256 for
  `OpenHTPC-1.3.1-Patina-PalScope.tar.gz` matched the build report independently
  (`80edb1552f664f28db83e4a741d80cbe75f873ec0c6eed94ab2ba83ee77c1481`).
- Authority: this extends Hermes **reading** only. The responsibility matrix in
  `OPENHTPC_ACTORS.md` is unchanged for writing, Git, deployment and product authority.
  Revocation is a single line: remove the `authorized_keys` entry on `.79`.

## Invocation pattern
On .79, after preparing an immutable snapshot:
~~~sh
openhtpc-hermes-audit SNAPSHOT_NAME 'Bounded read-only audit prompt, file:line evidence.'
~~~
This launches a separate one-shot container, not another gateway: UID/GID10000, terminal-only, explicit DeepSeek/OpenRouter/high, all capabilities dropped, no-new-privileges, read-only /opt/data/audits, dedicated clean HOME and masked SSH locations. No canonical repository, Docker socket or operator keys are mounted. SELinux shared labels (:z) permit the gateway and helper to use the data volume.

Capture stdout privately outside the snapshot; verify hashes before and after each real audit. Historical Unraid report paths below retain provenance; each /mnt/user/appdata/hermes-agent/reports/... file is now also preserved under /home/steve/.local/share/hermes-agent/reports/....

The gateway CLI is available via hermes, hermes --version, hermes gateway status. Use the bounded wrapper for OPENHTPC audits so the gateway's existing HD DVD SSH identity is not exposed to the reviewer.

On `.79`, `steve` is already a member of the `docker` group. Since 2026-10-11,
the two installed launchers automatically use `sg docker` when the calling
session has not yet inherited that supplementary group. This removes the need
for a manual `sudo` command without adding a `sudoers` rule. It does not widen
Hermes authority or replace the read-only audit wrapper.

## First mission

Map the production lifecycle:

media selection -> playback policy/dispatcher -> MPV launch -> real MPV termination -> exact tracked child completion -> Flex restoration.

Then identify code paths that could leave KWin/Wayland alive while Flex is absent or hidden, producing a black screen with a mouse cursor. Require file/line evidence, distinguish facts from hypotheses, and make no modifications.

The first report must be compared with the project's existing diagnoses before Hermes receives any workspace-write development task.

## CodeGraph

The audit lane retains snapshot-local one-shot CodeGraph only. The engineering
lane registers CodeGraph as an MCP in its dedicated HOME and indexes only the
isolated clone. Neither lane connects to the canonical Codex index or grants
write/control access to the canonical Fedora repository.

The controlled handoff `handoff-validation-r2-20261011` proved the engineering
connection: CodeGraph 0.20.1 indexed 232 files and returned seven import edges for
`payload/openhtpc-plugin-registry.py`. The same run read all six current project
skills and produced 24 PASS / 1 SKIP on the focused registry tests. Full provenance
and limitations are in
`docs/continuity/2026-10-11-codex-hermes-operational-handoff.md`.

A supplemental run exercised the essential graph surface on
`resolve_dependencies`: callers, callees, bidirectional call graph, impact/blast
radius, related tests and generic traversal. It also demonstrated why graph output
must be challenged: 21 cross-file callees were false positives from a same-name
nested `resolve`, and dynamic `importlib` loading hid real test relationships.
Hermes reported those limitations instead of promoting them to facts.

Future project skill names reserved by the operator are
`openhtpc-gpu-qualification`, `openhtpc-magnificence` and
`openhtpc-release-validation`. They are currently absent and must not be invented;
when deliberately added below `.agents/skills/`, the shared mount exposes them to
Hermes automatically.

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

## Promotion decision for Hermes

Steve explicitly authorized the second-engineer role on 2026-10-11. Promotion
is limited to the isolated engineering clone described above. The immutable
audit lane remains read-only, and the promotion grants no deployment, push,
merge, publication, physical-operation or canonical-stash authority.

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

### IT13 Max Magnificence assessment — 2026-10-11

Snapshot `openhtpc-it13-magnificence-20261011T114028Z-9754029` contains six crafted files only, not the repository. It records the verified branch/HEAD/VERSION/dirty digest and the explicitly authorized technical export. Before and after the audit, all six SHA-256 values matched; `.git`, canonical repository, Docker socket, SSH material, media and secrets were absent; the root-owned 0555/0444 project rejected an UID10000 write canary.

The `.79` wrapper launched a separate terminal-only container, not another gateway, with DeepSeek v4.1 flash through OpenRouter at high reasoning. Exit 0. The reviewer had no control access to `.59`. Report and operator dispositions are in `docs/audits/2026-10-11-it13-magnificence-hermes.md`; the checkpoint is `docs/continuity/2026-10-11-it13-magnificence-assessment.md`. Useful findings were retained, false positives were rejected from source, and no profile or physical qualification was promoted.

## Magnificence GPU matrix review — 2026-10-11

Snapshot `openhtpc-magnificence-matrix-20261011T162911Z`, curated and without
`.git`. The generated report is preserved at
`docs/audits/2026-10-11-magnificence-gpu-matrix-hermes.md`, SHA-256
`10c53e526ce15c09d545e461c964ea015971bde3f2d875f517bb82bd9db44e84`.
Hermes corroborated the eight exact identity/class/recipe rows, downgraded the
RX 580 row and global family policy to partial corroboration, and exposed C1–C7
as bounded findings requiring canonical verification. No preset, deployment or
physical qualification was changed by the review.
