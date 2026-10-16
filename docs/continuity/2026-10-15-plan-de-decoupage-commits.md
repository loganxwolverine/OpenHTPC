# OPENHTPC — plan de découpage du travail non commité (aucun commit)

Hermes, 2026-10-15. Base : HEAD `312ceb8`, arbre `19541911…`, worktree restauré et vérifié.
**Rien n'a été commité, rien n'a été ajouté à l'index** (`git diff --cached` est vide).

Le découpage ci-dessous a été **construit et testé dans un bac à sable**, pas seulement décrit :
les états A et B ont été produits pour de vrai, avec leurs empreintes et leurs résultats de tests.

## 0. Le fait qui dicte la séquence

`payload/openhtpc-ui.py` **ne contient aucune** des chaînes `page == "extensions"`,
`provenance_label`, `prerequisite_label`, `readiness_label`, `external_prerequisite` à HEAD.
`tests/test_plugin_framework_generic_system.py` **n'existe pas** à HEAD.

Donc la tranche ergonomie (B) n'a **pas de contexte d'application** à HEAD : elle modifie des
lignes qui n'existent que dans le travail non commité de Codex (A). La seule séquence correcte est
**A d'abord, B ensuite** — et c'est aussi la seule qui ne fasse pas passer le travail de Codex
sous un message d'ergonomie.

## A. Tranche qui doit précéder — « inventaire générique des extensions dans Système »

18 entrées, toutes nécessaires, parce que la page Extensions **consomme** la projection du modèle
et que le fichier de test **charge cinq modules** (registre, core, modèle, UI, moteur de session).

| Fichier | Δ vs HEAD | Rôle |
| --- | --- | --- |
| `payload/openhtpc-core.py` | +39 −6 | adaptation de Core aux faits persistés |
| `payload/openhtpc-plugin-registry.py` | +106 −12 | registre V2, validation, résolution et échec fermé |
| `payload/openhtpc-system-model.py` | +159 −0 | projection générique (produit `activation_label`, `provenance_label`, `prerequisite_label`, `external_prerequisite`, `readiness_label`, `hooks`) |
| `payload/openhtpc-ui.py` | +44 −0 | page `extensions` (3 hunks : `SYSTEM_PAGES`, `PAGE_TITLES`, le bloc de page) |
| `payload/openhtpc-session-engine.py` | +11 −6 | clé de page dans la rampe, libellés (`VIDÉO`, `MÉDIAS & DISQUES`, `Entry10=À PROPOS`) |
| `payload/openhtpc` | +2 −2 | `plugin_dependency_facts` transmis à `publish` / `set_enabled` |
| `payload/plugins/README.md`, `payload/plugins/available/plugin.bluray/plugin.json` | +3 −3 | « Blu-ray UHD » → « Support optique avancé » |
| `vendor/flex-launcher/src/launcher.c` | +45 −24 | taille de page propre à la rampe Core `SYSTEME` (onze entrées sans scroll) |
| `payload/flex/bin/flex-launcher`, `payload/flex/BUILD-METADATA.json` | binaire + +5 −5 | binaire reconstruit et métadonnée cohérente (vérifié : `binary_sha256` et `flex_source_fingerprint` correspondent) |
| `tests/test_plugin_framework_p2_registry.py` | +12 −0 | trois tests d'échec fermé (types non hashables, nom Unicode, API entier exact) |
| `tests/test_optical_asset_plugin_p2.py`, `tests/test_optical_presentation_plugin_p2.py` | +2 −0 | fixtures : `capabilities.json` avec `protected_media: AVAILABLE` |
| `tests/test_protected_optical_doctor_plugin_p2.py`, `tests/test_protected_optical_shadow_plugin_p2.py` | +2 −2 | libellé « Support optique avancé » |
| `tests/test_rc7_about_ux.py` | +1 −1 | `Entry9` → `Entry10` (une entrée insérée dans la rampe) |
| `tests/test_plugin_framework_generic_system.py` | **fichier neuf** (346 lignes, sans la garde B) | couverture hermétique de l'inventaire générique |

**Pourquoi A ne peut pas être plus petite.** La page Extensions lit
`activation_label`, `provenance_label`, `prerequisite_label`, `external_prerequisite`,
`readiness_label`, `hooks` — **tous produits par `openhtpc-system-model.py`**. Committer `ui.py`
seul produirait une page qui affiche « Indéterminée » partout : un état incohérent, et rouge en
test. La rampe à onze entrées explique la modification Flex ; le renommage explique le dernier
test. Rien dans cette liste ne dépend d'un autre chantier.

