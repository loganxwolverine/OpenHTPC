# IT13 Max — inventaire graphique et préparation Magnificence

Date : 2026-10-11, Europe/Brussels.

## Mandat et limites

Mission d'inventaire, cartographie, audit contradictoire et préparation d'essais. Aucun profil installé n'a été changé; aucune lecture n'a été lancée; aucun déploiement, commit, push ou publication n'a été effectué. Les profils déjà qualifiés restent inchangés.

Steve valide l'affichage actuel de la section Système sur l'IT13 et demande de le figer. La version réellement affichée est l'installation officielle OPENHTPC `1.3.1` / `public-release-1.3.1`, issue de `975402945376618db56e29945074ea30ddcd2cb8`. Les composants installés concernés correspondent octet pour octet à ce commit : `openhtpc-system-model.py` `a2fa079f59e65a2dd2998f4b5f8c9af7ad6b94a3136974c15261fad59e9e1d59`, `openhtpc-ui.py` `4b246714238d29a07468010b5dc9b3b3a7750c11ba2606d980cc878653197298`, `openhtpc-session-engine.py` `c4212959ec69ac5902c94f802d4eba5b1e791fff92ba5a622ce7f25e6564df0a`, et non aux changements plugins plus récents du worktree. Cette décision est `OPERATOR_PHYSICALLY_QUALIFIED` pour la présentation Système seulement; elle ne qualifie ni image vidéo, ni son, ni Magnificence. Cette mission n'a modifié aucun de ces composants d'interface.

## État du dépôt préservé

- Branche : `feature/magnificence-sd-auto`.
- HEAD : `975402945376618db56e29945074ea30ddcd2cb8`.
- VERSION : `1.3.1`.
- Worktree intentionnellement dirty avant mission, incluant le jalon plugins; préservé.
- Stashes inchangés : `stash@{0}` pre-sync stale RTX experiment; `stash@{1}` protégé `RC7 T5 network deferred`.
- `OPENHTPC_CURRENT_STATE.json` reste `STALE`; Autopilot reste fermé, sans contournement.

## Faits frais sur `192.168.1.59`

| Fait | État / preuve |
| --- | --- |
| Machine / OS | GEEKOM IT13 Max, firmware 0.28, Fedora 44 KDE, kernel `7.2.9-200.fc44`, Wayland — OBSERVED |
| CPU | Intel Core Ultra 9 185H, 16 cœurs / 22 threads — OBSERVED; Intel le classe Meteor Lake |
| GPU | `0000:00:02.0`, `8086:7d55`, Meteor Lake-P Intel Arc Graphics, pilote `i915` — OBSERVED |
| DRM persistant | `/dev/dri/by-path/pci-0000:00:02.0-render` → renderD128 — OBSERVED; seul le PCI est identité persistante |
| NPU | `0000:00:0b.0`, `8086:7d1d`, `intel_vpu` — OBSERVED; aucun rôle MPV/shader établi |
| Pile | Mesa 26.2.4, intel-media-driver 26.1.5, MPV 0.41.0, libplacebo 7.360.1, FFmpeg 8.1.3 — OBSERVED |
| Vulkan | Intel Arc MTL intégré, device UUID opaque `8680557d-0800-0000-0002-000000000000`; llvmpipe séparé — OBSERVED |
| VAAPI | MPEG-2/H.264/HEVC/Main10/VP8/VP9/AV1 exposés; VC-1 absent du snapshot — OBSERVED, pas une qualification par disque |
| Affichage | HDMI-A-1, 3840×2160@60, 10-bit rapporté, échelle 1,7 — OBSERVED; HDR inactif/non qualifié |
| Runtime MPV | Pure : `gpu-next` + Vulkan + `hwdec=vaapi`; binding actuel `RENDER_BOUND` au PCI/UUID ci-dessus — configuration OBSERVED, rendu post-mortem PROVEN sur une lecture terminée |
| Décodage runtime antérieur | backend VAAPI/hardware active OBSERVED; GPU physique de décodage NOT_PROVEN |

Le Core Ultra 9 185H est donc confirmé avec iGPU Arc Meteor Lake `0x7D55` et NPU séparé. Ce n'est ni une Arc A310 discrète (`8086:56a6`), ni un ancien iGPU HD/UHD/Iris Xe. Le nom Intel/Arc ne constitue pas une classe Magnificence.

## Cartographie CodeGraph et confirmation source

