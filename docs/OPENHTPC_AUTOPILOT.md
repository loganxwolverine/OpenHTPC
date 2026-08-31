# OPENHTPC Autopilot

OPENHTPC Autopilot is a local, bounded orchestration layer. Gemini CLI plans
and independently reviews in normal headless mode under the tracked,
deny-by-default `tools/autopilot/policies/gemini-readonly.toml` policy. Codex CLI executes one
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
adds short read-only Gemini and Codex smoke tests. `plan` invokes only Gemini,
validates and saves one plan, and never invokes Codex. `run` performs one safe
step. `--until-gate` replans after each accepted local commit, has a hard limit
of five, and stops at every failure, rejection, gate, dirty tree or no-work
decision. Press Ctrl-C to stop; subprocess timeouts also fail closed.

The installed default models are used unless `OPENHTPC_GEMINI_MODEL` or
`OPENHTPC_CODEX_MODEL` is set. Planner, reviewer and executor timeouts may be
set through `OPENHTPC_AUTOPILOT_PLANNER_TIMEOUT`,
`OPENHTPC_AUTOPILOT_REVIEWER_TIMEOUT`, and
`OPENHTPC_AUTOPILOT_EXECUTOR_TIMEOUT`. Online smoke-test timeouts use
`OPENHTPC_AUTOPILOT_GEMINI_DOCTOR_TIMEOUT` and
`OPENHTPC_AUTOPILOT_CODEX_DOCTOR_TIMEOUT`. Authentication remains entirely owned
by the installed CLIs; Autopilot never reads or changes their credential
stores.

Gemini is invoked with `--approval-mode default` and an explicit absolute
`--policy` path. The policy allows only bounded local read/search tools and
denies all other tools, including mutation, shell, network, MCP, and Plan Mode
transition tools. Autopilot intentionally does not use Gemini Plan Mode: its
interactive plan lifecycle is not the security boundary required for a
headless planner/reviewer. The deterministic policy, not prompt compliance,
enforces read-only operation. The online Gemini doctor uses this same command
architecture.

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
