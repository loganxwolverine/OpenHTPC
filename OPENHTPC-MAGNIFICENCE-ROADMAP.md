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
