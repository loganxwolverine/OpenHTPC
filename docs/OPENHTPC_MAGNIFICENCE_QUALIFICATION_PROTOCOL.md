# OPENHTPC — Protocole de qualification GPU / MPV / Magnificence

Dernière mise à jour : 2026-10-11, Europe/Brussels.

## Finalité et règle d'autorité

Ce protocole rend comparables plusieurs GPU sans transformer un benchmark synthétique en vérité produit. L'ordre de décision est :

1. qualité visuelle réellement observable et décision de Steve ;
2. stabilité MPV et exactitude du parcours ;
3. temps de rendu ;
4. absence de dropped/delayed frames ;
5. charge, mémoire, température et consommation lorsque mesurables ;
6. marge durable pendant une lecture longue.

Les caractéristiques matérielles servent uniquement à organiser les essais. Elles ne prouvent ni une classe Magnificence ni une supériorité : `iGPU = lent` et `GPU dédié = rapide` sont des hypothèses interdites. Les labels publics ou internes futurs (`Lite`, `Standard`, `HQ`, `HQ+` ou autres) restent **PROPOSÉS / NON FIGÉS** tant qu'une décision produit et des seuils qualifiés ne les ont pas établis.

Le runtime actuel reste fondé sur les profils statiques qualifiés et le fallback prudent documentés dans `OPENHTPC-MAGNIFICENCE-ROADMAP.md`. Ce protocole ne modifie pas ce contrat.

## Préconditions d'une campagne comparable

Avant tout essai, enregistrer dans une fiche datée :

- identifiant logique de la plateforme et provenance des faits ;
- Fedora, kernel, Mesa/pilote, MPV, libplacebo, FFmpeg ;
- session KDE/Wayland, sortie, résolution, cadence, profondeur, échelle et connecteur ;
- GPU par PCI, chemin DRM validé et Vulkan deviceUUID opaque ;
- résultat Vulkan réel et capacités VAAPI par codec ;
- version/build/HEAD OPENHTPC et état Git du protocole/outillage ;
- hash des configurations MPV effectives sous `~/.config/openhtpc/runtime/mpv/` ;
- hash du média et des shaders ;
- alimentation, refroidissement, profil énergétique et température ambiante si disponibles.

Pour comparer deux plateformes, aligner autant que possible Fedora, kernel, Mesa, MPV, libplacebo, `gpu-next`, Vulkan, politique VAAPI, shaders, sortie, cadence, média, timestamps de scènes et durée. Toute différence non évitable est enregistrée comme variable de confusion ; elle n'est jamais masquée.

Fedora reste propriétaire des pilotes et de la configuration GPU globale. OPENHTPC ne remplace ni ne répare les pilotes pour obtenir un meilleur score.

## Corpus vidéo

- `Alerte.mkv` reste le média principal de comparaison Magnificence lorsqu'il est légalement disponible sur l'hôte. Enregistrer son chemin local, son SHA-256, ses propriétés `ffprobe` et les timestamps exacts utilisés ; ne pas le copier dans le dépôt si sa distribution n'est pas autorisée.
- Conserver au moins une source SD/DVD difficile et, si le périmètre le requiert, des sources HD/UHD représentatives.
- Définir avant la campagne des scènes reproductibles : mouvement, détails fins, visages/peaux, aplats/gradients, bruit/compression et générique/texte.
- Utiliser la même source décodée et la même cadence de sortie pour les comparaisons directes. Un média différent crée une campagne distincte.

## Échelle progressive des essais

Chaque étape est testée séparément avant de passer à la suivante :

1. **PURE / baseline** : configuration effective sans traitement Magnificence ajouté ;
2. **lissage** : traitement de nettoyage seul, avec paramètres consignés ;
3. **piqué** : traitement de netteté seul ;
4. **upscale** : scaler/upscaler seul ;
5. **shaders individuels** : un shader autorisé à la fois ;
6. **combinaisons contrôlées** : ajout d'un composant à la fois, ordre exact consigné ;
7. **Magnificence actuel** : recette production inchangée correspondant au comparateur ;
8. **candidat éventuel** : uniquement après justification visuelle des étapes précédentes.

Les shaders restent ceux autorisés par la roadmap courante. Ce protocole n'autorise pas à élargir silencieusement le catalogue ni à changer les presets existants.

## Déroulement reproductible d'un passage

Pour chaque variante et scène :

1. vérifier qu'aucune autre lecture, mise à jour ou charge parasite connue n'est active ;
2. capturer la configuration et les versions avant la mesure ;
3. lancer MPV via le même chemin et avec la même liaison Vulkan ;
4. laisser une période de chauffe identique, exclue des statistiques ;
5. mesurer une fenêtre identique, idéalement plusieurs répétitions ;
6. collecter les compteurs MPV en delta, pas seulement leurs valeurs cumulées ;
7. arrêter/reaper le processus exact et vérifier l'absence de résidu ;
8. consigner succès/échec et toute anomalie sans supprimer les passages défavorables.

