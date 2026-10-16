# OPENHTPC — protocole de l'essai physique IT13 Max `.59` (profil installé)

Hermes, 2026-10-15. Essai **non encore déclenché** : ce document décrit ce qui est armé et ce que
Steve doit faire. Aucune recette n'est modifiée, rien n'est lancé par Hermes.

## 1. Ce que cet essai doit prouver — et ce qu'il ne prouve pas

Le profil exact `intel_meteor_lake_8086_7d55_sd_2160p` est **software-verified** : il est présent
dans les assets installés, et `openhtpc cinema-auto --scope DVD_PAL_FILM` résout bien, **mesuré sur
`.59` aujourd'hui** :

    recette RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD · profil 8086:7d55
    tier STRONG · affichage 3840x2160 · QUALIFIED_STATIC_PROFILE

Ce qui n'a **jamais** été fait, et que cet essai apporte : la **lecture physique post-installation** —
c'est-à-dire observer le produit lire réellement ce disque, avec cette recette, sur cette
installation. Tant que ce n'est pas fait, le profil reste `INSTALLED / SOFTWARE-VERIFIED`, jamais
`PHYSICALLY_QUALIFIED`.

Cet essai **ne** prouve **pas** : l'endurance sur film complet (item séparé), les autres sources,
le bruit ventilateur, ni l'intégration dans les règles familiales. Il ne touche aucun preset.

## 2. État de départ mesuré (2026-10-15, avant essai)

