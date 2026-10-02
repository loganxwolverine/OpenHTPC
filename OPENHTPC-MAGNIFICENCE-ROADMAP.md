# OPENHTPC Magnificence roadmap

## RC scope

Status: `RC PRIORITY — CURRENT FEDORA GRAPHICS STACK`

The first Magnificence RC targets hardware that works with the current Fedora graphics stack without requiring OPENHTPC to install, pin or replace a legacy vendor driver branch. The RC must remain installable, predictable and reversible, with PURE as the safe fallback when no qualified profile matches the active GPU, source class and display target.

The initial qualified matrix is intentionally finite. It includes current validated Intel, AMD and NVIDIA paths and does not infer an untested recipe merely because a GPU appears similar to a qualified one. Runtime benchmarking is not a recipe-selection mechanism.

## RC qualified matrix

The first Magnificence RC uses the following static hardware/output classes. These are implementation classes only; the public user choice remains binary: `PURE` or `MAGNIFICENCE`.

| Hardware profile | Class | Qualified output | Magnificence chain |
| --- | --- | --- | --- |
| Intel N150 (`8086:46d4`) | `LIGHT` | 1920x1080 | KrigBilateral |
| AMD Vega 3 / Ryzen 3 PRO 3200GE (`1002:15d8`) | `LIGHT` | 3840x2160 | KrigBilateral |
| Intel Arc A310 (`8086:56a6`) | `MEDIUM` | 3840x2160 | FSRCNNX-16 + KrigBilateral + OPENHTPC Vibrance Mild |
| Intel HD 630 (`8086:5912`) | `MEDIUM` | 1920x1080 | FSRCNNX-8 + KrigBilateral |
| AMD Radeon RX 580 (`1002:67df`) | `STRONG` | 3840x2160 | FSRCNNX-16 + KrigBilateral + SSimSuperRes + OPENHTPC Vibrance Mild |
| NVIDIA GeForce RTX 3050 (`10de:2507`) | `HIGH` | 3840x2160 | FSRCNN-HQ r2_32 + KrigBilateral + SSimSuperRes + OPENHTPC Vibrance Mild |
| AMD Radeon RX 5700 XT (`1002:731f`) | `HIGH` | 3840x2160 | FSRCNN-HQ r2_32 + KrigBilateral + SSimSuperRes + OPENHTPC Vibrance Mild |

Selection is profile-driven and does not use runtime benchmarking. A missing profile, incompatible output resolution, or missing selected shader falls back to `PURE`.

## RC validation gate

`tools/validate-magnificence-rc.py` is the authoritative current-RC software gate. It validates the static profile matrix, shader distribution/licensing, the untouched `release/1.2.0-stable-prep` reference, active playback/audio/release regressions, the full Media Foundation profile, `git diff --check`, and a clean worktree for the final run.

Historical tranche tests are retained unchanged even when their frozen assumptions refer to earlier UI wording or source snapshots. They are not silently weakened to make the current branch appear green.

## RC2 runtime smoke qualification

Internal candidate `OpenHTPC-1.2.0-Magnificence-RC2` is built from commit `c39a436a25d57f5cba65c59468171a14fa3a1b98` and independently verifies against SHA-256 `a872b8674c393520404e069d21dbbf41be056da0b4edd0d61baa422e0e1906a0`.

On the Core i7-7700 / Intel HD Graphics 630 reference host:

- update installation completed successfully after a rollback snapshot;
- the unqualified 2560x1440 desktop correctly resolved Magnificence to `PURE`;
- at the qualified 1920x1080 output, static selection resolved `intel_hd630_8086_5912_sd_1080p` / `RECIPE_MAG_SD_FSRCNNX8_KRIG` without runtime benchmark selection;
- an exact production-policy A/B run on the shipped PAL MPEG-2 reference clip reported zero decoder drops, zero delayed frames and zero mistimed frames for both PURE and Magnificence;
- Magnificence measured about 34.2 ms p95 rendering time for the 25 fps reference material, below the 40 ms source-frame budget;
- MPV `frame-drop-count` increased by essentially the same amount in PURE and Magnificence (61 versus 62), so that counter is treated as cadence/presentation behavior for this test rather than Magnificence-specific overload;
- the display was restored to its original 2560x1440 mode after testing, and the expected PURE fallback was re-confirmed.

### RC2 physical DVD qualification — PASS

A subsequent supervised physical run used the original DVD `GOTHIKA` in `/dev/sr0` on the same Core i7-7700 / Intel HD 630 host. The display was temporarily set to the qualified 1920x1080 mode and the production `openhtpc-play-dvd` dispatcher selected `RECIPE_MAG_SD_FSRCNNX8_KRIG` as expected.

Observed production playback evidence after about 250 seconds:

- DVD MPEG-2 PAL 720x576 at 25 fps;
- VA-API hardware decoding active;
- `gpu-next` output active;
- FSRCNNX-8 + KrigBilateral loaded and compiled with zero shader errors or warnings;
- frame-drop-count: 0;
- decoder-frame-drop-count: 0;
- vo-delayed-frame-count: 0;
- AC-3 48 kHz audio active through PipeWire/SPDIF;
- playback exited cleanly with code 0;
- human observation: image fluidity PASS, sound PASS, no visible freeze/stutter/cut reported.

The host was restored to its original 2560x1440 desktop after the run and the expected PURE fallback was re-confirmed.

One independent RC defect was exposed during launch: `openhtpc-play-dvd` still used obsolete direct runtime logger arguments for `READAHEAD_POLICY_APPLIED`. Playback itself continued normally, but the logger emitted an argparse error. The source has been corrected to use the supported repeated `--field key=value` contract and a regression test has been added. This logging-only fix requires a new committed candidate before public RC packaging; the physically tested RC2 archive itself remains unchanged.

## Legacy GPU support

Status: `POST-RC ROADMAP`

Legacy or vendor-branch-specific GPUs are deferred until after the first viable Magnificence RC. The goal is to study a separate support path, comparable in spirit to a legacy image/profile, without destabilizing the normal Fedora path.

### Quadro P2000 / Pascal reference

The Quadro P2000 (`10de:1c30`, Pascal/GP106) is the first recorded legacy case.

Observed during the October 2026 qualification attempt:

- Fedora 44 required the NVIDIA 580xx branch for the intended proprietary/NVDEC path.
- The system required additional kernel/driver handling that is outside the desired first-RC experience.
- NVDEC MPEG-2 and Vulkan worked once the 580xx stack was active.
- `FSRCNNX-8 + KrigBilateral` produced a promising 4K DVD image and stable short playback passages.
- Higher-load `FSRCNNX-16 + KrigBilateral` exposed PCIe physical-layer instability on the ZimaBoard 2 test setup (`Xid 79`, GPU fallen off the bus). This is a test-platform limitation and is not a basis for a production P2000 profile.
- No P2000 Magnificence profile is qualified for the first RC.

Future legacy work should isolate driver installation, rollback and update behavior from the main OPENHTPC path, then repeat qualification on a stable PCIe platform before any Pascal profile is promoted.

## Future source-aware restoration

Status: `POST-RC EXPLORATION`

The first RC keeps GPU/output qualification static and simple. A later phase may add source-aware restoration for difficult DVD masters, for example material with visible MPEG-2 mosquito noise or other compression damage. Any such mode must be separately qualified and must not silently replace the normal HIGH/STRONG recipes.
