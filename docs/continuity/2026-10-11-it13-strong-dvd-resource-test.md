# IT13 Max — essai ressources DVD avec candidat STRONG

Date : 2026-10-11, Europe/Brussels.

## Mandat et limites

Steve a inséré le DVD `Alexander_DVD1_vente` dans le GEEKOM IT13 Max `.59` et a autorisé une lecture réelle de la recette candidate la plus lourde retenue pour observer ressources iGPU, température et nuisance sonore. Cette autorisation couvrait l'essai, pas l'installation d'un profil, le déploiement, la publication ni la qualification visuelle de Magnificence.

Le dépôt de contrôle était sur `feature/magnificence-sd-auto`, HEAD `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`, avec le dirty worktree et les deux stashes préexistants préservés. L'installation `.59` réellement testée est OPENHTPC `1.3.1` / `public-release-1.3.1`. L'affichage Système validé par Steve est resté inchangé.

## Banc d'essai isolé

Un lanceur temporaire `/tmp/openhtpc_it13_strong_probe.py` (version finale SHA-256 `3458fca83fc89f63102a8d25c19cc34cf6e9c395c5d6240e355aa8000ee5c67c`) a lancé et suivi l'enfant MPV exact, sans modifier les fichiers installés. La lecture était plein écran et muette afin de rendre le bruit mécanique/ventilation perceptible. La fermeture a utilisé l'IPC MPV puis attendu l'enfant exact.

Chaîne demandée, dite `STRONG sans SSim` :

1. BWDIF conditionnel ;
2. `FSRCNNX_x2_16-0-4-1.glsl` ;
3. `KrigBilateral.glsl` ;
4. `OpenHTPC_Vibrance_Mild.glsl` ;
5. `rgba16hf`, `ewa_lanczossharp`, `mitchell`, `sigmoid-upscaling=yes`.

Le lancement incluait le `pure.conf` effectif, l'UUID Vulkan opaque validé et l'ajout `mpeg2video` à la whitelist de décodage, identique à la décision positive de `openhtpc-playback-policy.py` pour un DVD. Le run final ajoutait temporairement `--hwdec=vaapi-copy`, précédent déjà utilisé par les profils exacts A310/RX5700XT pour exposer les trames à un filtre logiciel. Il n'a injecté ni `vaapi-device`, ni changement de pilote, ni profil persistant.

## Essais et preuves fraîches

Un premier smoke a mis en évidence que la commande isolée initiale n'avait pas repris l'extension MPEG-2 de la politique : `hwdec-current=no`. Cette mesure n'a pas été utilisée comme preuve du chemin de décodage final. Après correction du banc, un smoke de 60 s a observé `hwdec-current=vaapi`, activité moteur vidéo moyenne `1,10 %`, rendu moyen `50,59 %`, temps shaders p95 `20,34 ms`, température package moyenne `53,60 °C`, et zéro perte.

Une première endurance directe a tourné du `2026-10-11T12:04:41Z` au `2026-10-11T12:16:52Z`, avec 60 s de chauffe puis 634 mesures utiles sur le titre DVD le plus long. Elle a confirmé la stabilité de la partie rendu, mais le journal a prouvé que BWDIF était désactivé faute de conversion depuis les surfaces VAAPI directes. Ses artefacts de contrôle sont conservés sur `.59` :

- `/home/steve/.local/state/openhtpc-it13-qualification/20261011T120441Z-strong-dvd/summary.json`, SHA-256 `f77bb361238584fe3f3f7f35c64e09920b85d85759153fd22cd8dcb9407ad3a5` ;
- `/home/steve/.local/state/openhtpc-it13-qualification/20261011T120441Z-strong-dvd/mpv.log`, SHA-256 `cfafadce5a98c0fdd457d7fe66aa9c8cf5a1505b2696bc717f215800e0524977` ;
- `telemetry.json`, 3 694 907 octets, SHA-256 `ec43b0af9f11b11e288521ae9dea7f3876ed039b2fb3b239fec6539f53e5911c`, même répertoire.

Le précédent `vaapi-copy` a alors été appliqué uniquement au lanceur temporaire. Un smoke de 60 s a confirmé simultanément `hwdec-current=vaapi-copy`, un graphe BWDIF actif et zéro perte. L'endurance finale complète a tourné du `2026-10-11T12:22:13Z` au `2026-10-11T12:34:25Z`, avec 60 s de chauffe puis 634 mesures utiles. Preuves principales sur `.59` :

- `/home/steve/.local/state/openhtpc-it13-qualification/20261011T122213Z-strong-dvd/summary.json`, SHA-256 `93174ebb41831a36e0015ca32f0fd83bf180bdf74dacf6b1ffbe1b9b94ce0008` ;
- `telemetry.json`, SHA-256 `708fa12e54fa3e386693d0a36e0ce569ec2d46ab082610d6f072d528ecdbecda`, même répertoire ;
- `mpv.log`, SHA-256 `f0f8db3730ecdd232cd24aa492ba7c4080ecf2f8fe34cf65d568a12d017c3505`, même répertoire.

