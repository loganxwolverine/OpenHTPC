# OPENHTPC — Ergonomie de la section Config : page EXTENSIONS — 2026-10-13

Préparé par Hermes sur demande de Steve : « m'assurer que l'ergonomie dans la section Config
est bien respectée ». Destination : `docs/continuity/` (fichier neuf). Vocabulaire :
`PROPOSED / NOT INTEGRATED`.

Ce document ne commite rien, ne construit rien et ne publie rien. Le correctif est proposé ;
son intégration appartient à Codex/Steve.

## 0. Base mesurée

- Base de travail : copie du worktree canonique tirée par le canal lecture seule le
  2026-10-13 (empreinte d'arbre `13d62564…2018`, 1055 fichiers).
- Dépôt canonique : branche `feature/magnificence-sd-auto`, HEAD `312ceb84`, VERSION `1.3.1`,
  worktree dirty (chantier de code de Codex). Aucune écriture de ma part.
- Fichier concerné : `payload/openhtpc-ui.py`, fonction `system_page_png`, branche `page ==
  "extensions"` (lignes ~552-576 à la base mesurée).

## 1. Périmètre

La page `EXTENSIONS` du menu Système (Config) : la liste des extensions et les deux lignes de
détail affichées sous chacune. Rien d'autre : ni la rampe du menu, ni les autres pages.

## 2. Findings

**F1 — FACT — le mot « Prérequis » désigne deux choses différentes sur la même page.**
- Extension avec prérequis système : la ligne affiche `item["prerequisite_label"]`
  (« Prérequis externe détecté / absent / indéterminé »), c'est-à-dire l'état d'un prérequis
  système (ex. présence de libaacs).
- Extension sans prérequis système : la ligne affiche `Prérequis : {dependencies}`, c'est-à-dire
  les dépendances **déclarées** par l'extension (`capacités:protected-optical-state`).
Deux concepts distincts, un seul mot à l'écran.

**F2 — FACT — la ligne de détail change de nature selon l'extension.**
Le code est bifurqué : si `prerequisite_label` existe, la ligne 2 devient
`Prérequis …` + `Capacité système : …` ; sinon elle devient `Fonctions : …` + `Prérequis : …`.
La ligne `Fonctions` disparaît donc entièrement de l'affichage pour l'extension qui porte un
prérequis. Deux extensions côte à côte ne se lisent pas comme avec comme, alors que la page est
faite pour être comparée d'un canapé.

## 3. Correction d'une affirmation antérieure (C1)

Dans mon message du 2026-10-13 j'ai avancé un troisième point : « le diagnostic nominal est
affiché en orange ». **C'est faux, et l'erreur vient de moi.** La couleur orange est bien
appliquée à tout diagnostic hors `{"PASS", "CAPABILITY_DEPENDENCY_MISSING"}`, mais :
- un diagnostic nominal vaut `PASS` (`openhtpc-plugin-registry.py` : `reason="PASS" if
  status=="SATISFIED"`), et `PASS` est précisément dans l'ensemble exclu ⇒ il n'est **jamais
  affiché** ;
- `CAPABILITY_DEPENDENCY_MISSING` est déjà rendu en clair par `Prérequis externe absent` +
  `Capacité système : Non disponible`, d'où son exclusion.
Mon constat provenait d'un modèle de test où j'avais **inventé** la valeur `DEPENDENCY_RESOLVED`,
qui n'existe pas dans le produit. Le mécanisme réel est sain : pas de correctif de couleur à
apporter, et aucune modification n'est proposée sur ce point.

## 4. Correctif proposé (PROPOSED / NOT INTEGRATED)

Un seul fichier, une seule région. Les deux lignes de détail deviennent à **position et à sens
fixes** pour toutes les extensions :

    ligne 1 (grise)  : « Dépendances : … »  |  « Fonctions : … »        ← ce que l'extension DÉCLARE
    ligne 2 (colorée): état du prérequis système  |  « Capacité système : … »
                       (ou « Diagnostic : … » orange quand un problème réel existe)

Conséquences voulues :
- « Prérequis » ne désigne plus qu'une seule chose : le prérequis système ; les dépendances
  déclarées s'appellent désormais « Dépendances » (F1) ;
- les quatre lignes occupent les mêmes emplacements pour toutes les extensions (F2) ;
- aucune information n'est supprimée : `Fonctions`, `Dépendances`, état du prérequis et capacité
  système restent tous affichés ;
- un problème réel (diagnostic hors ensemble nominal) prend la place de « Capacité système »,
  qui serait alors « Sans objet » : jamais deux informations différentes sur un même emplacement.
  Cette priorité est écrite dans le code, pas implicite.
- géométrie inchangée (pas de déplacement de carte, de ligne ni de taille de police majeure) :
  aucun risque de débordement ou de collision avec la ligne « + N extension(s) supplémentaire(s) ».

Livrable : `ergonomie-config-extensions.patch` (et sa copie strictement identique
`ergonomie-config-extensions.patch.md`, déposable telle quelle dans `docs/continuity/` puis
appliquée par `git apply -p1 docs/continuity/ergonomie-config-extensions.patch.md`).
SHA-256 : `dfbf40984bc9482b9139dd2ccfab415cbd4d6ade7b086689feb5a6ebc5562375`.
Fichier corrigé (après application) : sha256 `91d8fd86273478436c9cedd72789731726287e0741a0730da6f81bdcb159a9cd`
(avant : `43e9025b8a82b84cb72914e5679c2795d6d8c308d48a56f3c8db344caae9e7ae`).

## 5. Preuves réexécutées (pas citées)

- **Application réelle** : copie neuve du worktree, `git apply --check -p1` → OK, puis
  `git apply -p1` → OK ; `diff -rq` sur l'arbre entier ⇒ **exactement un fichier** diffère
  (`payload/openhtpc-ui.py`), et son empreinte est identique à celle du fichier corrigé.
- **Tests du projet sur la copie corrigée** : `test_plugin_framework_generic_system.py`,
  `test_rc7_about_ux.py`, `test_rc7_system_model.py` → **51 passed, 2 subtests passed**.
  C'est la même batterie qui verrouille les invariants de la rampe Système
  (`test_system_root_keeps_all_categories_on_one_compact_page`,
  `test_distributed_flex_matches_compact_system_source`). Aucun test n'encode les libellés
  remplacés : `grep` sur `tests/` montre que seuls `prerequisite_label` (dans
  `system-model.py`, non touché) est asserté.
- **Rendu réel de la page**, avant puis après, à partir du code : page `EXTENSIONS` rendue en
  1920×1080 et lue visuellement. Après correctif : les quatre extensions ont exactement deux
  lignes de détail à la même position, aucun débordement, aucun chevauchement, aucun texte
  tronqué ; états colorés de façon cohérente (vert détecté, orange absent/problème, gris
  sans objet) ; un seul élément orange sur la page, celui de l'extension réellement cassée.

## 6. Isolation

- Aucune écriture dans le dépôt canonique (ni fichier, ni index, ni commit). Le correctif vit
  dans `ergonomie-config/` de l'atelier.
- `payload/openhtpc-ui.py` est un fichier **suivi et non modifié** dans le `git status` du
  dépôt : l'application touche donc un fichier propre, pas une région du chantier de Codex.
  À vérifier au moment de l'application, l'état du worktree pouvant avoir bougé.
- Aucune qualification physique modifiée ; aucune donnée porteuse d'une qualification
  enregistrée n'est touchée.

## 7. Limites

- Je n'ai **pas** vu la page sur un vrai écran : le rendu que j'ai contrôlé est un PNG produit
  par le code, pas l'affichage couch. La validation visuelle reste celle de Steve.
- Mes tests tournent sur ma copie, pas sur le dépôt : ce sont des preuves de comportement du
  code proposé, pas un relevé d'intégration.
- Recommandation, non incluse dans le patch : ajouter au test de rendu existant
  (`test_extensions_page_is_a_canonical_system_page`) l'assertion que la page contient bien
  « Dépendances : » pour une extension sans prérequis. Sans elle, le retour au libellé ambigu
  ne casserait aucun test. À trancher par Codex (contrat AGENTS.md : correctif et son test se
  committent ensemble).

## 8. Prochaine action

1. Steve/Codex : appliquer le patch sur la base fraîche
   (`git apply -p1 docs/continuity/ergonomie-config-extensions.patch.md`), puis
   `sha256sum payload/openhtpc-ui.py` doit rendre `91d8fd86…59a9cd`.
2. Trancher la recommandation du §7 (test).
3. Validation visuelle couch par Steve ; le patch ne requalifie rien.
