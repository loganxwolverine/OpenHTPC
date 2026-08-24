# OPENHTPC 1.1.2 — AMD Codec Phase 2B Dev3 forensic

## Baseline and physical evidence

- Dev2 commit: `c06311aa1fde5eed3ded48f0296163e5c74d40d9`.
- The user-approved Fedora/RPM Fusion transaction restored H.264, HEVC and HEVC Main10 VA-API profiles, native FFmpeg H.264/HEVC decoders, and MPV H.264/HEVC VA-API exposure.
- RADV/Vulkan and Doctor READY remained operational. Media playback is not yet physically qualified.
- The same post-transaction `radeonsi` freeworld driver no longer exposes MPEG-2 VLD; OPENHTPC correctly observes `mpeg2=false`.

## MPEG-2 root cause

Mesa made MPEG-1/2 decoding an explicit `video-codecs` build choice named `mpeg12dec`. The Fedora 44 RPM Fusion `mesa-freeworld` spec enables:

`h264dec,h264enc,h265dec,h265enc,vc1dec,av1dec,av1enc,vp9dec`

It omits `mpeg12dec`. Mesa consequently disables the MPEG-2 Main decode profile in that build. This matches the physical before/after `vainfo` evidence exactly; it is not an OPENHTPC parser defect or a Vega hardware limitation.

Authoritative references:

- RPM Fusion spec: <https://github.com/rpmfusion/mesa-freeworld/blob/master/mesa-freeworld.spec>
- Mesa `mpeg12dec` option: <https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/f4959c16c82cec630b68a43b5d6ea06c1748c606>
- Mesa profile gating: <https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/55bab8998225f8b423678297d61789391adf1bd0>

The Fedora and freeworld `radeonsi_drv_video.so` files can coexist in separate directories. libva selects one driver search path for a `VADisplay`; it does not merge codec profiles from both drivers. `LIBVA_DRIVERS_PATH` permits read-only, per-process comparison, but using it during playback would introduce a new codec-dependent runtime routing policy.

Reference: <https://github.com/intel/libva/blob/master/va/va.c>

## Superset and architecture gate

No supported Fedora 44/RPM Fusion package configuration has been demonstrated that exposes MPEG-2, H.264, HEVC, HEVC Main10 and VP9 simultaneously. A corrected freeworld build including `mpeg12dec` is the smallest clean superset solution; no such repository package has been established.

Options requiring product decision:

1. Prefer an RPM Fusion packaging correction adding `mpeg12dec` (recommended; one driver, no runtime routing).
2. Add per-playback-process driver-path selection after proving both installed drivers independently work. This affects MEDIA/DVD launch policy, diagnostics, fallbacks and validation; it is not a bounded Dev3 correction.
3. Explicitly accept MPEG-2 software decode while using freeworld for H.264/HEVC. This knowingly loses an available hardware path and requires a product decision.
4. Maintain a custom Mesa build. This creates a packaging/security maintenance burden and is not recommended.

## Capability ownership finding

`openhtpc-capabilities.py` and its generated `runtime/capabilities.json` are the canonical live capability truth. `profile.json` duplicates codec observations in:

- `media_stack.observed_capabilities.vaapi_decode`;
- `gpu_topology.display_gpu.vaapi_decode`;
- `gpu_topology.processing_gpu.vaapi_decode`.

Dev2 refreshed only the first path, so immutable topology identity remained intact but mutable codec observations contradicted one another. Arbitrarily copying values into every duplicate would preserve the ownership defect.

Proposed ownership model:

- keep immutable GPU identity/topology in `profile.json`;
- make `runtime/capabilities.json` the only public current codec view;
- label any retained profile codec data explicitly as a generation-time snapshot/history, or remove it after all consumers migrate;
- make support/UI consume the canonical capability document;
- regenerate capabilities after an approved package transaction without rebuilding topology.

That schema/consumer migration targets the frozen Capability Engine and therefore is not applied in this forensic commit without an explicit architecture decision.

## Diagnostic deliverable

The collector now compares both installed VA driver paths read-only and runs a capability-consistency audit. The audit reports `CONTRADICTION`, `PASS`, or `UNKNOWN`, and classifies gained and lost codecs without calling a mixed transition universally better.

No package, repository, runtime, playback, Flex, audio or Hardware Passport generation behavior is changed. No Dev3 product candidate is produced.

## Verdict

`AMD_CODEC_PHASE2B_NEEDS_ARCHITECTURAL_DECISION`
