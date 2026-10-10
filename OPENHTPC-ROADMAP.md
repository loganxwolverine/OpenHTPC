# OPENHTPC — Roadmap globale

Dernière mise à jour : 2026-10-10 (Europe/Brussels).
Responsable des décisions et validations physiques : Steve Dehanne.

## Rôle et autorité

Ce document donne une vue globale de l'évolution du projet. Il relie les roadmaps spécialisées, les jalons et les travaux ouverts. Il ne remplace ni le code, ni les tests, ni les preuves de qualification, ni les autorisations d'Autopilot.

Ordre d'autorité : code/tests/artifacts, état de travail validé, documents de qualification/architecture, roadmap, conversations historiques.
Une entrée « prévu » n'autorise pas une implémentation, un commit, un déploiement ou une publication.
Un changement présent dans le dépôt n'établit pas son installation ni sa qualification physique.

## Point de situation vérifié

- Base Git observée à la création : branche `feature/magnificence-sd-auto`, HEAD `6cdaef763c593215550c241e70e13c773ac799d0` (nommage 1.3.0 Patina).
- Le changelog décrit 1.3.0 Patina. Cela ne prouve pas à lui seul une publication publique.
- Travaux 1.3.1 présents dans le worktree, non commité au relevé : stabilisation du cycle MEDIA/Flex, récupération après échec/interruption de mise à jour, recherche manuelle et couverture comportementale.
- Écart documentaire : `OPENHTPC_CURRENT_STATE.json` porte encore le workstream P2, une phase RC5 et un candidat RC7. Il ne décrit pas le jalon Patina ni les travaux 1.3.1. Sa réconciliation est à traiter avec le propriétaire du workstream et le schéma strict ; aucune autorisation ne doit être déduite de cette roadmap pour contourner ses gates.

## Jalons et chantiers

| Chantier | État au 2026-10-10 | Éléments vérifiables / limite | Suite |
| --- | --- | --- | --- |
| Media Foundation et UX 1.2.0 | Documenté comme livré | SQLite, médiathèque, identification, TMDb asynchrone, Unicode, sources réseau montées : CHANGELOG.md | Maintenir les régressions et qualifier les corrections |
| Magnificence / 1.3.0 Patina | Base implémentée, qualifications ciblées documentées | Profils précis + familles prudentes, Pure conservé ; aucune garantie universelle | Qualification continue par GPU/source/sortie |
| A310 CLEAN | Retenu dans le profil précis SD → 2160p | HQDN3D 1.4/1.0/0.05/0.05 + vaapi-copy, FSRCNNX-16 + Krig + Vibrance légère | Vérifier/documenter l'endurance de la chaîne finale complète |
| A310 DETAIL additionnel | Écarté pour le profil courant | Adaptive Sharpen, SSimSuperRes, RCAS : gain à distance normale insuffisant pour le coût | Ne pas réintroduire sans décision et nouvelle qualification |
| Stabilisation 1.3.1 | Gates `.67` et `.229` fermés ; identité stable, commit et artifact exact-commit préparés/vérifiés ; publication non autorisée | 2284 PASS, 18 SKIP, 0 FAIL. Audit Hermes terminé. Artifact `OpenHTPC-1.3.1.tar.gz` : devctl verify, métadonnées, checksum et `install.sh --check` PASS ; rapport/sidecar ignorés par Git font autorité pour commit/SHA. `.229` : image Magnificence « top », passthrough AC3 HDMI, fermeture/retour Flex et Santé PRÊT. Limites : identité physique GPU de décodage NOT_PROVEN ; écoute MEDIA `.67` complète et Denon `.67` non requalifiés ; MPEG-2 RX limité par sélection Mesa. | Conserver sans push/tag/publication jusqu'à autorisation séparée ; prochain chantier produit : généralisation du framework plugins |
| Hermes / DeepSeek | Accès et audits lecture seule opérationnels | Snapshots isolés, rapports contradictoires, aucun droit d'implémentation accordé | Comparer chaque finding au code/tests |
| Hermes → CodeGraph direct | Non établi | Faisabilité étudiée ; CodeGraph Fedora reste opérateur-médié | Instance dédiée au même snapshot, si décidée |
| Optique protégée | Architecture gelée, qualifications historiques par candidat | Core/plugin.bluray séparés ; états historiques à distinguer de l'état courant | Réconcilier le suivi avant une nouvelle tranche |
| Framework plugins / modularité | Socle P2 présent, généralisation produit à faire après 1.3.1 | Registre V2, contrats, états et `plugin.bluray` existent ; Système/actions/handlers génériques restent incomplets | Après 1.3.1 : Système → Extensions, contrats génériques, puis plugins DVD menu / extraction / HD DVD |
| GPU legacy / Pascal P2000 | Différé | Pas de profil P2000 promu ; limites pilote/plateforme documentées | Qualification sur plateforme PCIe stable, sans modifier les pilotes Fedora |
| Restauration dépendant de la source | Exploration future | Bruit MPEG-2, sources difficiles ; ne remplace pas les recettes actuelles | Définir une tranche et une qualification séparées |

