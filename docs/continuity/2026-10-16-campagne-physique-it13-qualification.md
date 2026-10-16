# 2026-10-16 — Campagne physique de qualification IT13 et enregistrement du statut

**Statut de ce document** : point de continuité opérationnel. Il consigne une campagne **réalisée
et acceptée**, et l'enregistrement canonique qui en découle. Il ne propose rien : il enregistre.

## Reprise et autorité

- **Auteur du projet et autorité finale** : Steve Dehanne.
- **Ce que Hermes a fait** : préparé et révisé le banc de mesure, analysé la campagne, rendu le
  verdict point par point, puis écrit le statut dans le profil sur autorisation explicite.
- **Ce que Steve a décidé** : acceptation de la campagne du 16/10 comme qualification physique
  réussie **pour le périmètre exact testé**, autorisation d'enregistrer `PHYSICALLY_QUALIFIED` pour
  le profil `intel_meteor_lake_8086_7d55_sd_2160p`, **sans toucher à la recette, au tier ni à la
  portée**, et refus explicite de toute promotion fondée sur une estimation d'opérateur.

Le fait est établi par la mesure ; l'écriture du statut est un acte de l'opérateur, autorisé.

## Périmètre qualifié — exactement

| | |
|---|---|
| plateforme | IT13 Max, `192.168.1.59`, installé OPENHTPC 1.3.1 |
| GPU | Intel `8086:7d55` (`0000:00:02.0`), UUID Vulkan `8680557d-0800-0000-0002-000000000000` |
| source | DVD PAL MPEG-2, 720×576, 25 i/s, 16/9 — disque `Alexander_DVD1_vente`, génération 4 |
| sortie | 3840×2160@60 |
| recette | `RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD` |
| tier | `STRONG` (inchangé) |
| lecture | **13:08:58 → 13:30:35**, soit **21 min 37 s** |
| fenêtre instrumentée | **1200 s pleines** (1260 s de session), 2579 échantillons produit |

## Le banc, et pourquoi il a été révisé

Sonde `it13_installed_profile_probe.py`, écrite pour observer une lecture de bout en bout sans
rien lancer. La **première campagne du matin** a été déclarée non mesurable : la sonde retenait un
processus auxiliaire portant la commande de mpv dans son `argv` (`"mpv" in cmdline`), et n'en
mesurait aucun chiffre utile. Quatre défauts ont été corrigés de façon bornée (schéma de mesure et
`interval` inchangés, tout additif, chiffres comparables à la campagne de référence du 11/10) :

- identification de mpv par son **exécutable** (`/proc/<pid>/exe`), pas par sa ligne de commande ;
- `argv` lu **à la détection** du processus (le lire après sa mort rend une chaîne vide) ;
- survie à la mort d'un premier mpv et rattachement au suivant, avec filtre sur la recette résolue
  et avancement par curseur ;
- copie périodique (30 s) **et** finale du journal mpv et des fichiers de preuve du produit, que le
  produit supprime en fin de lecture.

La révision a été revalidée avant réutilisation : sortie **identique octet pour octet** sur la
télémétrie du 11/10, et batterie de tests prouvant chaque défaut dans les deux sens.

## Verdict point par point

