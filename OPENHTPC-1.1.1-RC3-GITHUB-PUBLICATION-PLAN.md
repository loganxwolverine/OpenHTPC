# OPENHTPC 1.1.1 RC3 — GitHub publication plan

This is a preparation document only. It does not authorize automatic
publication, tagging or force-pushing.

## Audited Git state before publication

- Public remote: `git@github.com:loganxwolverine/OpenHTPC.git`
- Current local `main`: `62992ac15e352b70a61f2fb92a4271c7ccf261fa`
- Current local `origin/main`: `62992ac15e352b70a61f2fb92a4271c7ccf261fa`
- Public parent tag `v1.1.0-rc3`: `62992ac15e352b70a61f2fb92a4271c7ccf261fa`
- Maintenance first commit: `e05d6cf1d96a138b6b987dd1256b995b5ac8625a`
- Corrective commit: `3db12a097be88fd15b2d5cb4a3850151c50609e4`
- Physically qualified technical commit: `3080b46b0f7537222358c231a994ac838cfb691e`
- Plugin Framework P1 remains separate at
  `3b00a907e8a6933867b9dccc5498b06b6d74ee88`.

The maintenance branch is a linear three-commit descendant of `v1.1.0-rc3`.
No history rewrite, force-push, tag movement or Plugin Framework merge is
permitted. Existing tags `v1.0.0`, `v1.1.0-rc2` and `v1.1.0-rc3` must remain
unchanged.

## Qualified artifact

- `OpenHTPC-1.1.1-RC3-Audio-P0.tar.gz`
- `OpenHTPC-1.1.1-RC3-Audio-P0.tar.gz.sha256`
- SHA256:
  `6a1a8fe0e80f11c7f97717f0cd8d17c02eb841116633e3dad289d07f17e063a8`

Do not rebuild or rename the artifact. These are the only two primary binary
release assets.

## Proposed public release

- Tag: `v1.1.1-rc3`
- Title: `OPENHTPC 1.1.1 RC3 — Audio P0`
- GitHub pre-release: **Yes**
- Release notes source: `RELEASE-NOTES-OPENHTPC-1.1.1-RC3-FR-EN.md`
- Target: the final documentation commit descending from qualified technical
  commit `3080b46`.

Tagging the documentation commit is acceptable because the post-qualification
diff is documentation-only. The release assets remain the already-qualified
archive and checksum produced from `3080b46`.

## Required final audit before any push

1. Confirm the working tree is clean.
2. Confirm `main`, `origin/main` and `v1.1.0-rc3` still resolve as recorded.
3. Confirm `git merge-base v1.1.0-rc3 <documentation-commit>` is `62992ac…`.
4. Confirm `git diff --name-status 3080b46..<documentation-commit>` lists only
   the four officialization Markdown documents.
5. Re-run `sha256sum -c` against the existing artifact; do not rebuild it.
6. Review the bilingual release notes and codec qualification wording.

## Manual publication sequence for Steve

Use the repository's normal authenticated Git/GitHub workflow. Do not expose or
replace credentials, and do not use force options.

1. Fast-forward public `main` to the reviewed documentation commit.
2. Push `main` normally.
3. Create annotated tag `v1.1.1-rc3` at that same commit.
4. Push only the new tag; do not use `--tags`.
5. Create GitHub release `OPENHTPC 1.1.1 RC3 — Audio P0` as a pre-release.
6. Paste the bilingual release notes.
7. Attach only:
   - `OpenHTPC-1.1.1-RC3-Audio-P0.tar.gz`
   - `OpenHTPC-1.1.1-RC3-Audio-P0.tar.gz.sha256`
8. Verify the published asset checksum after download.

If an already-authenticated GitHub mechanism is not available, stop after the
local audit and perform these steps manually. Do not create an alternative
authentication path.
