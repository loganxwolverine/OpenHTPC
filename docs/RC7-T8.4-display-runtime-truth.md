# T8.4 — passive display runtime truth

Pre-flight, 2026-09-09, before implementation. Baseline 8cd6901.

## Existing path and defects

`openhtpc-ui.system_page_png(display)` reads `system-model.build().display`.
The model formerly consumed the capability snapshot's `display.active_output`.
`capabilities.generate()` queried KScreen text or fell back to DRM sysfs.
The installed snapshot recorded KScreen exit -6 and used sysfs fallback.
The model then incorrectly substituted the first available mode for current mode.
The process-context resolver successfully recovered the current same-user KDE
session; read-only KScreen JSON and text worked in that environment.

| Row | Existing source / reason for unknown | Proven authority / observed pre-flight |
|---|---|---|
| Sortie active | sysfs connected/enabled fallback | KScreen connected + enabled, unique output: HDMI-A-6 |
| Résolution | first available sysfs mode (not current proof) | KScreen currentModeId -> exact mode: 3840x2160 |
| Fréquence | sysfs mode has no refresh | same current mode: 60 Hz |
| Échelle KDE | absent in sysfs fallback | KScreen scale: 2 (200%) |
| Profondeur | unavailable; text parser previously mistook automatic limit for actual depth | NOT PROVABLE: maxBpc and automatic (10) are limits, not link measurements |
| HDR compatible | always UNKNOWN | exact connected card1-HDMI-A-6 EDID, 256 bytes, valid checksums, CTA HDR block 060d01: supported |
| HDR actuel | absent in sysfs fallback | KScreen hdr=false: disabled |
| Pipeline validé | collector hardcodes UNVALIDATED; no connector-bound validation ledger | ARCHITECTURALLY AMBIGUOUS; remain unknown |
| Session | hardcoded Wayland (KWin) | existing same-user graphical context resolves Wayland |
| Résolveur | hardcoded Phase A label | canonical passive KDE/KScreen collector |
| Rafraîchissement automatique | hardcoded presentation, no observed switching/validation fact | remain unknown; no behavior change |

## Authorities and boundaries

KScreen `-j` invokes GetConfigOperation and returns `currentModeId`, modes,
scale, connected/enabled, and HDR state. No output-setting command is used.
See [KDE doctor source](https://raw.githubusercontent.com/KDE/libkscreen/Plasma/6.6/src/doctor/doctor.cpp).
Its `automatic (10)` display is computed from power preference/limits, not an
actual link-depth measurement. Therefore this tranche publishes no current bpc.

EDID parsing is deliberately narrow: validate header, declared length, every
checksum and CTA block boundaries; recognize positive HDR EOTF evidence only.
Missing HDR evidence remains UNKNOWN, not a claim that HDR is impossible.
See [Linux HDR metadata parser](https://raw.githubusercontent.com/torvalds/linux/master/drivers/gpu/drm/drm_edid.c)
(`eotf_supported`, `drm_parse_hdr_metadata_block`). EDID does not supply any
current mode, refresh, scale, depth or HDR-enabled value.

The current page queries the existing canonical collector at build time, so a
saved Passport/capability snapshot cannot masquerade as current display state.
Failure yields unknown. One enabled, connected compositor output is required;
multiple outputs yield no selected output. EDID association requires exactly
one DRM connector with the exact connector name and connected status; no
cross-card or cross-output union. No new GPU topology authority is introduced.

`collect_display` accepts runner/sysfs/proc roots; model accepts an explicit
snapshot for tests. Normal callers keep the same four positional arguments.
The historical text parser remains available for existing consumers, but is
not the current page authority. Rendering/decode/audio/optical policy is unchanged.

## Post-update session proof

Normal update stops the OPENHTPC controller. On this salon KWin's environment
is not readable and Plasma Shell is not running. `/usr/bin/plasma-keyboard`
(PID 2062 at observation) is a same-UID direct child of `kwin_wayland` (PID 1985)
and exposes the existing Wayland socket environment. The existing graphical
context helper now accepts that verified executable/parent/UID relation as a
last fallback. It neither invents a socket nor starts a session. A synthetic
proc test rejects an unrelated parent. Post-update query: HDMI-A-6,
3840x2160, 60 Hz, scale 2, HDR off, positive HDR EDID evidence.
