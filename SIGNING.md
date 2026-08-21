# OPENHTPC official release signatures

Official OPENHTPC releases may be signed by Steve Dehanne with a dedicated
Ed25519 OpenSSH signing key and the namespace `openhtpc-release`.

The official public key, once created and explicitly approved for publication,
will be distributed as `keys/openhtpc-release-steve-dehanne.pub`. No private key
is stored in this project, release archives, support bundles, the Validator or
the OPENHTPC NAS publication directory.

An official release can provide three related files:

- `OpenHTPC-<version>.tar.gz`: release archive;
- `OpenHTPC-<version>.tar.gz.sha256`: SHA256 integrity record;
- `OpenHTPC-<version>.tar.gz.sig`: OpenSSH Ed25519 signature.

SHA256 detects any binary change. The signature authenticates that the archive
was signed by the holder of the official OPENHTPC release-signing key. It is
not DRM and does not restrict execution, modification, forks or redistribution
permitted by Apache-2.0.

To verify a future signed release:

```bash
tools/verify-release.sh \
  OpenHTPC-<version>.tar.gz \
  OpenHTPC-<version>.tar.gz.sha256 \
  OpenHTPC-<version>.tar.gz.sig \
  keys/openhtpc-release-steve-dehanne.pub
```

Existing tags `v1.0.0` and `v1.1.0-rc2` are historical and must not be replaced
to add a retroactive signature. Signing a future tag or release is an explicit
release act.
