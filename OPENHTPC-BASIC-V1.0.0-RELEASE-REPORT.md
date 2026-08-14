# OPENHTPC Basic V1.0.0 — Gold Master Release Report

## Release identity and provenance

- Public product: OPENHTPC Basic V1.0.0
- Public version: `1.0.0`
- Build ID: `basic-v1-gold`
- Build date: 2026-08-14
- Authoritative source: `/home/steve/OpenHTPC`
- Qualified functional provenance: OPENHTPC Basic V1 RC27, plus the isolated
  RC28 final-version uninstall compatibility delta
- Qualified RC27 checkpoint:
  `/home/steve/OPENHTPC-BASIC-V1-RC27-QUALIFIED-GOLD-SOURCE-20260814T140000+0200.tar.gz`
  (`8caf523ae13a5a62580310cb369f4b0d0faeaf5006f12b29cba0962519581974`)
- Qualified RC28 checkpoint:
  `/home/steve/OPENHTPC-BASIC-V1-RC28-QUALIFIED-COMPATIBILITY-SOURCE-20260814T140109+0200.tar.gz`
  (`69c2c64a9c41cb5f89fc643b4cc894ab810476245eaa52088216ffada042f105`)
- Gold source checkpoint:
  `/home/steve/OPENHTPC-BASIC-V1.0.0-GOLD-MASTER-SOURCE-20260814T140502+0200.tar.gz`
  (`d8859d3216f0b4ae5e4dc06cc65aa3de8adacbd6e3c21aa842a7f1c3a9dc2e05`)
- Git: this source tree is not Git-authoritative; no commit or `v1.0.0` tag was
  created.

## Versioning and diff audit

`4.0.0-basic-v1-rc27` was the former composite public RC identity, not an
independent protocol or schema version. Runtime JSON schemas remain independently
versioned. The final public VERSION is therefore exact `1.0.0`; no internal
`4.0.0` product identity was retained.

RC27 to RC28 changed only `uninstall.sh`, RC identity metadata/package naming,
and the new uninstall regression test. RC28 to V1.0.0 changed only
`VERSION`, `version.json`, the version constant in `install-openhtpc-fedora.sh`,
`build-basic-release.py`, Flex build metadata, `README-BASIC.md`, and version
assertions in two tests. The RC28 `uninstall.sh` is byte-identical in Gold.
The functional diff audit found no MEDIA, Flex binary, MPV/runtime, DVD, Doctor,
optical, support-bundle, POWER, Plasma lifecycle, or installer dependency-logic
change.

## Final version uninstall compatibility

RC27 guarded product-directory deletion with
`^4\.0\.0-basic-v1-rc[0-9]+$`. Exact `1.0.0` could not match, so a final install
would have retained its installed product directory. RC28 changed only that
guard to `^(4\.0\.0-basic-v1-rc[0-9]+|1\.0\.0)$`.

- RC fixture `4.0.0-basic-v1-rc28`: PASS; recognized and removed
- Final fixture `1.0.0`: PASS; recognized and removed
- Rejected fixtures `1.0`, `1.0.1`, `2.0.0`, `4.0.0`,
  `4.0.0-basic-v2-rc1`, `random`, and missing VERSION: 7/7 PASS; retained
- Path safety: PASS; the fixed `${HOME}/.local/lib/openhtpc` scope ignores an
  external install-path override, an isolated symlink fixture removed only the
  link, and outside/parent sentinels were preserved
- Actual extracted V1.0.0 `uninstall.sh` fixture: PASS; the final installed
  product directory was removed while media and unrelated paths remained
- Shell syntax (`bash -n`): PASS

No other uninstall semantics changed. Default uninstall preserves
`user-config.json`, Hardware Passport/profile, generated runtime/configuration,
logs/runtime state, and plugin state outside the product directory. Explicit
`--purge-config` retains its existing policy of removing OPENHTPC config, cache,
and state. Configured media sources and their files are never deleted.

## Qualification evidence

- RC28 full regression: 564 passed / 0 failed / 0 skipped / 564 total
- Gold targeted release gate: 144 passed / 0 failed / 0 skipped / 144 total
- Gold full regression: 564 passed / 0 failed / 0 skipped / 564 total
- Single Flex ownership: PASS; maximum simultaneous authoritative instances 1
- MEDIA pipeline (token → current manifest → dispatcher → canonical absolute
  path → MPV argv): PASS
- Doctor never-run fixture: PASS; `NOT_INITIALIZED`, `INACTIVE`, `NOT_TESTED`,
  and `FIRST_RUN` remain truthful neutral states; Overall READY
- Doctor post-Quit fixture: PASS; Desktop restore PASS,
  `USER_QUIT_TO_DESKTOP`, Overall READY; deliberate restore failure still blocks
- Optional TMDb `NOT_CONFIGURED` and plugins `NOT_INSTALLED`: non-blocking PASS
- DVD dispatcher/optical regression: PASS
- support-bundle privacy: PASS
- Quit-to-KDE and power command-path regression: PASS
- Installer structural/syntax and clean-HOME tests: PASS
- Neutral-path extraction and relocatability: PASS
- Entry permissions: `install.sh`, `update.sh`, and `uninstall.sh` executable

Final `openhtpc version` output:

```text
1.0.0
```

Representative clean first-run Doctor identity/result:

```text
Version                   1.0.0
Build                     basic-v1-gold
Build date                2026-08-14
Canonical optical state   NOT_INITIALIZED
Desktop restore           NOT_TESTED
Last OPENHTPC exit        FIRST_RUN
Overall: READY
```

## Artifact and hygiene evidence

- Archive: `OpenHTPC-Basic-V1.0.0.tar.gz`
- Size: 6,772,348 bytes
- SHA256: `141e33f34329d75ffb368b98ca9d9bb13b8f06e7d468f8723493c51bc81572d6`
- `sha256sum -c`: PASS
- Archive members: 61; one correct top-level directory; no duplicate,
  traversal, link, absolute-path, or nested-archive entry
- Extraction: PASS
- Secret scan: PASS
- Privacy/media/log/cache scan: PASS
- Builder path leakage scan: PASS
- RC27/release-candidate identity leakage scan: PASS
- Copyrighted qualification media: absent
- Release notes: `OPENHTPC-BASIC-V1.0.0-RELEASE-NOTES.md`

## Delivery

- Local immutable Gold artifact set:
  `/home/steve/releases/OpenHTPC-Basic-V1.0.0`
- NAS target: `smb://192.168.1.10/Tools/openhtpc/`
- NAS delivery and post-copy byte verification: PASS; all four expected files
  were retrieved and compared byte-for-byte, and the retrieved archive passed
  `sha256sum -c`

## Non-blocking roadmap

Future work may consider MEDIA typography polish, monitoring an occasional
focus/pointer UX observation if reproducible, automatic French/TrueFrench audio
selection, forced-subtitle policy, advanced cinematic/HDR processing, and the
optional plugin ecosystem. None is part of this frozen Gold Master.

## Verdict

OPENHTPC_BASIC_V1_0_0_GOLD_MASTER_READY
