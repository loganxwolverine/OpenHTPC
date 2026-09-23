# OPENHTPC 1.2.0 RC8

Pre-release: **Yes**
Reference physical validation: **PASS**

## English

### Media Foundation
- Persistent local SQLite media database with incremental scanning and normalized probing.
- Cached movie posters and dedicated movie detail pages.
- Unidentified living-room workflow for unmatched media.
- Human-controlled candidate acceptance, rejection and manual TMDb search.

### Responsive couch UI
- Library updates now run asynchronously.
- Identity enrichment now runs asynchronously.
- Manual TMDb searches now run asynchronously.
- Flex remains usable while background work is running.
- A small live banner reports running, success and failure states.

### International titles
- Open Sans remains the primary OPENHTPC interface font.
- Noto Sans CJK is used automatically as a fallback when the primary font lacks a glyph.
- Korean, Japanese and Chinese original titles can therefore render correctly instead of square placeholders.

### Reference physical qualification
Validated on:
- Fedora 44 KDE Plasma / Wayland
- AMD Ryzen 3 PRO 3200GE
- Radeon Vega 3
- Denon AVR-X1800H

The qualification covered the complete RC8 Media Foundation path through Dev6C3U, including incremental library updates, unidentified media, manual matching, asynchronous TMDb search, live activity feedback and a real Korean original title.

### Preserved from RC7
- Automatic frame-rate matching.
- Display-mode restoration and runtime synchronization.
- HDMI PCM / bitstream lifecycle improvements.
- Existing local media playback behavior.

### Network behavior
Normal library browsing and playback remain local-first. Network access is used only for the media enrichment/search operations that require TMDb.

## Français

### Media Foundation
- Base locale SQLite persistante avec scan incrémental et analyse normalisée des médias.
- Cache local des affiches et fiches film dédiées.
- Vue À identifier utilisable depuis le canapé pour les médias non reconnus.
- Acceptation, rejet et recherche TMDb manuelle sous contrôle de l'utilisateur.

### Interface canapé réactive
- La mise à jour de la médiathèque est désormais asynchrone.
- L'enrichissement d'une fiche est désormais asynchrone.
- La recherche manuelle TMDb est désormais asynchrone.
- Flex reste utilisable pendant les traitements en arrière-plan.
- Une petite bannière indique l'activité, la réussite ou l'échec.

### Titres internationaux
- Open Sans reste la police principale de l'interface OPENHTPC.
- Noto Sans CJK est utilisée automatiquement en secours lorsqu'un glyphe manque.
- Les titres originaux coréens, japonais ou chinois peuvent ainsi s'afficher correctement au lieu de petits carrés.

### Validation physique de référence
Validé sur :
- Fedora 44 KDE Plasma / Wayland
- AMD Ryzen 3 PRO 3200GE
- Radeon Vega 3
- Denon AVR-X1800H

La qualification couvre tout le parcours Media Foundation RC8 jusqu'à Dev6C3U : mise à jour incrémentale, médias à identifier, résolution manuelle, recherche TMDb asynchrone, bannière d'activité et affichage réel d'un titre original coréen.

### Préservé depuis RC7
- Adaptation automatique de la fréquence d'affichage.
- Restauration du mode d'affichage et synchronisation du runtime.
- Améliorations du cycle de vie audio HDMI PCM / bitstream.
- Comportement existant de la lecture des médias locaux.

### Réseau
La navigation dans la médiathèque et la lecture restent local-first. Le réseau n'est utilisé que pour les opérations d'enrichissement/recherche qui nécessitent TMDb.
