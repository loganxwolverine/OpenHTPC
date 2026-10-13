# OPENHTPC — Proposition : moderniser l'état machine (schéma 2) sans perdre les gates — 2026-10-13

Préparé par Hermes, lecture seule. **Proposition** : ce document n'écrit aucun état, ne
remplace aucun fichier existant et n'autorise rien. Il est destiné au propriétaire du
workstream, qui seul peut décider de la modernisation.

## 1. Le problème, en faits

**Deux fichiers d'état désignent un projet qui n'existe plus.**

| Fichier | Contenu | Incompatibilité |
| --- | --- | --- |
| `OPENHTPC_CURRENT_STATE.json` | `schema_version` 1, workstream `PROTECTED_OPTICAL_PLUGIN_FRAMEWORK_P2`, phase `P2_RC5_CANDIDATE_PREPARED_AWAITING_PHYSICAL_VALIDATION`, candidat `public-release-1.2.0-rc7`, `software_implementation_allowed=false`, gate `BEFORE_EXECUTION` / `PHYSICAL_VALIDATION` | Décrit la lignée 1.2.0/RC alors que HEAD est `9754029` en **1.3.1** |
| `.openhtpc-autopilot/state.json` | branche `feature/plugin-framework-p2-protected-optical`, HEAD `96a5711…`, `last_run` `2026-09-01`, gate `AFTER_IMPLEMENTATION`, `status=PLANNED` | Autre branche, autre workstream, état d'il y a six semaines |

**Conséquences observées, pas supposées :**

- le contrat d'agents classe ce fichier `STALE` et interdit d'en déduire une autorisation ;
- le handoff Codex↔Hermes du 2026-10-11 consigne qu'**Autopilot reste fermé** sur
  `OPENHTPC_CURRENT_STATE.json` STALE et le worktree dirty — « aucun contournement n'a été
  tenté » ;
- l'un des snapshots d'audit a **exclu** ce fichier de son périmètre, motif écrit noir sur
  blanc : « classified STALE for this workstream ». C'est la bonne pratique : la détection
  fonctionne, c'est la **décision** qui manque ;
- la roadmap globale le signale comme écart documentaire depuis le **2026-10-09** et le
  range en tête de ses « points à examiner » : « réconcilier l'état global et l'ancien état
  P2/RC5/RC7 sans perdre les gates ou l'historique ».

Autrement dit : la modernisation n'est pas un rangement, c'est ce qui **débloque la suite
automatisée** du projet.

## 2. Ce qui doit être préservé

- **Les gates historiques** : ce ne sont pas des erreurs, ce sont des preuves (RC1 NO_GO,
  RC3 NO_GO bitstream, RC4 PASS avec faux négatif de diagnostic, RC5, RC7 en attente). Ils
  doivent rester lisibles comme histoire, pas être effacés ni promus.
- **La frontière P2 gelée** et le périmètre de Core qu'elle décrit : toujours exacte.
- **La règle d'autorité** : le code et les tests priment sur tout état canonique ; un état
  incompatible avec HEAD/VERSION est classé STALE et **n'autorise rien**.

## 3. Forme proposée (schéma 2)

Un état qui décrit une **version** et des **autorisations**, avec historique append-only :

    {
      "schema_version": 2,
      "product":   {"version": "1.3.1", "build": "public-release-1.3.1",
                    "head": "<commit exact>", "branch": "feature/magnificence-sd-auto"},
      "workstream": {"id": "<à définir par le propriétaire>",
                     "name": "généralisation du framework plugins",
                     "phase": "ETAPE_1_ACTION_MEDIA", "status": "OPEN"},
      "gates": {
        "software":  {"status": "PASS", "evidence": "<run + date + compte PASS/SKIP/FAIL>"},
        "physical":  {"status": "<NON_REQUIS | REQUIS | QUALIFIÉ>", "scope": "<périmètre>"}
      },
      "next_action": {"kind": "<SOFTWARE | PHYSICAL | DECISION>",
                      "description": "<action bornée>",
                      "requires_authorization": true},
      "authorization": {"software_implementation_allowed": true,
                        "physical_operation_allowed": false,
                        "git": {"commit": false, "push": false, "tag": false, "publish": false}},
      "history": [ {"schema_version": 1, "superseded_on": "2026-10-13",
                    "file": "OPENHTPC_CURRENT_STATE.json.schema1",
                    "note": "P2/1.2.0 RC5-RC7 — historique, n'autorise rien"} ]
    }

**Invariants proposés, chacun testable :**

1. `product.head` doit correspondre à un commit réel, et `product.version` à `VERSION`.
2. Un état dont `product.version` ou `product.head` ne correspond pas à l'arbre courant est
   classé `STALE` **par le lecteur**, et toute autorisation en est ignorée.
3. `history` est **append-only** : on ajoute, on ne réécrit jamais un état antérieur.
4. `authorization.git` ne peut pas être vrai par simple effet de bord d'une autre
   autorisation.
5. Aucune autorisation ne peut être déduite d'un état STALE ni d'une roadmap.

## 4. Migration sûre

1. **Ne pas réécrire** `OPENHTPC_CURRENT_STATE.json` : le conserver tel quel comme
   historique (ou sous un nom explicite `….schema1`), et écrire un **nouveau** fichier
   schéma 2.
2. Même traitement pour `.openhtpc-autopilot/state.json`.
3. Faire échouer fermé tout lecteur qui ne connaît pas `schema_version: 2`, plutôt que de
   l'ignorer silencieusement.
4. Tranche dédiée, avec tests : un état schéma 1 reste lu comme historique, un état schéma 2
   incohérent avec HEAD est refusé.

## 5. Ce que je ne peux pas décider

- **Le `workstream.id` actuel** et l'**action suivante approuvée** : ce sont des décisions
  produit, pas des déductions d'auditeur. Le reste de la forme ci-dessus est proposable
  parce qu'il ne fait que refléter des règles déjà écrites ailleurs.
- Toute écriture dans ces fichiers : `put` ne dépose que des fichiers **neufs**, jamais des
  fichiers existants. La migration est donc, par construction, un acte d'opérateur/Codex.

## 6. Pourquoi je propose cela plutôt qu'un simple marquage

Marquer « historique » suffit à ne plus se tromper. Mais tant qu'aucun état ne décrit la
version **courante** et ses autorisations, chaque acteur doit recouper HEAD, VERSION, la
roadmap et des conversations pour savoir ce qui est permis — et Autopilot reste fermé. Un
état schéma 2 rend le projet **reprenable par un tiers** sans reconstitution : c'est
exactement ce qui manque pour « accueillir la suite ».
