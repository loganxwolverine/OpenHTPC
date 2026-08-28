# OPENHTPC 1.1.3 RC1 — Qualification record

Version: `1.1.3-rc1`  
Build: `public-release-1.1.3-rc1`  
Tag target after explicit publication authorization: `v1.1.3-rc1`

The RC1 product content is the frozen, physically qualified Dev16 baseline. RC
assembly changes release identity, validation tooling, reports, notes, and
artifact metadata only.

## Automated qualification

- Dev16 full regression: 314/314 PASS
- RC assembly focused release gate: recorded by the RC builder report
- RC assembly canonical full regression: recorded by the RC builder report

## Physical qualification

- Ryzen Dev15 → Dev16 update: PASS
- Cached MEDIA/Dvd submenu, remove/re-add `/home/steve/media`, immediate
  Alerte.mkv without OPENHTPC restart: PASS
- Alerte image, audio, seek, and return to MEDIA: PASS
- “300” Blu-ray-source MEDIA file: PASS
- “Romulus UHD” MEDIA file: PASS
- Optical refresh followed by MEDIA replay: PASS
- QUITTER → KDE: PASS
- Fedora reboot/autostart: PASS
- Fresh Fedora 44 KDE installation on ZimaBoard 2: PASS
- Doctor: READY
- Network MEDIA source: PASS
- Perfect Storm DVD detection, TMDb metadata, and playback: PASS
- Fresh-install reboot/autostart: PASS

The “300” and “Romulus UHD” results qualify media-file playback only. They do
not qualify protected Blu-ray/UHD optical-disc playback.

## Publication boundary

No Git tag, GitHub release, remote apply, or public release is authorized by
this assembly mandate.
