# Hermes — pré-revue contradictoire : contrat générique d'action média bornée

Date : 2026-10-13, Europe/Brussels. Préparé par Hermes ; destinataire : Codex/Steve.
Destination suggérée dans le dépôt : `docs/audits/2026-10-13-media-action-contract-hermes.md`
(fichier neuf, aucun conflit possible).

Autorité : **lecture seule**. Ce document ne propose aucune intégration, ne modifie
aucun preset et n'autorise aucune tranche. C'est une entrée pour la première tâche
Codex recommandée par `docs/continuity/2026-10-11-plugin-dependency-resolution.md`
(§ « Limites et prochaine action »), pas un plan validé.

## 0. Provenance de la base analysée

- Base tirée du dépôt canonique par canal SSH en lecture seule (commande forcée,
  whitelist `status|digest|export`, sans `.git`, `--no-optional-locks`).
- Branche `feature/magnificence-sd-auto`, HEAD
  `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`.
- Empreinte d'arbre de la base analysée :
  `35c03c7d34f4f8d7ff21188ed843a47e5c2b2b39e50788f836ac27293c44e3d9`
  (identique avant capture, après capture et recalculée sur la copie locale).
- Sujet : le contrat générique d'action média bornée, prochaine tranche autorisable
  après la résolution générique des dépendances (`JALON LOGICIEL COMPLET`, 2026-10-11).

## 1. FACTS vérifiés

**F1 — Trois hooks sur cinq sont déclarés mais n'ont aucune implémentation.**

- `payload/openhtpc-plugin-registry.py:18` :
  `HOOKS={"capability","doctor","ui_menu","media_handler","dispatcher"}`.
- `:166` : la validation du manifest n'accepte que des `capabilities` incluses dans
  `HOOKS` — donc `ui_menu`, `media_handler` et `dispatcher` sont **acceptables** aujourd'hui.
- `:216` : `registry()` construit bien `providers={hook:[] for hook in sorted(HOOKS)}`,
  mais aucune occurrence consommante de `ui_menu`, `media_handler` ou `dispatcher`
  n'existe ailleurs dans `payload/*.py` (recherche exhaustive : 1 occurrence chacun,
  celle de la déclaration).
- Le plugin de référence `payload/plugins/available/plugin.bluray/plugin.json` déclare
  `"capabilities": ["capability","doctor"]` — les deux seuls hooks réellement servis.

Conséquence : un plugin peut aujourd'hui **déclarer** une capacité dont personne ne
tient le contrat. C'est un état de schéma, pas un défaut runtime, mais la tranche devra
décider si la déclaration d'un hook non servi reste acceptée (et étiquetée comme telle
dans `Système → Extensions`) ou devient une erreur de manifest.

**F2 — Un canal d'action média existe déjà, et il est Core.**

`payload/openhtpc-media-action-control.py` (459 lignes) définit, lu directement :

- un chemin de requête par FIFO : `~/.local/state/openhtpc/media-action.fifo` (`:28`) ;
- un verrou : `~/.local/state/openhtpc/media/media-action.lock` (`:32`) ;
- un état et un journal : `media-action-status.json` (`:36`), `media-action.log` (`:40`) ;
- un validateur de jeton **strict** : `valid_action_token` (`:44`) exige un `str`
  (type exact), ASCII, de longueur bornée, conforme à un motif — donc pas de jeton
  libre ni de chaîne de commande ;
- un cycle de vie de worker et de groupe de processus : `ActionController` (`:153`),
  `action_running` (`:53`), `process_group_has_live_members` (`:126`), avec redaction
  des sorties (`redaction_token`, `:174`).

**F3 — Cette machinerie n'exécute pas de chaîne shell.**

Comptages sur les quatre artefacts d'action : `openhtpc-media-action-control.py`
(subprocess 5, `Popen` 2), `openhtpc-system-action` (subprocess 3),
`openhtpc-media-action-request` et `openhtpc-media-sources-action` (0).
**Zéro** `os.system`, **zéro** `exec(`. La contrainte « sans commande shell arbitraire »
est donc déjà la pratique du projet, pas une nouveauté à introduire.

**F4 — Le point d'appui du gating existe maintenant.**

`docs/continuity/2026-10-11-plugin-dependency-resolution.md` établit des états résolus
distincts (`AVAILABLE`, `DEPENDENCY_MISSING`, `DEPENDENCY_UNKNOWN`, `DEPENDENCY_INVALID`,
`DEPENDENCY_CYCLE`) et une instance unique consommée par Doctor **et** `Système → Extensions`.
Toute exposition d'action peut donc se gater sur un état déjà calculé, sans re-collecte.

**F5 — Le manifeste porte déjà la structure utile.**
`dependencies.capabilities` est un jeton contraint (`TOKEN_RE = ^[a-z][a-z0-9-]{0,63}$`,
`:22`), et `plugin.bluray` déclare `"protected-optical-state"` — c'est-à-dire que la
notion de « dépendance à une capacité » est déjà exprimée par des jetons stables.

## 2. Le cadrage que ces faits imposent (le point le plus utile)

La tranche n'est **pas** « créer une API d'action pour les plugins ». Elle est :
**permettre à un plugin dont l'état est `AVAILABLE` de contribuer à un canal d'action
Core déjà existant, sans acquérir d'autorité.**

Trois conséquences de cadrage :

1. Le contrat doit être **déclaratif et nominatif** : le plugin nomme une action par un
   jeton contraint ; Core le traduit dans son vocabulaire d'action existant. Le plugin ne
   doit jamais manipuler le chemin FIFO, le verrou, un PID, un descripteur ou une commande.
