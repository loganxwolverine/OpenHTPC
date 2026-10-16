# OPENHTPC — Plateformes matérielles de référence

Dernière mise à jour : 2026-10-11, Europe/Brussels.

## Objet

Ce registre décrit les machines utilisées ou prévues pour comparer OPENHTPC, MPV, Vulkan, VAAPI et Magnificence. Il ne remplace ni les profils runtime de `payload/assets/magnificence_profiles.json`, ni les preuves détaillées, ni une qualification physique datée.

Chaque valeur doit être classée comme l'un des états suivants :

- `OPERATOR_DECLARED` : fournie par Steve mais pas encore observée par OPENHTPC ;
- `OBSERVED` : collectée par un outil ou un log identifié ;
- `PROVEN` : associée à une preuve runtime digne de confiance selon `AGENTS.md` ;
- `PHYSICALLY_QUALIFIED` : validée sur le matériel réel par Steve ;
- `À MESURER` : volontairement inconnue ; aucune valeur ne doit être inventée.

L'identité GPU persistante est le PCI observé. Un nom commercial, `cardN`, `renderDN` ou l'ordre d'énumération ne constitue jamais une identité persistante.

## Parc de comparaison

| Identifiant logique | Machine / CPU | GPU | Mémoire | État de référence | Données restant à consolider |
| --- | --- | --- | --- | --- | --- |
| `SALON_A310` | Machine salon ; CPU à reprendre d'une preuve matérielle courante | Intel Arc A310 dédiée | À consolider | Profil exact A310 SD→2160p et parcours 1.3.1 physiquement qualifiés sur `.229` | Fiche complète OS/kernel/Mesa/MPV et endurance de la chaîne CLEAN finale |
| `VALIDATOR_RX5700XT` | Core i7-7700 | Radeon RX 5700 XT | À consolider | Profil HIGH et parcours ciblés physiquement qualifiés sur `.67` | Mémoire machine et fiche versionnée complète |
| `REFERENCE_HD630` | Core i7-7700 | Intel HD Graphics 630 | À consolider | Profil exact SD→1080p et DVD physique documentés | Fiche logicielle courante et revalidation selon protocole commun |
| `REFERENCE_RTX3050` | Machine de qualification historique | NVIDIA GeForce RTX 3050 | À consolider | Profil exact HIGH présent dans la matrice qualifiée | Fiche machine/version/endurance à consolider |
| `REFERENCE_RX580` | Machine de qualification historique | AMD Radeon RX 580 | À consolider | Profil exact STRONG présent dans la matrice qualifiée | Fiche machine/version/endurance à consolider |
| `REFERENCE_N150` | Plateforme Intel N150 | Intel N150 Graphics | À consolider | Profil exact LIGHT SD→1080p présent | Fiche machine/version/endurance à consolider |
| `REFERENCE_VEGA3` | Ryzen 3 PRO 3200GE | Radeon Vega 3 | À consolider | Profil exact LIGHT SD→2160p présent | Fiche machine/version/endurance à consolider |
| `NIPOGI_E3B_VEGA7` | NiPoGi E3B / Ryzen 5 7530U (`OPERATOR_DECLARED`) | Radeon Vega 7 (`OPERATOR_DECLARED`) | À MESURER | Comparateur demandé ; aucune entrée probante trouvée dans le dépôt au 2026-10-11 | Toute la fiche runtime et la qualification Magnificence |
| `GEEKOM_IT13_MAX_ARC` | GEEKOM IT13 Max / Core Ultra 9 185H (`OBSERVED`) | iGPU Intel Arc Meteor Lake-P `8086:7d55` (`OBSERVED`) | 24 Go LPDDR5 (`OPERATOR_DECLARED`) ; 22 GiB utilisables (`OBSERVED`) | **PROFIL EXACT STRONG INSTALLÉ POUR DVD PAL→4K60** | Lecture physique post-installation, acoustique, autres sources et endurance film complet |

Les anciens cas ZimaBoard 2/P2000 et autres plateformes restent documentés dans les rapports et la roadmap Magnificence. Leur migration vers une fiche complète pourra être faite lors d'une prochaine qualification ; ce lot ne réécrit pas leurs preuves historiques.

## Fiche de référence — GEEKOM IT13 Max