| point | verdict | source |
|---|---|---|
| détection du DVD physique | **PROUVÉ** | `optical-current.json` : `DVD_VIDEO`, `/dev/sr0`, `detected: true`, `DISC_STRUCTURE`, CERTAIN ; `optical_generation=4` consommée par la lecture |
| classification `DVD_PAL_FILM` | **corroborée, non lue** | attributs mesurés du disque = `source_scope` exact du profil ; aucun champ « portée » dans les preuves capturées |
| sélection du profil `8086:7d55` | **PROUVÉ** | `PLAYBACK_POLICY` : `CINEMA_AUTO` → `RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD`, motif `magnificence_profile` ; `GPU_RENDER_BINDING` PCI `0000:00:02.0`, `RENDER_BOUND` |
| tier `STRONG` | **PROUVÉ** | `classification_tier STRONG`, confiance `OPENHTPC_PHYSICAL_QUALIFICATION` |
| FSRCNNX-16 + KrigBilateral + Vibrance | **PROUVÉ PAR EXÉCUTION** | `vo_passes.fresh` de la télémétrie : `feature map 1..4`, `mapping 1_1..4_4`, `sub-band residuals 1..4`, `sub-pixel convolution 1`, `aggregation` ; trois passes `KrigBilateral` ; `OPENHTPC Vibrance Mild` |
| `vaapi-copy` | **PROUVÉ** | journal mpv : `Trying hardware decoding via mpeg2video-vaapi-copy` puis `[i][vd] Using hardware decoding (vaapi-copy)`, format décodeur `nv12` |
| **BWDIF** | **PROUVÉ par construction du graphe** | journal mpv : `mpv_src_in0 … nv12 \| auto_scale_0 \| Parsed_bwdif_0 (bwdif) \| mpv_sink_out0` — les images rapatriées du GPU sont bien désentrelacées par BWDIF, ce qui est le mécanisme même que la recette revendique |
| `gpu-next` / libplacebo | **PROUVÉ** | `vo/gpu-next/libplacebo v7.360.1` dans le journal |
| bascule 60 → 50 Hz | **SANS OBJET, mesuré** | `refresh-match-last.json` : `status: DISABLED`, `switch_requested`/`switch_verified` à `false` |
| démarrage réel | **PROUVÉ** | `PLAYBACK_BEGIN` / `PLAYBACK_PROCESS_STARTED`, `playback.log` à 13:08:58, `media_opened: true` |
| décodage observé | **PROUVÉ côté produit** | `vaapi-copy`, `hardware_active: true`, `status OBSERVED` ; moteur DRM `video` occupé sur 1128 des 1178 échantillons (moyenne 0,87 %, max 2,33 %) |
| pertes d'images | **PROUVÉ : zéro** | sur 2579 échantillons produit : `frame_drop_count`, `decoder_frame_drop_count`, `vo_delayed_frame_count` et leurs maxima à **0** ; avsync max 131 µs, min −23,6 ms |
| erreurs mpv | **zéro sur la fenêtre journalisée** | 0 ligne de niveau erreur sur 11 137 lignes, sur les 4 min 24 s que mpv écrit ; deux avertissements à t = 0,060 s (client IPC du produit pendant un hook de démarrage), sans rapport avec la lecture |
| charge CPU / GPU | **MESURÉ** | mpv **19,70 % d'un cœur** (p95 21,18) ; RSS 479 496 → 612 940 ko ; moteur `render` moyenne **52,23 %** (p95 57,32, max 63,48) ; fréquence GPU médiane 2283 MHz |
| températures | **MESURÉ** | paquet CPU moyenne **56,43 °C**, p95 **59 °C** ; acpitz constant 27,8 °C |
| audio | **PROUVÉ** | `requested PCM` → `resolved PCM`, motif `user_requested_pcm`, source AC3, AO pipewire, passthrough INACTIF, `fallback false` |
| arrêt propre | **PROUVÉ** | sortie mpv **code 0** ; `PLAYBACK_PROCESS_EXITED` puis `PLAYBACK_END` ; `playback_teardown_forced false` ; aucun processus résiduel |
| retour correct à Flex | **PROUVÉ** | aucun `FLEX_STARTED` entre `PLAYBACK_END` (13:30:35) et l'arrêt volontaire de la machine : l'instance Flex en place n'est jamais tombée et c'est elle qui était à l'écran ensuite |
| restauration du mode d'affichage | **SANS OBJET** | `restore_requested false` : rien n'avait été changé, l'écran est resté en 4K60 |
| observation opérateur | **consignée comme telle** | aucune anomalie visuelle signalée, y compris sur une séquence volontairement très animée |

**Stabilité sur 20 minutes pleines**, lue en cinq tranches de 4 minutes : rendu
52,2 / 52,3 / 52,1 / 52,2 / 52,4 %, CPU mpv 19,6 / 19,6 / 19,6 / 19,8 / 19,9 %, GPU
2248–2257 MHz, température moyenne 55,8–56,9 °C. **Aucune dérive, aucune perte.**

## Ce qui a été enregistré