2. L'allowlist n'est pas à inventer librement : elle doit **réutiliser le motif de jeton**
   déjà en vigueur (`TOKEN_RE`, `valid_action_token`) plutôt que d'introduire une seconde
   grammaire.
3. Le gating doit consommer l'instance résolue de F4 : une action n'est exposée que si le
   plugin est `AVAILABLE` **et** ses dépendances satisfaites. Un plugin désactivé,
   `BROKEN`, `DEPENDENCY_*` ne doit pas exposer d'action — c'est déjà la règle de
   `Système → Extensions`, il suffit de l'étendre à l'action.

## 3. Risques que la conception doit trancher (avec leur statut épistémique)

| # | Risque | Statut |
| --- | --- | --- |
| R1 | **Injection indirecte** : un label ou un identifiant d'action fourni par un manifest tiers finissant dans une commande, un fichier de configuration ou un rendu | FACT — la surface existe (manifests utilisateur acceptés) ; le format exact de la contribution est **à définir** |
| R2 | **Confusion d'autorité** : le plugin croit exécuter, Core exécute. Si le plugin fournit un *chemin* ou un *argv*, la frontière P2 est franchie | FACT — `AGENTS.md` interdit explicitement l'injection de commande dans Flex ; **à contractualiser** par la forme des données |
| R3 | **Cycle de vie** : qui possède le worker ? Si le plugin peut lancer, il faut un propriétaire unique, un reaping exact et une garde d'interaction (lane Flex) | FACT — `ActionController` existe et possède déjà le cycle de vie ; le plugin doit en rester exclu |
| R4 | **Concurrence** : deux actions simultanées (deux plugins, ou plugin + Core) | FACT — verrou existant (`media-action.lock`) ; **à vérifier** que la contribution plugin passe bien par lui |
| R5 | **Disponibilité dans l'UI** : exposer une action dépend de la fiche/disque courant, pas seulement du plugin | HYPOTHÈSE — la mécanique d'exposition par média n'a pas été lue ici |
| R6 | **Géométrie** : une action supplémentaire sur une page Flex déjà contrainte (plafond et rampes) | FACT — l'historique du jalon « rampe Système compacte » prouve que le plafond de boutons est un sujet réel sur cette UI |
| R7 | **Fuite d'information** : un état ou un motif d'erreur de plugin recopié dans un journal ou un bundle diagnostic | HYPOTHÈSE — la redaction existe côté contrôleur ; la politique pour les contributions n'est pas définie |

## 4. Forme minimale proposée (proposition, pas décision)

Un manifeste `openhtpc-plugin-v2` déclarerait une action par un bloc purement nominatif,
par exemple :

    "actions": [
      {"id": "extract-disc", "label": "EXTRAIRE LE DISQUE",
       "token": "disc-extract", "requires": ["protected-optical-state"]}
    ]

avec les invariants suivants, chacun testable hermétiquement :

1. `id`, `label` et `token` sont validés par les motifs **existants** (`TOKEN_RE`,
   `NAME_RE`) et par `valid_action_token` de Core ; aucune valeur libre n'est promue ;
2. le plugin ne fournit **ni** chemin, **ni** argument, **ni** commande, **ni** PID ;
3. Core seul résout `token` → action réelle, via son vocabulaire d'action existant ;
4. l'action n'est exposée que si le plugin est `AVAILABLE` et ses `requires` satisfaits ;
5. refus explicite et étiqueté (`DEPENDENCY_MISSING` / `DISABLED` / non exposé) côté UI ;
6. aucune nouvelle autorité I/O, lifecycle ou rendu n'est transférée au plugin.

## 5. Assertions que les tests hermétiques devraient porter

- un plugin factice `AVAILABLE` contribue une action → exposée, et **le token seul** est transmis ;
- le même plugin `DISABLED` → action non exposée, motif identique à celui affiché par `Système → Extensions` ;
- dépendance manquante → `DEPENDENCY_MISSING`, aucune action ;
- manifest malformé (action non conforme, types non hashables, booléen au lieu d'entier) → isolé, jamais promu ;
- aucune exécution d'entrypoint, aucune collecte, aucune lecture de matériel pendant la projection ;
- un label d'action ne peut atteindre **ni** une ligne de commande, **ni** un fichier de configuration exécutable ;
- la garde d'interaction (deuxième lancement pendant un enfant suivi) reste tenue par Core, pas par le plugin.

## 6. Ce que je n'ai PAS vérifié (limites explicites)

- Le corps complet de `openhtpc-media-action-control.py` : je l'ai lu par extraits
  (`:28`–`:53`, `:153`+, définitions) et par comptages, pas intégralement.
- Les appels historiques P2 « d'entrée/action » que le checkpoint de résolution laisse
  hors périmètre : repérés par nom de fichier (`openhtpc-media-action-request`,
  `openhtpc-media-sources-action`, `openhtpc-system-action`), **pas lus**.
- La chaîne d'exposition d'action côté interface (page média / disque) : non lue.
- Le côté Flex d'une contribution de menu : non lu.
- Aucun test n'a été exécuté pour cette pré-revue : elle est **statique**, sur base
  vérifiée par empreinte.

## 7. Prochaine action

Cette pré-revue est une **entrée** pour la première tâche Codex recommandée
(cartographier les contributions UI/action P2 existantes, définir une structure
déclarative allowlistée sans commande shell, faire contribuer un plugin factice
`AVAILABLE`). Elle ne remplace ni cette cartographie ni une décision de Steve, et
n'autorise aucune implémentation.
