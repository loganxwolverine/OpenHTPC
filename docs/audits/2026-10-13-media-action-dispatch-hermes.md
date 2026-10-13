# Hermes — dispatch du canal d'action média : réponse mesurée et deux corrections

Date : 2026-10-13. Hermes. Base : dépôt canonique, branche `feature/magnificence-sd-auto`,
HEAD `e84a2c8`, VERSION `1.3.1`. Ce document répond aux **cinq points non vérifiés** laissés ouverts
au §4 de `2026-10-13-media-action-cartography-hermes.md` — et il **corrige deux hypothèses** que
cette cartographie avait formulées.

## 1. Le dispatch complet, mesuré (FACTS avec file:line)

**D1 — Le `ActionController` n'interprète rien.** Il valide la *forme* du jeton
(`openhtpc-media-action-control.py:287`), prend le verrou de vie (`:177`), puis lance **un seul
entrypoint codé en dur** en lui passant le jeton tel quel :
`openhtpc-media-enrich.py --token <jeton> --home … --install …` (`:322-327`). Il n'existe **aucune
table de dispatch, aucun aiguillage par action** dans le contrôleur.

**D2 — Le jeton n'est pas décodé : il est cherché dans un manifeste.**
`openhtpc-media-enrich.py:1400` reconnaît le préfixe `iact_` et appelle
`enrich_action_token` (`:762`), qui délègue à
`openhtpc-media-match-ui.dispatch_action_result(home, token)` (`:542`). Ce dernier :

- charge `~/.local/state/openhtpc/media-actions/current.json` (`:553`) ;
- prend `manifest["items"]` (`:570`) et fait **`actions.get(token)`** (`:571`) ;
- si le jeton n'est pas une **clé** du manifeste → `INVALID_ACTION_TOKEN`, aucun effet (`:572-575`).

Le jeton est donc une **clé opaque de capacité**, pas une commande auto-descriptive. Sa forme
(`iact_{generation}_{token_suffix}_{cand_id}`, `openhtpc-media-match-ui:407`) n'est qu'une
convention de nommage de clé.

**D3 — Le vocabulaire d'action est fermé et appartient à Core.** `dispatch_action_result` n'accepte
que `accept`, `replace` et `reject` ; tout autre verbe → `UNKNOWN_ACTION` (`:608-632`). Un plugin ne
peut donc pas inventer d'action sans modification de Core.

**D4 — La protection anti-péremption réellement en place est une révision, pas une génération.**
L'entrée de manifeste porte `expected_revision` (`:580`), transmise à
`media_match.accept_candidate_by_id(…)` (`:614-621`) et `reject_candidates(…)` (`:624-628`).
`openhtpc-media-match.py:588-596` (et `:793-799`) refuse si `expected_revision != révision
courante`. `CANDIDATE_STALE` est alors traduit en `DISPATCH_STALE` **avec régénération de
l'interface et sans nouvelle tentative automatique** (`openhtpc-media-match-ui:636-645`).

**D5 — Le manifeste lui-même est un document de Core, écrit par le moteur de session.**
`openhtpc-session-engine.py:344` :
`data = {"schema": 1, "manifest_generation": generation, "sources": sources, "items": actions}`,
chemin défini en `:327`. Le manifeste est donc versionné par génération, et le contrôleur ne fait
que relayer une clé qui y est valide.

**D6 — Il existe une SECONDE famille de jetons, distincte.** `openhtpc-play.py` valide des jetons
`mact_[0-9a-f]{32}` (`:264`) contre un manifeste lu par le même chemin (`:88`), avec un état
d'action qui nomme explicitement `dispatcher_seen`, `token_found`, `page_id_match`,
`generation_valid`, `item_identity_valid` (`:255`). Autrement dit : le concept de **dispatcher**
existe déjà dans le produit — mais dans le canal `mact_`/lecture, pas dans le canal `iact_`.

**D7 — L'état d'action est observé, pas écrit, par le registre d'activités.**
`openhtpc-media-activity.py` lit `media-action-status.json` comme catégorie `_ACTION` (`:67`), le
suit par empreinte (`:204`) et l'expose avec les états library/action/search (`:222`).