| Mesure | Résultat observé |
| --- | --- |
| Source | MPEG-2 PAL 720×576, 25 fps, BT.601, DAR 16:9, sortie 3840×2160@60 |
| Rendu Vulkan | Intel Arc MTL `8086:7d55`, UUID demandé et confirmé par `[vo/gpu-next/libplacebo]` — `PROVEN` pour ce run |
| Décodage / filtre | `[vd] Using hardware decoding (vaapi-copy)`, `hwdec-current=vaapi-copy`, graphe `nv12 → yuv420p → BWDIF` actif — backend `OBSERVED`; PCI physique du décodeur `NOT_PROVEN` |
| Temps total des passes VO | moyenne `19,61 ms`, p95 `21,20 ms`, p99 `22,55 ms`, max `23,76 ms` ; budget source 25 fps `40 ms` |
| Moteur DRM render du contexte MPV | moyenne `51,64 %`, p95 `53,47 %`, max `57,33 %` |
| Moteur DRM video du contexte MPV | moyenne `0,97 %`, p95 `1,12 %`, max `1,25 %` |
| Fréquence iGPU | moyenne `2261 MHz`, médiane `2300 MHz`, p95/max `2350 MHz` |
| MPV CPU | moyenne `19,42 %` d'un cœur, p95 `20,66 %` |
| RSS MPV | moyenne `290 629 KiB`, p95 `316 617 KiB`, max `319 504 KiB` |
| Température package CPU | moyenne `55,96 °C`, médiane `56 °C`, p95 `57 °C`, p99 `64,67 °C`, pic bref `77 °C` |
| Pertes | frame `0`, decoder `0`, delayed `0`; propriété mistimed indisponible |
| Fin | MPV code 0, aucun MPV résiduel, Flex d'origine toujours seul PID `7701` |

La première moitié utile du run complet donne en moyenne `56,04 °C`, `51,71 %` de render, `19,60 ms` et `19,43 %` CPU; la seconde `55,88 °C`, `51,58 %`, `19,61 ms` et `19,40 %`. Cette comparaison ne montre pas de dérive thermique ou de cadence significative pendant la fenêtre testée.

Le noyau n'expose sur cette machine ni température iGPU distincte, ni énergie/package power exploitable par le banc, ni vitesse de ventilateur. La nuisance sonore reste donc une observation humaine de Steve, actuellement `NON ÉTABLIE` dans ce checkpoint.

## Finding de compatibilité et disposition

Les deux journaux prouvent que les shaders FSRCNNX-16, Krig et Vibrance ont été enregistrés et compilés sans erreur. Avec le chemin installé `hwdec=vaapi`, BWDIF n'a pas accepté le pixel format `vaapi` direct : MPV a consigné `failed to configure the filter graph` et a désactivé le filtre. Avec la surcharge temporaire `hwdec=vaapi-copy`, MPV a construit le graphe BWDIF et l'a conservé pendant tout le run, sans perte.

La chaîne complète candidate est donc `SOFTWARE_MEASURED` dans ce mode isolé. Cela ne modifie pas le fait que la recette de famille STRONG déclarée ne porte actuellement pas `--hwdec=vaapi-copy`, et que l'installation `.59` reste LIGHT/direct VAAPI. L'ajout éventuel de cette surcharge à un profil exact IT13 ou à une famille est une décision d'architecture séparée : le test ne la promeut pas automatiquement.

## État après essai et décision

- aucune modification de profil, shader, config OPENHTPC ou installation sur `.59` ; les empreintes de `profile.json`, `pure.conf` et `reference.conf` ont été relevées après l'essai ;
- aucune modification de `.229` ou `.67`, aucun commit/push/publication ;
- chaîne complète `vaapi-copy + BWDIF + FSRCNNX-16 + Krig + Vibrance` soutenue sur cet extrait, avec marge de cadence, sans perte ni dérive thermique mesurée — `SOFTWARE_MEASURED` ;
- après avoir assisté visuellement au résultat sur `.59`, Steve déclare cette recette lourde validée. La chaîne est donc `OPERATOR_PHYSICALLY_QUALIFIED` pour ce DVD PAL, cette sortie 3840×2160@60 et l'installation OPENHTPC 1.3.1 testée ; cette décision ne qualifie pas automatiquement d'autres sources, un film complet, le bruit, ni un profil Auto installé ;
- nuisance sonore : `HUMAN_OBSERVATION_REQUIRED` ;
- couverture Alerte/scène sombre, comparaison Pure/LIGHT/MEDIUM et film complet : toujours ouvertes pour généraliser la qualification au-delà de ce DVD ;
- prochaine action : consigner séparément la nuisance sonore, puis décider si `vaapi-copy` appartient à un futur profil exact IT13 ou à une règle plus étroite. Toute intégration reste une tranche distincte et n'est pas autorisée par cette validation seule.

