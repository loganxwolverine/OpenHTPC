# RC4 Patina — known limitations (2026-11-14)

- Diagnostic bundles created by the optional Validator remain local by default; uploading requires OPENHTPC_VALIDATOR_UPLOAD_OPT_IN=1 and an explicitly configured OPENHTPC_VALIDATOR_UPLOAD_SHARE.
- Poster wall is alphabetical. A separate Recently Added view and side filters
  for DVD-like / 1080p / UHD sources are outside RC4.
- TMDB credits are returned only after an authorized metadata refresh. Existing
  details snapshots without `credits` may display unknown cast/director until
  refreshed; no unattended API refresh or paid inference is enabled.
- Interactive DVD/Blu-ray menus are not qualified in RC4.
- Controller navigation within the Add Media Source form was previously
  reported as problematic and is not claimed as fixed.
- Poster-derived blurred film-card backdrops may vary in visual suitability.
- The salon SD/Magnificence and resume qualification is real but does not
  certify all GPUs, Dolby Vision pipelines, controllers or media containers.
- Release screenshot artwork can contain third-party movie posters; the owner requested their separate illustration in the RC4 release;
  all third-party artwork rights remain with their owners.

# Known limitations — OPENHTPC 1.2.0

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
