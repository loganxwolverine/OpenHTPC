# Qualification OPENHTPC du rendu

Ce document route vers `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md`; ce dernier reste l'autorité détaillée. Utiliser cette référence comme checklist opérationnelle, sans réécrire les conclusions historiques.

## Pré-vol d'une campagne

Enregistrer : plateforme, PCI/DRM/UUID Vulkan, versions Fedora/kernel/Mesa/MPV/libplacebo/FFmpeg, sortie et cadence, configuration MPV effective et hashes, média/hash/propriétés, shaders/hashes, conditions thermiques/énergétiques, HEAD/worktree et état installé. Aligner les variables ou les déclarer comme facteurs de confusion.

Ne pas utiliser `cardN`, `renderDN`, ordre d'énumération ou nom commercial comme identité persistante. Ne pas utiliser les helpers historiques comme autorité multi-GPU tant qu'ils ne sont pas liés au PCI validé.

## Budget par image

| Cadence | Budget nominal | Cible avec 25 % de réserve |
| ---: | ---: | ---: |
| 24 fps | 41,67 ms | 31,25 ms |
| 25 fps | 40,00 ms | 30,00 ms |
| 50 fps | 20,00 ms | 15,00 ms |
| 60 fps | 16,67 ms | 12,50 ms |

Calculer `1000 / fps`; la cible de réserve vaut `budget × 0,75`. La réserve de 25 % est l'objectif de conception OPENHTPC, pas un PASS automatique. Pour du contenu entrelacé bob/doublé, utiliser la cadence effective des images présentées et documenter la transformation.

## Mesures de rendu et drops

Après une chauffe identique, collecter sur une fenêtre identique :

- somme des passes `vo-passes` par image : moyenne, médiane, p95, p99, maximum ;
- deltas `frame-drop-count`, `decoder-frame-drop-count`, `vo-delayed-frame-count` et mistimed frames si disponibles ;
- erreurs/warnings de compilation, cache/starvation, code de sortie ;
- backend depuis `[vd]`, GPU Vulkan depuis `[vo/gpu-next/libplacebo]` ;
- charge/fréquence/mémoire/température/puissance seulement si attribuables au bon PCI.

Ne pas diagnostiquer une surcharge depuis un compteur cumulé unique. Comparer au PURE dans les mêmes conditions : des drops similaires peuvent provenir de la cadence ou de la présentation, comme l'a montré un essai HD630 consigné. Un p95 sous le budget mais avec pics récurrents, delayed frames ou dérive thermique n'établit pas une marge robuste.

## Protocole A/B

1. Préenregistrer défaut, hypothèse, scène/timestamps, distance, ordre, métriques et critère de rejet.
2. Produire PURE, puis une seule différence contrôlée B. Pour une chaîne, ajouter ensuite un composant à la fois.
3. Randomiser et masquer l'étiquette lorsque possible ; changer le mapping lors des répétitions.
4. Utiliser exactement média, seek, crop, cadence, sortie, audio et durée de chauffe identiques.
5. Mesurer plusieurs répétitions et conserver aussi les essais défavorables.
6. Comparer en mouvement à distance normale ; utiliser courte distance/captures identiques uniquement pour diagnostiquer.
7. Demander à Steve `A`, `B`, `INDISTINGUABLE` ou `REJECT`, avec défaut observé et contexte.
8. Décoder le mapping après la décision, puis tester endurance via le vrai parcours OPENHTPC.

Utiliser `ffmpeg-skill` seulement pour prober et préparer des extraits/captures identiques ; consigner toute ré-encodage comme variable de confusion. Ne jamais remplacer l'A/B runtime MPV par des sorties FFmpeg.

## Critères de décision

Viser : préférence visuelle répétable, p95 sous la cible de réserve, zéro drop/delayed attribuable au traitement, absence de pics récurrents au-dessus du budget, stabilité thermique et endurance. Une exception demande justification et décision explicite ; l'acceptation historique d'une faible réserve sur HD630 ne crée pas une règle générale.

Classer le résultat :

- `SOFTWARE_VERIFIED` : configuration/compilation/tests synthétiques seulement ;
- `SOFTWARE_MEASURED` : métriques réelles bornées, sans décision visuelle physique ;
- `OPERATOR_PHYSICALLY_QUALIFIED` : Steve a validé le rendu réel, dans le périmètre consigné ;
- `INCONCLUSIVE` : variables de confusion, marge ou préférence insuffisante ;
- `REJECTED` : critère de réfutation reproduit.

## Matrice de plateformes

Lire les valeurs courantes dans `docs/OPENHTPC_REFERENCE_PLATFORMS.md`, sans recopier une fiche potentiellement périmée. Couvrir au minimum :

- A310 salon : comparer au profil exact et tester l'endurance de la chaîne finale ; ne pas réintroduire DETAIL rejeté sans nouvelle preuve.
- Core Ultra 9 185H / Arc MTL : préserver le résultat DVD PAL `vaapi-copy + BWDIF + FSRCNNX-16 + Krig + Vibrance` comme preuve bornée ; acoustique, autres sources, film complet et intégration Auto restent séparés.
- Vega 7 / NiPoGi E3B : traiter comme `OPERATOR_DECLARED`/`À MESURER` tant que la fiche runtime commune n'existe pas.
- RX 5700 XT, HD630, RTX 3050, RX580, N150, Vega 3 et plateformes historiques : reprendre uniquement leur statut canonique actuel et réaligner les conditions avant comparaison.

Une recette qualifiée sur une plateforme n'autorise pas un tier par famille. Les comparaisons multi-GPU doivent utiliser le même corpus, la même sortie et la même méthode, ou déclarer précisément les écarts.

## Lien avec Magnificence Auto

Ordre production actuel à vérifier dans le code : profil exact physiquement qualifié → règle famille explicitement active → baseline LIGHT prudente si les capacités strictes sont établies → PURE. La skill n'autorise aucun changement de cet ordre.

Avant toute proposition Auto :

1. fermer les gates du protocole canonique ;
2. distinguer profil exact et règle famille ;
3. prouver présence/licence/hash des shaders et déploiement réel ;
4. définir fallback PURE et comportement si preuve manquante ;
5. ajouter tests de politique/statique et vérifier toutes les autorités de déploiement ;
6. mettre à jour registre plateforme, roadmap, preuves GPU et checkpoint dans le même lot ;
7. demander une autorisation explicite avant de modifier `magnificence_profiles.json`, `magnificence_gpu_knowledge.json` ou les presets.

ArtCNN, RAVU et tout shader hors catalogue Auto gelé restent exploratoires jusqu'à tranche et qualification explicites.
