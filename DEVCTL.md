# OPENHTPC Development Workflow Orchestrator

`tools/openhtpc-devctl` is a **development-only** tool that automates the
mechanical OPENHTPC development cycle.  It is **not** an OPENHTPC product
component and must never appear in `payload/`, `managed-files.txt`, or
`PRODUCT_FILES`.

---

## Normal Workflow

```
# 1. Inspect repo state
tools/openhtpc-devctl status

# 2. Run focused tests
tools/openhtpc-devctl test media-foundation

# 3. Build artifact from HEAD commit
tools/openhtpc-devctl build \
    --name OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3 \
    --build-id media-probe-dev3 \
    --dev-tranche DEV3 \
    --workstream MEDIA_FOUNDATION \
    --tests "22/22 PASS"

# 4. Verify artifact integrity
tools/openhtpc-devctl verify artifacts/OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3.tar.gz

# 5. Ship to physical target
tools/openhtpc-devctl ship artifacts/OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3.tar.gz

# 6. Snapshot & stop target before installation
tools/openhtpc-devctl target-prepare

# 7. Install on target via update.sh
tools/openhtpc-devctl target-install artifacts/OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3.tar.gz

# 8. Post-install read-only checks
tools/openhtpc-devctl target-check

# ── HUMAN VALIDATION GATE ─────────────────────────────────────────────
# Steve physically validates image / audio / refresh / Flex return.
# The tool prints instructions; it never auto-passes.
tools/openhtpc-devctl human-gate

# (after Steve has validated physically)

# 9. Collect validation bundle
tools/openhtpc-devctl collect

# 10. Record physical qualification
tools/openhtpc-devctl qualification \
    --artifact OpenHTPC-1.2.0-RC8-Media-Foundation-Dev3 \
    --image PASS \
    --audio PASS \
    --refresh PASS \
    --flex-return PASS
```

---

## Commands

| Command | Description |
|---------|-------------|
| `status` | Branch, HEAD, clean/dirty, protected stash, version |
| `test <profile>` | Run named test profile (media-db, media-probe, media-foundation) |
| `build ...` | Build artifact from exact HEAD commit via `git archive` |
| `verify <artifact>` | Verify archive, SHA256 sidecar, report, commit in repo |
| `ship <artifact>` | SCP artifact + SHA + report to target; verify remote SHA |
| `target-prepare` | Snapshot target dirs, then stop OPENHTPC cleanly |
| `target-install <artifact>` | Remote SHA check → extract → run update.sh |
| `target-check` | Read-only post-install checks (version, DB, probe, optional probe) |
| `collect` | Collect machine-readable validation bundle from target |
| `human-gate` | Print physical validation instructions for Steve |
| `qualification ...` | Record Steve's physical PASS/FAIL, write `.validation.json` |

---

## Safety

- No `shell=True` anywhere.
- All subprocess calls use explicit argument arrays.
- Bounded SSH timeouts (`ConnectTimeout=15`).
- Ship and target operations have `--dry-run` mode.
- No `rm -rf`, no `git reset --hard`, no `git push`, no `git tag`.
- Protected stash is never touched.
- Qualification requires explicit `--image`, `--audio`, `--refresh`, `--flex-return` values.
- No automatic physical PASS — Steve's observation is authoritative.
- Default target: `steve@192.168.1.11` / `/home/steve/dev/1.2/`

---

## Archive reproducibility

`build` uses `git archive --format=tar.gz` from the exact HEAD commit.
Only committed files are included — untracked/working-tree modifications are
excluded automatically.

The same commit on the same git installation produces the same archive bytes.
