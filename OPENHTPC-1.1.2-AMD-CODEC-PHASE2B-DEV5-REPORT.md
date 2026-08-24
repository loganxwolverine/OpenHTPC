# OPENHTPC 1.1.2-dev5 — Release metadata consistency

Status: ready for physical metadata validation; no playback required.

## Root cause and correction

Dev4 advanced the top-level `VERSION` and `payload/version.json`, but its build
workflow did not propagate that version into `payload/VERSION` or the
installer's `OPENHTPC_VERSION`. The installer faithfully copied the stale
payload metadata, so `openhtpc version` reported Dev2 while Doctor consumed the
current JSON metadata.

The root `VERSION` is now the single build-time version source. The release
metadata tool propagates it to `payload/VERSION`, `payload/version.json` and
the installer constant together with the intended build ID. The Dev5 builder
refuses to start unless all four versions and the build ID agree. It validates
the extracted archive again before emitting SHA256/report files.

An installed-layout simulation validates the files copied by the installer.
The installer log uses the same propagated constant and therefore reports
`1.1.2-dev5`.

Dev4 canonical capability consistency is physically validated and unchanged.
No AMD, capability, codec, runtime, package, MPEG-2 fallback, playback, Flex,
Wayland, audio, DVD or MEDIA behavior changes in Dev5.
