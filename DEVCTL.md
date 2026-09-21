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
| `build ...` | Export HEAD, build Flex from exported source, stage and verify artifact |
| `verify <artifact>` | Independently check archive, source commit, embedded Flex and provenance |
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

`build` exports the exact HEAD commit to a temporary staging tree. It configures
and compiles Flex from that exported source in a fresh temporary build directory,
copies the resulting executable into staging, and checks the copy's SHA256.
It generates `payload/flex/BUILD-METADATA.json` from that staged binary and
source, regenerates `MANIFEST.sha256`, creates the archive, and runs independent
artifact verification before reporting success. Only committed source is used;
working-tree changes are excluded.

The tracked `payload/flex/bin/flex-launcher` and its tracked metadata are **not**
authoritative for artifact generation. Build failure never falls back to them.
The verifier rehashes the archived binary, checks its ELF build ID and source
fingerprint, compares embedded identity fields with the report, validates the
manifest, and compares archived source file content and Git executable state
with the reported Git commit.
Build reproducibility now also depends on the CMake/compiler environment.

Staged Flex metadata uses schema 2. `binary_sha256` and `elf_build_id` describe
the staged executable. `source_commit`, `upstream_commit`, `source_revision`,
and `flex_source_fingerprint` describe the exported vendor source; the
fingerprint hashes sorted vendor-relative paths and each file's SHA256.
`artifact_build_id`, `dev_tranche`, `workstream`, and `product_version` identify
the OPENHTPC artifact and must match its report. `elf_build_id` is the ELF note,
not the artifact build ID.