CodeGraph sur le worktree courant trace `_magnificence_choice` → `_magnificence_selected_gpu`, `_magnificence_source_scope`, `_magnificence_family_choice` → `_magnificence_family_rule` et `_magnificence_capability_baseline`; `resolve` consomme le choix, puis le CLI `main` consomme `resolve`. Le graphe signale aussi de faux appels depuis `openhtpc-plugin-registry.py::resolve_dependencies` dus au nom générique `resolve`; la lecture des sources confirme qu'ils ne font pas partie du chemin Magnificence.

Source de vérité : `payload/openhtpc-playback-policy.py:65-401` et `:1583-1637`, `payload/assets/magnificence_gpu_knowledge.json:1-80,368-409`, profils et catalogue shaders. Ordre : profil exact qualifié → règle famille `ACTIVE` → baseline LIGHT si Vulkan exact + MPEG-2 strictement établis → Pure. Les règles Intel communautaires restent `REFERENCE_ONLY`.

## Recette réellement sélectionnée

L'appel borné du sélecteur installé avec `kind=dvd` rend :

```text
family:capability-baseline-light
RECIPE_MAG_FAMILY_LIGHT_KRIG
KrigBilateral.glsl
--vf=lavfi=[bwdif=mode=send_frame:parity=auto:deint=interlaced]
DVD_PAL_FILM / 3840x2160
CAPABILITY_BASELINE_LIGHT / LIGHT / CONSERVATIVE_CAPABILITY_BASELINE
```

Pourquoi : aucun profil exact `8086:7d55`, aucune règle famille ACTIVE applicable, mais une association Vulkan vendor/device unique et MPEG-2 VAAPI strictement présent. Le runtime ajoute les shaders dans l'ordre de la liste. `KrigBilateral` reconstruit la chroma 4:2:0 guidée par la luma; il n'est pas un upscale luma. BWDIF ne traite que les frames marquées entrelacées.

L'installation et HEAD ont aussi les mêmes empreintes pour la politique et ses données : playback policy `45974d63baf7b00ae0ae0a81ac75fe7ac67ed0b0801d66295ba6176cb09a3cc2`, knowledge `cd945d4a7d12d1377e8213acba1bceeb52a389100bfbac7d1f74247c03e8b4bb`, profils `15b76a3578b37fed97136f8fa41b355308fb0511f000309b41eea7311b60ad15`, Krig `a84951b430905176f381a009552b3153dc01142c86b3d17740a25514fe2128e2`. La comparaison dépôt/installation porte donc bien sur la recette effectivement installée.

Des événements d'une lecture DVD terminée consignent `CINEMA_AUTO` → `LIGHT_KRIG`, puis un rendu Vulkan MTL PROVEN et VAAPI OBSERVED. Aucun log conservé ne prouve la compilation/exécution individuelle de Krig ni sa durée. La sélection est donc établie; le bénéfice visuel, la charge, la marge et l'endurance restent NOT_MEASURED / NOT_PHYSICALLY_QUALIFIED. Le soupçon de Steve reste une hypothèse pertinente : la recette est générique et non adaptée par preuve, mais aucune mauvaise recette n'est démontrée.

## Hermes/DeepSeek et disposition

Le snapshot minimal `openhtpc-it13-magnificence-20261011T114028Z-9754029` a été vérifié sans `.git`, secret, clé SSH, dépôt canonique, socket Docker ni média; root-owned `0555/0444`; écriture UID10000 refusée. L'appel terminal-only DeepSeek/OpenRouter a terminé avec exit 0. Rapport et dispositions : `docs/audits/2026-10-11-it13-magnificence-hermes.md`.

Retenu : profil exact préférable à une famille Arc large après gate; lacune documentaire `DVD_PAL_FILM`; rôle chroma distinct; protocole réfutable. Réfuté : contradiction entre `selection_source`/`classification_method`, ambiguïté Vulkan due à llvmpipe et confusion Arc actuelle. Proposition HIGH non retenue comme premier essai.

## Candidats préparés, non appliqués

1. **C1 — MEDIUM gelé** : BWDIF conditionnel → `FSRCNNX_x2_8-0-4-1.glsl` (upscale/reconstruction luma) → `KrigBilateral.glsl` (reconstruction chroma). C'est l'incrément minimal au-dessus du LIGHT courant.
2. **C2 — STRONG gelé sans SSim** : BWDIF conditionnel → `FSRCNNX_x2_16-0-4-1.glsl` → `KrigBilateral.glsl` → `OpenHTPC_Vibrance_Mild.glsl`, avec les paramètres de la recette STRONG. Le coût est une estimation; couleur et reconstruction doivent d'abord être testées séparément. SSimSuperRes est écarté du premier tour car son gain A310 à distance normale avait été jugé disproportionné par rapport au coût.

