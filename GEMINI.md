@./AGENTS.md

Before OPENHTPC planning or review, use the same canonical memory as the other
actors: read `docs/OPENHTPC_CONTINUITY.md`, `docs/OPENHTPC_ACTORS.md`,
`OPENHTPC-ROADMAP.md`, and the latest checkpoint referenced by continuity.
Treat `OPENHTPC_CURRENT_STATE.json` as historical only when `AGENTS.md` classifies
it STALE against the checked-out HEAD/VERSION.

When OPENHTPC Autopilot invokes Antigravity CLI as planner or reviewer, remain
strictly read-only. Never edit repository files or execute mutation commands. Reason
from current repository and Git evidence, propose exactly one bounded task,
and return only the requested structured response. Distinguish software test evidence from
physical qualification. Never authorize push, tag, release, merge, rebase,
destructive Git, or credential operations. Do not assume moving I/O, security,
rendering, or playback execution out of Core is desirable.
