<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.2.0 RC6 — Physical Qualification Report

## 1. Release Identity & Artifact Provenance

- **Version**: `1.2.0-rc6`
- **Build**: `public-release-1.2.0-rc6`
- **Origin Qualified Commit**: `c34d8a166842707a19628bf234f8dafb2edd7c12`
- **Physical Test Artifact**: `artifacts/OpenHTPC-1.2.0-RC6.tar.gz`
- **Artifact SHA-256**: `506205d7dd47b2ae006380c2dcf9376ed9284acbbcf58fe8dc568b12d128e46b`
- **Artifact Size**: `114030942` bytes

## 2. Reference Bench Configuration

- **Operating System**: Fedora 44 KDE Plasma / Wayland
- **CPU**: Intel Core i5-6500
- **GPU (HDMI output)**: Intel Arc A310
- **Audio Path**: Intel Arc A310 HDMI -> Denon AVR-X1800H -> LG OLED
- **Audio Stack**: PipeWire / WirePlumber
- **OPENHTPC Identity**: `1.2.0-rc6` (`public-release-1.2.0-rc6`)
- **Installation Verification**: PASS
- **`openhtpc version`**: `1.2.0-rc6`
- **`openhtpc doctor`**: `Overall READY`

## 3. Physical Test 1 — MEDIA PipeWire IEC958 Recovery

Following a PipeWire/WirePlumber restart, the active HDMI sink node returned to the restricted default state:

- **Sink Node ID**: `68`
- **Effective IEC958 Codecs (Before)**: `PCM`, `DTS`, `AC3`
- **Action**: MEDIA BITSTREAM playback initiated without manual `pw-cli` mutation.
- **Effective IEC958 Codecs (After)**: `PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`
- **Film Start**: PASS
- **Audio Output**: PASS
- **Denon AVR Display**: `ATMOS`
- **Result**: **PHYSICAL PASS**

*Conclusion*: Validates the core RC6 mechanism. MEDIA BITSTREAM automatically and dynamically enriches the effective PipeWire HDMI sink when recreated in the restricted default state.

## 4. Physical Test 2 — MEDIA PCM Non-Regression

Following an additional PipeWire restart and sink recreation:

- **Sink Node ID**: `65`
- **Effective IEC958 Codecs (Before)**: `PCM`, `DTS`, `AC3`
- **Action**: OPENHTPC MEDIA playback initiated in `PCM` mode.
- **Film Start**: PASS
- **Audio Output**: PASS
- **Denon AVR Display**: `MULTI IN`
- **Effective IEC958 Codecs (After)**: `PCM`, `DTS`, `AC3` (`EAC3`, `TrueHD`, `DTS-HD` absent)
- **Result**: **PHYSICAL PASS**

*Conclusion*: MEDIA PCM performs no IEC958 HD preparation. The execution contract (`SKIPPED / PCM_MODE`) is physically consistent and confirmed.

## 5. Physical Test 3 — E-AC-3 JOC Dolby Atmos Passthrough

- **Media**: *Alien Romulus* (2024)
- **Audio Track**: English E-AC-3 JOC / Dolby Atmos
- **Sink Node ID**: `65`
- **Effective IEC958 (Before)**: `PCM`, `DTS`, `AC3`
- **OPENHTPC Audio Mode**: `BITSTREAM`
- **Film Start**: PASS
- **Audio Output**: PASS
- **Denon AVR Display**: `ATMOS`
- **Effective IEC958 (After)**: `PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`
- **Result**: **PHYSICAL PASS**
- **Qualification**: E-AC-3 JOC Dolby Atmos passthrough physically qualified on the reference bench.

## 6. Physical Test 4 — TrueHD Dolby Atmos Passthrough

Following a new PipeWire sink recreation:

- **Sink Node ID**: `61`
- **Effective IEC958 (Before)**: `PCM`, `DTS`, `AC3`
- **Media**: *Pacific Rim Uprising*
- **Audio Track**: English TrueHD Atmos 7.1
- **OPENHTPC Audio Mode**: `BITSTREAM`
- **Film Start**: PASS
- **Audio Output**: PASS
- **Denon AVR Display**: `ATMOS`
- **Effective IEC958 (After)**: `PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`
- **Result**: **PHYSICAL PASS**
- **Qualification**: TrueHD Dolby Atmos passthrough physically qualified on the reference bench.

## 7. Dynamic Sink Resolution Evidence

During the test sequences, dynamic PipeWire sink resolution encountered multiple real node IDs:

- `68`
- `65`
- `61`

None of these IDs were hardcoded or baked into the software fix. Dynamic sink resolution is confirmed as **PHYSICALLY OBSERVED = PASS** on the reference platform.

## 8. Physical Infrastructure vs. Software Defect Isolation

Internal qualification notes:
- A portion of Atmos playback failures observed prior to RC6 was traced to a physically defective / unreliable HDMI cable.
- Following cable remediation, LibreELEC confirmed `ATMOS` passthrough on identical hardware, proving that the physical chain (`Intel Arc A310 -> HDMI -> Denon AVR-X1800H`) is capable of Bitstream HD / Atmos transmission.
- The OPENHTPC software defect was distinct: MEDIA did not invoke dynamic IEC958 preparation.
- RC6 fixes the software defect. The physical cable fault and software recovery mechanisms remain strictly isolated.

## 9. Qualification Scope & Boundaries

Strict adherence to qualification taxonomy:
$$\text{DETECTED} \neq \text{SUPPORTED} \neq \text{PHYSICALLY QUALIFIED}$$

`PHYSICAL_QUALIFICATION = PASS` is established strictly for the following tested scope:
- MEDIA PCM mode;
- MEDIA BITSTREAM mode;
- Dynamic PipeWire IEC958 recovery;
- Initial restricted sink (`PCM`, `DTS`, `AC3`) -> dynamic enrichment to (`PCM`, `DTS`, `AC3`, `EAC3`, `TrueHD`, `DTS-HD`);
- E-AC-3 JOC Dolby Atmos passthrough;
- TrueHD Dolby Atmos passthrough;
- Reference bench configuration described above.

**Explicit non-claims**:
- Universal Dolby Atmos on Linux is **not** claimed.
- Compatibility with all AVR models is **not** claimed.
- Compatibility with all GPU vendors / drivers is **not** claimed.
- Compatibility with all Linux distributions is **not** claimed.
- Universal UHD Blu-ray compatibility is **not** claimed.
- Unexercised audio codecs and hardware paths are **not** claimed as physically qualified.

## 10. Protected Optical Baseline Status

- Protected Optical functional behavior is unchanged by RC6.
- Software regression gates: **PASS** (`816/816`).
- Historical RC5 physical qualification remains valid historical baseline evidence.
- Protected Optical was not retested physically during this MEDIA qualification sequence.

## 11. Summary Matrix

| Scope | Reference Bench Result | Status |
|---|:---:|:---:|
| MEDIA PCM Passthrough Isolation | `MULTI IN` (Sink unchanged) | **PASS** |
| MEDIA Dynamic IEC958 Preparation | `[PCM DTS AC3 EAC3 TrueHD DTS-HD]` | **PASS** |
| E-AC-3 JOC Dolby Atmos | `ATMOS` | **PASS** |
| TrueHD Dolby Atmos | `ATMOS` | **PASS** |
| Dynamic Sink Resolution | IDs 68, 65, 61 resolved | **PASS** |
| Protected Optical Software Regression | 100% test pass | **PASS** |

**OVERALL RC6 PHYSICAL REFERENCE QUALIFICATION = PASS**
