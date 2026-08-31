# OPENHTPC Autopilot deterministic policy

AI recommendation is not policy authority. The Python policy gates are
authoritative over planner, executor and reviewer output.

Gemini planner and reviewer processes run headlessly in normal approval mode
with the explicit tracked `gemini-readonly.toml` policy. That deny-by-default
allowlist permits only local repository read/search tools. Mutation, shell,
network, arbitrary MCP, and Plan Mode transition tools are denied. Gemini Plan
Mode is deliberately not used because its own interactive lifecycle is not a
deterministic headless security boundary. Prompt instructions are defense in
depth; the supplied policy is the tool-access boundary.

Autopilot accepts only strict JSON contracts and one bounded task per plan.
Risk classes are `DOCS_ONLY`, `SOFTWARE_NO_PHYSICAL`,
`SOFTWARE_PHYSICAL_GATE`, `HUMAN_APPROVAL_BEFORE_EXECUTION`, and `FORBIDDEN`.
Human gates are `NONE`, `BEFORE_EXECUTION`, or `AFTER_IMPLEMENTATION`, with a
closed reason vocabulary covering physical validation, Git publication or
history changes, security/hardware boundaries, credentials, system
configuration and other explicitly identified risk.

Push, tag, release, merge, rebase, branch deletion, destructive reset, forced
checkout, remote-ref mutation, sudo, package installation, external workspace
writes, credentials, validator deployment and NAS mutation are never automatic.
Neither an agent nor a prompt can waive these restrictions.

Every run begins clean on an expected branch and HEAD. Codex must leave HEAD
unchanged, touch only validated allowed paths, produce explicit command/return
code test evidence, and pass `git diff --check`. New diff text is scanned for
plausible credentials before review. Secrets are redacted from retained agent
output and prohibited from bounded state metadata.

Only an independent Gemini `ACCEPT`, complete deterministic checks and explicit
test evidence permit a local commit. `REJECT` preserves the workspace without
commit or reset. An after-implementation physical gate may permit an accepted
local commit, then must stop as `AWAITING_PHYSICAL_VALIDATION`; software tests
never create a physical PASS.

The Phase 12 P2 boundary remains frozen. Autopilot does not treat Core-owned
I/O, security, execution or rendering as migration defects. Changes to hardware
I/O ownership or security authority always require a pre-execution human gate.
