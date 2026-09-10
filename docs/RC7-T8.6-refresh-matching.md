# RC7 T8.6 — adaptation temporaire de fréquence

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

## Preflight et autorités

Le 09/09/2026, HEAD de départ 5f3b26b : configuration sans adaptation active,
aucun handshake MPV pausé, T8.5 strictement post-mortem. Le préflight KScreen
passif du salon expose HDMI-A-6, output ID 1, currentModeId 1, 3840×2160,
60 Hz, scale 2, HDR désactivé. Modes de même résolution : 23.976, 24, 25,
29.97, 30, 50, 59.94 et 60 Hz (certains timings ont plusieurs IDs).

T8.4 `collect_display()` / `parse_kscreen_json()` restent l'unique collecteur.
Extension additive : identifiant KScreen, currentModeId, modes et empreinte de
l'EDID valide du connecteur actif. Aucun mode EDID préféré n'est utilisé comme
mode courant. Aucun tableau Passport n'est utilisé pour commuter.

Le mécanisme KDE est `kscreen-doctor output.<ID>.mode.<MODE_ID>` ; il sélectionne
un mode existant via `setCurrentModeId`, sans arguments scale/HDR/bpc.
Source primaire : https://github.com/KDE/libkscreen/blob/master/src/doctor/doctor.cpp
L'opération KScreen applique une configuration d'output, pas une garantie que
le matériel ne resynchronise jamais le lien. Relecture et vérification requises.

## Cadence et limite V1

Fichiers locaux : `probe_media()` existant (ffprobe) fournit les deux taux
rationnels avg_frame_rate et r_frame_rate. Un seul flux vidéo, taux positifs
égaux, pas d'entrelacement déclaré ; échantillon borné des timestamps décodés
et vérification d'absence d'entrelacement. Les timestamps quantifiés à la
milliseconde sont tolérés. La cadence vient des rationnels, jamais du nom.
Ce contrôle ne promet pas une cadence constante au-delà de l'échantillon.
Les contenus à cadence variable/données incohérentes sont refusés dès qu'ils
sont identifiés ; aucune adaptation en cours de lecture.

DVD et Blu-ray/protégé passent par le même helper, avec cadence indisponible :
aucune commutation. Ni ffprobe sur média chiffré, ni réutilisation d'un log
T8.5 précédent, ni hypothèse PAL/NTSC. Une future cadence live nécessiterait
une tranche distincte ; T8.5 n'est pas transformé en télémétrie live.

## Politique et transaction

`refresh_matching=OFF` par défaut, y compris migration. Choix AUTO/OFF par
SYSTÈME → AFFICHAGE, persistance canonique `write_preference()`. Le libellé
indique une politique, pas un résultat observé. Les autres préférences restent
conservées. Une modification du réglage ne commute jamais directement l'écran.

Un seul output actif et identifié par connecteur + ID KScreen + hash EDID.
Résolution identique uniquement. Tolérance 0.003 Hz ramenée à la cadence ; les
familles 1000/1001 restent distinctes. Mode courant déjà multiple entier : pas
de mutation. Sinon plus basse fréquence compatible (exacte avant multiple).
Pas de politique 3:2. Les modes sont exclusivement des IDs KScreen existants.

`openhtpc-refresh-match.py` centralise sélection, exécution et restauration.
Verrou flock non bloquant conservé sur tout le cycle. Le concurrent ne commute
pas et n'écrase pas le journal du propriétaire. PREPARED est persisté avec
fsync avant requête, puis APPLIED après vérification. Le finally restaure
l'ID original exact, vérifie l'état et publie RESTORED avant suppression.
SIGTERM/SIGHUP lèvent une sortie dans le wrapper ; subprocess.run termine et
attend son enfant avant restauration. SIGKILL/panne : journal récupérable.