Le nettoyage/lissage n'est pas couvert par ces deux recettes génériques : BWDIF est un désentrelaceur, pas un débruiteur, et le HQDN3D qualifié sur A310 appartient à ce profil exact. FSRCNNX assure l'upscale/reconstruction luma, Krig la reconstruction chroma, Vibrance la couleur; aucune finition de contours séparée n'est retenue au premier tour. Risques C1 : bruit/compression renforcés et marge 4K insuffisante. Risques C2 : mêmes défauts plus suraccentuation/halos, saturation ou peaux artificielles, charge mémoire partagée, cadence et endurance. Un aspect plus spectaculaire n'est pas automatiquement un rendu plus naturel.

Ces candidats ne sont ni installés ni validés. Pure reste le fallback. Un profil exact `7d55` ne pourra être proposé à l'intégration qu'après la campagne et la décision visuelle de Steve.

## Protocole physique préparé

Préconditions : média légal local, mêmes hash/timestamps, sortie 3840×2160@60, même runtime/politique, profil énergétique et température ambiante consignés. Aucun `Alerte.mkv` n'a été trouvé dans les sources locales configurées ou le home de `.59`; `/dev/sr0` contient un média non monté et non identifié. Steve doit fournir/identifier `Alerte` et une scène sombre légale avant les essais.

Bras : Pure, LIGHT courant, C1, C2. Avant les combinaisons, isoler FSRCNNX-8, FSRCNNX-16 et Vibrance afin d'attribuer leurs effets. Pour chaque scène : 30 s de chauffe identique, fenêtre mesurée de 120 s, trois répétitions, ordre alterné/aveugle lorsque possible. Scènes : Alerte mouvement/détails/visages/bruit; scène sombre avec noirs/gradients; texte/générique; source entrelacée réellement marquée.

Mesures : `vo-passes` moyenne/médiane/p95/p99/max, compteurs en delta frame/decoder drops et delayed/mistimed, erreurs shader, cache/starvation, code de sortie; GPU busy/fréquence/température/mémoire partagée seulement si rattachables au PCI exact, sinon `UNAVAILABLE`. À 25 fps : p95 ≤30 ms visé, aucun pic récurrent >40 ms, zéro drop/delay attribuable. À 60 fps : p95 ≤12,5 ms si une source 60 fps est réellement dans le périmètre. Aucun échec visuel ne peut être compensé par un bon chiffre.

Steve observe à distance normale puis à courte distance diagnostique : détail utile, bruit/moustiques MPEG, halos/ringing, peau/plastique, noirs/banding, couleur, stabilité et fluidité. Un candidat doit battre Pure et LIGHT de façon reproductible sans surtraitement. Ensuite : scènes répétées puis endurance minimale 60 minutes avec contrôles début/milieu/fin; qualification produit finale idéalement sur film complet via le vrai parcours OPENHTPC. Toute instabilité, erreur shader, drop attribuable, p95 hors cible de façon répétée, pic récurrent hors budget ou absence de gain visuel réfute le candidat.

## Vérifications logicielles de cette mission

- CodeGraph réel sur le worktree : chemin de sélection cartographié; faux positifs confirmés par source.
- Sélecteur installé sur `.59` : résultat LIGHT/Krig ci-dessus, sans lecture ni mutation.
- Binding GPU : PCI/DRM/UUID cohérents et `RENDER_BOUND`.
- Tests locaux : `66 passed in 1.54s` pour `test_magnificence_policy.py`, `test_magnificence_static_auto.py`, `test_rc7_system_model.py`.
- Audit Hermes/DeepSeek : appel réel exit 0; isolation canary PASS.
- Sources primaires vérifiées : Intel ARK, manuel MPV, FFmpeg BWDIF, FSRCNNX upstream.

## Lacunes et prochaine action

- documenter explicitement la sémantique de `selection_source` versus `classification_method`;
- documenter ou réexaminer dans une tranche séparée le contrat `kind=dvd` → `DVD_PAL_FILM` sans sonde;
- ne jamais créer une règle future aliasée sur le seul mot `Arc`;
- conserver `physical_gpu_binding=NOT_PROVEN` pour le décodage;
- ajouter après campagne seulement les hash média, timestamps, séries brutes, logs, décision visuelle et endurance.

Prochaine action autorisée : Steve fournit/identifie les médias et autorise explicitement une session de lectures mesurées; l'opérateur prépare alors des variantes temporaires isolées, sans modifier le profil installé, et exécute Pure → LIGHT → C1 → C2 selon le protocole.