| Champ | Valeur / état |
| --- | --- |
| Identifiant logique | `GEEKOM_IT13_MAX_ARC` |
| Machine | GEEKOM IT13 Max, firmware 0.28 — `OBSERVED` par `hostnamectl` le 2026-10-11 |
| CPU | Intel Core Ultra 9 185H — `OBSERVED` dans le Hardware Passport 1.3.1 |
| GPU | Intel Meteor Lake-P / Intel Arc Graphics, identifiant `8086:7d55`, pilote kernel `i915` — `OBSERVED` |
| NPU distinct | Intel `8086:7d1d`, pilote `intel_vpu` — `OBSERVED`; aucune intégration MPV/shader OPENHTPC établie |
| Mémoire annoncée | 24 Go LPDDR5 — `OPERATOR_DECLARED` |
| Mémoire utilisable | 22 GiB — `OBSERVED` par le système ; le type LPDDR5 reste déclaratif |
| Adresse IP | `192.168.1.59` — fournie par Steve et utilisée pour la session d'installation du 2026-10-11 |
| Hostname | `IT13Max` — `OBSERVED` |
| Fedora / KDE / Wayland | Fedora 44 KDE Plasma Desktop Edition ; session Wayland — `OBSERVED` |
| Kernel | `7.2.9-200.fc44.x86_64` — `OBSERVED` |
| Mesa / pilote Vulkan | Mesa `26.2.4`; pilote Vulkan Intel open source — `OBSERVED` |
| PCI vendor:device | `8086:7d55` — `OBSERVED` |
| Adresse PCI persistante | `0000:00:02.0` — `OBSERVED` |
| Chemin DRM observé | `/dev/dri/by-path/pci-0000:00:02.0-render` → `/dev/dri/renderD128`; la correspondance persistante reste fondée sur le PCI |
| Vulkan deviceUUID opaque | `8680557d-0800-0000-0002-000000000000` — `OBSERVED` par `vulkaninfo`; aucune identité PCI n'en est déduite |
| VAAPI | MPEG-2, H.264, HEVC/Main10, VP8, VP9 et AV1 exposés par Intel iHD `26.1.5` — `OBSERVED`; GPU physique de décodage `NOT_PROVEN` |
| MPV / libplacebo / FFmpeg | MPV `0.41.0`; libplacebo `7.360.1`; FFmpeg runtime `8.1.3` — `OBSERVED` |
| Résolution, cadence, profondeur, connecteur | HDMI-A-1, 3840×2160 @ 60 Hz, 10 bits annoncés par KScreen, échelle 1,7 — `OBSERVED`; HDR inactif et non qualifié |
| Version/build OPENHTPC | `1.3.1` / `public-release-1.3.1`, artifact SHA-256 `933ce9a780bfc901c8cb90ca72e7973da088b87e294d0c2bb0b73e2aa608837c` |
| Média `Alerte.mkv` disponible et SHA-256 | **ABSENT des sources configurées et chemins locaux examinés sur `.59`; À FOURNIR/IDENTIFIER** |
| Baseline Pure | **À MESURER** |
| Shaders individuels / combinaisons | `vaapi-copy + BWDIF + FSRCNNX-16 + Krig + Vibrance` mesurés sur DVD PAL : temps VO p95 `21,20 ms` / budget `40 ms`, zéro perte — `SOFTWARE_MEASURED`; le chemin direct désactive BWDIF |
| Magnificence actuel | Profil exact `intel_meteor_lake_8086_7d55_sd_2160p` → `RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD`, installé et résolu par `CINEMA_AUTO` — `SOFTWARE_VERIFIED`; preuve physique héritée de l'essai borné précédent |
| Comparaison A310 / Vega 7 | **À MESURER dans un environnement aligné** |
| Endurance film | Endurance courte de la chaîne complète : 634 mesures utiles (~10,6 min après chauffe), render moyen `51,64 %`, package moyen `55,96 °C` / p95 `57 °C`, fréquence iGPU moyenne `2261 MHz`, zéro perte — `SOFTWARE_MEASURED`; film complet et nuisance sonore restent à mesurer/valider |
| Classe Magnificence | STRONG sans SSim `OPERATOR_PHYSICALLY_QUALIFIED` pour le DVD PAL/4K60 testé ; profil exact attribué et installé, aucune règle familiale |
| Dernière validation | 2026-10-11 : après la validation physique de la chaîne `vaapi-copy + BWDIF + FSRCNNX-16 + Krig + Vibrance`, le profil exact et la présentation Système issue de `.229` ont été installés sur `.59`. Doctor READY, onze entrées Système et résolution CINEMA_AUTO exacte vérifiés ; aucune nouvelle lecture physique post-installation |
| Problèmes / limites connus | GPU physique de décodage NOT_PROVEN; BWDIF incompatible avec VAAPI direct mais actif avec `vaapi-copy`; bruit ventilateur NON ÉTABLI; Alerte/scène sombre à identifier; autres sources, autres sorties et film complet non qualifiés |

## Emplacements d'intégration futurs

Le IT13 apparaît désormais dans la table runtime exacte parce que ses performances et sa qualification ont été établies pour le périmètre DVD PAL→4K60. Son Hardware Passport local conserve les faits observés propres à cette installation ; aucune extension de portée ne doit être inférée.

1. Les faits bruts hôte/GPU entrent par le Hardware Passport et les capacités existantes.
2. Les preuves humaines et comparatives sont consignées dans ce registre, le protocole et un checkpoint daté.
3. Une qualification exacte éventuellement acceptée peut ensuite créer une entrée dans `payload/assets/magnificence_profiles.json` avec tests dans `tests/test_magnificence_policy.py` et `tests/test_magnificence_static_auto.py`.
4. Une promotion de famille éventuelle relève de `payload/assets/magnificence_gpu_knowledge.json` et de `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` ; elle ne découle jamais automatiquement d'un nom de GPU ou d'un benchmark isolé.
5. Le chemin de décision production reste `openhtpc-playback-policy.py::_magnificence_choice`, consommé par `resolve`; toute future modification exige CodeGraph, tests et qualification appropriée.

Cette structure interdit qu'une simple annonce matérielle ou une estimation théorique remplace une preuve OPENHTPC.
