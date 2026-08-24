# OPENHTPC 1.1.2-dev1 — AMD Base P0 Dev1

Status: software candidate for first physical AMD validation.

## Baseline

- Frozen Audio P0 documentation head: `25c74afc90ddf1708f7159c66752e264729b44d9`
- Frozen Audio P0 technical commit: `3080b46b0f7537222358c231a994ac838cfb691e`
- Candidate version: `1.1.2-dev1`
- Build: `amd-base-runtime-validation-dev1`
- Branch: `post-1.1.1-rc3-amd-base-p0`

## Code root cause

The runtime generator already associated the selected physical GPU, PCI
function, render node, hardware Vulkan device, VAAPI capability, display GPU
and offload topology. Its final readiness gate nevertheless rejected every
backend whose normalized vendor was not `intel`, with the reason “Backend
AMD/NVIDIA non validé physiquement dans Build 3.” The veto was introduced in
the RC2 baseline commit `46c40d6ade649c1fe0853892b9b75a5d8622a88c`.

Because `ready` became false, the generator deleted candidate configs, set
`runtime_profiles.available` to an empty list, left PURE and REFERENCE pending,
and set `runtime.configuration_generated` and `mpv_configuration_generated` to
false. This was a validation-policy veto, not evidence of AMD incompatibility.

## Capability-driven correction

The vendor veto is removed. The existing safety gates remain authoritative:

- a reliably selected processing GPU;
- direct display path, or otherwise a separately validated offload path;
- video backend status `observed`;
- observed VAAPI decode API and Vulkan render API;
- an associated render node;
- required MPV options and values, including gpu-next, Vulkan and VAAPI;
- hardware Vulkan selection, which already excludes llvmpipe/lavapipe/CPU
  devices before runtime generation.

Equivalent observed capabilities now produce the same decision regardless of
vendor/model identity. Generation creates a candidate with validation status
`validation_pending`; it does not mark AMD physically validated.

## Expected Vega 8 candidate

For the supplied high-confidence, direct-path Passport, the existing generic
generator should produce:

```ini
vo=gpu-next
gpu-api=vulkan
hwdec=vaapi
vaapi-device=/dev/dri/renderD128
```

The render node is consumed from the Hardware Passport. No AMD, Vega, Raven,
Picasso, PCI device, card index or model is hardcoded.

## H.264/HEVC forensic

The Builder runs `vainfo --display drm --device <observed-render-node>` and
matches real `VAProfileH264*`, `VAProfileHEVCMain` and
`VAProfileHEVCMain10` VLD entries. It independently reads FFmpeg's real decoder
list. Therefore the supplied false H.264/HEVC values are coherent with the
commands available on that installation. They are not the current runtime
generation failure and are not prerequisites for creating the PURE UI/runtime
candidate.

Backlog: `AMD_PHASE2_MEDIA_CODEC_VALIDATION`. Phase 1 does not install RPM
Fusion, change Mesa or add dependencies.

## Deliberately unchanged

Audio P0, PipeWire, MPV audio policy, DVD/MEDIA playback policy, shaders,
Plugin Framework and Cinema Enhancement are unchanged. Graphical-session data
from SSH is not used to override the Passport captured in the real KDE Wayland
session.
