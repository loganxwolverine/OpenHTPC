# OPENHTPC 1.1 RC3 — Final officialization report

Date: 2026-08-23 (Europe/Brussels)

## Product decision

OPENHTPC Base is mature for RC3 officialization. Dev38 is the final retained
baseline. No further runtime, UI or code change is authorized before RC3
publication. The qualified archive must not be rebuilt or altered.

Formal status:

- `OPENHTPC_BASE_RC3_PHYSICALLY_QUALIFIED`
- `QUALIFIED_AND_FROZEN`
- `READY_FOR_PUBLICATION`

## Official baseline

- Version: `1.1.0-dev38`
- Build: `rc3-final-dvd-policy-refresh-corrective-dev1`
- Final candidate commit: `24bc2b46660c056e6f84ca3df723d12f69057724`
- Artifact: `OpenHTPC-1.1-RC3-Candidate-Dev38.tar.gz`
- SHA256: `a3a48f1d40b998ae5703c2f8aa3072d4a5b4ab0e5f670c46f1f3c6d45af7717f`

The final candidate commit identifies the qualified technical source. Future
publication-only metadata must not redefine or replace that candidate commit.

## Final physical qualification by Steve

- PURE → DVD detail: PASS
- CINÉMA AUTO → DVD detail: PASS
- DRIVEN, FRANÇAIS COMPLETS: PASS
- DRIVEN, subtitles OFF: PASS
- `Alerte.mkv`, FRANÇAIS COMPLETS: PASS
- DVD image and sound: PASS
- QUITTER → KDE: PASS
- Doctor READY: PASS

These results close the two dev38 corrective items and constitute the final
physical qualification of the OPENHTPC RC3 Base.

## Technical evidence retained

- Dev38 targeted tests: 9/9 PASS
- Dev38 checkout regression: 73/73 PASS
- Frozen workspace regression: 564/564 PASS
- Candidate validation: 65/65 PASS
- Extracted package manifest: PASS
- Validator installation through official `update.sh`: PASS
- Validator version/build: PASS
- Validator Doctor: `Overall: READY`
- NAS upload reread and byte-for-byte comparison: PASS

## Deliberately unchanged

Media Sources, local-media playback, DVD metadata and playback, PURE and
CINÉMA AUTO semantics, audio policy, OSD, capability truth, Performance Map,
Hardware Passport, appliance lifecycle, Doctor semantics and KDE restoration
remain the qualified dev38 behavior.

## Digital signing

No key is created. No signature or signing workflow is produced for RC3.

`RELEASE_SIGNING_DEFERRED_BY_PRODUCT_DECISION`

The SHA256 companion remains the RC3 integrity record. Historical signing
planning does not override this product decision.

## Publication boundary

The release notes and exact GitHub publication plan are prepared. No RC3 tag,
branch push, GitHub Release or asset upload has been performed by this
officialization step. Publication remains subject to Steve's explicit final
authorization.

## Verdict

`RC3_OFFICIALIZATION_READY`
