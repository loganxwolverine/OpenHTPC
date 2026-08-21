# Known limitations — OPENHTPC 1.1 Public Candidate R2

- Fedora 44 KDE Plasma on Wayland is the currently qualified platform.
- Automatic French/TrueFrench audio selection is not qualified.
- Automatic forced-subtitle selection is not qualified.
- Blu-ray and UHD media may be detected and represented in the interface, but
  complete physical Blu-ray/UHD playback is not qualified.
- Jellyfin, Plex and NAS plugins are not integrated.
- HDR-to-SDR phase C6 is not implemented.
- Plasma Bigscreen is not the canonical OPENHTPC desktop/session platform.
- Startup with a large mounted CIFS source was observed at approximately 14
  seconds; future MEDIA performance polish remains non-blocking backlog work.
- Optical titles may contain technical suffixes or atypical metadata. A future
  separately specified feature may cautiously normalize known suffixes such as
  `_D1`…`_D4` and `_DISC1`/`_DISC2` before TMDb lookup without truncating
  legitimate titles.

Unsupported or unknown capability evidence must not be interpreted as
validated playback support.
