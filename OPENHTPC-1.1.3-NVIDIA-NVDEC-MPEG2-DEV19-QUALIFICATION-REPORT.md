# OPENHTPC 1.1.3-dev19 — NVIDIA NVDEC MPEG-2 qualification record

Version: `1.1.3-dev19`  
Build: `nvidia-nvdec-mpeg2-whitelist-dev19`  
Commit: `84cfb3cae7581c0f03434642dd8f214241fc769f`

Dev19 is the physically qualified NVIDIA stabilization baseline for RC2. This
record separates repository automation, packaged-artifact verification,
physical validator observations, and an external Fedora/KDE platform
workaround.

## Automated evidence

- Targeted NVIDIA/runtime/release-metadata suite: 35/35 PASS.
- Full canonical regression suite: 355/355 PASS.
- The generated native NVIDIA path remains `gpu-next` + Vulkan + NVDEC.
- MPEG-2 is added only when the existing selected NVIDIA profile reports NVDEC
  MPEG-2 support; profiles without that support retain Dev18 behavior.
- Intel and AMD VA-API runtime expectations remain unchanged.

## Artifact evidence

- Artifact: `OpenHTPC-1.1.3-NVIDIA-Native-Dev19.tar.gz`
- Exact size: `113582823` bytes.
- SHA-256:
  `7df979f6e82e186c849bb1e982286a00e16e2aa3c30e72e2d955cb61e386e411`.
- Embedded version/build: `1.1.3-dev19` /
  `nvidia-nvdec-mpeg2-whitelist-dev19`.
- Manifest: 345 entries; 0 missing files; 0 unexpected managed files; 0
  checksum mismatches; PASS.
- `payload/openhtpc-runtime-generator.py` is present and manifested.
- NAS delivery: `NAS_DELIVERY_BLOCKED`. No delivery to the OPENHTPC Tools share
  is claimed.

## Physical evidence

Validator: OPENHTPCNVIDIA, Fedora 44 KDE Plasma/Wayland, Intel Core i7-7700,
Intel HD 630, NVIDIA RTX 3050 GA106, proprietary NVIDIA driver 610.57.04,
physical HDMI output on the RTX 3050 at 3840×2160 60 Hz.

- Dev18 → Dev19 update: PASS.
- Reported version/build, Hardware Passport, generated runtime, and Doctor
  Overall READY: PASS.
- Cold reboot, SDDM login, KDE Plasma Wayland session, and OPENHTPC autostart:
  PASS.
- Post-boot state: one authoritative UI, no unexpected Flex PID, one optical
  monitor, appliance RUNNING, Doctor Overall READY.
- MPEG-2 Main 720×576 25 fps 8-bit through OPENHTPC MEDIA: NVDEC, successful,
  PASS.
- H.264 High 1920×1080 24000/1001 fps 8-bit through OPENHTPC MEDIA: NVDEC,
  successful, PASS.
- HEVC Main 10 3840×2160 24 fps 10-bit through OPENHTPC MEDIA: NVDEC,
  successful, PASS.
- All three playback records used the same current hardware/runtime
  fingerprints.
- MPEG-2 changed from no recorded hardware backend before Dev19 to `nvdec`
  after Dev19, physically proving the whitelist correction.
- QUITTER → KDE: Flex and optical monitor stopped, no unexpected Flex PID,
  appliance STOPPED, Plasma desktop restored and usable, session preserved,
  no logout, Doctor Overall READY; PASS.
- The earlier observation of another Flex PID followed a PC reboot and is not
  a relaunch regression.

The physically generated NVIDIA PURE backend is:

```ini
vo=gpu-next
gpu-api=vulkan
hwdec=nvdec
hwdec-codecs=h264,vc1,hevc,vp8,vp9,av1,prores,prores_raw,ffv1,dpx,mpeg2video
```

## External Fedora/KDE platform workaround

Plasma Login Manager behavior with Fedora 44 and NVIDIA driver 610.57.04 is an
external platform issue, not an OPENHTPC runtime or installer defect. SDDM was
the tested login-manager workaround and passed cold-boot/login qualification.
SDDM is not made an OPENHTPC installer requirement by Dev19.

## Qualification verdict

NVIDIA Dev19 physical qualification: **PASS**. This verdict qualifies the
bounded machine, driver, runtime, update, playback, quit, and reboot evidence
above; it does not claim that an RC2 artifact has been physically tested.
