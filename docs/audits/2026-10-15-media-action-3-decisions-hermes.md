# OPENHTPC — contrat générique d'action média bornée : les trois décisions

Hermes, 2026-10-15. Pré-revue **statique**, sur base fraîche (HEAD `312ceb8`, arbre `19541911…`,
worktree restauré et vérifié). Aucune implémentation, aucun commit, aucun test exécuté pour ce
document.

**Répartition demandée.** Décision 1 = **isolée pour validation de Steve** (elle change ce que
l'utilisateur verra ou pourra faire) ; décisions 2 et 3 = **techniques et réversibles**, tranchées
par Hermes sauf objection.

## Faits re-mesurés aujourd'hui (le socle des trois décisions)

| # | Fait | Preuve (fichier, ligne) |
| --- | --- | --- |
| F1 | Trois hooks sur cinq sont **déclarés et jamais consommés** (`ui_menu`, `media_handler`, `dispatcher`) | `payload/openhtpc-plugin-registry.py:18` ; une seule occurrence chacun, la déclaration |
| F2 | Le contrôleur n'interprète rien : **un seul entrypoint codé en dur** (`openhtpc-media-enrich.py --token …`) | `payload/openhtpc-media-action-control.py`, `_launch()` |
| F3 | Le jeton n'est pas décodé : il est cherché comme **clé** de `media-actions/current.json` | `payload/openhtpc-media-match-ui:553-575` |
| F4 | Vocabulaire d'action **fermé** : `accept`, `replace`, `reject` — sinon `UNKNOWN_ACTION` | `…media-match-ui:577-632` |
| F5 | La protection anti-péremption réellement en place est `expected_revision` | `…media-match-ui:580`, `:614-628` ; `payload/openhtpc-media-match.py:588-596` |
| F6 | `manifest_generation` est **écrit** par le moteur de session et **lu nulle part ailleurs** | `payload/openhtpc-session-engine.py:337-350` ; recherche sur `payload/` : une seule occurrence consommée, dans le même fichier |
| F7 | Le manifeste est un document de **Core**, remplacé atomiquement, versionné par génération | `…session-engine.py:337-350` |
| F8 | Deux familles de jetons : `iact_` (action de candidat) et `mact_` (navigation/lancement) | `…media-match-ui:407` ; `…session-engine.py:323` ; `…openhtpc-play:64` |
| F9 | `origin` est **codé en dur à `"UI"`** | `payload/openhtpc-media-action-control.py:260` ; `openhtpc-media-search-control.py:222` |
| F10 | Aucune chaîne shell : 0 `os.system`, 0 `exec(` sur les artefacts d'action | comptages |

Cadrage imposé par ces faits : la tranche n'est pas « créer un canal d'action », mais **permettre à
un plugin `AVAILABLE` de faire inscrire par Core une entrée de manifeste bornée, sans détenir ni
composer de jeton**.

Deux corrections de nommage par rapport à mes notes du 2026-10-13 : les fichiers
`payload/openhtpc-media-match-ui` et `payload/openhtpc-play` **n'ont pas d'extension `.py`** ; la
génération du jeton `mact_` est dans `payload/openhtpc-session-engine.py:323`, le lecteur ne fait
que le valider.

---

# DÉCISION 1 — quel canal la tranche vise-t-elle ? *(à valider par Steve)*

**Décision à prendre.** La première tranche « action média » s'attache-t-elle au canal `iact_`
(actions de **candidat** : `accept` / `replace` / `reject`, mutation de la base média) ou au canal
`mact_` (activations de **menu** et **lancement de lecture**) ?

**Contexte.** Les deux canaux existent (F8), partagent le même manifeste (F7) et le même contrôleur
(F2), mais pas la même autorité : `iact_` agit sur une proposition de correspondance, `mact_` fait
démarrer une lecture. Aujourd'hui aucun plugin ne peut contribuer à l'un ou à l'autre : les jetons
sont frappés par Core seul.

**Options.**

| Option | Contenu | Conséquences techniques | Conséquences produit | Impact visible | Réversibilité |
| --- | --- | --- | --- | --- | --- |
| **1a. Cibler `iact_`** | Un plugin `AVAILABLE` fait inscrire une action bornée sur une proposition de correspondance | Vocabulaire déjà fermé (F4) ; garde de révision déjà en place (F5) ; **aucune** garde à inventer ; n'ajoute aucun bouton à la géométrie Flex de la page disque | Un plugin peut agir sur l'identification d'un média, pas sur la lecture | **Faible** : au plus une action bornée de plus sur une page de propositions existante | Élevée : retirer la contribution rétablit l'existant ; rien n'est retiré à Core |
| **1b. Cibler `mact_`** | Un plugin contribue une entrée de navigation/lancement | Il faudrait **d'abord** définir une garde de péremption au dispatch (F6 : aucune comparaison de génération n'existe) ; la famille `mact_` n'a jamais été conçue pour un tiers | Un plugin participe au lancement de lecture — responsabilité que Core garde explicitement | **Fort** : de nouveaux moyens de lancer un média apparaissent dans les menus | Moyenne : réversible, mais la garde doit être traitée à la conception, pas après |
| **1c. Les deux d'un coup** | Tranche commune | Deux fois le périmètre et les tests ; décision 3 bloquante immédiatement | Aucun bénéfice à court terme | Cumul des deux lignes | Faible en pratique : on n'arrive à rien |