Un passage court sert au criblage. Un candidat ne peut être qualifié sans lecture soutenue : au minimum les scènes répétées puis un film complet ou une durée longue explicitement enregistrée, avec contrôles début/milieu/fin. La validation longue doit utiliser le vrai parcours de lecture OPENHTPC lorsqu'elle prétend qualifier le produit, pas uniquement un MPV isolé.

## Mesures minimales

### MPV et rendu

- somme des passes `vo-passes` : moyenne, médiane, p95, p99 et maximum en ms ;
- `frame-drop-count` et `decoder-frame-drop-count`, en tenant compte des changements de cadence connus ;
- `vo-delayed-frame-count` et mistimed frames si exposés ;
- erreurs/avertissements de compilation shaders ;
- code de sortie, durée, starvation/cache underrun ;
- backend de décodage **OBSERVED** depuis `[vd]` et rendu Vulkan **PROVEN** seulement depuis le bloc `[vo/gpu-next/libplacebo]` associé au bon UUID.

Le backend VAAPI/NVDEC observé ne prouve pas le GPU physique de décodage. Ne pas déduire cette identité du GPU Vulkan.

### GPU et système

Quand le pilote expose des sources fiables et attribuables au bon PCI :

- GPU busy/utilisation : moyenne, médiane, p90, p95, maximum ;
- fréquence GPU : moyenne, p95/max et éventuel throttling ;
- mémoire GPU ou mémoire partagée utilisée ;
- température ;
- puissance/énergie ;
- mémoire système et pression mémoire ;
- stabilité des fréquences et températures dans le temps.

Une métrique indisponible reste `UNAVAILABLE`; elle n'est ni estimée ni transformée en zéro. L'instrumentation ne doit pas identifier durablement le GPU par `card0/card1` ou `renderD128/renderD129` : elle doit être rattachée au PCI validé. L'ancien helper de calibration qui parcourt `card1/card0` n'est donc pas une autorité suffisante pour une nouvelle qualification multi-GPU.

## Budget image et réserve

Budgets nominaux :

| Cadence | Budget d'une image | Cible indicative avec 25 % de réserve |
| --- | ---: | ---: |
| 24 fps | 41,67 ms | ≤ 31,25 ms |
| 25 fps | 40,00 ms | ≤ 30,00 ms |
| 60 fps | 16,67 ms | ≤ 12,50 ms |

La réserve de 25 % est une référence de conception lorsque pertinente, pas une preuve isolée. Rester juste sous le budget nominal ne suffit pas. Pour un candidat robuste, rechercher au minimum un p95 sous la cible de réserve, zéro drop/delayed attribuable au traitement, aucun pic récurrent au-dessus du budget et une charge/température stables pendant l'endurance. Toute exception doit être motivée par la qualité visuelle, le type de source et une décision explicite ; le HD630 historiquement accepté avec moins de réserve ne crée pas une règle générale.

## Validation visuelle

Steve compare à distance normale de visionnage et, si utile, à courte distance pour diagnostiquer :

- texture/détail utile ;
- bruit, moustiques MPEG et pixelisation ;
- halos, ringing et suraccentuation ;
- visages/peaux et aspect plastique ;
- banding, noirs bouchés et couleurs ;
- stabilité temporelle, scintillement et fluidité.

Une comparaison A/B ou aveugle est préférable lorsque praticable. Les captures à timestamp identique complètent l'observation en mouvement mais ne la remplacent pas. Le résultat est `ACCEPTÉ`, `REJETÉ` ou `À REVOIR`, avec justification et distance/écran consignés.

## Critères de promotion Magnificence Auto

Une plateforme peut recevoir une classe ou un profil exact seulement si :

- l'identité GPU/runtime et la sortie sont prouvées selon les contrats du projet ;
- Pure et chaque étape pertinente ont une preuve reproductible ;
- la recette finale gagne visuellement selon Steve ;
- les passages courts et l'endurance sont stables ;
- la marge est mesurée et jugée suffisante ;
- les comparaisons A310/Vega 7/IT13 utilisent des conditions alignées ou documentent leurs écarts ;
- le profil, ses limites, ses tests et son fallback Pure sont revus avant intégration.

Un benchmark favorable seul ne promeut rien. Une promotion exacte va dans `magnificence_profiles.json`; une règle de famille demande plusieurs preuves cohérentes et va dans `magnificence_gpu_knowledge.json` seulement après décision explicite. Le IT13 reste hors des deux fichiers jusqu'à ce gate.

## Dossier de preuve attendu

Chaque campagne conserve : fiche plateforme, commandes, versions, configs/hashes, scènes/timestamps, logs MPV, séries de mesures brutes, résumé statistique, captures éventuelles, décision visuelle de Steve, limites, état Git/OPENHTPC et lien vers le checkpoint. Les secrets, médias non redistribuables et identifiants privés ne sont jamais ajoutés au dépôt.

Les outils actuels `openhtpc-benchmark.py`, `openhtpc-calibrate.py`, `openhtpc-visual-review.py` et la télémétrie du matcher constituent des briques réutilisables, mais aucune n'est à elle seule l'autorité complète de ce protocole. Toute future automatisation doit d'abord corriger les valeurs de fallback/hypothèses historiques et l'identité GPU par énumération avant d'être utilisée comme preuve multi-plateforme.
