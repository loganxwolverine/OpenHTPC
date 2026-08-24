# OPENHTPC 1.1.2 — AMD Media Codec Phase 2A forensic

Status: waiting for the physical OS/API report; no product patch.

## Baseline and freeze

- AMD Base P0 technical baseline: `df285bf100b22ec75bc0ff62d5df73d914e308ea`
- Parent Audio P0 documentation head: `25c74afc90ddf1708f7159c66752e264729b44d9`
- Audio P0 technical baseline: `3080b46b0f7537222358c231a994ac838cfb691e`
- Phase 2A branch: `post-1.1.2-dev1-amd-media-codec-phase2a`

Steve's completed fresh-install smoke establishes
`AMD_BASE_P0_PHYSICALLY_VALIDATED`: Generated Runtime PASS, Doctor READY,
local KDE Flex launch/navigation PASS, quit-to-KDE PASS and zero recent Flex
crashes. Phase 2A does not change that capability-driven runtime. The distinct
`UPDATE_RUNTIME_REGENERATION_REQUIRED` issue remains backlog.

## Current codec evidence

The earlier Hardware Passport reported VAAPI MPEG-2 and VP9 available, while
H.264, HEVC Main and HEVC Main10 were unavailable; RPM Fusion was reported
disabled. This is evidence of what the installed API exposed to OPENHTPC, not
yet evidence of a silicon limitation or a packaging root cause. The raw
`vainfo`, RPM provenance and FFmpeg build data from that physical machine are
not yet available, so Phase 2A must not select a product remedy.

## OPENHTPC probes

The installer and Builder run, for each discovered character render node:

```text
vainfo --display drm --device <render-node>
```

They retain `Driver version` and `VAProfile` lines. MPEG-2, H.264, HEVC Main,
HEVC Main10, VP9 and AV1 are true only when their profile line also contains
`VAEntrypointVLD`. Encode-only `VAEntrypointEncSlice*` lines do not pass. The
canonical Capability Engine independently executes the same command for render
nodes associated with GPU PCI functions and parses stdout plus stderr. It
records per-GPU VAAPI profiles and folds them into the codec matrix.

FFmpeg software decoder availability is measured separately with:

```text
ffmpeg -hide_banner -decoders
```

The engine parses the six capability flags and exact decoder name; the older
installer/Builder grep exact `h264`, `hevc` and `av1` names. Neither result is
inferred from the GPU vendor.

The upstream libva-utils example emits profile names followed by a colon and
`VAEntrypointVLD`; repository tests prove that OPENHTPC accepts this syntax and
rejects encode-only lines. Render nodes are derived from DRM/sysfs and the
Hardware Passport. On the supplied Passport, `/dev/dri/renderD128` was
associated with the selected high-confidence AMD GPU; the collector reads that
value and does not guess or hardcode it.

Assessment before physical output: no parser defect is demonstrated.

## Fedora/package audit

The fresh installer requires `libva-utils`, `mesa-vulkan-drivers`, MPV and an
FFmpeg command (installing Fedora `ffmpeg-free` only if absent). For Intel only,
it may add `libva-intel-media-driver`. It does not explicitly require an AMD
VAAPI driver package.

Its optional multimedia extension can enable RPM Fusion free/nonfree after
interactive consent, but its package candidates are limited to
`intel-media-driver` and `libavcodec-freeworld`. It does not propose
`mesa-va-drivers-freeworld`; moreover, the extension's `intel-media-driver`
candidate is not guarded by the detected Intel-vendor flag. Thus its text promising available multimedia
complements is not yet a complete AMD package policy. This is an audit finding,
not a Phase 2A patch.

Fedora 44 publishes a codec-limited `ffmpeg-free` build and the Fedora Mesa
build provides `radeonsi_drv_video.so`. RPM Fusion publishes a Fedora 44
`mesa-va-drivers-freeworld` build. Package existence alone does not establish
which build is installed or which profiles it exposes on `openhtpcryzen`; the
collector records installed NEVRA, vendor, source repository and the RPM owner
of every VA driver before any decision.

Sources:

- Fedora package catalogue: https://packages.fedoraproject.org/pkgs/ffmpeg/ffmpeg-free/
- Fedora Mesa package catalogue: https://packages.fedoraproject.org/pkgs/mesa/
- libva-utils canonical output example: https://github.com/intel/libva-utils
- RPM Fusion Fedora 44 package repository: https://download1.rpmfusion.org/free/fedora/updates/44/x86_64/

## Ranked hypotheses pending physical evidence

1. **Fedora/RPM Fusion Mesa VAAPI codec split** — strongest repository-level
   lead: RPM Fusion offers a distinct freeworld VAAPI build and RPM Fusion was
   reported disabled. Required proof: installed owner/provenance plus raw
   `radeonsi` profiles.
2. **Installed Mesa VAAPI component/build differs from the assumed stack** —
   plausible because OPENHTPC does not explicitly require an AMD VAAPI package.
   Required proof: driver file owner, NEVRA and `vainfo` driver line.
3. **FFmpeg codec-limited Fedora build** — independently plausible for false
   software-decoder flags because Fedora labels `ffmpeg-free` codec-limited;
   it cannot by itself explain missing VAAPI profiles. Required proof:
   `ffmpeg -version` and complete decoder list.
4. **Actual hardware/firmware exposure limitation** — possible but not shown.
   Required proof: correct `radeonsi` driver on the Passport node still omits
   profiles in raw `vainfo`, followed by hardware-specific authoritative data.
5. **Wrong render node or runtime environment** — lower likelihood because the
   Passport associated a direct-path node and DRM-mode `vainfo` does not depend
   on KDE/Wayland. The collector verifies sysfs identity and node existence.
6. **OPENHTPC parser defect** — currently lowest: canonical libva syntax and
   VLD/encode discrimination pass tests. Reassess only if the physical raw
   syntax contains an unhandled valid form.

## Collector safety and handoff

`tools/openhtpc-amd-codec-forensic.sh` is diagnostic-only. It uses no sudo,
package installation, repository mutation, graphical-session probe, OPENHTPC
mutation or media playback. It writes only the explicitly selected report in
the invocation directory. The Passport excerpt is restricted to capability and
runtime keys; no user configuration or credentials are collected.

Phase 2B is explicitly out of scope. Return the generated text report for a
separate decision.
