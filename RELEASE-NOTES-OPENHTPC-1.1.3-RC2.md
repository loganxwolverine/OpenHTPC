<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.1.3 RC2

OPENHTPC 1.1.3 RC2 adds native NVIDIA support to the OPENHTPC hardware stack:
GPU/display selection, NVIDIA capability discovery, and NVDEC with Vulkan.
MPEG-2 NVDEC is enabled on NVIDIA through a conditional MPV whitelist.

Intel and AMD retain their existing VAAPI/Vulkan paths. Physical qualification
is complete on NVIDIA, AMD, and Intel validators, with no physical regression
observed on Intel or AMD.

RC2 remains a prerelease. Blu-ray, UHD, Jellyfin, Plex, and Streaming plugins
are optional and were not installed during this qualification. Protected UHD
is not universally supported, and unqualified bitstream formats or MPEG-2
hardware paths are not promised.

SHA-256:
`2729d5f77f70c9f8f7425d4a8efc6d3e70969902732df94120d45adf15cf6fdf`
