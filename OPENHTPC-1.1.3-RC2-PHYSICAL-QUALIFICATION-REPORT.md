<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.1.3 RC2 — Physical qualification report

## Release identity

- Version: `1.1.3-rc2`
- Build: `public-release-1.1.3-rc2`
- Artifact: `OpenHTPC-1.1.3-RC2.tar.gz`
- SHA-256: `2729d5f77f70c9f8f7425d4a8efc6d3e70969902732df94120d45adf15cf6fdf`
- Size: `113587453` bytes
- Assembly commit: `3828b32`
- Final software tests: `357/357 PASS`

## NVIDIA / RTX 3050

- Fedora 44 KDE Wayland
- Proprietary NVIDIA driver operational
- Native NVIDIA runtime using NVDEC and Vulkan
- MPEG-2 NVDEC: **PHYSICAL PASS**
- H.264 1080p NVDEC: **PHYSICAL PASS**
- HEVC Main10 4K NVDEC: **PHYSICAL PASS**
- Reboot / SDDM / KDE / OPENHTPC autostart: **PASS**
- Quit OPENHTPC to KDE: **PASS**
- Doctor: **Overall READY**

## AMD / Ryzen

- Fedora 44 KDE Wayland
- Runtime:
  - `vo=gpu-next`
  - `gpu-api=vulkan`
  - `hwdec=vaapi`
  - `vaapi-device=/dev/dri/renderD128`
- H.264 High 1920x1080:
  - `hardware_decode_backend=vaapi`
  - `successful=true`
- HEVC Main10 3840x2160 10-bit:
  - `hardware_decode_backend=vaapi`
  - `successful=true`
- Observed RC2 runtime fingerprint: `0c53f0c83d2360c53034c9f6ed4d28d7ce0aaf5e6d298387b72ca5b365a02290`
- Reboot / autostart: **PASS**
- Quit OPENHTPC to KDE: **PASS**
- Final Doctor:
  - UI instances: `0`
  - Appliance state: `STOPPED`
  - Plasma Shell: **PASS**
  - Desktop restore: **PASS**
  - Last OPENHTPC exit: `USER_QUIT_TO_DESKTOP`
  - Overall: **READY**

## Intel / ZimaBoard 2

- Fedora 44 KDE Wayland
- Runtime:
  - `vo=gpu-next`
  - `gpu-api=vulkan`
  - `hwdec=vaapi`
  - `vaapi-device=/dev/dri/renderD128`
- H.264 High 1920x1080:
  - `VAAPI`
  - `successful=true`
  - `validated_at=2026-08-30T14:40:54+02:00`
- HEVC Main10 3840x2160 10-bit:
  - `VAAPI`
  - `successful=true`
  - `validated_at=2026-08-30T14:41:25+02:00`
- Observed hardware fingerprint: `f5c677830d9422e05ef11fc060970b2cf62ca94285c508a5c5af57e4ee2c9bfd`
- Observed RC2 runtime fingerprint: `a044f1653b1f80bb2bcdde5c8fca5793ba2589175f910655e27e7ef2516c0261`
- Reboot / autostart: **PASS**
- Quit OPENHTPC to KDE: **PASS**
- Final Doctor:
  - UI instances: `0`
  - Appliance state: `STOPPED`
  - Plasma Shell: **PASS**
  - Desktop restore: **PASS**
  - Last OPENHTPC exit: `USER_QUIT_TO_DESKTOP`
  - Overall: **READY**

## Conclusion

**RC2 PHYSICAL QUALIFICATION = PASS**

Physically validated platforms:

- NVIDIA
- AMD
- Intel

## Known limits and evidence boundary

- Blu-ray, UHD, Jellyfin, Plex, and Streaming plugins were not installed for
  this qualification; these optional plugins are not claimed as physically
  qualified here.
- Bitstream formats beyond those qualified historically are not promised by
  this report.
- Protected UHD is not presented as universally supported.
- Software MPEG-2 on platforms where the hardware backend was not physically
  qualified is not presented as a hardware-support promise.