Au démarrage OPENHTPC et avant une nouvelle tentative : récupération de
PREPARED/APPLIED seulement si même identité, un seul output et timing de
l'ID original inchangé. Sinon RECOVERY_UNSAFE, aucune mutation. Un journal
illisible est également conservé et bloque la nouvelle commutation.
Aucune recherche approximative de mode de secours. Une restauration échouée
reste explicite et récupérable. Aucun killall, aucun paramètre Fedora écrit.

Journaux locaux : `.local/state/openhtpc/refresh-transaction.json` et
`refresh-match-last.json`. Les diagnostics conservent cadence, original,
cible et résultat de vérification lorsqu'ils ont réellement été observés.
Le schéma T8.5 est inchangé. Le retour protégé reste soumis au dispatcher suivi.

## Qualification

Tests hermétiques : modes synthétiques, runtime injecté, arrêt normal et
exceptions, récupération, identité/ID réutilisé, concurrence, paramètres KDE
mode-only, réglage/migration, modèles T8.4/T8.5.
Aucune commutation réelle réalisée par l'agent avant qualification.
Première qualification physique : un fichier local progressif connu
23.976/24 fps, activer AUTO dans OPENHTPC, lire puis arrêter et vérifier le
retour. L'agent lit les journaux et KScreen, Steve observe image/son/retour.

## Correction après premier essai physique

Le chemin local absolu était correctement transmis, sans URI ni perte de
quoting. Sur le fichier réel, avg_frame_rate et r_frame_rate valaient tous deux
24000/1001. Le rejet provenait du dernier intervalle de l'échantillon ffprobe,
doublé lors de la vidange du décodeur à la limite en paquets. Le même défaut
se déplaçait à la dernière paire avec 160, 192 puis 320 paquets, tandis que
l'intervalle auparavant rejeté était normal avec davantage de données.

La fenêtre validée est désormais explicitement les 128 premières images,
avec au moins 32 images de lookahead, sur la même sonde bornée à 160 paquets.
Les seuils par intervalle et taux moyen restent inchangés. Une discontinuité
interne reste refusée. Ce n'est pas une garantie de CFR sur tout le fichier.

Chaque tentative garde une archive `refresh-attempts/<owner>.json`, avec hash
du chemin (sans contenu ni titre), source, rationnel, décimal, raison du probe,
comptages d'images, décision, modes, demandes et vérifications, résultat de
lecture et restauration. Le dispatch_id local est corrélé. `playback_started`
est confirmé après retour du runner, pas déduit d'un écran noir. Le journal
courant peut suivre la tentative suivante sans supprimer la preuve archivée.

Validation passive réelle après correction : 24000/1001 accepté, AUTO,
3840×2160 à 60 Hz, cible mode 17 à 23.975999832 Hz. Aucune commutation de
qualification effectuée par l'agent.

## Télémétrie de présentation MPV

Lors de la lecture (qu'elle soit adaptée en fréquence ou conservée à 60 Hz),
`openhtpc-refresh-match.py` injecte un serveur IPC local dédié sur socket UNIX
d'exécution (`openhtpc-mpv-<owner>.sock`) et échantillonne passivement les
propriétés MPV exposées au runtime :
`video-sync` effectif, cadences déclarées et estimées (`container-fps`,
`estimated-vf-fps`, `display-fps`, `estimated-display-fps`), rapports de
synchronisation (`vsync-ratio`, `vsync-jitter`), compteurs de pertes et de retards
(`frame-drop-count`, `decoder-frame-drop-count`, `mistimed-frame-count`,
`vo-delayed-frame-count`), décalage A/V (`avsync`, `total-avsync-change`) et
chronométrage des passes de rendu du vo (`vo-passes`).
Les valeurs absentes ou non exposées restent `null` sans invention.
Le résultat est persisté dans `refresh-match-last.json`, dans l'archive de la
tentative `refresh-attempts/<owner>.json` et dans `presentation-telemetry-last.json`,
associé au `dispatch_id` courant.
