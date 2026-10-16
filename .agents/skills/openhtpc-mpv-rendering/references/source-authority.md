# Autorité, provenance et sources

## Ordre de décision

Appliquer cet ordre sans confondre nature et autorité des preuves :

1. code, tests, artefacts et fichiers runtime effectifs OPENHTPC ;
2. état courant applicable, documents d'architecture et de qualification ;
3. documentation officielle correspondant aux versions réellement installées ;
4. source amont originale du shader examiné ;
5. résultats expérimentaux reproductibles OPENHTPC ;
6. analyses communautaires, utiles seulement comme pistes ;
7. hypothèses explicitement réfutables.

La documentation amont définit la sémantique générale du logiciel. Elle ne prouve ni la configuration effective d'un hôte, ni l'exécution d'un hook, ni la qualité visuelle, ni la marge d'une plateforme.

## Étiquettes obligatoires

| Étiquette | Usage |
| --- | --- |
| `OFFICIAL` | Affirmation appuyée par une documentation officielle versionnée ou par le code amont primaire. |
| `REPO_FACT` | Valeur présente dans le code, les tests ou un artefact du dépôt ; ne prouve pas l'installation. |
| `EXPERIMENT` | Mesure reproductible avec commande, versions, média, fenêtre et logs conservés. |
| `OPERATOR_OBSERVATION` | Jugement ou observation physique attribué explicitement à Steve. |
| `HYPOTHESIS` | Explication ou bénéfice attendu qui reste à tester. |
| `UNAVAILABLE` / `NOT_PROVEN` | Information manquante ou preuve insuffisante ; ne jamais combler par défaut. |

Conserver le vocabulaire OPENHTPC `DETECTED`, `AVAILABLE`, `SUPPORTED`, `OBSERVED`, `PROVEN` et `PHYSICALLY_QUALIFIED` avec son sens strict défini dans `AGENTS.md`.

## Sources officielles prioritaires

Consulter la version stable correspondant à l'hôte avant `master` lorsque les deux divergent.

- MPV, manuel stable : <https://mpv.io/manual/stable/>
- MPV, manuel master : <https://mpv.io/manual/master/>
- MPV, différences gpu-next/gpu : <https://github.com/mpv-player/mpv/wiki/GPU-Next-vs-GPU>
- libplacebo, custom shaders : <https://libplacebo.org/custom-shaders/>
- libplacebo, dépôt officiel/mirror et API : <https://github.com/haasn/libplacebo>
- libplacebo, API des hooks : <https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/shaders/custom.h>
- Vulkan, `VkPhysicalDeviceIDProperties` : <https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceIDProperties.html>
- Mesa, documentation : <https://docs.mesa3d.org/>
- libva, API VA-API : <https://github.com/intel/libva>

Points de garde : le format des user shaders MPV est annoncé instable ; `deviceUUID` est opaque et ne doit pas servir à dériver le PCI ; VAAPI décrit un backend/API et ne prouve pas à lui seul le GPU physique de décodage.

## Sources primaires des shaders

- FSRCNNX : <https://github.com/igv/FSRCNN-TensorFlow>
- KrigBilateral et SSimSuperRes : sources attribuées à Shiandow/igv dans les en-têtes distribués ; vérifier les URLs et révisions consignées dans `payload/assets/shaders/catalog.json` et les fichiers eux-mêmes.
- RAVU : <https://github.com/bjin/mpv-prescalers>
- ArtCNN : <https://github.com/Artoriuz/ArtCNN>
- FidelityFX FSR/CAS : <https://gpuopen.com/fidelityfx-superresolution/>, puis vérifier le port MPV réellement distribué.

Une source shader primaire explique l'intention et la syntaxe ; elle ne qualifie pas son usage OPENHTPC.

## Documents OPENHTPC à ne pas dupliquer

Lire et lier, sans recopier leurs tableaux ou conclusions :

- `AGENTS.md` : invariants GPU, runtime, logs et preuve ;
- `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md` : campagne et promotion ;
- `docs/OPENHTPC_REFERENCE_PLATFORMS.md` : plateformes et statut des preuves ;
- `OPENHTPC-MAGNIFICENCE-ROADMAP.md` : profils et décisions historiques ;
- `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` : portée du classifieur et sources secondaires ;
- `payload/assets/magnificence_profiles.json` : profils exacts et observations consignées ;
- `payload/assets/magnificence_gpu_knowledge.json` : règles de famille et baseline ;
- `payload/assets/shaders/catalog.json` et les shaders distribués : artefacts et provenance ;
- `payload/openhtpc-playback-policy.py` : décision production actuelle ;
- `payload/openhtpc-gpu-runtime.py` et `payload/openhtpc-runtime-generator.py` : topologie et génération runtime ;
- tests `test_magnificence_policy.py`, `test_magnificence_static_auto.py` et `test_rc7_gpu_runtime.py` : contrats exécutables.

## Discipline de recherche

Enregistrer URL, version/tag/commit ou date de consultation, affirmation supportée et éventuelle divergence avec la version installée. Citer précisément la section ou le fichier. Si deux sources divergent, ne pas choisir silencieusement : rapporter la divergence et tester la version réelle.
