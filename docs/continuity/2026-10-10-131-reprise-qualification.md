# OPENHTPC 1.3.1 — reprise et qualification logicielle — 2026-10-10

Relevé initial et consolidation : 2026-10-10, Europe/Brussels.
Ce document complète les checkpoints DVD/audio et multi-GPU ; il conserve leurs validations physiques sans les promouvoir au lot de hotfixes plus récent.

## Autorité et limites

- Dépôt canonique : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`, machine `.229`.
- Branche revérifiée : `feature/magnificence-sd-auto`.
- HEAD : `6cdaef763c593215550c241e70e13c773ac799d0`.
- VERSION racine : `1.3.0` ; stabilisation 1.3.1 toujours non commitée.
- Stashes revérifiés et non modifiés : `pre-sync stale RTX experiment 2026-10-02`, `RC7 T5 network deferred`.
- Référence stable : `release/1.2.0-stable-prep` = `cae1f8f496dfd71c243bfef4fa199b66d1c7cd30`.
- Aucun commit, push, tag ou release. Aucun candidat installé sur `.229`.
- `OPENHTPC_CURRENT_STATE.json` reste STALE ; aucune migration ni autorisation n'en est déduite.

## Différences retrouvées à la reprise

Le texte de transmission était moins récent que le worktree et la roadmap :
- un checkpoint partagé supplémentaire, `2026-10-10-validator-131-dvd-audio-multigpu.md`, consigne déjà la publication multi-GPU et 378 PASS ;
- le worktree contient aussi un verrou global `playback-active.lock` partagé par MEDIA/DVD/protected/update, les diagnostics de commande mpv effective du backend Blu-ray et l'acceptation du nom de release après la version dans le README ;
- plusieurs tests historiques avaient déjà été adaptés aux libellés MAGNIFICENCE, à la disparition du réglage vidéo dans la fiche DVD, ou explicitement désactivés pour identité source gelée ;
- `.67` avait quitté normalement vers KDE à `2026-10-10T13:00:26Z` : `STOPPED`, `USER_QUIT_TO_DESKTOP`, `desktop_restore=PASS`, aucun mpv/Flex résiduel ;
- l'index de continuité disait encore que le retest DVD était requis, malgré la qualification physique finale enregistrée dans le checkpoint DVD.

Aucune de ces différences n'a été écrasée ou ramenée à l'état du texte ancien.

## Installation .67 et synchronisation bornée

L'identité installée reste `1.3.1-rc1-validator`, snapshot worktree, pas build Git officiel.
La comparaison payload/install a trouvé 199 fichiers identiques et cinq fichiers de lecture plus anciens (hors identités/version et artefacts Flex générés).

À `2026-10-10T13:20:38Z`, session arrêtée et lecteurs absents, sauvegarde puis remplacement atomique et vérification SHA-256 de :
- `openhtpc-play`
- `openhtpc-play-dvd`
- `openhtpc-play-optical`
- `openhtpc-protected-optical-backend.py`
- `openhtpc-refresh-match.py`

Sauvegarde : `/home/steve/.local/state/openhtpc/manual-backups/20261010T132038Z-131-qualification-sync/`.
Le fichier `sync.json` y conserve les empreintes avant/après et le statut `VERIFIED`.
Source/staging : `/home/steve/dev/qualification/20261010T132100Z-131-sync/`.
Les verrous global/DVD/refresh ont été détenus pendant la mutation. Configuration utilisateur et VERSION installée conservées.
Les 31 fichiers source Flex exportés sont identiques à ceux du snapshot initial compilé ; le binaire installé reste SHA-256 `7d8ce4fb5cadf145ad9053282288dd352b4a09bf47bfb5cf705910ccc06d4f79`.

Session relancée normalement : Home Controller et Flex observés actifs, état RUNNING.
PIDs observés (à revérifier) : Home 131756, Flex 132001.
La dernière transaction DVD demeure RESTORED, lecture RC=0, restauration vérifiée et mode courant 3840×2160 @ 60 Hz.
Cela confirme les preuves antérieures ; aucune nouvelle lecture physique n'a été inventée.

## Publication multi-GPU — revérifiée

Profil effectivement installé :
- HD630 `0000:00:02.0` : MPEG2/H264/HEVC/Main10/VP9 vrais, AV1 faux ;
- RX5700XT `0000:03:00.0` : MPEG2/VP9 vrais, H264/HEVC/Main10/AV1 faux ;
- display/processing/selection/blueprint RX concordent avec le PCI RX ;
- media_stack global = union.
Le sink Denon réseau RAOP observé n'est pas une preuve de disponibilité/qualification du Denon HDMI mémorisé. S/PDIF reste le défaut observé.

## Gates logiciels — preuves de cette reprise

Snapshot de travail pris depuis Git + fichiers non suivis non ignorés, sans autorité Git propre. Tests exécutés sur copie dans des namespaces utilisateur/montage/PID/réseau ; home réel masqué, aucun accès au Wayland réel, Git canonique monté en lecture seule uniquement pour les assertions historiques.

1. Ciblé lecture/audio/refresh/updater/backend/release : 121 PASS ; un test avait initialement échoué faute d'historique Git dans la copie. Le même test a ensuite PASS avec Git en lecture seule : 122 tests distincts PASS.
2. `python3 tools/validate-magnificence-rc.py --allow-dirty` :
   - contrat statique profils/shaders/référence stable : PASS ;
   - ACTIVE_TESTS : 469 PASS, 2 SKIP ;
   - `tools/openhtpc-devctl test media-foundation` : 773 PASS ;
   - diff check : PASS.
3. 29 fichiers de régression modifiés/additionnels, sans doublon avec le gate précédent : 605 PASS, 13 SKIP, 21,42 s.
4. Autopilot après correction des fixtures : 85/85 PASS, 0,40 s.

Total des deux gates non redondants : **1847 PASS, 15 SKIP**.
C'est un gate de développement `--allow-dirty`, pas la qualification d'une release propre/commitée.

Classification :
- 2 SKIP = contrôles mpv/Wayland matériels indisponibles dans l'espace isolé ; raisons explicitement retrouvées dans `test_rc7_gpu_runtime.py` ;
- 13 SKIP = `OBSOLETE_FROZEN_SOURCE_IDENTITY`, déjà présents à la reprise. Ils restent une dette de couverture à convertir en invariants ; ils ne sont pas comptés comme PASS ;
- quatre tests doctor Autopilot dépendaient des vrais exécutables AGY/Codex malgré une détection mockée. Les probes de version et le contexte Git concerné sont maintenant mockés ; les commandes attendues sont vérifiées explicitement. Aucune assertion produit affaiblie, aucune modification de conftest.py ;
- le premier gate sous UID 0 de namespace a également échoué sur le refus volontaire de l'installateur d'être exécuté en root. La reprise avec UID 1000 et home masqué a passé ; l'échec environnemental reste dans les logs ;
- le backend Blu-ray/argv effectif passe sur le worktree plus récent. L'ancien incident ne doit plus être décrit comme non traité sans comparer ce correctif.

Preuves persistantes sur `.229` :
`/home/steve/OpenHTPC/validator-builds/qualification-20261010T1317-reprise/`.
Logs : `development-gate-nonroot.log`, `changed-regression-final.log`, `focused.log`, `historical-git-access.log`, `validator-sync.log`, fichiers provenance et manifests.
Manifest source final (avant cette documentation) : `144ecc2fff1ff21c67adf6e7b1b4aa6d0ceb0081ac82379a84ff09d9b35ff8b6`.

## Audit Hermes contradictoire

Snapshot : `openhtpc-audit-20261010T133100Z-6cdaef7-131-final-r2`.
Archive SHA-256 : `0f81a76e3e16d58fc0d09cfe16bad231442d91094bad00e0eb7111aaafb2e0ea`.
539 fichiers vérifiés par SHA/ownership, projet sans .git ; root propriétaire, dossiers 0555/fichiers 0444 ; tentative d'écriture UID10000 refusée.
Invocation directe `/opt/hermes/.venv/bin/python -m hermes_cli.main`, UID10000, terminal seul, DeepSeek v4.1 flash/OpenRouter/high.
Rapport prévu : `/mnt/user/appdata/hermes-agent/reports/openhtpc-audit-20261010T133100Z-6cdaef7-131-final-r2.md`.
Audit terminé : code 0, stderr vide ; les 539 empreintes ont été revérifiées après la lecture. Rapport copié dans `docs/audits/2026-10-10-131-hermes-final.md` et dans le dossier de preuves sur `.229`. Aucun blocage source reproduit par le reviewer ; ses hypothèses ne deviennent pas des faits par cet avis.
L'ancien snapshot non audité reste conservé ; aucun raccord MCP Hermes→CodeGraph ni réparation de runtime n'est prétendu.

## Qualification physique / prochaine action

Steve confirme désormais le parcours Rules Of Engagement sur le lot synchronisé `.67` : image/son, lancement depuis Flex et retour correct à la fiche DVD. Les deux lectures consignées finissent avec code 0 ; la dernière restauration à 60 Hz et les verrous libres sont vérifiés. Détails et limites dans la clôture ci-dessous.
Avant cet essai, le lecteur était vide et un média inconnu avait été détecté sur /dev/sr1. Dernier état contrôlé : Rules Of Engagement sur /dev/sr0, DVD_VIDEO, génération 60.
Aucune source locale n'est configurée (`local_media_sources=[]`).
Restent : accueil/fiche CJK, MEDIA local :tracked et recherche TMDb/topmost. La cohérence audio et l'absence de lecteurs/matcher/dialogues/verrous orphelins sont vérifiées pour le cas DVD Rules Of Engagement, sans généralisation aux autres parcours.
Le smoke DVD du lot synchronisé est maintenant PASS déclaré par Steve ; la qualification globale demeure ouverte.
Les findings Hermes sont comparés ci-dessous ; fermer les parcours physiques restants avant conclusion.
Ne pas déployer sur `.229` avant fermeture du gate `.67`. Ensuite snapshot salon et même candidat, parcours A310 ciblés ; demander le commit seulement après revue du lot et qualifications requises.
Plugins génériques restent le chantier suivant après 1.3.1 ; aucune nouvelle recette vidéo ou fonction plugin n'a été lancée.

## Disposition de l'audit et correctif post-audit

- F1, tests gelés : dette acceptée et explicitement comptabilisée (13 SKIP), sans promotion en PASS. Les suites d'équivalence/pureté/plugin et les gates fonctionnels demeurent actifs ; remplacer les tests d'identité par des invariants adaptés reste à faire.
- F2, menu DVD : attente historique désalignée ; les réglages sont dans Lecture, correction de test conforme au produit, sans nouvelle suppression de fonctionnalité dans cette reprise.
- F3, héritage de verrous : **reproduit indépendamment**. Un appel du dispatcher DVD sans FLEX_RETAINED et avec argument invalide rendait la main à la vraie forme d'exécution standalone via une UI de fixture ; pendant la vie de cette UI, `playback-active.lock` et `play-dvd.lock` restaient détenus. Terminaison de la seule UI de fixture par son PID exact. Correctif minimal : fermer les FD 8 et 9 dans `return_ui()` avant l'exec de la UI ; le chemin Flex retenu garde son exit normal. Nouveau test comportemental exécute le dispatcher de production et vérifie les deux verrous libres alors que la UI de fixture est encore vivante.
- Gate après F3 : **125/125 PASS**, suites stabilisation, tracked lifecycle, audio/display, refresh, DVD policy et audio routing. Transcript persistant : `dvd-return-lock-post-audit-gate.txt`. Ne pas additionner ces tests aux 1847 (recouvrement de suites).
- F3 déployé sur `.67` après ce gate, sous verrous global/DVD/refresh et sans mpv actif : `openhtpc-play-dvd` SHA-256 `46d9524b57a30b12332b895e7a7c44f2414ee438a854692b9e0966674feef95f` ; sauvegarde `/home/steve/.local/state/openhtpc/manual-backups/20261010T134154Z-dvd-return-lock/`, statut VERIFIED. Pas de redémarrage UI nécessaire ni nouvelle qualification physique prétendue.
- F4, argv effectif : changement intentionnel et tests du backend/consommateurs passés ; `test_rc7_audio_routing.py` également couvert dans le gate post-audit. L'ancien incident était déjà corrigé dans le worktree retrouvé, contrairement au texte de transmission moins récent.
- F5, cadence 24/23.976 vers une fréquence doublée disponible : question de politique/qualification pour écrans proposant 48/47.952 Hz ; aucune régression reproduite ni changement de politique fait. Le validateur du cas PAL n'expose pas ce mode. Ne pas rouvrir la qualification RX shaders.
- F6/F7 : séquencement display/audio et préférence BITSTREAM conservée concordent avec code/tests et preuves précédentes.
- F8, absence de ligne PCI dans un miroir : risque général à tester séparément ; aucune divergence sur les miroirs PCI réels `.67`, revérifiés tous cohérents. Pas de correctif transversal spéculatif.
- F9 : récupération update conforme aux tests ; SIGQUIT n'est pas dans les signaux déjà requis INT/TERM/HUP, aucune extension impulsive.
- F10 : identité 1.3.0 canonique / snapshot 1.3.1-validator intentionnelle et documentée, sans release officielle. Le reviewer avait les checkpoints antérieurs au nouveau gate 1847 ; sa remarque sur leur périmètre est conservée avec cette limite. Qualification physique des parcours MEDIA/recherche et du lot plus récent demeure NOT_PROVEN.

Le snapshot Hermes R2 reste immuable et conserve l'état avant F3. Le correctif F3 et son test sont un supplément opérateur logicielment vérifié, **pas un nouveau snapshot prétendument audité**. La documentation de reprise/roadmap a été consolidée après l'audit ; le rapport original n'a pas été réécrit.

## Essai Rules Of Engagement — en cours, 10/10/2026 à 16:08 (Europe/Brussels)

Steve a inséré Rules Of Engagement et a demandé d'exclure le lecteur HD-DVD du projet parallèle.
Périphérique sélectionné et corroboré par inventaire sysfs/udev : /dev/sr0, TSSTcorp DVD+-RW TS-U633A, volume Rules of Engagement. Le lecteur /dev/sr1 est explicitement exclu de toute lecture/éjection/action de cet essai.
État OPENHTPC : DVD_VIDEO, génération 56 ; fiche publiée L'Enfer du devoir. SHA du dispatcher installé : 46d9524b57a30b12332b895e7a7c44f2414ee438a854692b9e0966674feef95f.
Lecture lancée par le dispatcher de production avec OPENHTPC_FLEX_RETAINED=1 et /dev/sr0 explicite. Ce lancement CLI ne qualifie pas une activation Flex :tracked ; ce parcours reste à tester depuis l'UI.
PIDs propres à cet essai : dispatcher 175218, matcher 175380, mpv 175602 ; IPC /tmp/openhtpc-mpv-95e92d31f66a4320b1c9ae9051c8bebf.sock (à revérifier avant toute commande ultérieure).
Observation IPC : titre Rules of Engagement, lecture non suspendue, MPEG2 720x576, cadence 25 Hz, écran 50 Hz, piste AC3 stéréo, sortie PCM via PipeWire/S/PDIF. Denon mémorisé indisponible, repli système ; préférence BITSTREAM conservée.
Home 131756 et Flex 132001 restent actifs. Résultat physique image/son et restauration finale : EN ATTENTE de Steve, aucun PASS physique supplémentaire enregistré.
Preuves : rules-of-engagement-trial.json et rules-of-engagement-playing.json dans le dossier de preuves .229 ; preuves avant lecture et dispatch.log dans /home/steve/dev/qualification/rules-of-engagement-20261010T140808Z sur .67.

## Clôture du parcours DVD Rules Of Engagement — 10/10/2026, Europe/Brussels

**PASS physique déclaré par Steve sur .67 : image, son, lancement via LIRE LE DVD dans Flex et retour correct à la fiche DVD.**
Réponses conservées : « tout semble s'être bien déroulé », puis « Oui, lancement depuis Flex et retour correct » à la question ciblée sur la seconde lecture de 16 h 13 à 16 h 15.
La première lecture de qualification CLI (dispatcher 175218, /dev/sr0, génération 56) s'est terminée à 16:09:35 avec code 0. Une seconde lecture DVD /dev/sr0, génération 60, est consignée de 16:13:20 à 16:15:01, également code 0 ; Steve confirme l'avoir lancée depuis Flex. Les logs corroborent la lecture/sortie, l'attribution à l'activation UI est sa déclaration explicite.
À 16:16, le mpv initial était déjà absent : aucune commande quit, aucun signal ni arrêt forcé n'a été envoyé. Contrôle indépendant final : session RUNNING, mêmes Home 131756 et Flex 132001 ; zéro mpv/matcher/dialogue résiduel ; verrous playback-active/play-dvd/refresh-match tous libres.
Dernière transaction : RESTORED, playback_exit_code=0, playback_teardown_forced=false, restauration demandée et vérifiée ; kscreen confirme 3840×2160 à 60 Hz après la lecture PAL à 50 Hz. Audio observé PCM/S/PDIF, préférence BITSTREAM conservée et Denon mémorisé indisponible ; aucune qualification HDMI/bitstream n'en est déduite.
Périmètre limité au DVD TSSTcorp /dev/sr0 et à Rules Of Engagement. Aucun essai, éjection ou lancement demandé sur le lecteur HD-DVD /dev/sr1 du projet parallèle. Des changements optiques intermédiaires figurent dans les logs ; ils ne sont pas attribués à cette reprise, qui n'a envoyé aucune action à /dev/sr1.
Preuves ajoutées au dossier .229 : rules-of-engagement-exit-transcript.txt, rules-of-engagement-ui-lifecycle.txt, rules-of-engagement-qualification-result.json ; état avant/après et exit-observation.json conservés sur .67.
Ce jalon ferme le smoke DVD du lot synchronisé, sans clôturer la qualification globale 1.3.1 : MEDIA local :tracked, recherche TMDb/topmost et rendu CJK restent séparés, puis déploiement et qualification A310 .229 après fermeture du gate .67. Aucun commit/push/tag/release.

## Reprise live suivante — 10/10/2026 à 16:27–16:29 (Europe/Brussels)

Contrôle read-only après relecture de la constitution, des roadmaps et des checkpoints : branche, HEAD, VERSION racine et stashes correspondent toujours au relevé ci-dessus. Le worktree reste volontairement non commité. `OPENHTPC_CURRENT_STATE.json` décrit toujours l'ancien workstream P2 et reste STALE. L'installation `.229` est toujours OPENHTPC 1.3.0 ; aucun candidat 1.3.1 n'y a été installé.

Sur `.67`, l'installation rapporte toujours `1.3.1-rc1-validator`. La session est RUNNING, Flex est actif (PID observé 132001, à ne pas réutiliser sans vérification), aucun mpv/matcher/dialogue n'est actif et les verrous `playback-active.lock`, `play-dvd.lock` et `refresh-match.lock` sont libres. Le mode live revérifié via l'environnement de la session est 3840×2160 @ 60 Hz. Le dernier diagnostic refresh reste RESTORED avec sortie 0, restauration vérifiée, PCM/S/PDIF effectif et préférence BITSTREAM conservée.

Le snapshot de capacités installé publie toujours les faits par PCI : HD630 `0000:00:02.0` avec MPEG-2/H.264/HEVC/Main10/VP9 supportés et RX5700XT `0000:03:00.0` avec MPEG-2/VP9 supportés mais H.264/HEVC/Main10 non supportés ; les miroirs display/processing RX et l'union machine restent cohérents.

Une capture ponctuelle de l'écran live montre `ETERNAL_SUNSHINE` sur le média optique actuellement présenté. L'inventaire indique ce volume sur `/dev/sr1`, lecteur HD-DVD du projet parallèle explicitement exclu : aucune sélection, lecture, éjection ou mutation n'a été envoyée à `/dev/sr1`. Les qualifications encore ouvertes restent donc inchangées : fiche CJK sur le média approprié dans `/dev/sr0`, recherche TMDb/topmost observée sous Wayland, et MEDIA local `:tracked` après disponibilité d'une source locale. Aucun PASS physique nouveau n'est revendiqué par ce contrôle.

## Anomalie Compatibilité vidéo RX5700XT — constat du 10/10/2026 à 16:37

Steve a signalé que Système → Compatibilité vidéo affiche VC-1, H.264, HEVC et HEVC 10 bits « Non pris en charge » alors que le GPU de rendu est la RX 5700 XT. La page réelle a été capturée et inspectée : elle présente bien ces négatifs sous « GPU de rendu : AMD/ATI • Accélération : VA-API ».

Le snapshot publié n'invente pas ces valeurs : un `vainfo` direct sur le chemin persistant RX `pci-0000:03:00.0-render` expose seulement MPEG-2, JPEG, VP9 et VideoProc. H.264/HEVC sont absents. En revanche, AMD documente la RX 5700 XT comme capable de décodage 4K H.264 et H.265/HEVC. L'écart est donc entre la capacité matérielle et la pile VA-API Fedora actuellement disponible, pas une limitation matérielle démontrée de la carte.

État paquet revérifié : `mesa-va-drivers-freeworld` n'est pas installé ; seul le `radeonsi_drv_video.so` de `mesa-dri-drivers-26.2.3-1.fc44` est chargé. RPM Fusion Free/Updates est actif et propose actuellement `mesa-va-drivers-freeworld` pour Fedora 44. Aucune installation ou mutation Fedora n'a été effectuée pendant ce diagnostic.

Défaut produit identifié dans `payload/install-openhtpc-fedora.sh` : le déclenchement du complément multimédia repose sur les booléens VA-API agrégés de toute la machine. Sur la machine Intel+AMD, les capacités H.264/HEVC de la HD630 masquent donc les manques propres à l'AMD et peuvent empêcher totalement l'appel à `install_multimedia_extension`. Le chemin `OPENHTPC_UPDATE_MODE=1` exclut également cette proposition ; les installations 1.3.0 et 1.3.1-validator consignées sont passées directement de DÉPENDANCES à INSTALLATION. Le journal historique ne montre aucune installation réussie du complément AMD et l'historique DNF ne montre pas le paquet.

Classification : **ANOMALIE OUVERTE 1.3.1**. La publication PCI→PCI est exacte pour ce qui est actuellement exposé, mais le libellé « Non pris en charge » confond disponibilité backend courante et capacité matérielle. Correction attendue avant clôture : décision de dépendance par GPU/PCI sans union multi-GPU, comportement explicite du chemin update, puis libellé Système distinguant « matériel non supporté » de « indisponible via la pile VA-API actuelle ». Toute installation Fedora sur `.67` exige une action bornée séparée et une nouvelle mesure ; aucun support ne doit être promu avant preuve.

### Correction source et état installé

Correction implémentée dans le worktree, sans commit :
- l'installateur annote chaque observation `vainfo` avec le vendor sysfs du render node et calcule séparément les manques AMD et Intel ; l'union machine reste uniquement la vue globale ;
- le mode update détecte désormais qu'une remédiation par GPU est nécessaire et la consigne comme différée au mode interactif, sans ouvrir un prompt DNF caché pendant une mise à jour ;
- Système traduit un `UNSUPPORTED` issu du backend courant par « Indisponible via VA-API » au lieu d'en faire une incapacité matérielle générale ;
- nouveau test de régression : Intel complet + AMD limité conserve l'union globale complète mais exige bien le complément AMD.

Gates après correction : 66/66 ciblés, puis 313 PASS / 5 SKIP sur collecteur, enablement, audit codec, modèle Système, runtime GPU, audio/routage/affichage, update/runtime, reconstruction Passport, UI et métadonnées release. `bash -n` et `git diff --check` PASS. Les SKIP sont les contrôles matériels déjà conditionnels de la suite GPU ; aucun n'est promu en PASS.

Le scan Média signalé par Steve a été observé revenu `IDLE`, sans processus scan/ingest/enrich/probe ni mpv. Les deux composants runtime `openhtpc-system-model.py` et `openhtpc-ui.py` ont alors été synchronisés atomiquement sur `.67` sous le verrou global, avec sauvegarde `/home/steve/.local/state/openhtpc/manual-backups/20261010T1645-rx-vaapi-ui/`. SHA-256 installés : modèle `a2fa079f59e65a2dd2998f4b5f8c9af7ad6b94a3136974c15261fad59e9e1d59`, UI `4b246714238d29a07468010b5dc9b3b3a7750c11ba2606d980cc878653197298`. L'installateur n'est pas un fichier runtime installé séparément ; sa correction reste dans la source du prochain candidat.

La simulation DNF de la remédiation réelle propose une installation (`mesa-va-drivers-freeworld-26.2.4`) et six mises à jour Fedora Mesa 26.2.3→26.2.4 (`mesa-dri-drivers`, `mesa-filesystem`, `mesa-libEGL`, `mesa-libGL`, `mesa-libgbm`, `mesa-vulkan-drivers`). Aucun paquet n'a été installé. Une tentative d'approbation mal ciblée vers la machine locale `.229` a été rejetée avant exécution ; aucune mutation locale ou distante n'en résulte. La transaction correcte doit viser explicitement `.67` et recevoir l'autorisation opérateur informée avant exécution. Après éventuelle installation : nouvelle mesure `vainfo` RX, refresh canonique des capacités, contrôle écran Système et régressions lecture RX nécessaires.

### Transaction Fedora autorisée et re-probe — 10/10/2026 à 16:56–17:00

Steve a explicitement autorisé la transaction Mesa bornée sur `.67`. Le prévol immédiatement antérieur était propre : activité Média `IDLE`, aucun mpv ni processus scan/ingest/enrich/probe, verrous playback/DVD/refresh libres et sudo non interactif disponible.

La transaction distante a terminé avec code 0 : installation de `mesa-va-drivers-freeworld-26.2.4-1.fc44` et alignement en `26.2.4-1.fc44` de `mesa-dri-drivers`, `mesa-filesystem`, `mesa-libEGL`, `mesa-libGL`, `mesa-libgbm` et `mesa-vulkan-drivers`. Aucune mutation n'a été faite sur `.229`.

Le `vainfo` direct sur le chemin persistant RX `pci-0000:03:00.0-render` charge désormais `/usr/lib64/dri-freeworld/radeonsi_drv_video.so` et expose VC-1 Simple/Main/Advanced, H.264 Constrained Baseline/Main/High, HEVC Main/Main10 et VP9 Profile0/Profile2. Le refresh canonique `openhtpc-capabilities.py --refresh` a terminé avec code 0. Dans `~/.config/openhtpc/runtime/capabilities.json`, le nœud exact AMD `0000:03:00.0` publie désormais VC-1, H.264, HEVC Main et HEVC Main10 `SUPPORTED` via VA-API ; AV1 et MPEG-2 restent `UNSUPPORTED` pour le backend chargé par défaut. La vue globale machine reste une union et le nœud Intel demeure séparé. Cela prouve la disponibilité backend annoncée, pas encore une qualification physique de chaque codec.

Le packaging Fedora/RPM Fusion est complémentaire et non une simple surcouche : le pilote Freeworld annonce explicitement H.264/H.265/VC-1 et ne publie pas MPEG-2, tandis qu'un probe forcé avec `LIBVA_DRIVERS_PATH=/usr/lib64/dri` retrouve MPEG-2/JPEG/VP9 mais perd H.264/H.265/VC-1. OPENHTPC ne possède pas encore de sélection de variante VA-API par codec ; il ne faut donc pas publier une union fictive des deux pilotes comme capacité runtime courante. Le MPEG-2 RX reste une limitation backend/politique ouverte distincte ; le fallback logiciel sûr de mpv reste disponible et aucune décision négative par GPU n'est ajoutée.

La session graphique existante n'est pas un environnement final fiable après remplacement de Mesa : Fedora `dnf5 needs-restarting` demande un reboot et le processus Flex observé conserve des mappings supprimés de `libEGL_mesa.so` et `libgbm.so`. Deux tentatives de capture Spectacle ont avorté avant création d'image ; aucune validation visuelle n'en est déduite. Le redémarrage de `.67` reste **EN ATTENTE d'une autorisation opérateur explicite**. Après redémarrage : revérifier session/Flex/60 Hz, snapshot par PCI, écran Système → Compatibilité vidéo et un smoke lecture RX borné avant de clore l'anomalie.

### Reboot autorisé, restitution et smoke HEVC — 10/10/2026 à 17:46–17:53

Steve a explicitement autorisé le reboot de `.67`. Le dernier prévol était propre (`MEDIA=IDLE`, aucun mpv/scan, verrous playback/DVD/refresh libres). La machine est revenue avec un nouvel identifiant de boot `fbd2b9a2-1057-4b2d-bef9-d11b4d3ae5cb`, KDE/Wayland actif.

L'autostart OPENHTPC s'est bien exécuté mais a échoué fermé après `SESSION_START` : le changement de fingerprint avait rendu le Hardware Passport `PASSPORT_STALE`. Une première reconstruction lancée depuis SSH avec `DISPLAY=:0` mais sans autorité X11 a fait échouer `vulkaninfo`, donc le Builder a correctement refusé la régénération runtime (`RUNTIME_REGENERATION_NOT_READY`) et aucun Flex n'a été forcé avec ce profil incomplet. Le probe Vulkan Wayland pur (`DISPLAY`/`XAUTHORITY` retirés, socket Wayland et bus utilisateur explicites) a ensuite passé et retrouvé l'UUID RX exact. Une seconde reconstruction canonique dans cet environnement a produit RX5700XT + `vaapi + vulkan`, runtime MPV prêt ; `openhtpc-session-start --check-only` a donné PASS.

OPENHTPC a ensuite été relancé par son entrée normale. État final observé : session RUNNING, Home Controller PID 4395, moniteur optique PID 4488 et Flex PID 4664 (PIDs purement ponctuels, à revérifier), aucun mpv/matcher/dialogue résiduel. Le mode reste 3840×2160 @ 60 Hz. Une capture réelle montre l'accueil Flex revenu ; ce constat visuel de l'assistant n'est pas promu en validation physique de Steve.

Le rendu non interactif de la page installée Système → Compatibilité vidéo, construit avec le modèle et le snapshot réels `.67`, affiche désormais VC-1, H.264/AVC, HEVC/H.265, HEVC 10 bits, VP9 et VP9 10 bits « Pris en charge » via VA-API. MPEG-2 et AV1 sont affichés « Indisponible via VA-API » ; AV1 est absent de Navi 10, et MPEG-2 relève de la séparation des variantes Mesa documentée ci-dessus. L'ancien libellé générique « Non pris en charge » a disparu pour ces indisponibilités backend.

Smoke technique autorisé : 10 secondes naturelles d'un fichier HEVC Main 1920×1040 du catalogue Média, audio désactivé, `gpu-next`/Vulkan lié à l'UUID RX et `hwdec=vaapi`. mpv a terminé avec code 0. Preuves runtime : `[vo/gpu-next/libplacebo] Device Name: AMD Radeon RX 5700 XT`, PCI `1002:731f`, UUID attendu, Mesa RADV 26.2.4 ; `[vd] Using hardware decoding (vaapi)` et sortie `vaapi[nv12]`. Le socket IPC exact de cet essai, resté comme fichier après sortie naturelle, a été supprimé explicitement ; aucun mpv ne subsiste. Flex et le 60 Hz sont restés/revenus actifs. Cela qualifie techniquement ce smoke HEVC ; aucune appréciation physique image de Steve n'est revendiquée.

Le complément H.264 demandé a également été exécuté : 8 secondes naturelles sur un flux H.264 High 1920×1080 du catalogue Média, mêmes UUID RX et backend, sans audio. mpv RC=0 ; libplacebo identifie RX5700XT/RADV 26.2.4 et `[vd]` consigne `Trying hardware decoding via h264-vaapi` puis `Using hardware decoding (vaapi)`, sortie `vaapi[nv12]`. Socket exact retiré, aucun mpv résiduel, session toujours RUNNING et 3840×2160 @ 60 Hz. H.264 et HEVC disposent donc chacun d'une preuve runtime technique distincte après reboot.

### Jalon Compatibilité vidéo figé par Steve — 10/10/2026

Steve confirme physiquement l'écran Système → Compatibilité vidéo après correction et autorise à figer ce jalon. La présentation validée montre VC-1, H.264/AVC, HEVC/H.265, HEVC 10 bits, VP9 et VP9 10 bits pris en charge via VA-API. MPEG-2 et AV1 restent explicitement présentés comme « Indisponible via VA-API » selon la vérité du backend courant ; AV1 est une limite Navi 10 et MPEG-2 reste la limitation documentée de sélection entre variantes Mesa, avec fallback logiciel sûr.

Statut du jalon : **PHYSICALLY_QUALIFIED et figé sur `.67`** pour l'écran Compatibilité vidéo et les smokes techniques H.264/HEVC associés. Cette acceptation ne clôt pas toute la 1.3.1 et n'autorise pas implicitement commit, push, tag ou release. Prochaine qualification : MEDIA local `:tracked`, puis recherche TMDb/topmost et CJK ; la politique MPEG-2 par variante reste une limitation ouverte séparée à ne pas masquer.

## Faux état Santé globale après démarrage — correction du 10/10/2026

Steve a ensuite signalé `Santé globale : PROBLÈME` dans Système → Vue d'ensemble. Le constat live distinguait deux vérités : `openhtpc doctor --json` rapportait `overall=READY` avec les contrôles essentiels PASS, tandis que l'image Système générée au démarrage affichait encore `PROBLÈME`.

Cause reproduite dans le cycle de vie : `openhtpc-home.py` publiait toutes les images Système lors de `regenerate()`, avant de lancer Flex et d'inscrire son PID autoritaire dans l'état de session. Le modèle de santé voyait donc correctement Flex absent pendant cette fenêtre de bootstrap, produisait `BLOCKED`, puis cette image restait en cache après le démarrage réussi. Le mapping `BLOCKED → PROBLÈME` et Doctor n'étaient pas fautifs et n'ont pas été affaiblis.

Correctif minimal non commité : le rendu des pages Système est isolé dans `render_system_pages()` ; le contrôleur Home le rappelle après l'écriture atomique du PID Flex autoritaire et après une attente bornée vérifiant ce PID enfant exact dans les processus UI gérés, avant l'événement `FLEX_STARTED`, sans republier la configuration Flex. Un échec de ce rafraîchissement est journalisé mais ne tue pas le Flex déjà lancé. Deux tests couvrent l'écrasement BLOCKED→READY par le helper de production et l'ordre publication PID → observation du fils exact → rendu → `FLEX_STARTED`.

Gate ciblé : **118 PASS** sur stabilisation 1.3.1, modèle Système, audio UX, affichage runtime, tracked lifecycle et concurrence de démarrage. Le premier lancement n'a exécuté aucun test en raison d'un `PYTHONPATH` absent ; relance identique avec `PYTHONPATH=.` propre. `git diff --check` PASS.

Les deux fichiers de production ont été synchronisés sur `.67` après contrôle d'absence de mpv, avec sauvegarde `/home/steve/.local/state/openhtpc/manual-backups/20261010-system-health-post-start-refresh/`. Aucun redémarrage ni déploiement `.229`. Une régénération non disruptive depuis l'état live a produit à 18:29 l'image installée montrant `ÉTAT : PRÊT` et `Santé globale : PRÊT` ; Doctor est resté READY. Il s'agit d'une preuve technique/visuelle de l'assistant, pas encore d'une confirmation physique de Steve. Le comportement automatique au prochain démarrage est logiciellement vérifié mais reste physiquement NOT_PROVEN jusqu'à un futur démarrage normal observé.

## Qualification MEDIA local `:tracked` — 10/10/2026

La source `/home/steve/Movies` configurée par Steve a terminé son premier passage : 185 fichiers découverts, 90 automatiquement identifiés et 95 laissés à vérifier. Flex a été publié avec des fiches jouables. Le statut batch demeure `FAILED/PARTIAL` à cause d'un enrichissement partiel unique ; la bibliothèque et ses actions ont néanmoins été publiées. Cette classification reste à distinguer d'une source ou d'une lecture défaillante.

Steve a lancé depuis Flex la fiche **Terminator 3 : Le Soulèvement des machines**, puis `LIRE LE FILM`. Il confirme physiquement : image OK et retour à Flex OK. Pour l'audio, sa formulation est « on va dire que c'est ok » mais son casque n'était pas branché : ne pas promouvoir cela en qualification auditive complète.

Preuves techniques du même dispatch : action `:tracked` résolue depuis le manifeste courant ; dispatcher PID 12929, parent direct = Flex PID 4664 ; fichier MKV H.264 1920×1080 23,976 fps ; RX5700XT Vulkan prouvée et décodage VA-API observé ; durée 58 s ; mpv ouvert, sortie code 0, `error_class=NONE`. L'audio AC-3 demandé en BITSTREAM a appliqué le fail-safe attendu vers PCM/PipeWire parce que la cible Denon mémorisée était absente et que le sink système n'était pas HDMI ; passthrough observé INACTIVE. Après sortie : même Flex 4664 actif, aucun mpv/dispatcher/matcher/dialogue résiduel observé, activité MEDIA IDLE et verrous playback/refresh/media-action/media-search/library-update libres.

Une incohérence de diagnostic secondaire a été trouvée : `media-action-last.json` indiquait `flex_instances=0` malgré le PPID Flex exact et le processus vivant. Cause : `openhtpc-play` transmettait à `pgrep` POSIX un groupe non capturant propre à Python `(?:...)`. Correction minimale vers le groupe POSIX `( |$)`, sans changement du lancement ni de `waitpid`. Gates : 66/66 ciblés ; suite `test_media_match_ui.py` 69/69 hors sandbox (dans le sandbox, son test volontaire de blocage réseau recevait `PermissionError` avant son mock). Le composant corrigé a été synchronisé avec sauvegarde `/home/steve/.local/state/openhtpc/manual-backups/20261010-media-flex-telemetry/`, SHA-256 `d59b57e8beac6bf609ad49e6ad4e68355a66fc511f1014ec8480ad299fd1d6a7`. Le helper installé retourne désormais exactement `(1, [4664])`. Aucun second essai physique n'est requis pour cette correction de télémétrie seule.

Statut : **MEDIA local `:tracked` physiquement qualifié sur `.67` pour image, cycle de vie et retour Flex**. Audio techniquement observé PCM, mais qualification auditive physique complète NOT_PROVEN. Aucun commit/push/tag/release et aucun déploiement `.229`.

## Recherche manuelle TMDb / topmost — qualification du 10/10/2026

Cas choisi : fichier local non identifié `Dark Knight`, média version 13. Depuis Flex, Steve a parcouru `MÉDIA → À identifier → Dark Knight → IDENTIFIER LE FILM → RECHERCHER MANUELLEMENT → LANCER LA RECHERCHE`, a constaté la fenêtre de saisie correctement au premier plan sous KDE/Wayland, saisi la recherche demandée et vu les résultats. Il confirme toutes ces étapes à 100 %.

La transaction UI est enregistrée `SUCCESS`, code 0, de 16:46:14 à 16:46:18 UTC. La page de résultats publiée contient quatre propositions, dont `The Dark Knight : Le Chevalier noir (2008)`. Comme demandé, aucun candidat n'a été accepté : l'identité canonique reste `UNMATCHED`, `work_id=null`, `match_locked=0`. État final : MEDIA `IDLE`, verrous action/search/library libres, aucun `openhtpc-media-manual-search-ui`, `openhtpc-text-entry` ou `kdialog` résiduel ; Flex PID 4664 toujours actif lors du contrôle.

Statut : **recherche manuelle TMDb et comportement topmost PHYSICALLY_QUALIFIED sur `.67`**. La prochaine qualification physique ouverte est le rendu CJK/Hangul dans la fiche appropriée. Aucun commit/push/tag/release et aucun déploiement `.229`.

## Rendu CJK/Hangul — qualification physique du 10/10/2026

Le disque inséré par Steve n'était pas *Perhaps Love* mais **Identity**. OPENHTPC l'a correctement classé DVD_VIDEO PAL sur `/dev/sr0`, génération 67, puis a publié une fiche cohérente *Identity* (2003) depuis un match TMDb confiant. Aucune lecture ni éjection automatique ; l'état optique est resté celui de ce disque.

Comme *Identity* ne contient pas les crédits CJK/Hangul nécessaires, une prévisualisation isolée a été rendue avec **le composant installé** `openhtpc-disc-view.py` et **le cache réel** conservé de *Perhaps Love*. Elle n'a remplacé ni `optical-current.json`, ni `disc-sheet.png`, ni la configuration Flex. Le PNG exact affichait les crédits `杜國威`, `林愛華`, `金城武`, `周迅`, `張學友` et `지진희`. L'assistant l'a inspecté indépendamment sans carré, puis l'a affiché temporairement en plein écran sur `.67`.

Steve confirme physiquement que ces glyphes sont corrects. L'aperçu Gwenview lancé pour cette seule vérification a ensuite été terminé proprement par son PID exact 15434 ; le processus a disparu, Flex PID 4664 est resté actif et aucun mpv n'était présent. Le DVD *Identity* est resté inséré et inchangé, génération 67.

Statut : **renderer CJK/Hangul PHYSICALLY_QUALIFIED sur `.67`**. Limite conservée : ce jalon valide le rendu exact du composant installé avec les vraies métadonnées mises en cache ; il ne prétend pas qu'un nouveau cycle physique d'insertion de *Perhaps Love* a été rejoué. Aucun commit/push/tag/release et aucun déploiement `.229`.

## Parcours DVD réel City of Violence — qualification physique du 10/10/2026

Steve a ensuite inséré **City of Violence** dans `/dev/sr0` et effectué lui-même le parcours complet depuis Flex : recherche manuelle, validation de la fiche, contrôle des caractères asiatiques, lecture du DVD, fermeture de la lecture et retour à Flex. Il confirme explicitement chaque étape comme correcte. Ce jalon qualifie donc le rendu CJK/Hangul dans un vrai cycle optique, et lève la limite du précédent aperçu isolé pour ce cas coréen précis.

Les preuves installées concordent avec sa validation : le cache de cette empreinte DVD contient `The City of Violence`, statut `PASS`, confiance `USER_CONFIRMED_MATCH`, TMDb 20605, le réalisateur `류승완`, ainsi que `이원재` et `류승완` parmi les auteurs. Le disque est passé à la génération optique 69 ; la lecture a commencé à 18:53:12 et s'est terminée avec code 0. La transaction de fréquence est `RESTORED` : source PAL 25 fps, commutation 3840×2160 @ 50 Hz vérifiée, puis restauration 3840×2160 @ 60 Hz demandée et vérifiée. Le contrôle live final confirme le 60 Hz.

La télémétrie de cette lecture consigne zéro frame drop et zéro decoder-frame drop. Le rendu Vulkan RX5700XT `0000:03:00.0` est `PROVEN`; le backend de décodage `vaapi-copy` et son activité matérielle sont `OBSERVED`, mais l'identité physique du GPU de décodage reste correctement `NOT_PROVEN`. Il ne faut donc pas déduire de ce DVD une preuve de décodage MPEG-2 par la RX ni fusionner les capacités des variantes Mesa. L'audio observé a appliqué le repli attendu vers PCM/PipeWire sur le sink S/PDIF, la préférence BITSTREAM et la cible Denon hors ligne restant inchangées ; aucune qualification auditive ou bitstream supplémentaire n'est inventée.

`playback_teardown_forced=true` ne décrit pas une interruption de lecture : mpv avait déjà écrit son marqueur de sortie volontaire `Exiting... (Quit)` et le garde-fou a terminé le PID exact seulement après le délai de démontage graphique de 1,5 s. Le résultat publié reste `COMPLETED`, `media_opened=true`, `exit_code=0`, puis Flex est revenu comme Steve l'a confirmé. Contrôle après coup : Flex PID observé 4664 toujours actif, aucun mpv, tous les verrous playback/DVD/refresh/MEDIA libres, disque ensuite éjecté et état optique génération 70 `EMPTY`.

Statut : **parcours DVD City of Violence PHYSICALLY_QUALIFIED sur `.67`**, incluant recherche manuelle, fiche réelle, caractères coréens, image, sortie et retour Flex. Audio techniquement observé PCM ; écoute physique détaillée et HDMI/bitstream restent hors de cette preuve. Aucun commit/push/tag/release et aucun déploiement `.229`.

## Gate logiciel final après qualifications `.67` — 10/10/2026

Le premier appel non borné `pytest -q` a inclus les copies historiques sous `artifacts/OpenHTPC-*` et s'est arrêté pendant la collecte avec 213 collisions de noms de modules. Aucun test produit n'a été exécuté par cet appel et ces erreurs ne sont pas classées comme régressions. Les artifacts n'ont été ni supprimés ni modifiés.

Le périmètre canonique explicite `PYTHONPATH=. pytest -q tests tools/autopilot/tests` a ensuite donné **2273 PASS, 11 FAIL, 18 SKIP**. Les onze échecs provenaient tous de l'interdiction sandbox de créer des sockets : un test de garde réseau, trois tests IPC mpv et sept tests de contexte Wayland. Les trois fichiers concernés ont été relancés hors sandbox, sans autre changement : **98/98 PASS**. Le résultat dédupliqué du gate canonique est donc **2284 PASS, 18 SKIP, 0 FAIL**.

Les 18 SKIP restent explicitement non promus en PASS. Aucun des anciens échecs d'attentes optiques figées n'est présent dans ce gate courant. `git diff --check` PASS. Le worktree 1.3.1 reste volontairement non commité et les deux stashes protégés sont inchangés.

## Audit Hermes final du delta et dispositions — 10/10/2026

Snapshot immuable : `openhtpc-audit-20261010T170140Z-6cdaef7-131-final-delta`, archive SHA-256 `901291b719c955157b08f36addf6433af6332152aa48a386472bc772ea123b27`. Snapshot sans `.git`, root:root, dossiers 0555 et fichiers 0444 ; tentative d'écriture UID10000 refusée. Empreinte globale avant et après audit identique : `dac3d2bfdef58a8799c8aa3ef47ce32ed5c06bd7d7f157b778b633447051b5d0`. Audit DeepSeek v4.1 flash/OpenRouter/high, terminal seul : code 0, stderr vide. Rapport conservé sur Unraid et copié dans `docs/audits/2026-10-10-131-hermes-final-delta.md`.

Hermes n'a reproduit aucun défaut sur les six deltas demandés : ordre DVD et repli PCM, garde-fou de teardown, publication PCI sans union trompeuse, libellés Compatibilité vidéo, rafraîchissement Santé après PID Flex, télémétrie MEDIA et lifecycle tracked exact. Son avis reste consultatif ; les constats suivants ont été vérifiés dans le dépôt canonique :

- **Flex payload ancien : constat réel mais non bloquant pour le candidat installé `.67`.** Le binaire `payload/flex/bin/flex-launcher` et sa vieille métadonnée ne correspondent pas au `unix.c` courant. En revanche, le binaire effectivement installé et qualifié sur `.67` a SHA-256 `7d8ce4fb5cadf145ad9053282288dd352b4a09bf47bfb5cf705910ccc06d4f79`, sa métadonnée porte la même empreinte et la chaîne du correctif `Could not probe launched application process` est présente. Le build officiel reconstruit Flex depuis la source exportée ; avant `.229`, le snapshot worktree doit de même embarquer un binaire reconstruit et une métadonnée cohérente. Avant release, l'artifact officiel post-commit devra passer cette vérification. Le vieux payload n'est pas déclaré prêt.
- **VC-1 absent de la projection `vaapi_decode` : défaut réel corrigé.** `PROFILE_CODEC_MAP` inclut désormais `vc1`; les fixtures multi-GPU vérifient la projection globale et PCI. Gate ciblé 66/66 PASS. Le fichier a été synchronisé sur `.67` avec sauvegarde `/home/steve/.local/state/openhtpc/manual-backups/20261010-vc1-profile-projection/`, puis le refresh canonique a enregistré `vaapi_decode.vc1 false→true`. Profil effectif : union machine VC-1 true ; display/processing RX `0000:03:00.0` VC-1 true, MPEG-2 false, H.264/HEVC/Main10/VP9 true. Aucun mpv résiduel, Flex intact et verrous libres.
- Le risque historique d'un miroir sans PCI exact restant inchangé demeure accepté comme limitation non reproduite sur `.67`, dont les deux rôles portent le PCI RX exact. Aucun fail-closed booléen artificiel n'est inventé dans cette reprise.
- Les remarques sur le vieux validateur public, les documents de continuité privés et un test dépendant de l'hôte sont classées dette de packaging/test, pas régression runtime. Les chemins Flex non trackés restent hors playback ; toute future lecture doit continuer à utiliser `:tracked`.

Aucune autorité de commit, push, tag ou release n'est issue de cet audit.

## Fermeture du gate `.67` — Santé globale confirmée par Steve

Steve confirme physiquement que **Système → Vue d'ensemble → Santé globale** affiche désormais **PRÊT**. Cette confirmation complète la preuve technique précédente (`openhtpc doctor` READY et image régénérée PRÊT) et qualifie physiquement le correctif de rafraîchissement post-démarrage sur le validateur `.67`.

Le gate `.67` est donc **FERMÉ / PHYSICALLY_QUALIFIED** pour les parcours demandés : Compatibilité vidéo RX5700XT, DVD/refresh/retour Flex, recherche manuelle TMDb/topmost, CJK/Hangul réel, MEDIA local `:tracked` pour image/cycle/retour, et Santé globale. Limites conservées : écoute audio MEDIA complète NOT_PROVEN faute de casque ; HDMI/bitstream Denon non requalifié dans ce local ; MPEG-2 RX reste une limite de sélection entre variantes Mesa et l'identité physique du GPU de décodage reste NOT_PROVEN.

Prochaine action désormais autorisée par la séquence de qualification : snapshot de sécurité `.229`, construction honnête du snapshot worktree avec Flex reconstruit depuis la source courante, puis déploiement sur `.229` et parcours A310 ciblés. Cela ne vaut toujours pas autorisation de commit, push, tag ou release.

## Déploiement du candidat identique sur `.229` — qualification physique en attente

Snapshot de sécurité pré-déploiement : `/home/steve/dev/snapshots/openhtpc-pre-131-20261010T173744Z` avec manifeste SHA-256. Candidat honnête du worktree dirty : `/home/steve/OpenHTPC/validator-builds/OpenHTPC-1.3.1-rc2-validator-20261010T173932Z`, archive SHA-256 `db5ba62d294b676cd52287c04f679b1d5a947b782b8233af083777bf503507e3`. Il est explicitement non officiel, fondé sur HEAD `6cdaef7` avec l'état dirty enregistré. Ses 545 fichiers ont été vérifiés contre le manifeste. Flex a été reconstruit depuis la source courante ; son SHA-256 `7d8ce4fb5cadf145ad9053282288dd352b4a09bf47bfb5cf705910ccc06d4f79` correspond au binaire déjà qualifié sur `.67` et à sa métadonnée.

`./update.sh --check` a réussi puis `./update.sh` a installé `1.3.1-rc2-validator` / build `validator-worktree-rc2` sur `.229`, conservé le Hardware Passport, régénéré les données runtime et relancé la session. Une première lecture Doctor pendant la fenêtre de redémarrage a transitoirement indiqué DEGRADED/Flex absent ; aucune panne persistante n'a été conclue. Après publication de l'autorité de session, Doctor donne **READY**, avec une seule instance Flex PID 1290718, un seul moniteur optique, `Runtime ownership: PASS` et `Appliance state: RUNNING`. Le runtime autoritaire est `session-20261010T174332-1290372`; KWin/Wayland est vivant. Le service systemd Flex reste inactif conformément au pilotage par Home Controller.

KScreen observe HDMI-A-6 connecté en 3840×2160 @ 60 Hz, échelle 2, profondeur courante 10 bits. Le snapshot capacités régénéré le 10/10 associe affichage et traitement à l'Arc A310 PCI `0000:03:00.0`; les capacités VAAPI restent publiées par GPU. Une résolution sans lancement de la politique DVD installée donne `RECIPE_MAG_SD_FSRCNNX16_KRIG_VIBRANCE_MILD`, liaison Vulkan au même PCI/UUID, `--hwdec=vaapi-copy`, HQDN3D CLEAN puis FSRCNNX-16, KrigBilateral et Vibrance Mild.

Statut intermédiaire à l'installation : candidat **INSTALLED / SOFTWARE_READY** sur `.229`, avant qualification physique.

## Fermeture du gate `.229` — A310 physiquement qualifiée

Steve confirme sur `.229` : **image « top »**, son OK en passthrough, fermeture correcte, retour Flex correct et Santé globale PRÊT. Cette déclaration opérateur constitue la preuve physique ; elle est corroborée par la télémétrie de la dernière lecture DVD à 19:53:58 Europe/Brussels : `playback_started=true`, sortie code 0, rendu Vulkan A310 PCI `0000:03:00.0` PROVEN, backend `vaapi-copy` matériel OBSERVED sans fallback. L'identité physique du GPU de décodage reste conformément au contrat `NOT_PROVEN` et n'est pas déduite du GPU de rendu.

Le passthrough AC3 est ACTIVE via PipeWire sur `alsa_output.pci-0000_04_00.0.hdmi-surround71`, sans fallback. La transaction refresh est `RESTORED` : 3840×2160 60 Hz → 50 Hz vérifié → 60 Hz restauré et vérifié. Après sortie : aucun mpv, matcher, dispatcher DVD ou kdialog résiduel ; verrous playback/DVD/refresh/MEDIA disponibles ; une seule instance Flex reste active. Doctor demeure **READY**, runtime ownership PASS, une instance UI et un moniteur optique.

Le gate `.229` est donc **FERMÉ / PHYSICALLY_QUALIFIED** pour le parcours A310 ciblé demandé : Flex, Magnificence DVD, image, passthrough HDMI, fermeture, retour Flex, restauration d'affichage et Santé globale. Le candidat 1.3.1 a désormais passé les gates `.67` et `.229`. Prochaine action : présenter le bilan final, les limites conservées et le diff à Steve, puis demander son autorisation explicite avant tout commit. Aucun commit, push, tag ou release n'est encore autorisé par ce jalon.

## Autorisation de finalisation 1.3.1

Après présentation du bilan, Steve autorise explicitement la finalisation de l'identité **OPENHTPC 1.3.1**, la préparation et la vérification de l'artifact, puis la création du commit correspondant. Cette autorisation n'inclut **ni push, ni tag, ni publication/release distante**.

Les autorités de version sont préparées avec `VERSION=1.3.1`, `payload/VERSION=1.3.1`, build ID `public-release-1.3.1`, produit `OPENHTPC 1.3.1` et date de build 2026-10-10. README, changelog, installateur, tests de cohérence et notes de version bilingues 1.3.1 sont alignés. L'artifact officiel doit être construit uniquement après le commit, depuis son HEAD exact, avec Flex reconstruit et provenance schema 2.

Après ce changement d'identité, la suite canonique redonne **2273 PASS, 11 FAIL, 18 SKIP** dans le sandbox ; les onze échecs sont exactement les cas réseau/IPC/Wayland empêchés de créer des sockets. La relance hors sandbox des trois fichiers concernés donne **98/98 PASS**. Résultat dédupliqué inchangé : **2284 PASS, 18 SKIP, 0 FAIL**. Les validations de métadonnées 1.3.1 et les syntaxes Bash installateur/updater passent.

Le vieux `tools/validate_public_candidate.py`, intitulé lui-même « Public Candidate R2 », donne 59/65 : il attend encore littéralement `1.1.0-dev38` et `rc3-final-dvd-policy-refresh-corrective-dev1`, exige une ancienne chaîne textuelle d'asset, scanne des documents/tests opérateur pour des chemins privés, et compare le vieux binaire Flex brut du payload à sa métadonnée historique. Il est classé **STALE / non autorité de release 1.3.1** ; ses échecs ne sont ni masqués ni transformés en PASS, et ses contrôles n'ont pas été affaiblis. L'autorité artifact actuelle est `tools/openhtpc-devctl build` puis `verify`, qui exporte le commit exact, reconstruit Flex depuis cette source et vérifie manifeste, SHA et provenance schema 2.

Le commit de release autorisé a ensuite été créé et l'artifact canonique `artifacts/OpenHTPC-1.3.1.tar.gz` construit depuis le commit exact. Les autorités durables de ce build sont `artifacts/OpenHTPC-1.3.1-report.json` et `artifacts/OpenHTPC-1.3.1.tar.gz.sha256` (artifacts volontairement ignorés par Git). Le gate requis est : `openhtpc-devctl verify` PASS, validation des métadonnées d'archive PASS, checksum PASS et `install.sh --check` extrait PASS sans mutation. Le rapport porte le commit source exact et la métadonnée Flex schema 2 ; il doit rester l'autorité pour le SHA final après toute reconstruction du commit. Aucun push, tag, signature ou publication n'a été effectué.
