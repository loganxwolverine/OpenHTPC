# OPENHTPC protected optical roadmap

## UHD optical playback performance / dropped output frames

Status: `DEFERRED / OBSERVE`

Physical context: ZimaBoard 2, external USB optical drive, real protected UHD
4K media and HEVC Main10. Playback opened successfully and produced video and
audio, but important dropped output frames were observed.

Dev5 records the limitation without changing cache, video synchronization,
display refresh, Vulkan, VA-API, tone mapping, HDR, USB behavior or MPV
options. No ZimaBoard-specific workaround is introduced. If the same problem
is reproduced on AMD or NVIDIA, raise its priority and open a dedicated
performance project.

## Protected optical → plugin migration

Status: `PLANNED — PLUGIN FRAMEWORK P2`

Protected optical support remains experimental and integrated into the
development branch. Future Blu-ray/UHD plugins have not been extracted, so
the Plugin Registry truthfully reports Blu-ray and UHD as `NOT_INSTALLED` even
when the integrated protected-optical capability is `ENABLED`.

Core ownership should remain limited to canonical optical device detection,
generic optical state, the generic provider contract, dispatcher security and
generic Doctor/plugin-framework hooks. A future optical/Blu-ray/UHD plugin
should own libbluray-specific probing, AACS provider integration, Blu-ray/UHD
classification, `bd://` launch semantics, media-specific presentation assets
and diagnostics.

Stable boundaries to preserve are the canonical optical state, capability
snapshot/provider statuses, generation-bound action token, dispatcher request
contract, last-attempt record and Doctor/plugin registry interfaces. Dev5 is
an audit only: no file is moved and Plugin Framework P2 is not started.
