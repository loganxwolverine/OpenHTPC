# OPENHTPC 1.2.0 RC4 — Candidate preparation record

Version: `1.2.0-rc4`  
Build: `public-release-1.2.0-rc4`

RC1 is `NO_GO`; RC2 is `PHYSICAL_GATE_NO_GO`; RC3 is `PHYSICAL_GATE_NO_GO`.

Physical investigation on RC3 demonstrated that the MPV bitstream contract was
properly constructed (`--audio-spdif=ac3,eac3,dts,dts-hd,truehd`, `--aid=auto`,
`--audio-channels=auto`), but Fedora PipeWire/WirePlumber defaults the active
HDMI sink node to `iec958.codecs = [ "PCM", "DTS", "AC3" ]`, causing protected
DTS-HD Blu-ray playback to fall back to stereo/silence. Causality was physically
proven: applying `iec958Codecs: [ PCM DTS AC3 EAC3 TrueHD DTS-HD ]` immediately
produced physical DTS-HD bitstream playback on the Denon AVR.

RC4 adds dynamic PipeWire HDMI sink inspection, deterministic `iec958.codecs`
preparation, post-mutation verification, and enriched atomic diagnostics in
`~/.local/state/openhtpc/protected-optical-last-command.json`.

RC4 purpose is `PROTECTED_BLURAY_PIPEWIRE_HD_PASSTHROUGH_PREPARATION`.
Its status is `PENDING_PHYSICAL_VALIDATION_NOT_QUALIFIED` and is not qualified.