**État A exact** (mesuré) :

    payload/openhtpc-ui.py                       43e9025b8a82b84cb72914e5679c2795d6d8c308d48a56f3c8db344caae9e7ae
    tests/test_plugin_framework_generic_system.py c6629cc40c09d01aae20602896850c112253b4097f16948404e38578f43f3da1

**Tests A** (rejoués dans une copie avec historique, état A) :

    pytest tests/test_plugin_framework_generic_system.py -q        → 21 passed
    pytest <batterie voisine de dix fichiers> -q                   → 172 passed, 5 skipped, 0 failed

**Message proposé pour A** — c'est la tranche de Codex, c'est **son** message à valider :

    feat(system): generic extension inventory in System → Extensions

    Core now adapts strict persisted facts; the plugin registry resolves plugins,
    capabilities and system dependencies in one place and fails closed on absent,
    invalid or cyclic entries. Doctor and the System → Extensions page consume the
    same resolved instance and the same reason vocabulary.

    The page becomes the eleventh entry of the System ramp; Flex gets its own page
    size for the Core SYSTEME ramp so eleven entries fit without scrolling.
    plugin.bluray is renamed "Support optique avancé" — no manifest presents itself
    as installed any more.

    Fixtures and the About entry are adjusted for the new ramp. No playback path,
    no Magnificence preset and no installed host is modified by this commit.

## B. Tranche ergonomie Hermes — vient **après** A, et rien qu'après

Aucun fichier neuf : **deux hunks dans deux fichiers déjà présents dans A.**

| Fichier | Hunk | Δ | Empreinte avant (état A) | Empreinte après (état B) |
| --- | --- | --- | --- | --- |
| `payload/openhtpc-ui.py` | bloc de la page `extensions`, lignes de détail | +11 −8 | `43e9025b…` | `91d8fd86…` |
| `tests/test_plugin_framework_generic_system.py` | garde `test_extensions_detail_lines_have_one_fixed_meaning_per_line` | +24 | `c6629cc4…` | `219fb4e5…` |

Patchs autonomes, déjà déposés : `docs/continuity/ergonomie-config-extensions.patch.md` et
`docs/continuity/ergonomie-config-garde-test.patch.md`. Les deux passent dans les deux sens :
inverses, ils reproduisent **exactement** les empreintes de A — c'est ainsi que le découpage a été
prouvé, pas supposé.

**Dépendance A → B :** B modifie des lignes écrites par A. A ne dépend pas de B. L'application de
B sans A échoue (`git apply --check` refuse, le contexte est absent).

**État B exact** (mesuré) :

    payload/openhtpc-ui.py                       91d8fd86273478436c9cedd72789731726287e0741a0730da6f81bdcb159a9cd
    tests/test_plugin_framework_generic_system.py 219fb4e562101a64256bd4474089f3dd8b0dc397a93143e1d71084e4ea36ed87

**Tests B** (rejoués) :

    pytest tests/test_plugin_framework_generic_system.py -q        → 22 passed
    pytest <même batterie de dix fichiers> -q                      → 173 passed, 5 skipped, 0 failed

Plus la **garde dans les deux sens** : 1 passed sur le code corrigé, 1 failed sur le code
d'origine (morsure sur `'Dépendances : ' not found`). Sans ce contrôle, une garde fausse passe
inaperçue.

**Message proposé pour B :**

    fix(ui): give each Extensions detail line one fixed meaning

    The two detail lines of the System → Extensions page depended on whether an
    extension declared a prerequisite: with one, line 1 carried the prerequisite and
    line 2 read "Capacité système"; without one, line 1 carried the functions and
    line 2 was labelled "Prérequis" while holding the declared dependencies. The same
    position changed meaning from one extension to the next, and "Prérequis" named two
    different things.

    Line 1 now carries what the extension DECLARES (dependencies, functions); line 2
    carries what the SYSTEM found (system prerequisite, system capability, or
    diagnostic). No per-extension branching.

    Builds on the Extensions page introduced by the preceding commit; touches no
    other behaviour.

    Guard: test_extensions_detail_lines_have_one_fixed_meaning_per_line — verified in
    both directions (passes on the corrected code, fails on the original).

