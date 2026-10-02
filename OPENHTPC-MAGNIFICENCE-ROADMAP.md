# OPENHTPC Magnificence roadmap

## RC scope

Status: `RC PRIORITY — CURRENT FEDORA GRAPHICS STACK`

The first Magnificence RC targets hardware that works with the current Fedora graphics stack without requiring OPENHTPC to install, pin or replace a legacy vendor driver branch. The RC must remain installable, predictable and reversible, with PURE as the safe fallback when no qualified profile matches the active GPU, source class and display target.

The initial qualified matrix is intentionally finite. It includes current validated Intel, AMD and NVIDIA paths and does not infer an untested recipe merely because a GPU appears similar to a qualified one. Runtime benchmarking is not a recipe-selection mechanism.

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
