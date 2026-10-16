---
name: openhtpc-mpv-rendering
description: Procédure de référence OPENHTPC pour analyser, configurer et qualifier le rendu vidéo MPV/libplacebo avec gpu-next, Vulkan, VAAPI, scalers luma/chroma et shaders custom. Utiliser pour étudier le pipeline, l'ordre et les hook points des shaders, FSRCNNX, KrigBilateral, SSimSuperRes, CAS/RCAS, RAVU ou ArtCNN, mesurer temps de rendu et dropped frames, conduire des A/B sur les plateformes OPENHTPC, ou préparer une décision Magnificence Auto sans promouvoir un preset sans preuve.
---

# OPENHTPC MPV Rendering

## Appliquer l'autorité correcte

1. Lire `AGENTS.md`, `docs/OPENHTPC_CONTINUITY.md`, `OPENHTPC-ROADMAP.md`, le dernier checkpoint pertinent et `.git/OPENHTPC_STATE.md` s'il existe.
2. Vérifier branche, HEAD, worktree, stashes, `VERSION` et applicabilité de `OPENHTPC_CURRENT_STATE.json`.
3. Classer chaque affirmation `OFFICIAL`, `REPO_FACT`, `EXPERIMENT`, `OPERATOR_OBSERVATION` ou `HYPOTHESIS`. Ne jamais transformer une hypothèse ou une disponibilité en preuve.
4. Lire [references/source-authority.md](references/source-authority.md) avant toute recherche ou recommandation. Préférer les manuels officiels MPV, libplacebo, Vulkan et Mesa, puis les sources amont originales des shaders.

## Suivre la procédure

1. Définir le défaut visuel, la source, la sortie et le résultat réfutable. Ne pas commencer par choisir un shader.
2. Capturer la configuration MPV effective dans `~/.config/openhtpc/runtime/mpv/`, les versions, l'identité PCI persistante, le UUID Vulkan opaque, le média et les hashes. Une valeur absente reste `UNAVAILABLE`.
3. Cartographier décodage, filtres, interop, plans luma/chroma, hooks, scaling, color management et présentation avec [references/rendering-pipeline.md](references/rendering-pipeline.md). Distinguer GPU de rendu PROVEN, backend de décodage OBSERVED et GPU physique de décodage NOT_PROVEN.
4. Examiner les directives `//!HOOK`, `//!BIND`, `//!SAVE`, `//!WHEN`, tailles et descriptions dans les fichiers réellement distribués. Vérifier l'ordre effectif avec les logs et `vo-passes`; ne pas le déduire du seul ordre d'une liste.
5. Pour chaque shader envisagé, remplir les six champs obligatoires de [references/shader-catalog.md](references/shader-catalog.md) : défaut, étage, bénéfice, artefacts, coût qualitatif, validation/réfutation.
6. Établir PURE, isoler un composant à la fois, puis tester les combinaisons contrôlées selon [references/qualification.md](references/qualification.md). Mesurer des deltas après chauffe, pas des compteurs cumulés isolés.
7. Faire décider la qualité visuelle par Steve sur le matériel réel. Un benchmark, une compilation ou une capture ne constitue pas une qualification physique.
8. Relier toute promotion envisagée à Magnificence Auto seulement après les gates documentés. Ne jamais modifier un preset, une règle de famille ou la politique de lecture sans autorisation explicite.

## Produire une conclusion auditable

Rapporter séparément : source et version, faits observés, hypothèses, résultats expérimentaux, limites, régressions, état dépôt/installé et prochaine décision humaine. Pour une recommandation shader, inclure les six champs obligatoires et un verdict `ACCEPT`, `REJECT` ou `INCONCLUSIVE` borné à la plateforme/source/sortie testée.

## Mobiliser les skills connexes

- Utiliser `shader-programming` pour inspecter ou modifier la logique GLSL, les espaces, échantillonnages, branches et coûts théoriques. Les directives mpv/libplacebo et les mesures OPENHTPC restent autoritaires.
- Utiliser `ffmpeg-skill` pour prober un média, extraire des segments/captures identiques ou constituer un corpus local reproductible. Ne pas l'utiliser pour simuler le chemin runtime MPV ni pour remplacer une validation en mouvement.

## Charger les références à la demande

- [references/source-authority.md](references/source-authority.md) — hiérarchie de preuve, sources officielles et documents canoniques.
- [references/rendering-pipeline.md](references/rendering-pipeline.md) — pipeline gpu-next/Vulkan/VAAPI, scalers, hooks et ordre.
- [references/shader-catalog.md](references/shader-catalog.md) — fiche de décision FSRCNNX, KrigBilateral, SSimSuperRes, CAS/RCAS, RAVU et ArtCNN.
- [references/qualification.md](references/qualification.md) — budgets 24/25/50/60 fps, temps de rendu, drops, A/B, marge GPU, plateformes et Magnificence Auto.
