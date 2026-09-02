# Known limitations — OPENHTPC 1.2.0 RC1

- Fedora 44 KDE Plasma on Wayland is the currently qualified platform.
- Automatic French/TrueFrench audio selection is not qualified.
- Automatic forced-subtitle selection is not qualified.
- Protected optical dependencies added after Hardware Passport/runtime
  snapshot generation currently require `openhtpc rebuild-passport` before
  the refreshed capability is published.
- UHD dropped frames observed on ZimaBoard 2 remain a deferred platform and
  performance limitation.
- Jellyfin, Plex and NAS plugins are not integrated.
- HDR-to-SDR phase C6 is not implemented.
- Plasma Bigscreen is not the canonical OPENHTPC desktop/session platform.
- Plasma Login Manager behavior with Fedora 44 and NVIDIA driver 610.57.04
  required the externally configured SDDM workaround on the NVIDIA validator.
  SDDM is not an OPENHTPC installer requirement.
- Startup with a large mounted CIFS source was observed at approximately 14
  seconds; future MEDIA performance polish remains non-blocking backlog work.
- Optical titles may contain technical suffixes or atypical metadata. A future
  separately specified feature may cautiously normalize known suffixes such as
  `_D1`…`_D4` and `_DISC1`/`_DISC2` before TMDb lookup without truncating
  legitimate titles.

Unsupported or unknown capability evidence must not be interpreted as
validated playback support.