**D8 — Le champ `origin` de l'état est codé en dur à `"UI"`** (`openhtpc-media-action-control.py:260`).
Une action d'origine non-interface serait donc **indiscernable** dans l'état et le journal.

## 2. Les deux corrections de ma propre cartographie

1. **« Le jeton est la capacité » — exact, mais pas par décodage.** Ma cartographie (§2, invariant 2)
   affirmait qu'un jeton frappé pour la génération N est refusé après passage à N+1, et présentait
   ce refus comme *déduit du rôle de `generation`*. **Le mécanisme réel est différent** : le jeton est
   refusé parce qu'il n'est plus une **clé du manifeste courant** (D2), le manifeste étant réécrit par
   génération (D5). La génération n'est pas comparée dans le jeton.
   Conséquence à ne pas manquer : **je n'ai trouvé aucune comparaison de `manifest_generation` à la
   génération courante au moment du dispatch.** La fraîcheur repose donc sur le remplacement du
   manifeste, pas sur une vérification au dispatch. C'est un point à trancher explicitement.

2. **Le hook n'est pas le véhicule.** J'envisageais `media_handler` / `dispatcher` comme accroche.
   Mesuré : le dispatch est *un entrypoint codé en dur + un manifeste*. La contribution d'un plugin
   doit donc passer par la **déclaration d'une entrée de manifeste**, jamais par un nouveau hook.

## 3. Conséquence de conception (ce que la mesure impose)

La tranche n'est pas « exposer un canal d'action aux plugins ». Elle est :

> **Permettre à un plugin `AVAILABLE` de faire inscrire, par Core, une entrée de manifeste bornée
> dans le vocabulaire d'action existant, sans jamais détenir ni composer de jeton.**

Trois règles en découlent, chacune vérifiable :

1. **Le plugin ne fournit jamais de jeton** et n'y a jamais accès : la clé est frappée par Core à
   l'écriture du manifeste. Un plugin qui peut nommer une clé peut viser une action hors contexte.
2. **Le plugin ne choisit pas le verbe librement** : `accept`/`replace`/`reject` sont le vocabulaire
   fermé de Core (D3) ; toute extension de vocabulaire est une modification de Core, donc hors tranche.
3. **Toute entrée de manifeste issue d'une contribution doit porter `expected_revision`** (D4) —
   c'est la seule protection anti-péremption réellement en place.

## 4. Ce que je n'ai toujours PAS vérifié (limites honnêtes)

- **Qui écrit le manifeste `mact_`** et si les deux familles partagent le même fichier : non lu.
- **La comparaison de `manifest_generation` au dispatch** : je ne l'ai **pas** trouvée ; je n'affirme
  pas qu'elle n'existe pas ailleurs.
- **L'exposition côté interface** (page média/disque) et **le côté Flex** d'une contribution de menu :
  non lus. Mon §4 précédent les listait déjà ; ils le restent.
- **Aucun test n'a été exécuté pour ce document** : analyse statique, sur base vérifiée par empreinte
  (`git rev-parse HEAD` = `e84a2c8`).

## 5. Première tâche recommandée à Codex, précisée

Deux décisions à prendre **avant** d'écrire du code, parce qu'elles changent la cible :

1. **Quel canal** est visé par la tranche « action média » : le canal `iact_` (action de candidat,
   mutation de base, périmètre étroit) ou le canal `mact_`/dispatcher (lancement de lecture, déjà
   muni des notions `page_id_match` / `generation_valid` / `item_identity_valid`) ? Mon analyse porte
   sur le premier ; le second n'a été qu'entrevu.
2. **Comment une entrée de manifeste d'origine plugin est distinguée** d'une entrée d'origine
   interface, alors que `origin` est aujourd'hui codé en dur à `"UI"` (D8).

Tant que ces deux points ne sont pas tranchés, toute implémentation choisirait la cible à la place
du projet. Ce document ne remplace aucune de ces décisions et n'autorise aucune implémentation.
