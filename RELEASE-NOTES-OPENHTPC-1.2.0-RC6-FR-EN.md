# OPENHTPC 1.2.0 RC6

Pre-release: **Yes**  
Physical validation: **PASS (Reference bench)**

## Fixed
- MEDIA BITSTREAM now reuses the shared PipeWire HDMI IEC958 preparation mechanism.
- Automatic recovery when the HDMI PipeWire sink is recreated with only PCM/DTS/AC3 enabled.
- EAC3, TrueHD and DTS-HD capabilities are restored dynamically before MEDIA bitstream playback.

## Preserved
- MEDIA PCM behavior unchanged.
- Protected Optical functional behavior unchanged.
- Dynamic sink resolution; no hardcoded PipeWire node ID.

## Physical reference validation
- MEDIA PCM: **PASS**
- E-AC-3 JOC Dolby Atmos: **PASS**
- TrueHD Dolby Atmos: **PASS**
- Reference bench only (Fedora 44 KDE Wayland, Intel Core i5-6500, Intel Arc A310 -> Denon AVR-X1800H -> LG OLED).

## Français

### Corrigé
- MEDIA BITSTREAM réutilise désormais le mécanisme partagé de préparation PipeWire HDMI IEC958.
- Récupération automatique lorsque le sink HDMI PipeWire est recréé avec uniquement PCM/DTS/AC3 activés.
- Les capacités EAC3, TrueHD et DTS-HD sont restaurées dynamiquement avant la lecture bitstream MEDIA.

### Préservé
- Comportement MEDIA PCM inchangé.
- Comportement fonctionnel Protected Optical inchangé.
- Résolution dynamique du sink ; aucun node ID PipeWire codé en dur.

### Validation physique de référence
- MEDIA PCM : **PASS**
- E-AC-3 JOC Dolby Atmos : **PASS**
- TrueHD Dolby Atmos : **PASS**
- Banc de référence uniquement (Fedora 44 KDE Wayland, Intel Core i5-6500, Intel Arc A310 -> Denon AVR-X1800H -> LG OLED).
