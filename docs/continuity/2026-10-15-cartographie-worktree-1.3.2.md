# OPENHTPC — cartographie du worktree canonique et préparation du gel 1.3.2

Hermes, 2026-10-15. Lecture seule sur le dépôt ; **aucun commit, aucun index touché**.
Destination suggérée dans le dépôt : `docs/continuity/2026-10-15-cartographie-worktree-1.3.2.md`
(fichier neuf, aucun conflit).

## 0. Base mesurée (pas héritée d'un document)

| | |
| --- | --- |
| Dépôt | `/home/steve/OpenHTPC/github-openhtpc-rc2-integration` sur `.79` |
| Branche | `feature/magnificence-sd-auto` |
| HEAD | `312ceb84eac7764ec360d6d52a628e64734206f4` |
| VERSION | `1.3.1` |
| Worktree | 59 entrées — 27 fichiers suivis modifiés, 32 entrées non suivies |
| Index | **vide** : `git diff --cached` ne rend rien (rien n'est préparé) |
| Empreinte d'arbre | `19541911ee828c2d675956a99c5c4b46176cc10aefaece7cf41d96f9af11f82a` |
| Aucune dérive | les fichiers du worktree n'ont pas bougé depuis le 2026-10-13 18:16 (contrôlé par empreinte et par date) |

Méthode : la sauvegarde du jour a été restaurée dans un bac à sable et vérifiée (refs, stashes,
HEAD, arbre, état sale reproduits à l'identique) ; les attributions ci-dessous sont lues sur
cette copie restaurée, qui porte exactement l'arbre canonique.

## 1. Fichiers suivis modifiés (27) — attribution par chantier

### A. Framework plugins / page `Système → Extensions` (travail de Codex, non commité)

| Fichier | Δ | Ce que c'est |
| --- | --- | --- |
| `payload/openhtpc-core.py` | +39 −6 | Adaptation Core aux faits persistés, résolution des dépendances |
| `payload/openhtpc-plugin-registry.py` | +106 −12 | Registre V2, validation des manifests, résolution plugins/capabilities/système |
| `payload/openhtpc-system-model.py` | +159 −0 | Projection générique de l'inventaire Système / Extensions |
| `payload/openhtpc` | +2 −2 | `plugin_dependency_facts` transmis à `publish` / `set_enabled` |
| `payload/openhtpc-ui.py` | +47 −0 | **Mixte** : rendu Extensions (Codex) **et** correctif d'ergonomie du soir (Hermes) |
| `payload/openhtpc-session-engine.py` | +11 −6 | Clé de page `extensions` ajoutée à la rampe ; libellés Système (`VIDÉO`, `MÉDIAS & DISQUES`, `Entry10=À PROPOS`) |
| `payload/plugins/README.md` | +1 −1 | « Blu-ray UHD » → « Support optique avancé » |
| `payload/plugins/available/plugin.bluray/plugin.json` | +2 −2 | Idem, nom et libellé Doctor |
| `payload/flex/BUILD-METADATA.json` | +5 −5 | Binaire Flex reconstruit : `binary_sha256`, `build_id`, `flex_source_fingerprint`, `product_version` 1.2.0-rc8 → 1.3.1 |
| `payload/flex/bin/flex-launcher` (binaire) | — | Reconstruit (rampe Système à onze entrées) |
| `vendor/flex-launcher/src/launcher.c` | +45 −24 | Taille de page propre à la rampe Core `SYSTEME` + géométrie des boutons |
| `tests/test_plugin_framework_p2_registry.py` | +12 −0 | Trois tests fail-closed (types non hashables, nom Unicode vs ponctuation de chemin, API entier exact) |
| `tests/test_optical_asset_plugin_p2.py` | +1 −0 | La fixture écrit désormais `capabilities.json` (`protected_media: AVAILABLE`) |
| `tests/test_optical_presentation_plugin_p2.py` | +1 −0 | Idem |
| `tests/test_protected_optical_doctor_plugin_p2.py` | +1 −1 | Libellé « Support optique avancé » |
| `tests/test_protected_optical_shadow_plugin_p2.py` | +1 −1 | Idem |
| `tests/test_rc7_about_ux.py` | +1 −1 | `Entry9` → `Entry10` (une entrée a été insérée dans la rampe) |

### B. Magnificence / profil exact IT13

| Fichier | Δ | Ce que c'est |
| --- | --- | --- |
| `payload/assets/magnificence_profiles.json` | +109 −0 | Profil `intel_meteor_lake_8086_7d55_sd_2160p` (DVD PAL → 4K60) |
| `tests/test_magnificence_policy.py` | +75 −0 | Tests du profil et de sa portée |
| `OPENHTPC-MAGNIFICENCE-ROADMAP.md` | +38 −0 | État du profil IT13 |
| `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` | +33 −0 | Preuves GPU consignées |

### C. Gouvernance, acteurs, documentation

| Fichier | Δ | Ce que c'est |
| --- | --- | --- |
| `AGENTS.md` | +56 −4 | Contrat des agents (accès Hermes, obligations d'audit) |
| `OPENHTPC-PLUGIN-ROADMAP.md` | +80 −32 | Priorités framework plugins / `plugin.dvd-menu` |
| `OPENHTPC-ROADMAP.md` | +40 −6 | Point de situation et jalons |
| `GEMINI.md` | +6 −0 | AGY doit lire la mémoire canonique avant tout plan |
| `README.md` | +9 −0 | Renvois vers AGENTS / CONTINUITY / ROADMAP / ACTORS / REFERENCE_PLATFORMS |
| `.gitignore` | +4 −1 | `.agents/` n'est plus ignoré en bloc : le skill projet devient versionnable |

### D. Ergonomie Extensions (Hermes, correctif du 2026-10-13 au soir)

Ce chantier n'est **pas** un fichier : c'est un hunk dans deux fichiers qui appartiennent aussi
au chantier A. Détail au §3.

## 2. Entrées non suivies (32) — attribution

| Entrée | Nature | Chantier |
| --- | --- | --- |
| `docs/continuity/2026-10-11-*` (13 fichiers) | Checkpoints du 11/10 | Continuité |
| `docs/continuity/2026-10-13-ergonomie-section-config-extensions.md`, `-c2.md` | Rapport d'ergonomie + corrections C2/C3 | Ergonomie (livrable Hermes, propriété `steve`) |
| `docs/continuity/2026-10-13-soir-fin-de-journee-ergonomie-et-59.md` | Point de reprise du soir | Continuité (livrable Hermes) |
| `docs/continuity/ergonomie-config-extensions.patch.md` | Patch du correctif (+11 −8) | Ergonomie (livrable Hermes) |
| `docs/continuity/ergonomie-config-garde-test.patch.md` | Patch de la garde (+24) | Ergonomie (livrable Hermes) |
| `docs/audits/2026-10-11-it13-magnificence-hermes.md` | Rapport d'audit | Audit |
| `docs/audits/2026-10-11-magnificence-gpu-matrix-hermes.md` | Rapport d'audit | Audit |
| `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md` | Protocole de qualification | Magnificence |
| `docs/OPENHTPC_REFERENCE_PLATFORMS.md` | Registre des plateformes | Plateformes |
| `tests/test_plugin_framework_generic_system.py` | **Mixte** : fichier neuf (Codex) + garde d'ergonomie (Hermes) | A + D |
| `tests/test_hermes_engineer_handoff.py` | Test du couloir d'ingénierie | Gouvernance / continuité |
| `tools/hermes-engineer/` | Outillage du couloir d'ingénierie Hermes | Gouvernance / continuité |
| `.agents/` | Skill projet `openhtpc-mpv-rendering` | Skill projet |
| `.hermes/` | **Échafaudage de l'agent Hermes** (liens vers ses skills externes) — pas de l'état projet | À exclure du gel |
| `skills-lock.json` | **Sous-produit de l'agent Hermes** (verrou des 5 skills externes installés depuis GitHub) — pas de l'état projet | À exclure du gel |

## 3. Tranche ergonomie Extensions — commit minimal **préparé, non créé**

### 3.1 Obstacle mesuré, à trancher avant d'écrire la commande

Le correctif et sa garde **ne peuvent pas** être commités seuls à partir de HEAD :

- à HEAD, `payload/openhtpc-ui.py` **ne contient aucune** des chaînes `page == "extensions"`,
  `provenance_label`, `prerequisite_label`, `readiness_label`, `external_prerequisite` ;
- le contexte du hunk corrigé (`provenance_label`, les deux lignes de détail) est donc du
  travail **non commité de Codex** ;
- `tests/test_plugin_framework_generic_system.py` **n'existe pas à HEAD** : le fichier est neuf,
  et la garde y a été insérée.

Conséquence : le hunk d'ergonomie n'a pas de contexte dans HEAD. Il s'applique **après** (ou avec)
la tranche A. Un commit « ergonomie seul » est impossible aujourd'hui ; le prétendre produirait un
commit qui embarquerait la tranche de Codex sous un message d'ergonomie. **C'est le point à
trancher** : séquencer (A commitée, puis D) — recommandé — ou assumer un commit unique mixte.

### 3.2 Contenu exact du commit D (une fois A posée)

- `payload/openhtpc-ui.py` : un seul hunk, `+11 −8`. Empreinte avant `43e9025b8a82b84cb72914e5679c2795d6d8c308d48a56f3c8db344caae9e7ae`,
  après `91d8fd86273478436c9cedd72789731726287e0741a0730da6f81bdcb159a9cd`.
  Patch autonome : `docs/continuity/ergonomie-config-extensions.patch.md`.
- `tests/test_plugin_framework_generic_system.py` : garde `test_extensions_detail_lines_have_one_fixed_meaning_per_line`, `+24`.
  Empreinte avant `c6629cc4…`, après `219fb4e562101a64256bd4474089f3dd8b0dc397a93143e1d71084e4ea36ed87`.
  Patch autonome : `docs/continuity/ergonomie-config-garde-test.patch.md`.
- Aucun autre fichier. Aucun fichier de documentation dans ce commit (les livrables datés sont
  des fichiers neufs et se committent à part).

### 3.3 Message proposé (convention du dépôt : conventional commits, en anglais)

    fix(ui): give each Extensions detail line one fixed meaning

    The two detail lines of the System → Extensions page depended on whether an extension
    declared a prerequisite: with one, line 1 carried the prerequisite and line 2 read
    "Capacité système"; without one, line 1 carried the functions and line 2 was labelled
    "Prérequis" while holding the declared dependencies. The same position therefore changed
    meaning from one extension to the next, and "Prérequis" named two different things.

    Line 1 now carries what the extension DECLARES (dependencies, functions); line 2 carries
    what the SYSTEM found (system prerequisite, system capability, or diagnostic). No
    per-extension branching.

    Guard: test_extensions_detail_lines_have_one_fixed_meaning_per_line — verified in both
    directions (passes on the corrected code, fails on the original).

### 3.4 Tests à exécuter avant le commit (mesurés aujourd'hui, dans l'arbre restauré)

    pytest tests/test_plugin_framework_generic_system.py -q
    # 22 passed

    pytest tests/test_plugin_framework_p2_registry.py tests/test_magnificence_policy.py \
      tests/test_rc7_about_ux.py tests/test_optical_asset_plugin_p2.py \
      tests/test_optical_presentation_plugin_p2.py tests/test_protected_optical_doctor_plugin_p2.py \
      tests/test_protected_optical_shadow_plugin_p2.py tests/test_hermes_engineer_handoff.py \
      tests/test_magnificence_source_scope_guard.py tests/test_plugin_framework_generic_system.py -q
    # 173 passed, 5 skipped, 0 failed  (11,20 s)

Deux précisions de méthode, parce qu'elles ont coûté un faux échec :

- ces tests ont besoin de l'**historique Git** (`test_optical_presentation_plugin_p2` lit
  `git show <commit>:…`) : les rejouer dans un répertoire sans historique produit un échec
  artificiel ;
- la garde a été vérifiée **dans les deux sens** dans un banc isolé : sur le code corrigé
  (1 passed) et sur le code d'origine restauré par le patch inverse — dont l'application
  reproduit exactement l'empreinte `43e9025b…` déclarée la veille — (1 failed, morsure sur
  `'Dépendances : ' not found`).

## 4. Points cohérents vérifiés, points ambigus signalés

**Cohérent (vérifié, pas supposé) :**

- `payload/flex/BUILD-METADATA.json` correspond réellement au binaire reconstruit :
  `binary_sha256` déclaré = sha256 du fichier sur disque (`ee1b2a29…`) ;
- `flex_source_fingerprint` déclaré = empreinte recalculée de `vendor/flex-launcher` par
  `tools/openhtpc-devctl::_source_fingerprint` (`c6505ad2…`) : la métadonnée suit bien la source
  modifiée ;
- l'index Git est **vide** : rien n'est préparé à moitié.

**Ambigu — à dispositionner avant le gel :**

1. `skills-lock.json` : verrou des cinq skills externes installés par l'agent Hermes
   (`ffmpeg-skill`, `python-testing-patterns`, `shader-programming`, `skill-creator`,
   `verification-before-completion`). Ce n'est pas du travail projet. Il apparaîtrait dans un
   commit de gel comme un artefact inexpliqué.
2. `.hermes/` : échafaudage de l'agent (liens vers ses skills). Même remarque.
3. `.gitignore` dé-ignore le skill projet : décision de gouvernance qui mérite d'être écrite,
   pas seulement appliquée.
4. `payload/openhtpc-ui.py` et `tests/test_plugin_framework_generic_system.py` portent deux
   chantiers : à ne pas fondre dans une identité unique sans le dire.
5. `product_version` passe de `1.2.0-rc8` à `1.3.1` dans les métadonnées Flex, alors que
   l'identité du dépôt est déjà `1.3.1` : cohérent, mais c'est un changement de provenance
   d'artefact qui devra figurer dans la note de version.

**Identité 1.3.2 — ce qui reste vrai :** aucun sanitized artifact ne contient la tranche A, le
profil IT13 ni le correctif D. Le gel 1.3.2 est donc bien un chantier d'identité séparé
(VERSION, `CHANGELOG.md`, métadonnées, artifact exact-commit), et il exige d'abord une décision
sur le point 1 du §3.1 (séquençage A puis D).

## 5. Ce que je n'ai PAS fait / PAS vérifié

- **Aucun commit, aucun `git add`, aucune écriture** dans le dépôt canonique. L'index est intact.
- Je n'ai **pas** exécuté la suite complète (≈ 2 284 tests) : seulement le fichier d'ergonomie et
  la batterie voisine (§3.4). Un gate complet reste à faire au moment du gel.
- L'attribution des changements de **documentation** (AGENTS, roadmaps, README, GEMINI) est faite
  par lecture des hunks, pas par traçabilité d'auteur : je nomme le chantier, pas la main.
- Je n'ai pas jugé si la tranche A est **complète** ou seulement cohérente : c'est un jugement de
  Codex, pas un fait que j'ai mesuré.
