# OPENHTPC 1.3.2 RC4 — Patina

**Notes de publication RC4 / RC4 prerelease notes**
Version : `v1.3.2-rc4`
État : mur, lecture SD/reprise et enrichissement TMDB vérifiés sur le salon Fedora 44 KDE le 14 novembre 2026.

## Français

### Changements réellement livrés

- **UX-M1/M2 — Médiathèque** : mur d'affiches navigable à la manette, ordre alphabétique A–Z, fiche film accessible directement ; cadence de répétition directionnelle validée **420 ms au démarrage / 120 ms entre répétitions**. Grille sans activation préalable du mode bêta, comportement de repli si catalogue vide ou sans titres identifiés.
- **UX-F1 — Fiche enrichie** : genres, note TMDB, synopsis, caractéristiques vidéo (résolution et codec), information de colorimétrie SDR/HDR/Dolby Vision lorsqu'elle est connue, et arrière-plan bokeh issu de l'affiche. Les champs réalisation et casting **s'affichent uniquement lorsque les données figurent dans l'instantané des crédits du fournisseur**.
- **P0 V5.2 — Reprise de lecture** : fenêtre de décision **Reprendre / Depuis le début / Retour** pour une lecture effectivement interrompue avant 90 % ; enregistrement de la position à l'arrêt volontaire, sans modifier les anciens checkpoints à l'installation.
- **Lecture et Magnificence** : lancement MPV corrigé, rendu Magnificence SD pour sources PAL de résolution voisine du DVD ; sur les fichiers **4:3 en Magnificence**, remplissage de la dalle 16:9 par recadrage contrôlé (sans déformation), sans imposer ce recadrage aux films 16:9, HD/UHD ou aux menus de disques.
- **Installation/mise à jour** : composants du mur, de la fiche et de la reprise intégrés au manifeste et aux scripts gérés ; procédures de sauvegarde et de restauration disponibles.

### Limites connues et conditions

- **Confidentialité :** les archives de diagnostic Validator restent locales par défaut ; un transfert exige une destination et une activation explicites. Les captures de démonstration sont fournies séparément à la demande du propriétaire ; les jaquettes de films restent la propriété de leurs ayants droit.

- **Réalisation et casting :** le fournisseur inclut désormais `append_to_response=credits` dans **la requête de détails existante**, sans second appel. Sur le salon de qualification, **119 des 140 présentations** ont été enrichies avec succès le 14 novembre, sans erreur, sous plafond autorisé ; **21 instantanés restent sans crédits**. Le mur reconstruit affiche des noms de réalisateur sur **113 des 135 fiches identifiées** et des acteurs sur **115/135**. Ce sont des mesures propres à ce salon, pas des garanties pour toute médiathèque. Aucune actualisation réseau n'est lancée automatiquement ; les anciennes fiches non enrichies peuvent toujours indiquer « Non renseigné ».
- **Vues de classement :** pas de vue séparée « Récemment ajoutés » ni de filtres latéraux « Proche DVD / 1080p / UHD » dans cette RC. La médiathèque principale est classée A–Z ; les autres vues restent à développer.
- **Menus DVD/Blu-ray interactifs :** non annoncés comme fonctionnalité RC4.
- **Ajout de source à la manette :** limitation d'ergonomie précédemment signalée, non déclarée corrigée ici.
- La réussite du test sur deux films PAL SD et de la reprise sur le salon ne certifie pas toutes les combinaisons GPU, écran, Dolby Vision ou codecs.

### Validation et distribution

- Installation et mises à jour ponctuelles sur Fedora 44 KDE, salon `.229` ; tests utilisateur confirmés le **14 novembre 2026** : mur d'affiches, plein écran Magnificence sur deux films basse résolution et reprise fonctionnelle.
- Comparaison SHA256 du code installé : **214/214 composants gérés conformes** au candidat `rc4-uxf1-credits-complete-isolated-20261114` après l'installation du correctif TMDB. La préparation ajoute une sécurisation du Validator (diagnostics conservés localement par défaut) et actualise les documents ; la lecture, la reprise, le mur d’affiches, les fiches et le binaire Flex validés sur le salon restent inchangés.
- Trois captures 1920×1080 illustrent le mur, sa navigation et une fiche : elles ont été réalisées en QA SDL hors écran sur le M910x (pas une recette physique de manette) et sont jointes séparément à la release, à la demande du propriétaire. Jaquettes et visuels des films : droits réservés à leurs ayants droit.
- **Version candidate distribuée sous le tag `v1.3.2-rc4`.** Vérifier l’archive et son SHA256 téléchargés depuis la page officielle GitHub.

## English

### Delivered changes

- **UX-M1/M2:** gamepad-friendly alphabetical poster wall; directional repeat timing **420 ms initial / 120 ms interval**. No beta flag required; fallback for empty or unidentified libraries.
- **UX-F1:** film details with genres, TMDB rating, synopsis, video codec/resolution, known SDR/HDR/Dolby Vision metadata and poster-derived bokeh. Director and cast are displayed **only when provider credits are actually available**.
- **P0 V5.2:** Resume / Start over / Back choice after a qualified interrupted viewing; saved position on voluntary exit.
- **Playback/Magnificence:** MPV launch fixed; PAL SD 4:3 films use aspect-preserving crop-to-fill in Magnificence, without imposing the crop on 16:9, HD/UHD or disc menus.
- **Installer/update:** poster wall, film card and resume components are explicitly included in the managed manifest.

### Known limitations

- **Privacy:** optional Validator logs stay local by default; an explicit opt-in and destination are required for uploading. Illustrative QA screenshots with third-party poster artwork are attached separately at the owner's request, not included in the source archive.

- The provider adds `append_to_response=credits` to the **same movie-details request**, with no extra call. On the qualified salon, 119/140 records were refreshed successfully, 21 remain pending; the refreshed movie wall displays director names on 113/135 identified cards and cast on 115/135. These counts are machine-specific. No automatic metadata refresh takes place when installing RC4.
- No separate Recently Added or DVD-like/1080p/UHD side-filter view; current wall is alphabetical.
- Interactive DVD/Blu-ray menus and the previously reported source-entry gamepad form issue are **not** claimed as fixed.
- QA screenshots were rendered offscreen; the owner requested them as separate release attachments. Third-party movie poster rights remain with their respective owners.

### Validation and release status

On November 14, 2026 the owner validated the RC4 poster wall, two low-resolution Magnificence movies, resume and the enriched film-card display. The single-request TMDB credits provider is installed and 119 actual metadata refreshes were verified in SQLite (zero failures). Remaining: 21 old records if further refresh is desired. This prerelease includes a tagged source archive, SHA256 checksum and optional illustrative screenshots.

**Release Candidate 4 / Prerelease — `v1.3.2-rc4`.**
