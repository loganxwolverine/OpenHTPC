# OPENHTPC 1.1.2-dev2 — AMD Fedora Codec Enablement

Status: software candidate for physical package remediation and API validation.
No media playback has been qualified by this candidate.

## Baseline

- AMD Base P0 physically validated technical commit: `df285bf100b22ec75bc0ff62d5df73d914e308ea`
- Phase 2A forensic commit: `78069be6c98a64126b96ef5050b622d006653956`
- Candidate: `1.1.2-dev2`
- Build: `amd-fedora-codec-enablement-dev2`

The capability-driven AMD runtime, Vulkan/RADV configuration, PURE/REFERENCE
profiles, audio engine, DVD/MEDIA pipelines and desktop lifecycle are unchanged.

## Physical Phase 2A evidence

On `openhtpcryzen`, Mesa Gallium 26.1.7 `radeonsi` initializes successfully on
the Passport render node. It exposes MPEG-2, JPEG and VP9 VLD profiles but no
H.264, HEVC Main or HEVC Main10 VLD profile. Fedora's FFmpeg 8.1.2 build also
explicitly disables the native `h264` and `hevc` decoders. MPV consequently
does not list their VAAPI hardware paths. These are two independent confirmed
software-stack blockers.

## Fedora 44 / RPM Fusion resolution

RPM metadata from the signed Fedora 44 RPM Fusion Free packages establishes an
additive transaction:

```text
mesa-va-drivers-freeworld-26.1.7-1.fc44
libavcodec-freeworld-8.1.2-3.fc44
```

`mesa-va-drivers-freeworld` installs its video drivers in
`/usr/lib64/dri-freeworld`, provides the Fedora `mesa-va-drivers` capability and
does not replace `mesa-vulkan-drivers`. `libavcodec-freeworld` installs the
complementary ABI under `/usr/lib64/ffmpeg`, provides `libavcodec.so.62`, and is
described by its RPM as complementing the distribution counterpart. Its only
declared conflict is `libavcodec-free < 8.1.2`; the physical Fedora package is
8.1.2. Therefore no `dnf swap`, FFmpeg-wide replacement or Vulkan package
replacement is proposed.

The installer presents the exact packages before mutation. With consent and
RPM Fusion Free already enabled, the bounded transaction is:

```text
sudo dnf5 install --refresh mesa-va-drivers-freeworld libavcodec-freeworld
```

(`dnf` is used when `dnf5` is unavailable.) If RPM Fusion Free is absent, its
official Fedora-release bootstrap RPM is proposed after the same consent.
RPM Fusion Nonfree is not enabled for AMD. Package availability is checked
after repository activation and before installation.

## Truth and refresh

Installation success does not imply codec success. The installer immediately
reruns `vainfo` and FFmpeg decoder probes. Missing results remain unvalidated.
For an existing Passport, only `media_stack` is atomically refreshed; runtime,
GPU topology and every unrelated field are preserved. The canonical Capability
Engine is subsequently executed with `--refresh`. The PURE runtime file is not
rewritten because its qualified VAAPI/Vulkan configuration is unchanged.

The generic `rpmfusion_enabled` Builder field formerly required both the Free
and Nonfree base repositories. That made a valid Free installation appear
false. It now reports true when any enabled RPM Fusion Free/Nonfree family is
observed.

## Intel dependency hygiene

The former multimedia extension could propose `intel-media-driver` whenever
VAAPI codecs were absent, regardless of the detected GPU. Candidate selection
is now package-family aware:

- Intel GPU: Intel media driver candidate only;
- AMD GPU: Mesa VAAPI freeworld candidate only;
- missing FFmpeg decoders: libavcodec freeworld candidate independently.

No installed Intel package is removed from the physical validator.

## Physical validation sequence

First half only:

1. leave OPENHTPC stopped;
2. run `./install.sh` from the extracted Dev2 candidate;
3. review the exact package list and consent;
4. run the Phase 2A forensic collector again;
5. verify H.264/HEVC VLD profiles, native FFmpeg decoders and MPV hwdec entries;
6. run `openhtpc doctor` and return the report.

API visibility is `SUPPORTED`, not `VALIDATED`. Media playback is a later step.

Second-half playback matrix, only after the first-half decision:

| Source | Required evidence |
|---|---|
| MPEG-2 | source codec, requested/actual hwdec, render node, drops, clean exit |
| H.264 1080p | same |
| HEVC 8-bit | same |
| HEVC Main10 | only if the API exposes Main10; same evidence |
| VP9 | same |

No Phase 2B physical result is fabricated in this report.
