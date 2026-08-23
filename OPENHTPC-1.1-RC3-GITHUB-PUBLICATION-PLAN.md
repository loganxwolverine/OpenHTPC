# OPENHTPC 1.1 RC3 — Exact GitHub publication plan

Date prepared: 2026-08-23 (Europe/Brussels)

## Immutable inputs

- Existing repository: `git@github.com:loganxwolverine/OpenHTPC.git`
- Publication branch: `main`
- Current audited remote `main`: `46c40d6ade649c1fe0853892b9b75a5d8622a88c`
- Existing immutable RC2 tag: `v1.1.0-rc2`
- Qualified source commit: `24bc2b46660c056e6f84ca3df723d12f69057724`
- Proposed annotated RC3 tag: `v1.1.0-rc3`
- Qualified release asset: `OpenHTPC-1.1-RC3-Candidate-Dev38.tar.gz`
- SHA256: `a3a48f1d40b998ae5703c2f8aa3072d4a5b4ab0e5f670c46f1f3c6d45af7717f`
- Release notes: `RELEASE-NOTES-OPENHTPC-1.1-RC3-FR-EN.md`

Read-only preparation confirmed that `origin/main` still matches the local RC2
integration baseline and that `v1.1.0-rc3` does not currently exist remotely.

## Required publication commit

Create one normal descendant of current `origin/main`, using the qualified
dev38 public tree without changing qualified runtime/UI/code content. Public
packaging metadata and release documentation may be added, but the archive
itself must remain outside the Git tree and must never be rebuilt.

Recommended commit subject:

```text
OPENHTPC 1.1 RC3 public baseline
```

Before commit, verify:

1. the source is exactly the qualified dev38 content;
2. no archive, user configuration, logs, credentials, private paths or private
   network addresses are tracked;
3. `MANIFEST.sha256`, candidate validation and syntax checks pass;
4. the qualified archive still has the recorded SHA256;
5. the diff contains no unassigned runtime/UI/code modification.

## Annotated tag

After the public commit is reviewed and Steve explicitly authorizes
publication, create exactly one annotated tag targeting that reviewed commit:

```bash
git tag -a v1.1.0-rc3 -m "OPENHTPC 1.1 RC3
Public release candidate derived from physically qualified dev38."
```

Verify locally before any push:

```bash
git rev-parse v1.1.0-rc3^{}
git show --no-patch --decorate v1.1.0-rc3
git ls-remote --tags origin v1.1.0-rc3 'v1.1.0-rc3^{}'
```

The last command must remain empty before first publication. Never replace or
force-update an existing tag.

## Push sequence after explicit authorization

Fetch and require a fast-forward relationship:

```bash
git fetch --prune origin
git merge-base --is-ancestor origin/main HEAD
git push origin main
git push origin refs/tags/v1.1.0-rc3
```

Do not use `--force`, `--force-with-lease`, `--tags`, `--all` or `--mirror`.
Push the branch and the single tag explicitly.

## GitHub Release and assets

Create a prerelease titled `OPENHTPC 1.1 RC3`, targeting `v1.1.0-rc3`, using
the bilingual release-notes file verbatim. Attach exactly:

- `OpenHTPC-1.1-RC3-Candidate-Dev38.tar.gz`
- `OpenHTPC-1.1-RC3-Candidate-Dev38.tar.gz.sha256`

The JSON and Markdown qualification reports may be attached as supporting
evidence if Steve explicitly approves their public publication. No `.sig`,
public key or signing asset is created for RC3.

The current environment has no `gh` executable. Therefore GitHub Release
creation and asset upload require either an explicitly authorized later step
with an available authenticated GitHub mechanism or Steve's manual GitHub UI
action. No credential should be requested, read or stored by OPENHTPC tooling.

## Post-publication verification

Verify all of the following:

1. remote `main` equals the reviewed public commit;
2. `v1.1.0-rc3^{}` equals that same commit;
3. `v1.0.0` and `v1.1.0-rc2` are unchanged;
4. the GitHub Release is marked prerelease and targets `v1.1.0-rc3`;
5. the downloaded archive hashes to
   `a3a48f1d40b998ae5703c2f8aa3072d4a5b4ab0e5f670c46f1f3c6d45af7717f`;
6. the SHA256 companion verifies successfully;
7. no signature asset is present;
8. no qualified runtime/UI/code file differs from dev38.

## Current execution boundary

- Public commit created: no
- RC3 tag created: no
- Branch pushed: no
- Tag pushed: no
- GitHub Release created: no
- Artifact uploaded to GitHub: no
- Qualified artifact modified or rebuilt: no
- Signing key/signature created: no

Publication awaits Steve's explicit final authorization.

`RC3_GITHUB_PUBLICATION_PREPARED`
