# OPENHTPC 1.1 RC3 — Release notes / Notes de version

## Français

OPENHTPC 1.1 RC3 stabilise la base home-cinema locale pour Fedora 44 KDE
Plasma sous Wayland. Cette RC repose sur la baseline dev38 physiquement
qualifiée et gelée.

### Points principaux

- Interface canapé et cycle de vie appliance OPENHTPC stabilisés.
- Gestion graphique de zéro à plusieurs Media Sources accessibles comme
  chemins locaux, avec ajout, navigation et retrait non destructif.
- Lecture des médias locaux, y compris les noms de fichiers longs et complexes.
- Détection, fiche détaillée, métadonnées et lecture DVD qualifiées.
- Préférences globales de lecture persistantes pour le mode vidéo, l'audio et
  les sous-titres.
- OSD UTF-8 concis indiquant mode vidéo, audio et sous-titres.
- Mode PURE par défaut et mode CINÉMA AUTO fondé sur le catalogue de recettes
  qualifiées et la Performance Map locale. CINÉMA AUTO peut légitimement
  résoudre vers PURE; il n'implique pas systématiquement un shader.
- Correction de FRANÇAIS COMPLETS sur DVD: l'inventaire DVD qualifié autorise
  désormais la sélection française du titre effectivement lu par MPV.
- Correction du rafraîchissement de la fiche DVD après changement du mode
  vidéo global depuis SYSTÈME → LECTURE.
- Retour fiable vers KDE Plasma après QUITTER.

### Limitations connues

- Plateforme qualifiée: Fedora 44 KDE Plasma sous Wayland.
- La sélection automatique audio Français/TrueFrench et la sélection
  automatique des sous-titres forcés ne sont pas qualifiées.
- Blu-ray et UHD peuvent être détectés et représentés, mais leur lecture
  physique complète n'est pas qualifiée dans cette base.
- Jellyfin, Plex, NAS et streaming ne sont pas intégrés au Core.
- HDR vers SDR/C6 n'est pas implémenté.
- Les sources réseau doivent déjà être montées et accessibles comme chemins
  locaux; OPENHTPC ne configure pas lui-même SMB/NFS.

### Intégrité et signature

L'archive RC3 est fournie avec un SHA256. Il n'y a pas de signature numérique
pour RC3, par décision produit: `RELEASE_SIGNING_DEFERRED_BY_PRODUCT_DECISION`.

## English

OPENHTPC 1.1 RC3 stabilizes the local-first home-theater base for Fedora 44
KDE Plasma on Wayland. This release candidate is built from the physically
qualified and frozen dev38 baseline.

### Highlights

- Stabilized couch UI and OPENHTPC appliance lifecycle.
- Graphical management of zero to multiple Media Sources exposed as local
  filesystem paths, with safe add, browse and non-destructive removal flows.
- Local-media playback, including long and complex filenames.
- Qualified DVD detection, detail view, metadata and playback.
- Persistent global playback preferences for video mode, audio and subtitles.
- Concise UTF-8 OSD showing video mode, audio and subtitle state.
- PURE remains the default; CINEMA AUTO uses the qualified Recipe Catalogue
  and the local Performance Map. CINEMA AUTO may correctly resolve to PURE and
  does not imply that a shader is always applied.
- Fixed FULL FRENCH subtitles on DVD: qualified DVD inventory now enables MPV
  to select a French subtitle track for the title actually being played.
- Fixed DVD detail refresh after changing the global video mode under
  SYSTEM → PLAYBACK.
- Reliable return to KDE Plasma after QUIT.

### Known limitations

- Qualified platform: Fedora 44 KDE Plasma on Wayland.
- Automatic French/TrueFrench audio selection and automatic forced-subtitle
  selection are not qualified.
- Blu-ray and UHD may be detected and represented, but complete physical
  playback is not qualified in this Base.
- Jellyfin, Plex, NAS and streaming are not integrated into Core.
- HDR-to-SDR/C6 is not implemented.
- Network sources must already be mounted and accessible as local paths;
  OPENHTPC does not configure SMB/NFS mounts.

### Integrity and signing

RC3 ships with a SHA256 integrity file. RC3 is not digitally signed by product
decision: `RELEASE_SIGNING_DEFERRED_BY_PRODUCT_DECISION`.
