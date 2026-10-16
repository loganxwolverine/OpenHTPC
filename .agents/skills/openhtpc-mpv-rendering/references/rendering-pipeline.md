# Pipeline MPV, gpu-next, Vulkan et VAAPI

## Modèle de travail

Utiliser ce schéma comme carte conceptuelle, jamais comme preuve d'un run particulier :

`source → demux → decode → filtres vidéo → interop/upload → plans LUMA/CHROMA → hooks custom → scaler(s) → conversion/couleur → présentation`

`vo=gpu-next` confie le rendu vidéo à libplacebo. `gpu-api=vulkan` choisit l'API de rendu. `hwdec=vaapi` ou `hwdec=nvdec` choisit une politique de décodage, distincte du GPU Vulkan. Selon le backend, le format, l'interop et les filtres, des étapes peuvent être réordonnées, fusionnées, omises ou déclencher une copie. Vérifier la configuration effective et les logs du run.

## Séparer les identités

- Persister l'identité GPU par PCI et chemin DRM by-path validé.
- Traiter le UUID Vulkan comme opaque ; normaliser uniquement en minuscules si requis par OPENHTPC.
- Prouver le GPU Vulkan depuis `[vo/gpu-next/libplacebo]` et le bloc associé au UUID demandé.
- Observer le backend de décodage uniquement depuis `[vd]`.
- Laisser `physical_gpu_binding=NOT_PROVEN` et `physical_gpu_pci=null` tant qu'une source indépendante ne prouve pas le décodeur physique.
- Ne jamais imposer une décision négative `hwdec=no` spécifique à un GPU lorsque seul le GPU de rendu est prouvé.
- Ne pas injecter `--vaapi-device` dans le chemin VAAPI direct normal de MPV 0.41 ; OPENHTPC distingue `vaapi` et les besoins éventuels de `vaapi-copy`.

## Scaling luma/chroma

- `scale` traite l'upscaling principal ; `dscale` le downscaling ; `cscale` la reconstruction chroma ; `tscale` le domaine temporel. Vérifier les définitions exactes dans le manuel de la version MPV.
- Une vidéo 4:2:0 contient une chroma de résolution inférieure à la luma. Un prescaler LUMA et un reconstructeur CHROMA ne sont donc pas interchangeables.
- Un shader qui redimensionne LUMA/CHROMA peut court-circuiter ou modifier le travail restant du scaler intégré. Ne pas additionner des noms d'algorithmes comme si chaque étape s'exécutait nécessairement.
- Consigner résolution source, crop/anamorphisme, résolution de sortie, ratio par axe, `scale`, `cscale`, `dscale`, options linéaires/sigmoïdes et antiringing.

## Hooks mpv/libplacebo

Inspecter dans chaque fichier :

- `//!HOOK` : texture/étage déclencheur ;
- `//!BIND` : dépendances accessibles ;
- `//!SAVE` : résultat intermédiaire ou remplacement ;
- `//!WIDTH` / `//!HEIGHT` : changement de taille ;
- `//!WHEN` : condition réelle d'activation ;
- `//!OFFSET`, `//!COMPONENTS`, `//!COMPUTE` et `//!DESC` : géométrie, format, exécution et nom du pass.

Hooks importants documentés par MPV : plans d'entrée `LUMA`, `CHROMA`, image `MAIN`, `LINEAR`, `SIGMOID`, `PREKERNEL`, `POSTKERNEL`, `SCALED` et `OUTPUT`. Leur disponibilité et leurs contraintes diffèrent ; relire le manuel stable et la documentation libplacebo correspondant à la version installée.

## Ordre des shaders

1. Capturer la liste exacte fournie par la politique de lecture et tous les ajouts CLI.
2. Lire tous les blocs de chaque shader, pas seulement le premier `HOOK`.
3. Construire le graphe par hook, `BIND`/`SAVE`, tailles et `WHEN`.
4. Lancer un cas dont les conditions déclenchent réellement chaque shader.
5. Vérifier compilation et ordre observé dans `[vo/gpu-next/libplacebo]` et `vo-passes`.
6. Échouer fermé sur hook absent, condition fausse, erreur de compilation, ordre ambigu ou association entre blocs de devices distincts.

L'ordre des chemins dans `glsl-shaders` est une intention de configuration. Il ne prouve ni l'activation, ni l'ordre inter-hook, ni le résultat final. La présence d'un fichier dans le dépôt ne prouve pas son chargement.

## Configuration et logs autoritaires

- Lire uniquement `~/.config/openhtpc/runtime/mpv/pure.conf` et `reference.conf` comme configurations générées effectives.
- Capturer la commande finale de lecture et les overrides temporaires.
- Accepter la preuve de rendu seulement depuis `[vo/gpu-next/libplacebo]`.
- Accepter la preuve de décodage seulement depuis `[vd]` et analyser chronologiquement les transitions hardware/software.
- Ne jamais combiner un bloc Vulkan d'un device avec un second bloc pour fabriquer une association.
- Traiter l'observation T8.5 comme post-mortem : avant la fin du processus correspondant, rendu et décodage restent non prouvés pour cette session.

## VAAPI et filtres

Tester séparément `vaapi` et, seulement si l'architecture/le profil l'autorise, `vaapi-copy`. La copie peut rendre les frames accessibles à un filtre logiciel mais modifie le chemin et son coût. L'expérience IT13 du 2026-10-11 a observé BWDIF désactivé en VAAPI direct et actif avec `vaapi-copy`; cette observation est bornée à ce run et ne constitue pas une règle universelle.

Vérifier que les réglages audio, PipeWire, cadence d'affichage et lifecycle restent inchangés. Le travail de rendu n'autorise aucune réparation de pilote ou configuration GPU globale Fedora.
