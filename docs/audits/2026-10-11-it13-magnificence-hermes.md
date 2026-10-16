# Audit Hermes/DeepSeek — IT13 Max / Magnificence Auto

Date : 2026-10-11, Europe/Brussels.

## Provenance et isolation

- Snapshot : `openhtpc-it13-magnificence-20261011T114028Z-9754029`.
- Périmètre exporté avec autorisation explicite de Steve : six fichiers rédigés pour l'audit (provenance, faits IT13, extraits de politique, recettes/shaders, contraintes de qualification, liens primaires). Aucun dépôt complet ni shader intégral.
- Branche/HEAD/VERSION déclarés : `feature/magnificence-sd-auto`, `975402945376618db56e29945074ea30ddcd2cb8`, `1.3.1`; worktree dirty consigné, diff suivi SHA-256 `b3d6fd6ec3c6dfadf7780b7c3643146149cde3766cf9f5e99d6b284829628020` au moment de la préparation.
- Avant l'appel : six empreintes comparées, `.git` absent, aucun dépôt canonique ni socket Docker visible, snapshot root-owned `0555/0444`, écriture UID 10000 refusée.
- Exécution : conteneur one-shot, terminal-only, UID/GID 10000, capacités supprimées, `no-new-privileges`, HOME dédié, SSH masqué, audits montés en lecture seule. Modèle distant `deepseek/deepseek-v4.1-flash` via OpenRouter, reasoning high. Exit 0. Aucune seconde gateway lancée et aucun accès de contrôle à `.59`.

## Rapport reçu — synthèse fidèle

Hermes distingue correctement les faits suivants : l'iGPU Meteor Lake `8086:7d55`, l'Arc A310 discrète `8086:56a6`, les anciens iGPU Intel et le NPU séparé `8086:7d1d`; l'absence de profil exact IT13; le fallback courant `CAPABILITY_BASELINE_LIGHT`; l'absence de mesure ou qualification physique; et la nécessité de ne pas attribuer de coût shader au NPU.

Findings proposés :

1. ambiguïté alléguée entre `selection_source=GPU_KNOWLEDGE_DB` et `classification_method=CAPABILITY_BASELINE_LIGHT`;
2. `kind=dvd` classé `DVD_PAL_FILM` sans sonde de cadence/standard, alors que la branche locale échoue fermé;
3. risque futur de confondre iGPU Arc et Arc discrète avec des règles par nom;
4. doute sur l'unicité Vulkan en présence de llvmpipe;
5. sélection statique sans mesure runtime;
6. GPU physique de décodage non prouvé;
7. résolution 4K commune à l'IT13 et l'A310, donc insuffisante comme discriminant;
8. KrigBilateral doit être décrit comme reconstruction chroma, séparément des axes nettoyage/upscale/finition/couleur.

Hermes recommande un profil exact `8086:7d55` plutôt qu'un rattachement à une famille Arc discrète, uniquement après qualification. Ses deux propositions sont :

- candidat 1 : BWDIF → FSRCNNX-8 → KrigBilateral → Vibrance Mild, coût estimé modéré;
- candidat 2 : chaîne HIGH générique, BWDIF → FSRCNNX-16 → KrigBilateral → SSimSuperRes → Vibrance Mild avec `rgba16hf` et scalers associés, coût estimé élevé.

Le rapport demande une comparaison Pure / LIGHT courant / deux candidats avec scènes identiques, p95/p99/max de `vo-passes`, drops/delays, erreurs shader, charge/température, examen visuel et endurance. Toute performance est explicitement restée `HYPOTHESIS`.

## Disposition indépendante OPENHTPC

| Finding / proposition | Disposition | Preuve / raison |
| --- | --- | --- |
| identité MTL, séparation A310/anciens Intel/NPU | **RETENU** | Inventaire PCI/runtime frais et spécification Intel du 185H concordent. Aucun chemin NPU dans le code MPV/shaders. |
| `selection_source` contre `classification_method` | **RÉFUTÉ comme contradiction** | `openhtpc-playback-policy.py:309-334` fixe distinctement la méthode de classification et la source de la recette. La nomenclature peut être mieux documentée, mais les deux champs ne portent pas la même sémantique. |
| `DVD_PAL_FILM` inconditionnel pour `kind=dvd` | **RETENU comme lacune documentaire/contrat source, hors changement de cette mission** | `openhtpc-playback-policy.py:65-103` le confirme. BWDIF utilise toutefois `deint=interlaced`, donc les trames progressives marquées telles quelles passent inchangées selon FFmpeg. Aucun défaut IT13 n'est démontré. |
| confusion actuelle par le mot « Arc » | **RÉFUTÉ pour le code actuel / risque futur retenu** | Les alias présents sont A770/A750/A580/A380 ou UHD/Iris Xe/HD; aucun alias générique `Arc`. Toutes ces règles sont `REFERENCE_ONLY`. Toute future famille doit éviter un alias Arc non borné. |
| llvmpipe rend la baseline ambiguë | **RÉFUTÉ** | `openhtpc-playback-policy.py:251-280` filtre Vulkan par vendor/device exact `8086:7d55`; llvmpipe ne correspond pas. |
| sélection statique ≠ qualification | **RETENU** | Le runtime ne benchmarke pas. La sélection LIGHT est un fallback prudent, pas une preuve de qualité ou de marge. |
| absence de GPU physique de décodage bloque toute mesure | **RÉFUTÉ comme blocage** | Elle interdit d'attribuer le décodage à un PCI, mais n'empêche pas de mesurer les passes de rendu Vulkan liées au UUID prouvé, les compteurs MPV et le système complet. La limite doit rester explicite. |
| résolution seule insuffisante / profil exact préférable | **RETENU** | Le device ID exact sépare aujourd'hui l'A310 et l'IT13. Aucun profil/famille ne sera ajouté avant le gate physique. |
| candidat 1 avec Vibrance immédiate | **MODIFIÉ** | Premier candidat retenu : recette MEDIUM existante, FSRCNNX-8 puis KrigBilateral, sans couleur afin d'isoler le gain de reconstruction. Vibrance sera testée séparément avant toute combinaison. |
| candidat 2 HIGH complet | **REJETÉ comme premier candidat** | Trop de variables et coût attendu élevé. Le second candidat retenu est la recette STRONG existante FSRCNNX-16 + KrigBilateral + Vibrance, avec SSimSuperRes exclu initialement : sur A310, son gain à distance normale était déjà jugé disproportionné par rapport à son coût. |

## Apport démontré de l'audit

Apport utile : il a rendu explicites la lacune de portée `DVD_PAL_FILM`, le risque futur d'une famille « Arc » trop large, le rôle chroma distinct de KrigBilateral et un protocole réfutable. Il n'a démontré aucune mauvaise classification actuelle ni aucun défaut de performance. Les faux positifs `selection_source` et llvmpipe ont été écartés par lecture du code. Sa chaîne HIGH n'est pas retenue comme candidat initial.

Sources primaires vérifiées indépendamment : spécification Intel Core Ultra 9 185H, manuel MPV, documentation/code FFmpeg BWDIF et releases FSRCNNX d'igv. Elles confirment l'identité `0x7D55`, la séparation GPU/NPU, l'ajout ordonné de hooks GLSL, `send_frame` et `deint=interlaced`, ainsi que le rôle d'upscale FSRCNNX; elles ne fournissent aucune mesure de performance OPENHTPC sur l'IT13.

Aucune modification de profil, lecture, installation, qualification physique, commit, push ou publication n'est issue de cet audit.
