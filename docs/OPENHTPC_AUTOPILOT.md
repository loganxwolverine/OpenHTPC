# OPENHTPC Autopilot

OPENHTPC Autopilot is a local, bounded orchestration layer. Google Antigravity
CLI plans and independently reviews in headless `--mode=plan`. Codex CLI executes one
validated plan in a workspace-write sandbox without committing. The Python
orchestrator validates policy, Git state, paths, schemas, tests and secrets,
and is the only component allowed to make an accepted local commit. It never
pushes.

## Commands

```text
./tools/openhtpc-autopilot doctor
./tools/openhtpc-autopilot doctor --online
./tools/openhtpc-autopilot status
./tools/openhtpc-autopilot plan
./tools/openhtpc-autopilot run
./tools/openhtpc-autopilot run --until-gate --max-steps 3
```

`doctor` checks local prerequisites without agent calls. `doctor --online`
adds short read-only Antigravity and Codex smoke tests. `plan` invokes only Antigravity,
validates and saves one plan, and never invokes Codex. `run` performs one safe
step. `--until-gate` replans after each accepted local commit, has a hard limit
of five, and stops at every failure, rejection, gate, dirty tree or no-work
decision. Press Ctrl-C to stop; subprocess timeouts also fail closed.

The Codex online doctor is a minimal read-only text heartbeat requiring the
exact output `CODEX_OK`; it does not use a response schema. The real Codex
executor remains a separate workspace-write path with its strict structured
executor-report schema, test evidence, path checks, and HEAD guard.

The installed default models are used unless `OPENHTPC_AGY_MODEL` or
`OPENHTPC_CODEX_MODEL` is set. Planner, reviewer and executor timeouts may be
set through `OPENHTPC_AUTOPILOT_PLANNER_TIMEOUT`,
`OPENHTPC_AUTOPILOT_REVIEWER_TIMEOUT`, and
`OPENHTPC_AUTOPILOT_EXECUTOR_TIMEOUT`. Antigravity reasoning effort may be
set to `low`, `medium`, or `high` with `OPENHTPC_AGY_EFFORT`. Online smoke-test timeouts use
`OPENHTPC_AUTOPILOT_ANTIGRAVITY_DOCTOR_TIMEOUT` and
`OPENHTPC_AUTOPILOT_CODEX_DOCTOR_TIMEOUT`. Authentication remains entirely owned
by the installed CLIs; Autopilot never reads or changes their credential
stores.

Antigravity is invoked non-interactively with explicit `--mode=plan`, JSON
output, bounded print/subprocess timeouts, and native `--json-schema` for plans
and reviews. Python independently validates every `structured_output`; native
schema enforcement never replaces deterministic policy. Before and after each
planner/reviewer call, Autopilot compares HEAD, porcelain status, changed paths,
tracked diffs, and untracked content. Any mutation stops safely without reset.
Antigravity authentication, including the locally authenticated Google AI Pro
session, remains external: Autopilot neither reads nor modifies credentials or
global settings. Runtime artifacts use `antigravity-planner.*` and
`antigravity-reviewer.*`; older ignored runs need no migration.

## Runtime and inspection

Ignored runtime data lives under `.openhtpc-autopilot/`. `state.json` contains
only bounded status metadata. Each `runs/<run-id>/` records redacted context,
plan, policy, executor report, reviewer result, stderr, diff and summaries.
No hidden reasoning is requested or stored.

On rejection, failure, unexpected path, HEAD mutation or secret detection,
Autopilot preserves the workspace and stops. Inspect the run directory and
`git status`; resolve the issue manually. It never resets or cleans changes.
After manual resolution, begin again from a clean authorized HEAD. A saved
plan is evidence, not permission to bypass a fresh preflight.

## Physical validation

For `SOFTWARE_PHYSICAL_GATE`, implementation, software tests, independent
review and a local commit may complete. Autopilot then stops at
`AWAITING_PHYSICAL_VALIDATION`. It does not deploy, operate validators, invent
results or start a subsequent phase. A human records physical qualification
through the normal OPENHTPC process.

The stable rules are defined independently in
`docs/OPENHTPC_AUTOPILOT_POLICY.md`. AI recommendation is not policy authority.
