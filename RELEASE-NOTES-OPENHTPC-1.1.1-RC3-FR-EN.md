# OPENHTPC 1.1.1 RC3 — Audio P0

Pre-release: **Yes**

## Français

OPENHTPC 1.1.1 RC3 ajoute une politique audio simple et persistante dans
SYSTÈME → AUDIO : **PCM** ou **BITSTREAM**.

### Nouveautés

- PCM est le mode sûr par défaut d’une installation fraîche.
- Le mode audio se configure après installation depuis l’interface couch.
- L’ancien choix audio de l’installateur a été supprimé.
- DVD et MEDIA utilisent la même politique audio persistante.
- La page AUDIO se rafraîchit immédiatement après un changement de mode.
- Les actions PCM, BITSTREAM et RETOUR utilisent le dock inférieur.
- Les diagnostics distinguent la politique demandée de l’observation MPV
  réelle grâce à `AUDIO_POLICY` et `AUDIO_POLICY_OBSERVED`.

### Qualification physique

AC3 / Dolby Digital est **PHYSIQUEMENT QUALIFIÉ** sur une chaîne Fedora 44
KDE/Wayland → HDMI → AVR Denon. BITSTREAM a produit Dolby Digital sur l’AVR;
PCM a produit le PCM multicanal attendu (`MULTI IN`). La commutation, le
diagnostic Actif/Inactif, le DVD, QUITTER → KDE et Doctor READY ont passé le
smoke final.

E-AC3, DTS, DTS-HD MA et Dolby TrueHD sont présents dans la politique runtime,
mais leur qualification physique AVR est encore **PENDING**.

Cette pré-release descend normalement de `v1.1.0-rc3`. Elle ne modifie ni le
tag ni les artefacts historiques de la RC3 publique.

## English

OPENHTPC 1.1.1 RC3 adds a simple persistent audio policy under SYSTEM → AUDIO:
**PCM** or **BITSTREAM**.

### Changes

- PCM is the safe default for a fresh installation.
- Audio mode is configured after installation from the couch UI.
- The former installer audio-mode question has been removed.
- DVD and MEDIA share the same persistent audio policy.
- The AUDIO page refreshes immediately when the mode changes.
- PCM, BITSTREAM and BACK use the lower action dock.
- Runtime diagnostics distinguish requested policy from real MPV evidence using
  `AUDIO_POLICY` and `AUDIO_POLICY_OBSERVED`.

### Physical qualification

AC3 / Dolby Digital is **PHYSICALLY QUALIFIED** on a Fedora 44 KDE/Wayland →
HDMI → Denon AVR chain. BITSTREAM produced Dolby Digital at the AVR; PCM
produced the expected multichannel PCM (`MULTI IN`). Switching, Active/Inactive
diagnostics, DVD playback, quit-to-KDE and Doctor READY passed the final smoke.

E-AC3, DTS, DTS-HD MA and Dolby TrueHD are present in the runtime policy, but
their physical AVR qualification remains **PENDING**.

This pre-release is a normal descendant of `v1.1.0-rc3`. It does not alter the
public RC3 tag or historical artifacts.