**Conséquences techniques (communes).** Le plugin **nomme** seulement (identifiant, libellé, jeton
contraint) ; il ne fournit ni chemin, ni argument, ni commande, ni PID, ni clé de manifeste. Core
frappe la clé, garde le verrou de vie, le cycle du worker et le rendu. Aucune nouvelle grammaire de
jeton.

**Conséquences produit.** `1a` sert « un plugin exploite une correspondance » ; `1b` sert
directement `plugin.dvd-menu` (désigné premier vrai plugin installable) — mais ce plugin reste de
toute façon bloqué par MPV 0.42 pour les menus DVD.

**Impact visible pour l'utilisateur.** `1a` : marginal, borné à une page existante. `1b` : de
nouvelles entrées de lancement dans les menus, donc un mode de lecture qui n'est plus décidé par
Core seul.

**Réversibilité.** `1a` : réversible sans dette (contribution déclarative, retirable). `1b` :
réversible dans le code, mais l'effet utilisateur dure tant qu'une extension est installée — donc il
dépend de l'installation, pas du code.

**Recommandation Hermes/DeepSeek : `1a`.** Raison en une ligne : c'est le seul canal dont le risque
est déjà borné par un mécanisme **mesuré** (`expected_revision`), donc le seul où un plugin peut
contribuer **sans gagner d'autorité** — le critère même du cadrage. Condition de retournement : si
la priorité devient `plugin.dvd-menu`, `1b` est la cible et la décision 3 devient **préalable**, pas
simultanée.

---

# DÉCISION 2 — comment distinguer une entrée d'origine plugin ? *(tranchée par Hermes)*

**Décision à prendre.** Comment une entrée de manifeste d'origine plugin se distingue-t-elle d'une
entrée d'origine interface, alors que `origin` est figé à `"UI"` (F9) ?

**Contexte.** Dès qu'une entrée peut venir d'ailleurs, l'état d'action et le journal deviennent
muets sur l'origine — exactement quand l'audit en a besoin. C'est une question de traçabilité, pas
de sécurité : personne ne gagne de pouvoir ici.

**Options.**

| Option | Contenu | Conséquences techniques | Impact visible | Réversibilité |
| --- | --- | --- | --- | --- |
| **2a. Champ `origin` écrit par Core** | `"UI"` ou `"plugin:<id>"`, écrit au moment où Core frappe la clé, propagé à l'état et au journal | Additif à un schéma versionné ; la porte de validation du manifeste doit le couvrir ; politique de redaction à définir | **Aucun** si le champ n'est pas affiché | Élevée (champ retiré = état antérieur) |
| **2b. Troisième famille de jetons** | L'origine est dans la forme de la clé | Duplique une grammaire contractuelle déjà validée ; on a déjà `iact_` et `mact_` | Aucun directement | Faible : une grammaire publiée ne se retire pas |
| **2c. Déduire l'origine du manifeste émetteur** | Ne rien stocker | L'information est perdue au moment utile, non vérifiable | Aucun | Sans objet |

**Conséquences produit.** Aucune : le plugin ne déclare pas ce champ, Core l'écrit sur sa propre
production — ce n'est donc pas une modification du contrat public des plugins.

