# OPENHTPC Autopilot deterministic policy

AI recommendation is not policy authority. The Python policy gates are
authoritative over planner, executor and reviewer output.

Planning authority is code/tests/artifacts, canonical project state for the
current workstream and approved next action, current architecture and
qualification documents, roadmap, then historical material. Canonical state
cannot override code truth; it prevents reconstruction of current phase intent
from history.

Antigravity planner and reviewer processes run headlessly with explicit
`--mode=plan`, native JSON-schema output, and bounded timeouts. Prompt-level
read-only instructions are reinforced by deterministic before/after workspace
fingerprints covering HEAD, status, tracked diffs, changed paths, and untracked
content. Any mutation is a safe stop and is never automatically reset.
Antigravity authentication and global settings remain outside repository and
Autopilot authority.

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

Only an independent Antigravity `ACCEPT`, complete deterministic checks and explicit
test evidence permit a local commit. `REJECT` preserves the workspace without
commit or reset. An after-implementation physical gate may permit an accepted
local commit, then must stop as `AWAITING_PHYSICAL_VALIDATION`; software tests
never create a physical PASS.

`PHYSICAL_VALIDATION_REQUIRED` does not mean
`STOP_BEFORE_SOFTWARE_IMPLEMENTATION`. A bounded software task may implement,
software-test, undergo independent review, and receive an accepted local commit
before stopping. Such a plan uses `SOFTWARE_PHYSICAL_GATE`,
`AFTER_IMPLEMENTATION`, `PHYSICAL_VALIDATION`, and `next_step_policy=STOP`.
The STOP applies after that implementation. A task that itself requires
physical manipulation, first device-I/O ownership transfer, security-authority
transfer, system configuration, a destructive operation, or another protected
boundary remains gated before execution.

The Phase 12 P2 boundary remains frozen. Autopilot does not treat Core-owned
I/O, security, execution or rendering as migration defects. Changes to hardware
I/O ownership or security authority always require a pre-execution human gate.
Architecture freeze is not feature-cutover completion.