## Points à examiner, sans décision automatique

1. Réconcilier l'état global et l'ancien état P2/RC5/RC7 sans perdre les gates ou l'historique.
2. Pour la chaîne A310 finale avec CLEAN : compléter les preuves de lecture longue. La session physique de 1 h 09 documentée dans le profil concernait FSRCNNX-8 + Krig, pas la chaîne finale.
3. Confirmer selon les sources le bénéfice des profils LIGHT face à Pure : le classement C2 historique plaçait Pure devant Krig.
4. Distinguer l'objectif de réserve GPU (~25 % préféré) d'une preuve par profil ; le HD630 accepte explicitement une réserve réduite.
5. Vérifier l'ordre effectif des étapes shaders au runtime si une affirmation d'ordre en dépend ; les tests de liste ne prouvent pas l'ordre des hooks.
6. Maintenir les findings Hermes comme avis à vérifier, pas comme modifications autorisées.

Ces points proviennent de documents/code et du rapport contradictoire Magnificence du 2026-10-09. Ils ne rendent pas caduques les validations visuelles réalisées par Steve.

## Documents de référence

- [Changelog](CHANGELOG.md) : changements par version.
- [Roadmap Magnificence](OPENHTPC-MAGNIFICENCE-ROADMAP.md) : profils et qualifications image.
- [Profils Magnificence](payload/assets/magnificence_profiles.json) : chaînes précises et preuves consignées.
- [Connaissances GPU](payload/assets/magnificence_gpu_knowledge.json) : règles de famille et statut des références.
- [Roadmap optique protégée](OPENHTPC-PROTECTED-OPTICAL-ROADMAP.md) : historique spécialisé ; lire les dates/candidats.
- [Roadmap Plugins](OPENHTPC-PLUGIN-ROADMAP.md) : modularité, généralisation P2 et extensions post-1.3.1.
- [État de travail](OPENHTPC_CURRENT_STATE.json) : état machine soumis au schéma ; écart signalé ci-dessus.
- [Contrat agents](AGENTS.md) : limites et obligations.
- [Autopilot](docs/OPENHTPC_AUTOPILOT.md) : orchestration et gates.
- [Hermes auditeur](docs/OPENHTPC_HERMES_AUDITOR.md) : isolation, reviews et limites.

Rapport Magnificence sur Unraid : `/mnt/user/appdata/hermes-agent/reports/openhtpc-magnificence-audit-20261009T103531Z.md`.
Snapshot audité : `openhtpc-magnificence-audit-20261009T103531Z`. Rapport terminé avec code 0 ; aucune qualification visuelle/physique nouvelle n'en découle.

## Maintenance obligatoire

À chaque jalon, changement de priorité, décision acceptée, qualification réussie/échouée, ou nouvelle limite :
- actualiser la ligne concernée et la date de mise à jour ;
- ajouter une entrée datée au journal ci-dessous, avec décision, état et preuve ;
- mettre à jour la roadmap spécialisée si nécessaire ;
- signaler les divergences avec l'état machine ; ne pas changer ses autorisations par simple déduction ;
- distinguer proposé, implémenté, vérifié logiciel, qualifié physique et publié ;
- conserver les décisions antérieures dans le journal plutôt que les effacer.

L'agent chargé du changement maintient cette documentation dans le même lot de travail. Hermes lecture seule remet ses observations à l'opérateur ; il ne modifie pas ce fichier.
Pas de réécriture périodique autonome : la maintenance accompagne les événements réels du projet.

## Journal d'évolution