`payload/assets/magnificence_profiles.json`, profil `intel_meteor_lake_8086_7d55_sd_2160p` :
ajout d'un bloc `physical_qualification` **distinct**. Rien d'autre n'a bougé — vérifié champ par
champ avant/après (`magnificence`, `classification`, `source_scope`, `display_scope`, `gpu`,
`measurement`, `software`) et par comparaison du fichier auquel le bloc inséré a été retiré.

Point d'attention conservé : les sélecteurs du produit gardent `magnificence.status` sur son
**préfixe** (`TECHNICALLY_QUALIFIED…`). Ce préfixe n'a **pas** été touché — le modifier aurait
retiré le profil de la sélection, en silence.

## Écarts constatés

- **Durée de la première campagne du matin** : l'opérateur rapportait « plus de 20 minutes », la
  mesure produit donnait 9 min 32 s (11:56:28 → 12:06:00). Décision : retenir la mesure produit,
  ne pas surclasser une estimation. La campagne retenue ce jour fait, elle, **21 min 37 s**,
  conforme au rapport d'opérateur — la mesure et l'observation concordent cette fois.
- **Fenêtre d'erreurs mpv** : le journal ne couvre que 4 min 24 s sur 21 min 37 s ; l'absence
  d'erreur est prouvée sur cette fenêtre, le reste de la lecture étant couvert par la télémétrie du
  produit (0 perte sur 2579 échantillons).
- **Défaut du banc découvert pendant la campagne** : la sonde capturait les fichiers produit à
  l'instant de la durée cible alors que mpv vivait encore, donc copiait l'état de la lecture
  **précédente** (mesuré : télémétrie horodatée 12:06:00 pour la lecture 13:08:58→13:30:35). N'a
  faussé **aucun chiffre de rendu** — seulement le rangement de la copie de session. Corrigé en
  **révision 3** de la sonde (attente de la mort réelle de mpv, champ `capture_after_exit`,
  détection de zombie), validée et **conservée hors dépôt** : c'est un outil de qualification de
  poste, pas un composant produit.
- **Annonce réseau corrigée** : une disparition de `.59` avait été rattachée à la veille de la
  machine. La mesure dit l'inverse — arrêt propre et volontaire (`The system will power off now!`,
  `poweroff.target`), puis redémarrage. Consigné pour ne pas hériter d'une inférence.

## Limites — hors qualification

Nommément exclues de la qualification enregistrée :

- **endurance film complet** : 21 min 37 s observées pour un disque de 2 h 48 min 29 s ;
- **autres sources et autres sorties** : non testées ;
- **bruit du ventilateur** : non mesuré (aucun capteur disponible) ;
- **exact physical GPU binding du décodage** : `physical_gpu_binding` reste `NOT_PROVEN` ;
- **pics thermiques isolés** : 14 échantillons sur 1178 (1,2 %) entre 72 et 95 °C, isolés d'une
  seconde, avec CPU et fréquence normaux au même instant ; **cause non établie**, à traiter par une
  mesure bornée dédiée si on veut trancher — en aucun cas par une retouche de la donnée qualifiée ;
- **validation spécifique d'une source 10 bits** : le finding « dithering 8 bits observé contre
  `bit_depth_observed: 10` » reste **OUVERT** et ne bloque pas cette qualification.

## Preuves conservées

- **Lot hors machine** : partage NAS `192.168.1.10`, dossier
  `htpc project/hermes-it13-20261016b` — 34 fichiers, 4,7 Mio, empreintes sha256 **relues depuis la
  destination**.
- **Course de sonde** : `~/.local/state/openhtpc-it13-qualification/20261016T102110Z-installed-profile`
  sur `.59`.
- **Journal produit** : `playback.log`, 13:08:58 → 13:30:35, `exit_code=0`, `optical_generation=4`.
- **Enregistrement** : bloc `physical_qualification` du profil (statut `PHYSICALLY_QUALIFIED`,
  10 preuves, 6 exclusions nommées).

## Prochaine action

Aucune sur ce périmètre : la qualification est enregistrée et ses limites sont écrites. Les suites
possibles sont des chantiers **séparés**, chacune demandant sa propre décision : endurance film
complet, autres sources et sorties, mesure bornée des pics thermiques, finding 8/10 bits.
