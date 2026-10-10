# OPENHTPC 1.3.1 validator — DVD/audio/multi-GPU checkpoint — 2026-10-10

## Scope and authority

This checkpoint records the verified state of the uncommitted OPENHTPC 1.3.1 validator work on `.67` (`openhtpc3050`, Core i7-7700 + Intel HD630 + Radeon RX 5700 XT). It does not authorize a commit, push, tag, release or deployment to `.229`.

## Physical DVD lifecycle — PASS

Steve physically confirmed the final DVD launch and then repeated the test himself: the film starts normally.

Final recorded refresh lifecycle:

- initial desktop: 3840×2160 @ 60 Hz;
- PAL DVD cadence target: 3840×2160 @ 50 Hz;
- switch requested and verified;
- playback started;
- playback exit code: 0;
- restore requested and verified;
- desktop returned to 3840×2160 @ 60 Hz;
- no residual mpv / refresh matcher / DVD dispatcher process after exit; Flex remains alive.

Magnificence on the RX 5700 XT remained the qualified HIGH recipe with `vaapi-copy`, BWDIF, FSRCNN-HQ r2_32, KrigBilateral, SSimSuperRes and Vibrance Mild.

## Black-screen/audio incident — root cause and final behavior

The failing path was not a video-render failure. mpv received its first video frame while the PipeWire AC3 passthrough stream immediately failed with `no target node available` on the effective S/PDIF sink `alsa_output.pci-0000_00_1f.3.iec958-stereo` (`ALC1150 Digital`).

A PCM smoke to the same exact sink succeeded. Therefore the product rule is now fail-safe:

- user BITSTREAM preference remains stored unchanged;
- after any display modeset, OPENHTPC resolves the effective sink;
- if passthrough is proven/qualified (for example a valid HDMI target), bitstream is retained;
- if passthrough is not proven on the effective sink, that playback is launched as PCM instead of failing;
- the resolved sink is explicitly pinned for the playback.

Final telemetry on the passing physical run records:

- `effective_audio_device=pipewire/alsa_output.pci-0000_00_1f.3.iec958-stereo`;
- `effective_audio_mode=PCM`;
- `effective_audio_reason=passthrough_unproven_post_modeset`;
- PipeWire state reaches `streaming` and mpv reports `audio ready`;
- no `no target node available` error.

An earlier apparent retest failure was invalid: an older DVD dispatcher, launched before the latest matcher deployment, was still alive behind an invisible `kdialog` error and held the DVD lock. Closing that exact dialog/process allowed the corrected path to be tested cleanly.

## Multi-GPU capability publication — PASS

Installed `.67` runtime/profile publication was verified against exact PCI identities:

- RX 5700 XT `0000:03:00.0`: VAAPI MPEG-2=true, VP9=true; H.264=false, HEVC=false, HEVC Main10=false, AV1=false.
- Intel HD630 `0000:00:02.0`: VAAPI MPEG-2=true, H.264=true, HEVC=true, HEVC Main10=true, VP9=true, AV1=false.
- `profile.json` `display_gpu.vaapi_decode` matches the RX exact observation.
- `profile.json` `processing_gpu.vaapi_decode` matches the RX exact observation.
- global `media_stack.observed_capabilities.vaapi_decode` equals the union of both GPUs.

All three consistency checks passed.

## Software gates after final audio fix

- focused display/audio/refresh routing gate: 93/93 PASS;
- expanded relevant regression gate: 378/378 PASS in 20.55 s;
- `git diff --check`: PASS.

The worktree remains uncommitted. `.229` remains untouched by this validator candidate. No protected stash was altered.
