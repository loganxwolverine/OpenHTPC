# OPENHTPC Magnificence — GPU evidence register

## Purpose

This document is the human-readable companion to `payload/assets/magnificence_gpu_knowledge.json`.
The JSON database stores both runtime-eligible OPENHTPC rules and reference-only external family
evidence. Community-derived tiers are not runtime authority until OPENHTPC explicitly promotes
them. This register explains the methodology and evidence behind those references.

The goal is not to discover new shaders. The Magnificence shader scope is frozen to:

- KrigBilateral
- FSRCNNX 8
- FSRCNNX 16
- FSRCNN-HQ r2_32
- SSimSuperRes
- OPENHTPC Vibrance Mild

RAVU, ArtCNN, CfL and other shaders are outside this classifier.

## Evidence hierarchy

1. **OPENHTPC physical qualification** — highest authority. Exact GPU/output profiles always win.
2. **OPENHTPC user reports** — multiple consistent reports may justify promoting a family rule after review.
3. **External community configurations or reports** — reference evidence only; they never activate a recipe by themselves.
4. **Single external/user report** — corroboration only; never enough to justify an aggressive recipe by itself.
5. **Observed local capabilities** — Vulkan device match plus MPEG-2 hardware decode are mandatory for any generalized recipe.
6. **Unknown capable hardware** — conservative LIGHT/KrigBilateral baseline while evidence accumulates.
7. **Missing required capabilities** — PURE.

Runtime benchmarking is not used to select a recipe.

## Frozen inferred recipes

| Tier | Inferred recipe |
| --- | --- |
| LIGHT | KrigBilateral |
| MEDIUM | FSRCNNX-8 + KrigBilateral |
| STRONG | FSRCNNX-16 + KrigBilateral + Vibrance Mild |
| HIGH | FSRCNNX-16 + KrigBilateral + SSimSuperRes + Vibrance Mild |

FSRCNN-HQ r2_32 is intentionally excluded from family inference. It remains reserved for exact
OPENHTPC physical qualifications such as the RTX 3050 and RX 5700 XT profiles.

## Main external evidence

### bses2018 / plex-shader-profiles

This project implements GPU auto-detection from the renderer device name and maps hardware to
high/mid/low tiers. Its cinema chains use the same core family as OPENHTPC: FSRCNNX-16 +
SSimSuperRes + KrigBilateral for high, FSRCNNX-8 + KrigBilateral for mid, and KrigBilateral for
low. It provides broad NVIDIA, AMD and Intel model mappings.

Source: https://github.com/bses2018/plex-shader-profiles

OPENHTPC use: primary community family-map seed, never an override for a physically qualified
OPENHTPC profile.

### PopeyeURS / ulyssescaballes-mpv.config

The published performance notes recommend RTX 3060 / RX 6700 XT class hardware for a full 4K
shader pipeline, lighter FSRCNNX profiles for GTX 1660 / RX 5600 XT class hardware, reduced load
on Arc A7xx, and light profiles on Intel integrated graphics. It also explicitly recommends
FSRCNNX-16 as a lighter/stable cross-platform path on Linux/AMD.

Source: https://github.com/popeyeurs/ulyssescaballes-mpv.config

OPENHTPC use: corroborates conservative family boundaries and supports not generalizing HQ32.

### Reddit r/mpv — GPUs for MPV shaders (2026)

Users discuss RX 580 as around the lower practical boundary for shader-heavy 4K use and report
that integrated graphics can become choppy with expensive shaders. Another participant suggests
RTX 3060 or Arc A750 for a more capable HTPC target.

Source: https://www.reddit.com/r/mpv/comments/1r584zg/gpus_for_mpv_shaders/

OPENHTPC use: low-confidence corroboration only.

### Reddit r/mpv — RTX 3060 full-4K configuration

A user reports that a previous GTX 1070 configuration had to be constrained to 1080p and that an
RTX 3060 allowed use of the full 3840x2160 settings.

Source: https://www.reddit.com/r/mpv/comments/18t231j/

OPENHTPC use: corroborates the RTX 3060-and-above HIGH family boundary; not a precise shader
benchmark.

### Reddit r/mpv — GTX 1660 Ti gpu-next/Vulkan configuration

A GTX 1660 Ti user reports a gpu-next + Vulkan + NVDEC setup for normal playback.

Source: https://www.reddit.com/r/mpv/comments/1b80mft/

OPENHTPC use: backend compatibility evidence only. It does not by itself justify a heavy recipe.

### Reddit r/mpv — RX 6600 configuration

An RX 6600 user reports using an mpv configuration built around external shaders.

Source: https://www.reddit.com/r/mpv/comments/126q1pm/

OPENHTPC use: compatibility corroboration only. The MEDIUM family tier remains conservative.

### mpv community configuration — dynamic FSRCNNX degradation

A real-world mpv configuration demonstrates the practical ladder FSRCNNX-16 -> FSRCNNX-8 -> off
when frame problems occur.

Source: https://github.com/mpv-player/mpv/issues/16671

OPENHTPC use: supports the chosen x16/x8/light tier structure. OPENHTPC does **not** copy the
runtime benchmark/degradation selection mechanism for the RC.

### iwalton3 / default-shader-pack

A widely used mpv/Plex MPV Shim shader pack includes FSRCNNX and KrigBilateral variants and warns
that heavier shader presets can produce dropped frames depending on GPU capability.

Source: https://github.com/iwalton3/default-shader-pack

OPENHTPC use: corroborates the need for tiered load and safe fallback.

## Important counter-evidence and limits

Shader cost depends on both GPU capability and output resolution. Community configurations warn
that performance varies by platform and that users should inspect dropped frames and shader timing.

A modern mpv configuration by classicjazz also emphasizes that shader cost scales with output
resolution and that lighter fallbacks are necessary on weaker hardware. That project has moved to
different shaders, so it is **not** used to alter OPENHTPC's frozen shader set; it is only evidence
for the hardware/output-aware design.

Source: https://github.com/classicjazz/mpv-config

A reported RX 6750 XT case with a substantially heavier NNEDI3 configuration still showed dropped
frames. This is why OPENHTPC classifies the RX 6750 XT as capable of the conservative HIGH family
recipe but does not infer the physically qualified HQ32 recipe solely from raw GPU class.

## Current runtime behavior versus reference tiers

The external family tiers remain recorded for comparison — for example GTX 1660 base as LIGHT, GTX 1660 Super/Ti as MEDIUM, RTX 3060-class as HIGH, RX 6600-class as MEDIUM, and RX 6750 XT-class as HIGH — but all current community-derived rules are marked `REFERENCE_ONLY`. They therefore do **not** select those tiers at runtime.

Until an OPENHTPC promotion exists:

- a GTX 1660 with verified Vulkan + MPEG-2 decode receives the conservative LIGHT/KrigBilateral capability baseline;
- an RX 6750 XT with the same verified capabilities also receives that provisional LIGHT baseline despite its much higher external reference tier;
- an exact OPENHTPC-qualified GPU/output receives its exact physically validated profile;
- hardware without the required capability evidence falls back to PURE.

This deliberate conservatism reflects OPENHTPC's own counter-evidence: physical tests on cards such as RX 580, RTX 3050 and RX 5700 XT have already shown that generic community tiers can substantially understate what the targeted Linux/DVD pipeline can sustain. Promotions must therefore be based on OPENHTPC evidence rather than copied from external rankings.
