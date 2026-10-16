# OPENHTPC — Ergonomie section Config / page EXTENSIONS : corrections du 2026-10-13

Document de correction, déposé par Hermes le 2026-10-13 après l'application du correctif.
Il corrige `docs/continuity/2026-10-13-ergonomie-section-config-extensions.md` (ci-après « le
rapport ») et consigne un effet de bord découvert pendant l'application.

**Pourquoi un document séparé plutôt qu'une correction sur place** : le rapport est la propriété
de `steve` (`-rw-r--r-- steve steve`, sans entrée ACL d'écriture pour `hermes-eng`). Le compte
d'ingénierie ne peut donc pas le réécrire ; il peut seulement créer des fichiers neufs dans
`docs/continuity/`. Le propriétaire (Steve) ou Codex doit soit appliquer les remplacements
ci-dessous, soit remplacer le rapport.

## C2 — le §6 du rapport était faux

Phrase fautive du rapport (§6, Isolation) :

> `payload/openhtpc-ui.py` est un fichier **suivi et non modifié** dans le `git status` du
> dépôt : l'application touche donc un fichier propre, pas une région du chantier de Codex.

C'est faux. Mesure faite sur `.79` avant application :

    $ git status --short payload/openhtpc-ui.py
     M payload/openhtpc-ui.py

Le fichier est **suivi et déjà modifié** : il porte une partie du chantier non committé de Codex
(les libellés de la page Extensions). Le correctif s'ajoute donc **dans la tranche de Codex**, il
n'est pas isolé. J'avais lu le status trop vite en rédigeant.

Ce qui reste vrai : la base patchée correspondait exactement à l'état mesuré du dépôt
(`payload/openhtpc-ui.py` = `43e9025b…` relevé sur `.79` juste avant l'application), donc les
hunks sont sans ambiguïté, et le correctif ne touche qu'un fichier de code.

**Texte de remplacement pour le §6 du rapport :**

> - Aucune écriture dans le dépôt au moment de la rédaction ; les deux correctifs y ont ensuite
>   été appliqués par Hermes, **sans commit**, sur instruction explicite de Steve, par la voie
>   d'ingénierie autorisée (`hermes-eng` : ni sudo, ni Docker, ni déploiement).
> - `payload/openhtpc-ui.py` est un fichier **suivi ET déjà modifié** dans le `git status` du
>   dépôt (` M`) : il porte une partie du chantier non committé de Codex. Le correctif s'y ajoute
>   donc, dans le chantier de Codex, et non dans une région propre. La base patchée correspondait
>   exactement à l'état du dépôt (`43e9025b…` mesuré sur `.79` juste avant), donc les hunks sont
>   sans ambiguïté — mais l'intégration committée devra assumer que cette correction appartient à
>   la même tranche.
> - Aucune qualification physique modifiée ; aucune donnée porteuse d'une qualification
>   enregistrée n'est touchée.

## C3 — la première version de la garde de test était fausse

La garde `test_extensions_detail_lines_have_one_fixed_meaning_per_line` comptait d'abord deux
emplacements par ligne de détail, alors que le code corrigé en écrit **trois** au coin droit de la
ligne 2 (« Capacité système », ou le diagnostic, mutuellement exclusifs). Le défaut a été vu en
exécutant la garde **contre le code corrigé, avant livraison** : elle échouait. Version livrée :
elle **passe** sur le code corrigé et **échoue** sur le code d'origine. Conservé ici parce que le
projet garde l'histoire des options et de leurs erreurs.

## F3 — FACT — effet de bord de l'application : la propriété des fichiers a changé

`git apply` écrit un fichier neuf puis le renomme : le fichier prend le propriétaire du compte qui
applique, et l'ACL héritée du répertoire. Appliqué par `hermes-eng`, cela donne :

| Fichier | Propriété de référence (frères non touchés) | Après mon application |
| --- | --- | --- |
| `payload/openhtpc-ui.py` | `-rwxrwxr-x+ steve steve`, ACL `user:hermes-eng:rwx` | `-rwxrwxr-x+ hermes-eng hermes-eng` |
| `tests/test_plugin_framework_generic_system.py` | `-rw-rw-r--+ steve steve`, ACL `user:hermes-eng:rw-` | `-rw-rw-r--+ hermes-eng hermes-eng` |

**Conséquence réelle** : `steve` n'est plus propriétaire et n'a plus d'entrée ACL sur ces deux
fichiers ; il tombe sur les permissions « autres » (`r-x` pour le payload, `r--` pour le test).
L'opérateur — et donc Codex, qui travaille sous ce compte — **ne peut plus écrire dans ces deux
fichiers**. Le contenu, lui, est correct (empreintes ci-dessous).

**Remède (une commande, à exécuter par Steve, propriétaire de l'arbre) :**

    cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration && sudo chown steve:steve payload/openhtpc-ui.py tests/test_plugin_framework_generic_system.py && ls -l payload/openhtpc-ui.py tests/test_plugin_framework_generic_system.py

Le mode et l'ACL `user:hermes-eng` déjà présents correspondent alors à l'état de référence ; aucun
`chmod` n'est nécessaire. La leçon pour la suite : appliquer un patch par le compte d'ingénierie
transfère la propriété du fichier — à faire précéder d'un accord, ou à suivre de ce `chown`.

## Empreintes après application (relevées sur `.79`)

| Fichier | Avant | Après |
| --- | --- | --- |
| `payload/openhtpc-ui.py` | `43e9025b8a82b84cb72914e5679c2795d6d8c308d48a56f3c8db344caae9e7ae` | `91d8fd86273478436c9cedd72789731726287e0741a0730da6f81bdcb159a9cd` |
| `tests/test_plugin_framework_generic_system.py` | `c6629cc40c09d01aae20602896850c112253b4097f16948404e38578f43f3da1` | `219fb4e562101a64256bd4474089f3dd8b0dc397a93143e1d71084e4ea36ed87` |

## Prochaine action

1. **Steve** : la commande `chown` de F3 (rend l'écriture à l'opérateur).
2. **Steve** : validation visuelle couch de la page EXTENSIONS.
3. **Codex/Steve** : décision de commit — correctif et garde ensemble, dans la tranche
   `payload/openhtpc-ui.py` ; et appliquer (ou refuser) les remplacements C2/C3 dans le rapport.