| Point | Valeur mesurée |
| --- | --- |
| Hôte | `IT13Max` / `.59`, Fedora 44, KDE/Wayland, Core Ultra 9 185H, 22 Gio |
| OPENHTPC installé | `1.3.1`, Doctor **READY** (tous PASS ; TMDb `NOT_CONFIGURED`) |
| GPU | `0000:00:02.0` Intel Arc Meteor Lake `8086:7d55`, Mesa 26.2.4, Vulkan 1.4.354 |
| Disque présent | `/dev/sr0` — DVD-VIDEO **non protégé**, `Alexander_DVD1_vente`, 2 h 49 min, 20 chapitres |
| Source du disque | MPEG-2 **PAL 720x576, 25 i/s**, 16/9 — exactement la portée `DVD_PAL_FILM` du profil |
| Audio du disque | AC3 5.1 français, AC3 5.1 anglais, AC3 2.0 anglais |
| État optique produit | `canonical_state = DVD_VIDEO`, `classification_source = DISC_STRUCTURE`, confiance `CERTAIN` |
| Affichage | HDMI-A-1, **3840x2160@60.00 actif** ; le mode **3840x2160@50.00** est disponible (nécessaire au PAL) |
| Audio produit | cible `SYSTEM` / mode `PCM` (état d'usine, non reconfiguré depuis la réinstallation) |
| Session | aucune instance OPENHTPC en cours (retour au bureau à 16 h 22 ce matin) |

## 3. Instrumentation armée

Sonde : `~/openhtpc-qualification/it13_installed_profile_probe.py` (copiée sur `.59`), lancée en
tâche de fond, en attente du mpv **du produit** — elle ne lance rien elle-même.

- run : `~/.local/state/openhtpc-it13-qualification/20261015T144937Z-installed-profile/`
- fenêtre : 60 s de préchauffage puis **1200 s de mesure** à partir de l'apparition de mpv
- échantillonnage 1 s : température paquet CPU (coretemp), acpitz, fréquence GPU, CPU mpv,
  RSS mpv, occupation des moteurs DRM (`render`, `copy`, `video`, `video-enhance`, `compute`)
  lue dans `/proc/<pid>/fdinfo`
- toutes les 2 s : mode d'affichage actif (kscreen-doctor) et télémétrie de présentation du produit
  (`presentation-telemetry-last.json` : les champs RÉELS du produit sont `switch_requested`,
  `switch_verified`, `restore_requested`, `restore_verified`, `settled`, `status` — cette
  installation n'expose ni `PREPARED`, ni `APPLIED`, ni `RESTORED`)
- sorties : `telemetry.jsonl` (écrit à chaque seconde, résiste à un arrêt brutal), `telemetry.json`,
  `summary.json` — **même schéma** que la campagne du 2026-10-11, donc chiffres comparables

Validation de la sonde avant usage, faite aujourd'hui :

- ses statistiques **reproduisent à la 6e décimale** le résumé conservé du 2026-10-11 sur les sept
  métriques (p95 et moyenne : `render_busy_pct` 53,472571 / 51,643905 ; `vo_pass_sum_ms`
  21,196656 / 19,608872 ; températures, fréquence GPU, CPU, RSS) — méthode de mesure identique,
  vérifiée par recalcul sur les fichiers sources de la veille ;
- lectures réelles sur `.59` : capteurs, fréquence GPU (883 MHz au repos), moteurs DRM (les cinq
  moteurs lus sur un vrai client GPU), mode d'affichage (4K60 lu).

**CORRECTION du 2026-10-16 — la limite déclarée ici était FAUSSE.** Ce document affirmait que le
produit démarre mpv **sans** `--input-ipc-server`, donc que le temps par passe (`vo-passes`) et les
compteurs de pertes d'images n'étaient pas observables en mode produit.

Mesuré le 2026-10-16 sur `.59`, dans l'argv complet du mpv du produit : **le produit démarre bien
mpv avec** `--input-ipc-server=/tmp/openhtpc-mpv-<identifiant>.sock`. `vo-passes` et les compteurs
de pertes sont donc disponibles, par deux voies indépendantes :

- la télémétrie de présentation du produit (`presentation-telemetry-last.json`) : `vo_passes.fresh`
  porte la liste des passes RÉELLEMENT exécutées, avec leurs noms et leurs temps, et
  `frame_drop_count` / `decoder_frame_drop_count` / `vo_delayed_frame_count` y figurent avec leurs
  maxima ;
- le socket IPC lui-même, interrogeable pour `vo-passes` et `frame-drop-count`.

Conséquences : la « relance instrumentée » (`--mode replay`) n'est plus nécessaire pour obtenir ces
champs ; elle reste utile pour une mesure en direct. La sonde, elle, déclare encore
`availability.mpv_ipc_stats = false` : c'est un défaut d'outillage à corriger (révision 3), pas une
limite du produit. Ce qui continue d'être jugé sur les autres indicateurs : la stabilité,
l'occupation GPU/CPU avec marge et les températures.

## 4. Ce que Steve fait — une seule action

Sur `.59`, devant l'écran :

1. lancer **OPENHTPC** (icône du bureau ou menu d'applications → OPENHTPC) ;
2. choisir **LIRE LE DVD** ;
3. regarder la lecture démarrer, laisser tourner **au moins 20 minutes** (la fenêtre de mesure),
   puis quitter la lecture normalement (arrêt habituel, comme d'habitude) ;
4. me dire ce qu'il a vu : image, son, saccades éventuelles, bruit du ventilateur, et si le retour
   à Flex puis au bureau s'est bien passé.

Rien d'autre. Hermes ne lance pas l'application et ne touche à rien : il observe.

Si quelque chose se comporte mal, l'arrêt normal suffit — la mesure s'arrête d'elle-même à la mort
de mpv, et les 20 minutes écoulées restent exploitables.

## 5. Ce que je mesure ensuite, point par point

| À prouver | Source de preuve |
| --- | --- |
| détection du DVD physique | `optical-current.json` (état canonique, génération, appareil) + journal produit |
| classification `DVD_PAL_FILM` | décision de politique du produit (JSON de lecture) : `presentation`, portée, résolution, cadence |
| sélection du profil `8086:7d55` | même JSON + `openhtpc cinema-auto` relu après coup |
| tier `STRONG` | `classification_tier` du profil résolu |
| recette `FSRCNNX-16 + Krig + Vibrance` | **arguments mpv exacts** du produit (`--glsl-shaders-append=…`), lus dans son propre JSON de politique et son journal mpv |
| chaîne vidéo prévue (BWDIF, vaapi-copy, gpu-next) | journal mpv : `--vf=lavfi=[bwdif…]`, `Looking at hwdec…`, `Using hardware decoding (…)`, vo `gpu-next` |
| bascule 60 → 50 Hz | **sans objet sur cette installation** : `refresh-match-last.json` rend `status: DISABLED` avec `switch_requested` et `switch_verified` à `false` — aucun appariement de fréquence n'est demandé et l'affichage reste à 60 Hz. Si un jour il était activé, lire `switch_requested`/`switch_verified`, **et** le `Hz:` du vo wayland dans le journal mpv, **et** la chronologie de la sonde |
| démarrage réel de la lecture | existence du processus mpv, événements produit (`PLAYBACK_PROCESS_STARTED`, `PLAYBACK_BEGIN`), croissance du journal |
| décodage observé | `hwdec-current` / analyse du journal par l'outil du produit (`openhtpc-playback-analyze.py`) |
| pertes d'images / erreurs mpv | erreurs et avertissements comptés dans le journal mpv **et** compteurs de pertes lus dans `presentation-telemetry-last.json` (`frame_drop_count`, `decoder_frame_drop_count`, `vo_delayed_frame_count` et leurs maxima) — **observables** en mode produit, voir §3 |
| charge CPU / GPU | sonde : CPU mpv (% d'un cœur), moteurs DRM `render`/`video`/`copy`, fréquence GPU |
| températures | sonde : paquet CPU, acpitz ; p95/min/max sur la fenêtre mesurée |
| stabilité | sonde : dispersion sur 20 min, absence de dérive thermique, absence de sortie de la fenêtre |
| audio | politique audio du produit (`requested`/`resolved`/`reason`) + sortie observée |
| arrêt propre | code de sortie mpv, absence de processus et de verrou résiduels |
| retour correct à Flex | événements produit (`PLAYBACK_END`, retour d'interface), instance Flex unique |
| restauration du mode d'affichage | `refresh-match-last.json` : `restore_requested` / `restore_verified` (à `false` quand aucun changement n'a été demandé) + mode relu par la sonde |

Tout ce qui ne sera pas observé sera écrit comme tel — jamais comblé par déduction.

## 6. Ce qui restera `NOT_PROVEN` après cet essai

- décodeur **physique** employé pour le MPEG-2 (le produit et mpv prouvent `vaapi-copy` observé,
  pas quel moteur matériel décode) ;
- *(retiré le 2026-10-16 : `vo-passes` et compteurs de pertes sont observables en mode produit — voir §3)* ;
- endurance film complet, autres sources, bruit, intégration dans les règles familiales ;
- qualité visuelle : elle n'appartient qu'à Steve (aucune mesure ne remplace son œil).

## 7. Après l'essai

1. rapatriement du run depuis `.59` (télémétrie, journal mpv, JSON de politique) et préservation
   hors machine avec `MANIFEST.sha256` — la leçon du 2026-10-11 (`/tmp` non durable) ne se répète pas ;
2. analyse : tableau point par point du §5, avec la source de chaque affirmation ;
3. checkpoint daté proposé à Steve ou Codex — **aucune promotion de statut décidée par Hermes**.
