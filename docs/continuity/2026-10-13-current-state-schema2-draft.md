# OPENHTPC — Brouillon prêt à l'emploi : `OPENHTPC_CURRENT_STATE.json` schéma 2

Préparé par Hermes, 2026-10-13. Suite de `2026-10-13-current-state-schema-proposal.md`.
Destination : `docs/continuity/2026-10-13-current-state-schema2-draft.md`.

Deux valeurs sont marquées **À REMPLIR PAR LE PROPRIÉTAIRE** : ce sont des décisions produit,
pas des déductions d'auditeur. Tout le reste est dérivé de faits déjà écrits dans le dépôt.

## Brouillon

    {
      "schema_version": 2,

      "product": {
        "version": "1.3.1",
        "build": "public-release-1.3.1",
        "branch": "feature/magnificence-sd-auto",
        "head": "<commit exact après le correctif PAL>"
      },

      "workstream": {
        "id": "<À REMPLIR PAR LE PROPRIÉTAIRE>",
        "name": "généralisation du framework plugins — étape 1",
        "phase": "ACTION_MEDIA_BORNEE",
        "status": "OPEN"
      },

      "gates": {
        "software": {
          "status": "PASS",
          "scope": "registre / inventaire / Système → Extensions",
          "evidence": "2026-10-11, jalon de résolution des dépendances : 75 PASS / 3 SKIP ; régressions 209 PASS / 8 SKIP ; gate global applicable 2188 PASS / 23 SKIP / 12 FAIL dont 11 dus au bac à sable (98 PASS hors bac à sable) et 1 contrôle de provenance Flex préexistant"
        },
        "physical": {
          "status": "NON_REQUIS_POUR_CETTE_TRANCHE",
          "scope": "aucune lecture physique n'est nécessaire pour clore la tranche logique ; une inspection écran reste possible après déploiement explicitement autorisé"
        }
      },

      "next_action": {
        "kind": "SOFTWARE",
        "description": "définir le contrat générique d'action média bornée : cartographier les contributions d'action existantes, localiser le dispatch interne du ActionController, puis faire contribuer un plugin factice AVAILABLE sans qu'il puisse frapper ni nommer de jeton",
        "requires_authorization": true
      },

      "authorization": {
        "software_implementation_allowed": true,
        "physical_operation_allowed": false,
        "deployment_allowed": false,
        "git": {"commit": false, "push": false, "tag": false, "publish": false}
      },

      "history": [
        {
          "schema_version": 1,
          "superseded_on": "2026-10-13",
          "file": "OPENHTPC_CURRENT_STATE.json.schema1",
          "note": "workstream PROTECTED_OPTICAL_PLUGIN_FRAMEWORK_P2, phase P2/RC5, candidat 1.2.0-rc7 — historique, n'autorise rien"
        },
        {
          "schema_version": 1,
          "superseded_on": "2026-10-13",
          "file": ".openhtpc-autopilot/state.json.schema1",
          "note": "branche feature/plugin-framework-p2-protected-optical, run du 2026-09-01 — historique, n'autorise rien"
        }
      ]
    }

## Migration, étape par étape

1. `git mv OPENHTPC_CURRENT_STATE.json OPENHTPC_CURRENT_STATE.json.schema1` — ou le laisser en
   place si un renommage gêne : dans les deux cas il reste **intact**, jamais réécrit.
2. Même traitement pour `.openhtpc-autopilot/state.json`.
3. Créer `OPENHTPC_CURRENT_STATE.json` avec le contenu ci-dessus, deux champs remplis.
4. Faire échouer **fermé** tout lecteur qui ne connaît pas `schema_version: 2` : refuser,
   ne pas ignorer silencieusement.
5. Tests à ajouter : un état schéma 1 est lu comme historique sans autoriser quoi que ce soit ;
   un état schéma 2 dont `product.head` ou `product.version` ne correspond pas à l'arbre
   courant est classé `STALE` par le lecteur et ses autorisations sont ignorées ; `history`
   ne peut pas être réécrit.

## Invariants (déjà portés par la proposition ; rappel)

- le code et les tests priment sur tout état ;
- un état STALE n'autorise rien, quelle que soit la roadmap en face ;
- `history` est append-only ;
- aucune autorisation Git ne découle d'une autre autorisation.

## Ce que ce brouillon ne fait pas

Il n'écrit rien, ne renomme rien, ne remplace rien. `put` ne peut pas modifier un fichier
existant : la migration d'état est, par construction, un acte d'opérateur/Codex. Et les deux
champs en majuscules restent la décision du propriétaire du workstream.
