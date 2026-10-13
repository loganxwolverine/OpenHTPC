# Hermes — cartographie du canal d'action média : un canal de capacité, pas un catalogue d'actions

Date : 2026-10-13, Europe/Brussels. Hermes, lecture seule. Complète
`2026-10-13-media-action-contract-hermes.md`.
Destination suggérée : `docs/audits/2026-10-13-media-action-cartography-hermes.md` (fichier neuf).

Base : dépôt canonique, branche `feature/magnificence-sd-auto`, HEAD `9754029`, VERSION `1.3.1`,
empreinte d'arbre `298c1b7d…` (1 041 fichiers, tirée après la pose des deux livrables).

## 1. Ce que la lecture établit (FACTS, avec file:line)

**C1 — La couche de requête est un simple transport, sans sémantique.**
`payload/openhtpc-media-action-control.py:74-87` (`request_action`) : elle valide la **forme**
du jeton, refuse si une action tourne déjà (`action_running`), puis écrit le jeton dans la FIFO
en non-bloquant. Elle n'interprète jamais le jeton.

**C2 — Un seul propriétaire du cycle de vie.**
`ActionController` (`:153`) est instancié **une fois**, par le démon applicatif, en
`payload/openhtpc-home.py:213`, et fermé par `atexit` (`:217`) aux côtés des contrôleurs
update / search / activity. Verrou, état, journal, redaction et reaping appartiennent donc à
Core, pas au demandeur.

**C3 — La grammaire du jeton est un préfixe de capacité.**
`:25` : `_TOKEN_PATTERN = re.compile(r"iact_[A-Za-z0-9_-]+", re.ASCII)` ; `:23` :
`MAX_TOKEN_CHARS = 256`. Rien de plus : pas de vocabulaire fermé, pas d'énumération d'actions.

**C4 — Les jetons sont *frappés* par les composants qui connaissent le contexte.**
`payload/openhtpc-media-match-ui:407` compose `iact_{generation}_{token_suffix}_{cand_id}` et
`:456` `iact_{generation}_{token_suffix}_rej`. Les consommateurs
(`openhtpc-media-match-ui:689`, `payload/openhtpc-media-enrich.py:1299` et `:1400`) prennent un
jeton en argument et exigent le préfixe `iact_`.

**C5 — Il n'existe aucun jeton littéral dans le produit.**
Recherche exhaustive : **0** jeton `iact_*` distinct écrit en dur dans `payload/` et `tools/`.
Tous sont produits à l'exécution. Autrement dit, le jeton **est** la capacité : sa valeur encode
l'intention (génération, suffixe, identifiant de candidat) et son possesseur peut la présenter.

**C6 — La `generation` est un fait produit de premier ordre.**
Elle est lue et comparée partout dans `openhtpc-home.py` (`:34`, `:55`, `:65-73`, `:86-119`) et
invalide donc naturellement un jeton frappé dans un contexte antérieur.
`payload/openhtpc-media-activity.py:76` référence par ailleurs le verrou `media-action.lock`
dans son registre d'activités.

## 2. La conséquence de conception — et elle corrige ma propre pré-revue

Ma pré-revue (`2026-10-13-media-action-contract-hermes.md` §4) proposait une structure
déclarative d'actions **nommées**, avec un `token` fourni par le manifeste. **C'est la mauvaise
forme** au regard de C4-C5. Le canal existant n'est pas un catalogue d'actions qu'on allowliste :
c'est un **canal de capacité** où le jeton lui-même est la preuve d'autorisation, et où la
frappe appartient à Core.

Le risque central de la tranche n'est donc **pas** l'injection de commande — il n'y a aucune
chaîne shell (§ F3 de la pré-revue) — mais **la frappe de capacité** :

> Si un plugin peut nommer, fournir, construire ou conserver un jeton `iact_*`, il peut déclencher
> une action Core hors de son contexte légitime **sans jamais toucher aux I/O**. C'est une
> acquisition d'autorité invisible au contrôle d'interface.

Forme correcte qui en découle : le plugin déclare une **intention** (ce qu'il sait faire, sur
quelle classe de média, exigeant quel fait de capacité déjà publié) ; **Core seul frappe le
jeton**, dans son espace de génération, au moment où le contexte est vérifié ; le plugin ne
reçoit, ne construit et ne persiste jamais de jeton.

## 3. Invariants et assertions hermétiques proposés

1. Un plugin ne peut **pas** faire frapper un jeton sans décision contextuelle de Core ;
   le manifeste ne contient **aucun** champ de jeton.
2. Un jeton frappé pour la génération N est **refusé** après passage à N+1 (le fait existe déjà :
   C6).
3. Le refus « une action tourne déjà » reste une décision **Core** (`action_running`), jamais un
   état calculé par le plugin.
4. Aucune chaîne d'origine plugin n'entre dans la composition du jeton au-delà d'un identifiant
   opaque **validé et borné** — le motif `cand_id` / `token_suffix` montre que Core compose et que
   l'identifiant n'est qu'un composant.
5. Un plugin désactivé, `BROKEN` ou `DEPENDENCY_*` ne peut pas faire exposer d'action, et le motif
   affiché est **le même** que celui de `Système → Extensions` (déjà garanti par le jalon de
   résolution des dépendances).
6. Le plugin ne reçoit ni chemin FIFO, ni verrou, ni PID, ni descripteur, ni statut, ni journal.
7. Aucune exécution d'entrypoint n'a lieu pendant la projection ou la frappe.

## 4. Ce que je n'ai PAS vérifié

- Le **dispatch interne** : je n'ai pas localisé le code qui, dans `ActionController`, transforme
  un jeton en effet concret. C'est la pièce qui décide *qui* interprète `generation` /
  `token_suffix` / `cand_id` — et donc le point exact où le contrat devra être accroché.
- Les règles de composition de `token_suffix` et la validation de `cand_id`.
- Qui **lit** `media-action-status.json` et le journal, et sous quelle garde.
- L'exposition côté interface (page média/disque) et le côté Flex d'une contribution de menu.
- La durée de vie effective d'un jeton (frappé à la génération N, présenté à N+1 : le refus est
  **déduit** du rôle de `generation`, pas observé).

## 5. Prochaine action

Pour Codex, la première tâche recommandée reste la même, mais son objet se précise : localiser le
**dispatch interne** du `ActionController` et ses règles de composition de jeton, puis définir la
forme déclarative côté plugin **sans champ de jeton** et l'accroche de frappe côté Core. Cette
cartographie ne remplace pas cette étape et n'autorise rien.
