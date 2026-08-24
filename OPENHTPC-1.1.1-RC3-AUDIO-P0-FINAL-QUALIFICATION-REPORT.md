# OPENHTPC 1.1.1 RC3 — AUDIO P0 Final Qualification Report

Date: 2026-08-24  
Status: `AUDIO_P0_PHYSICALLY_QUALIFIED` / `QUALIFIED_AND_FROZEN`

## Authoritative candidate

- Version: `1.1.1-rc3`
- Build: `post-rc3-audio-passthrough-p0-rc3`
- Branch: `post-rc3-audio-passthrough-p0`
- Qualified technical commit: `3080b46b0f7537222358c231a994ac838cfb691e`
- Parent public baseline: `v1.1.0-rc3` / `62992ac15e352b70a61f2fb92a4271c7ccf261fa`
- Artifact: `OpenHTPC-1.1.1-RC3-Audio-P0.tar.gz`
- SHA256: `6a1a8fe0e80f11c7f97717f0cd8d17c02eb841116633e3dad289d07f17e063a8`

The artifact above is the physically qualified binary candidate. It must not be
rebuilt. There is no RC4. Documentation commits made after `3080b46` do not
change the qualified archive.

## Initial root cause

The historical installer accepted a Bitstream preference, but that intent was
stored only in Builder/Hardware Passport data. It did not reach the persistent
playback preference, runtime policy resolver or actual MPV command. MPV was
therefore launched without the intended `audio-spdif` policy and decoded the
audio to multichannel PCM. Eight active HDMI channels were evidence of a PCM
sink configuration, not evidence of passthrough.

## Frozen audio architecture

The official user policy is binary: `PCM` or `BITSTREAM`. Its single source of
truth is `audio_output_mode` in the existing user configuration. A fresh
installation defaults to `PCM`; the installer no longer asks the user to choose
an audio mode.

PCM means MPV decodes audio and outputs PCM through PipeWire/HDMI. It forces no
passthrough. BITSTREAM requests passthrough for the supported candidate formats
while formats outside that set continue through normal PCM decoding. The frozen
MPV policy is:

```text
--audio-spdif=ac3,eac3,dts,dts-hd,truehd
```

PipeWire remains the audio server. There is no direct-ALSA bypass and no
receiver-, GPU- or machine-specific rule.

## Frozen UI and diagnostic semantics

- Requested PCM immediately means `Passthrough numérique : Inactif`; this is a
  deterministic policy statement and does not claim a playback observation.
- Requested BITSTREAM without a matching runtime observation means
  `Passthrough numérique : Indéterminé`.
- Requested BITSTREAM with real MPV SPDIF evidence means
  `Passthrough numérique : Actif`.
- A channel count, HDMI presence or configured `audio-spdif` option alone never
  proves active bitstream.

`AUDIO_POLICY` records requested policy, source codec when known, resolution,
reason and effective `audio-spdif`. `AUDIO_POLICY_OBSERVED` is emitted from the
real MPV log for relevant MEDIA and DVD playback paths. Observation history is
preserved for support diagnostics.

## Physical qualification evidence

Environment supplied and operated by Steve:

- Fedora 44 KDE / Wayland
- HDMI audio path
- Denon AVR
- DVD: *Destination Graceland*, AC3 / Dolby Digital

Final smoke results:

- BITSTREAM selection and immediate AUDIO-page refresh: PASS
- DVD playback in BITSTREAM: PASS
- AVR identified Dolby Digital and did not show MULTI IN: PASS
- AUDIO after playback showed requested BITSTREAM and passthrough Active: PASS
- PCM selection and immediate requested-mode refresh: PASS
- PCM immediately showed passthrough Inactive: PASS
- Same DVD in PCM produced AVR MULTI IN: PASS
- QUITTER restored KDE: PASS
- `openhtpc doctor`: Overall READY

## Exact qualified scope

Physically qualified:

- multichannel PCM through HDMI/PipeWire;
- AC3 / Dolby Digital bitstream;
- persistent PCM ↔ BITSTREAM switching;
- immediate AUDIO UI refresh and lower action dock;
- DVD runtime observation and truthful Active/Inactive diagnostics;
- DVD playback and KDE restoration.

Runtime support is present for E-AC3, DTS, DTS-HD and TrueHD, but those codecs
have not received explicit physical AVR qualification and must not be described
as physically qualified.

| Codec | Runtime policy | Physical AVR qualification |
|---|---|---|
| AC3 / Dolby Digital | Supported/configured | PASS |
| E-AC3 | Supported/configured | PENDING |
| DTS | Supported/configured | PENDING |
| DTS-HD MA | Supported/configured | PENDING |
| Dolby TrueHD | Supported/configured | PENDING |

## Freeze statement

The public `v1.1.0-rc3` tag, commit, archive and history remain unchanged.
Plugin Framework V1 P1 at `3b00a907e8a6933867b9dccc5498b06b6d74ee88`
is independent and is not part of this release. No P2 or Cinema Enhancement
work is included.

Final status: `AUDIO_P0_PHYSICALLY_QUALIFIED` / `QUALIFIED_AND_FROZEN`.
