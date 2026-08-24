# OPENHTPC 1.1.2-dev3 — AMD codec capability consistency

Status: software candidate ready for physical codec playback validation.

## Baseline and product decision

- Dev2 functional baseline: `c06311aa1fde5eed3ded48f0296163e5c74d40d9`.
- Dev3 forensic parent: `8b726c265a3c82f391e621989d451e58d4fdd314`.
- Version: `1.1.2-dev3`.
- Build: `amd-codec-capability-consistency-dev3`.

Dev2's explicit-consent RPM Fusion Free transaction is preserved unchanged:
`mesa-va-drivers-freeworld` plus `libavcodec-freeworld`. No per-codec libva
driver routing, custom Mesa package or additional MPEG-2 transaction exists.

## MPEG-2 policy

The current Fedora 44 RPM Fusion freeworld driver exposes H.264, HEVC, HEVC
Main10 and VP9 but omits MPEG-2 VLD. Its Mesa build list omits the selectable
`mpeg12dec` option. OPENHTPC records MPEG-2 hardware decode as false.

MPV's existing `hwdec=vaapi` configuration remains unchanged. MPV documents
that it falls back to software decoding when hardware decoding is impossible;
its default hardware-codec allowlist also excludes MPEG-2. OPENHTPC does not
disable that fallback or introduce a hard failure. MPEG-2 playback remains
pending physical validation and is never reported as hardware decode.

## Passport consistency

One existing `vainfo`/FFmpeg observation now feeds all compatibility views in
one atomic profile write:

1. `media_stack.observed_capabilities` receives the current observation;
2. every existing `gpu_topology` `vaapi_decode` mirror receives a copy of that
   same value;
3. no topology probe or topology rebuild is performed;
4. failures before replacement leave the original profile intact.

Per-codec changes are retained in bounded `capability_change_history` entries
and printed as `CAPABILITY_CHANGE` records. A mixed transition can contain an
MPEG-2 `LOSS` and H.264/HEVC/Main10 `GAIN` entries simultaneously.

Long-term removal of these mirrors is tracked as
`CAPABILITY_SINGLE_SOURCE_MIGRATION`. It is not implemented in Dev3.

## Physical qualification

The supplied helper takes an explicit label and explicit MPV source. It does
not infer media from filenames, override libva driver paths or alter OPENHTPC.
It records source metadata when available, requested and observed decoding,
render node, drop counters, decoder errors, exit status and the operator's
fluidity confirmation. Every generated result remains `PENDING_REVIEW` until
Steve's evidence is reviewed.

The required matrix is MPEG-2/DVD, H.264 1080p, HEVC Main 8-bit, HEVC Main10
and VP9. MPEG-2 may pass with observed software fallback; H.264/HEVC/Main10
hardware qualification requires actual `vaapi` observation, with a 10-bit
source proven for Main10.

AMD runtime generation, PURE/REFERENCE contents, playback dispatch, Flex,
Wayland lifecycle, audio and DVD/MEDIA product policy are unchanged.