**Recommandation Hermes/DeepSeek : `2a`**, avec deux garde-fous : le champ est écrit **par Core
uniquement**, et il n'est **pas affiché** dans un premier temps (il vit dans l'état et le journal).
Condition de retournement : si Steve veut que l'origine soit **visible** (par exemple « action
fournie par une extension »), la décision redevient produit et je la remonte.

---

# DÉCISION 3 — vérifier la fraîcheur du manifeste au dispatch ? *(tranchée par Hermes)*

**Décision à prendre.** Faut-il comparer `manifest_generation` à la génération courante au moment
du dispatch, alors qu'aucune comparaison n'existe (F6) ?

**Contexte.** Un jeton périmé est aujourd'hui refusé parce qu'il n'est plus une **clé** du manifeste
courant (F3), le manifeste étant remplacé atomiquement (F7). C'est correct, mais c'est un refus
**par absence**, avec le motif `INVALID_ACTION_TOKEN` — qui se lit « jeton invalide » et non « la
liste a changé ».

**Options.**

| Option | Contenu | Conséquences techniques | Impact visible | Réversibilité |
| --- | --- | --- | --- | --- |
| **3a. Statu quo** | La fraîcheur reste garantie par le remplacement atomique + `expected_revision` | Aucune | Aucun | Sans objet |
| **3b. Comparer `manifest_generation` au dispatch** | Le contrôleur relit la génération et la compare | **Garde décorative** : la génération attendue viendrait du même document relu par la clé — comparer un champ à lui-même ne prouve rien | Aucun | — |
| **3c. Porter la génération dans la clé et refuser explicitement** | `iact_` porte **déjà** la génération : Core rend un motif distinct (`ACTION_MANIFEST_STALE`) au lieu de `INVALID_ACTION_TOKEN` | Le jeton reste refusé : aucune décision ne change, seuls le motif et la télémétrie s'améliorent | **Mineur** : message différent à l'écran quand la liste a changé | Élevée |

**Conséquences produit.** `3a` et `3c` ne changent rien à ce que l'utilisateur peut faire. `3b` est
à écarter : une garde décorative est pire qu'aucune garde, parce qu'elle fait croire que le chemin
est couvert.

**Recommandation Hermes/DeepSeek : `3a` pour cette tranche** (donc : **ne rien changer**), et `3c`
seulement si le canal visé devient `mact_` — là, l'ambiguïté du motif conduit l'utilisateur à
relancer une lecture au lieu d'actualiser une liste. **La décision 3 dépend donc de la décision 1.**

---

## Récapitulatif de la répartition

| Décision | Nature | Qui tranche | Raison |
| --- | --- | --- | --- |
| 1 — quel canal | Produit : change ce que les plugins pourront faire et, pour `1b`, ce que l'utilisateur voit à l'écran | **Steve** | Contrat public + comportement visible + responsabilité du Core |
| 2 — origine des entrées | Technique, additive, invisible | **Hermes**, sauf objection | Le plugin ne déclare rien de plus ; Core écrit un fait sur sa propre production |
| 3 — fraîcheur au dispatch | Technique, réversible, sans effet utilisateur (`3a` = statu quo) | **Hermes**, sauf objection | Ne change ni les jetons acceptés ni les actions ; la variante visible (`3c`) n'est proposée que si la décision 1 change de cible |

## Première tâche proposée, une fois la décision 1 prise

1. Core écrit, à la frappe de la clé, l'entrée de manifeste **et** son champ `origin` (décision 2).
2. Une entrée issue d'un plugin n'est produite que si le plugin est `AVAILABLE` et ses `requires`
   satisfaits — en réutilisant l'instance résolue qui sert déjà Doctor et `Système → Extensions`,
   jamais une recollecte.
3. Le plugin nomme ; il ne fournit ni chemin, ni argument, ni commande, ni PID, ni clé de manifeste.
4. Vocabulaire d'action inchangé (`accept`/`replace`/`reject`) : toute extension est une
   modification de Core, donc hors tranche.

## Ce que je n'ai PAS vérifié

- Corps complet de `openhtpc-media-action-control.py` et `openhtpc-media-match-ui` : lus par extraits
  et par comptages, pas intégralement.
- Le **canal `mact_`** n'a été qu'entrevu : ma mesure porte sur `iact_` et sur le contrôleur.
- L'exposition côté interface (page média/disque) et le côté Flex d'une contribution : non lus.
- Aucun test exécuté pour cette pré-revue : elle est **statique**, sur base vérifiée par empreinte.