| Date | Événement / décision | État et preuve |
| --- | --- | --- |
| 2026-10-09 | Création de la roadmap globale à la demande de Steve | Vue initiale issue du dépôt à HEAD 6cdaef7 et du worktree ; état machine ancien signalé |
| 2026-10-09 | Hermes ajouté comme reviewer externe | Accès testé et audits lecture seule ; procédure dans docs/OPENHTPC_HERMES_AUDITOR.md |
| 2026-10-09 | Audit Magnificence reçu | Recommande de conserver la base et de préciser les preuves ; findings consultatifs |
| 2026-10-09 | Stabilisation 1.3.1 observée en cours | Worktree non commité ; aucune qualification finale ni publication affirmée |
| 2026-10-10 | Modularité plugins reconfirmée comme objectif produit | Socle P2 vérifié dans le dépôt ; priorité post-1.3.1 formalisée dans `OPENHTPC-PLUGIN-ROADMAP.md` avec Blu-ray/UHD, extraction disque, HD DVD et menus DVD |
| 2026-10-10 | Vérité Affichage/Audio et adaptation de fréquence DVD corrigées sur le candidat `.67` | 248/248 tests voisins PASS ; sortie audio active séparée de la préférence hors ligne ; S/PDIF reconnu ; cadence `lsdvd` transmise au matcher ; AUTO activé sur `.67`, validation physique du changement/restauration de fréquence encore requise |
| 2026-10-10 | Régression DVD « écran noir jusqu’à → » retrouvée : ordre bitstream/refresh inversé dans le dispatcher | Cause concordante avec l'incident historique du 10/09 : `openhtpc-play-dvd` préparait PipeWire avant le modeset ; correction candidate délègue la décision audio au matcher pour imposer modeset/settle → audio prep → mpv ; 96/96 gate ciblé PASS, déployé sur `.67`, retest physique encore requis ; checkpoint `docs/continuity/2026-10-10-dvd-refresh-audio-ordering.md` |
| 2026-10-10 | Validation physique du cycle DVD 1.3.1 sur `.67` | Steve confirme que le film démarre puis reteste lui-même : PASS. Télémétrie finale : 3840×2160 60→50 Hz vérifié, lecture démarrée, `playback_exit_code=0`, restauration demandée/vérifiée et retour 60 Hz. Le sink S/PDIF `ALC1150 Digital` refusant l'AC3 passthrough via PipeWire, la lecture bascule automatiquement en PCM lorsque le passthrough post-modeset n'est pas prouvé ; la préférence BITSTREAM reste inchangée et un HDMI qualifié conserve le bitstream. |
| 2026-10-10 | Publication multi-GPU corrigée et vérifiée sur `.67` | RX 5700 XT `0000:03:00.0` publie MPEG-2+VP9 seulement ; HD630 `0000:00:02.0` publie H.264/HEVC/Main10/MPEG-2/VP9 ; `display_gpu` et `processing_gpu` correspondent exactement à la RX ; vue globale = union des GPU. Contrôles PCI→PCI tous vrais. |
| 2026-10-10 | Gate de consolidation après correctif audio | 378/378 tests unitaires/régression ciblés PASS en 20,55 s ; `git diff --check` PASS. Aucun commit, tag, push ou release effectué. |
| 2026-10-10 | Reprise depuis le checkpoint, état live plus récent préservé | 5 fichiers de lecture synchronisés sur `.67` avec sauvegarde/empreintes ; 1847 PASS et 15 SKIP explicitement classifiés, 4 fixtures Autopilot rendues hermétiques sans affaiblir les assertions ; audit immuable Hermes reçu, héritage des verrous vers la UI DVD standalone reproduit/corrigé et 125/125 PASS ; aucune installation candidate `.229`, aucun commit/release. Voir `docs/continuity/2026-10-10-131-reprise-qualification.md`. |
| 2026-10-10 | Smoke DVD du lot synchronisé clôturé sur .67 — Rules Of Engagement | Steve confirme image/son, lancement depuis Flex et retour correct à la fiche. Deux sorties DVD code 0 ; dernière restauration 60 Hz vérifiée, aucun lecteur/matcher/dialogue résiduel, trois verrous libres. Lecteur TSSTcorp /dev/sr0 uniquement ; aucun essai sur le HD-DVD /dev/sr1. MEDIA/recherche/CJK et salon .229 restent à qualifier. |
| 2026-10-10 | Anomalie Système → Compatibilité vidéo constatée sur RX5700XT | AMD documente H.264/HEVC decode, mais le `vainfo` RX courant ne les expose pas : `mesa-va-drivers-freeworld` est absent. L'installateur agrège les GPU avant de décider le complément et la HD630 masque le manque AMD ; l'update ne propose pas ce complément. La publication PCI reste fidèle à la pile courante, mais « Non pris en charge » confond indisponibilité backend et incapacité matérielle. Incident ouvert, aucune mutation Fedora effectuée. |
| 2026-10-10 | Correctif multi-GPU VA-API implémenté et UI synchronisée sur `.67` | Décision installateur séparée AMD/Intel, update diagnostique la remédiation différée, libellé « Indisponible via VA-API », test exact Intel complet/AMD incomplet. 313 PASS / 5 SKIP. Scan Média observé IDLE avant synchronisation atomique des deux composants UI. Transaction Fedora simulée : 1 installation + 6 mises à jour Mesa ; non exécutée en attente d'autorisation explicite. |
| 2026-10-10 | Backend VA-API RX5700XT restauré sur `.67` après autorisation | `mesa-va-drivers-freeworld-26.2.4` installé et six paquets Mesa alignés. `vainfo` RX et snapshot canonique par PCI exposent désormais VC-1/H.264/HEVC/Main10 ; Intel et AMD restent séparés. Le packaging est complémentaire : Freeworld perd MPEG-2, que le pilote Fedora expose ; sélection VA-API par codec non implémentée, fallback logiciel conservé. Fedora exige un reboot et Flex garde des mappings Mesa supprimés : validation visuelle et smoke lecture restent ouverts, sans PASS physique inventé. |
| 2026-10-10 | Reboot `.67` et smokes RX post-Mesa terminés | Reboot explicitement autorisé. Passport d'abord refusé STALE, puis reconstruit en environnement Wayland pur après isolement d'un `DISPLAY` SSH sans autorité X11. Prévol PASS, OPENHTPC RUNNING, rendu installé Compatibilité vidéo corrigé. Smokes H.264 8 s et HEVC 10 s : RX5700XT/RADV 26.2.4 prouvée par libplacebo, décodage VA-API observé par `[vd]`, RC=0, retour Flex et 3840×2160 @ 60 Hz, aucun résidu. Pas de PASS physique Steve inventé. |
| 2026-10-10 | Compatibilité vidéo RX5700XT figée | Steve confirme physiquement l'écran corrigé. Jalon `.67` PHYSICALLY_QUALIFIED pour cette page ; VC-1/H.264/HEVC/Main10/VP9 affichés pris en charge, limites MPEG-2/AV1 explicitement distinguées. Cela ne clôt pas la qualification globale 1.3.1 et ne vaut pas autorisation Git/release. |
| 2026-10-10 | Faux `Santé globale : PROBLÈME` corrigé sur `.67` | Doctor était READY : l'image avait été générée avant publication du PID Flex puis conservée en cache. Rendu Système extrait et relancé après publication atomique puis observation bornée du PID enfant exact, sans masquer BLOCKED ni republier le menu ; 118 PASS et diff check propre. Deux fichiers installés avec sauvegarde, image live inspectée `PRÊT`. Confirmation physique Steve et comportement après prochain démarrage encore NOT_PROVEN. |
| 2026-10-10 | MEDIA local `:tracked` qualifié sur `.67` | Steve confirme image et retour Flex sur Terminator 3 ; audio non pleinement qualifié faute de casque. Dispatcher PID 12929 enfant direct de Flex 4664, H.264/VA-API, 58 s, RC=0, PCM observé, même Flex actif et tous verrous libres. Compteur Flex diagnostic corrigé de regex Python vers POSIX : 66 PASS ciblés, suite MEDIA 69 PASS, helper installé retrouve exactement le PID 4664. |
| 2026-10-10 | Recherche manuelle TMDb/topmost qualifiée sur `.67` | Steve confirme toutes les étapes à 100 % sur Dark Knight : saisie devant Flex et résultats corrects. Transaction UI SUCCESS/code 0, quatre propositions publiées, identité laissée UNMATCHED comme demandé, activité IDLE, verrous libres et aucune UI auxiliaire résiduelle. |
| 2026-10-10 | Renderer CJK/Hangul physiquement qualifié sur `.67` | Le DVD inséré était Identity et sa fiche était cohérente. Prévisualisation isolée produite par le renderer installé avec le cache réel Perhaps Love, sans mutation de l'état optique : Steve confirme `杜國威`, `林愛華`, `金城武`, `周迅`, `張學友`, `지진희` sans carrés. Aperçu fermé par PID exact, Flex intact. Pas de nouvelle insertion Perhaps Love revendiquée. |
| 2026-10-10 | Parcours DVD City of Violence physiquement qualifié sur `.67` | Steve confirme recherche manuelle, fiche réelle et caractères coréens, lecture, fermeture et retour Flex. Cache `USER_CONFIRMED_MATCH`; PAL 25→50→60 Hz vérifié, RC=0, zéro drop, rendu RX prouvé, `vaapi-copy` observé avec GPU de décodage physique NOT_PROVEN, PCM observé, aucun résidu et verrous libres. Le garde-fou n'a libéré mpv qu'après son propre marqueur `Exiting... (Quit)`. |
| 2026-10-10 | Gate logiciel final post-qualification `.67` | Périmètre canonique `tests` + Autopilot : 2284 PASS, 18 SKIP, 0 FAIL après relance hors sandbox des 11 cas bloqués uniquement par la création de sockets (98/98 PASS). L'appel initial non borné avait collecté les anciens artifacts et produit 213 collisions de modules ; aucune régression produit n'en est déduite. `git diff --check` PASS. |
| 2026-10-10 | Audit Hermes final du delta et correction VC-1 | Snapshot root-owned read-only, sans `.git`, empreinte avant/après identique ; audit code 0/stderr vide. Aucun défaut sur les six deltas. Finding VC-1 réel : ajouté à la projection `vaapi_decode`, 66 PASS, synchronisé et rafraîchi sur `.67`. Finding Flex : binaire installé `.67` contient le correctif et sa métadonnée correspond ; le vieux payload source ne correspond pas et devra être reconstruit pour `.229` puis par le build officiel post-commit. |
| 2026-10-10 | Gate `.67` fermé après confirmation Santé | Steve confirme physiquement `Santé globale : PRÊT`. Les parcours `.67` demandés sont fermés avec limites audio/bitstream/décodeur explicitement conservées. Étape suivante : snapshot `.229`, candidat worktree avec Flex reconstruit, puis qualification A310 ; aucune autorisation Git/release. |
| 2026-10-10 | Candidat 1.3.1-rc2 déployé sur `.229` | Snapshot de sécurité effectué, snapshot dirty-worktree vérifié (archive SHA-256 `db5ba62d294b676cd52287c04f679b1d5a947b782b8233af083777bf503507e3`) et Flex reconstruit. Installation réussie ; après la fenêtre transitoire de démarrage, Doctor READY, une instance Flex/moniteur, runtime ownership PASS, A310 PCI `0000:03:00.0`, 3840×2160@60 et recette Magnificence A310 exacte. Qualification physique A310 encore NOT_PROVEN. |
| 2026-10-10 | Gate `.229` A310 fermé | Steve confirme image « top », passthrough, fermeture, retour Flex et Santé PRÊT. Télémétrie : lecture DVD code 0, rendu Vulkan A310 PROVEN, `vaapi-copy` OBSERVED, passthrough AC3 ACTIVE, 60→50→60 Hz restauré/vérifié, aucun processus ou verrou résiduel. Les deux validateurs sont qualifiés ; prochaine décision requise : autorisation explicite de commit. |
| 2026-10-10 | Finalisation 1.3.1 et commit explicitement autorisés | Steve autorise l'identité 1.3.1, la préparation/vérification de l'artifact et le commit correspondant. Push, tag et publication restent hors autorisation. Identité préparée comme `1.3.1` / `public-release-1.3.1`, famille Patina. |
| 2026-10-10 | Gate logiciel rejoué après identité 1.3.1 | Métadonnées cohérentes ; résultat dédupliqué 2284 PASS, 18 SKIP, 0 FAIL. L'ancien validateur Public Candidate R2 reste rouge 59/65 sur des attentes 1.1.0-dev38/ancien asset/vieux payload Flex et est classé STALE sans affaiblissement ; le build/verify exact-commit avec Flex reconstruit reste l'autorité artifact. |
| 2026-10-10 | Commit et artifact OPENHTPC 1.3.1 préparés | Commit autorisé créé ; artifact canonique reconstruit depuis le HEAD exact avec Flex schema 2. `openhtpc-devctl verify`, métadonnées d'archive, checksum et contrôle non destructif installateur PASS. SHA et commit exacts restent dans le rapport/sidecar ignorés. Aucun push, tag ni publication. |

Les jalons antérieurs sont conservés dans CHANGELOG.md et les roadmaps spécialisées. Leur date de réalisation n'est pas inventée ici.

## Continuité entre conversations

Point d’entrée obligatoire : [OPENHTPC_CONTINUITY.md](docs/OPENHTPC_CONTINUITY.md).

2026-10-09 : note opérateur locale préservée en checkpoint partagé ; relevé Git capturé. Lecture et consolidation obligatoires au démarrage et à la transmission. Aucune nouvelle qualification physique établie.