## Comment produire A puis B, concrètement

    # 1) état A : retirer mes deux hunks du worktree
    cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration
    git apply -R -p1 docs/continuity/ergonomie-config-extensions.patch.md
    git apply -R -p1 docs/continuity/ergonomie-config-garde-test.patch.md
    sha256sum payload/openhtpc-ui.py tests/test_plugin_framework_generic_system.py
    #    doit rendre 43e9025b… puis c6629cc4…
    # 2) tests A, puis commit A (fichiers du tableau A uniquement)
    # 3) état B : remettre mes deux hunks
    git apply -p1 docs/continuity/ergonomie-config-extensions.patch.md
    git apply -p1 docs/continuity/ergonomie-config-garde-test.patch.md
    sha256sum payload/openhtpc-ui.py tests/test_plugin_framework_generic_system.py
    #    doit rendre 91d8fd86… puis 219fb4e5…
    # 4) tests B, puis commit B (les deux mêmes fichiers, seulement mes hunks)

Avertissement de forme : après un `git apply`, **le fichier change de propriétaire**
(`hermes-eng` au lieu de `steve`) et Steve perd l'écriture dessus. Prévoir
`sudo chown steve:steve <fichiers>` après application (piège déjà rencontré le 2026-10-13).

## C. Ce qui doit rester **hors** de A et de B

| Lot | Entrées | Contenu | Pourquoi séparé |
| --- | --- | --- | --- |
| **C1 — Magnificence / profil IT13** | 4 | `payload/assets/magnificence_profiles.json`, `tests/test_magnificence_policy.py`, `OPENHTPC-MAGNIFICENCE-ROADMAP.md`, `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` | Chantier image, aucun rapport avec l'inventaire Système ; porte une **qualification physique** enregistrée — à ne pas mêler |
| **C2 — Gouvernance et acteurs** | 6 | `AGENTS.md`, `GEMINI.md`, `README.md`, `.gitignore`, `OPENHTPC-ROADMAP.md`, `OPENHTPC-PLUGIN-ROADMAP.md` | Décisions d'autorité et de documentation ; se committent en lot `docs:` |
| **C3 — Continuité, audits, outillage** | 29 | 22 checkpoints `docs/continuity/` (dont 2 patchs et le point de reprise du soir), 2 rapports `docs/audits/`, 2 documents racine (`QUALIFICATION_PROTOCOL`, `REFERENCE_PLATFORMS`), `.agents/` (skill projet), `tests/test_hermes_engineer_handoff.py`, `tools/hermes-engineer/` | Matière de continuité et outillage d'agent ; aucun effet produit |
| **Hors projet** | 1 (+1) | `skills-lock.json` ; `.hermes/` (absent de la copie restaurée, exclu par conception) | Voir ci-dessous |

Total : 58 entrées classées dans la copie restaurée + `.hermes/` = **59** sur `.79`, comme le
relève `git status`.

## Avis sur les deux éléments ambigus

**`skills-lock.json`** — c'est le verrou des cinq skills **externes installés par l'agent Hermes**
(`ffmpeg-skill`, `python-testing-patterns`, `shader-programming`, `skill-creator`,
`verification-before-completion`, tous tirés de dépôts GitHub). Ce n'est **pas** du payload
OPENHTPC : c'est l'état de l'outillage de l'agent qui a travaillé dans le dépôt. Recommandation :
**ne pas le committer** ; l'ajouter au `.gitignore` (il se régénère tout seul) ou le supprimer.
À trancher par Steve, mais aucune version du produit n'a besoin de ce fichier.

**`.hermes/`** — **confirmé : infrastructure d'agent, pas payload OPENHTPC.** Contenu observé :
quatre kilo-octets, uniquement des liens vers les skills de l'agent. Il ne porte aucun état projet.
Recommandation alignée sur ton avis : hors périmètre, exclu du gel 1.3.2 — et il est déjà
automatiquement exclu du snapshot d'arbre que j'utilise. Une ligne de `.gitignore` suffit à le
rendre explicite.

## Ce que ce découpage ne dit pas

- Il ne juge pas la tranche A **complète** : c'est une appréciation de Codex, pas un fait mesuré.
- Il ne dit rien de la **suite** de la ligne 1.3.x (identité 1.3.2, artifact) : c'est un chantier
  distinct, après A et B.
- Les tests cités sont ceux du lot voisin ; le **gate complet** (≈ 2 284 tests) reste à rejouer au
  moment du gel.
