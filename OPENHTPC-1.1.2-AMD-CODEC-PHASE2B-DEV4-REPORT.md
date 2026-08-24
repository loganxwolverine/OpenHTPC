# OPENHTPC 1.1.2-dev4 — Canonical capability refresh consistency

Status: software candidate ready for physical consistency validation only.

## Baseline and physical Dev3 failure

- Dev3 commit: `a9e819e268a8cb4b075568cfd40f68119b46ef18`.
- Version: `1.1.2-dev4`.
- Build: `amd-codec-canonical-refresh-consistency-dev4`.

Physical Dev3 evidence proved that `openhtpc capabilities --refresh` generated
the correct canonical codec matrix while leaving stale codec mirrors in
`profile.json`. Dev3 synchronized only an installer-local refresh function;
the canonical Capability Engine wrote only `runtime/capabilities.json`.

## Bounded correction

The canonical `openhtpc-capabilities.py::refresh()` operation now:

1. runs the existing capability probes exactly once;
2. derives the legacy profile codec vocabulary from that canonical snapshot;
3. makes `media_stack.observed_capabilities.vaapi_decode` current;
4. synchronizes every existing `gpu_topology` `vaapi_decode` compatibility
   mirror from the same dictionary;
5. stages and validates both JSON documents before replacing either;
6. performs one atomic replacement of the complete profile.

MPEG-2, H.264, HEVC, HEVC Main10, VP9 and AV1 values are derived from observed
canonical statuses. No physical machine values, GPU identity or render node
are hardcoded. VP9 is true when either canonical VP9 profile is supported.

Per-capability gains/losses remain bounded in profile history. The current
refresh also reports its changes in the canonical output. An unchanged second
refresh produces no new history entry.

The installer already executes the installed canonical Capability Engine
unconditionally near completion. Consequently an existing coherent or stale
profile is refreshed even when freeworld packages are already installed and
the dependency transaction is a no-op.

Probe failure, invalid profile input or staging failure occurs before any
replacement and preserves the previous profile. The snapshot lock serializes
canonical refresh operations.

AMD runtime generation, `gpu-next`, Vulkan/RADV, `hwdec=vaapi`, render-node
selection, package remediation, MPEG-2 fallback, playback, Flex, Wayland,
DVD/MEDIA and audio are unchanged.

Physical Dev4 scope stops after version, Doctor, canonical refresh and the
read-only consistency check. No media playback is requested.
