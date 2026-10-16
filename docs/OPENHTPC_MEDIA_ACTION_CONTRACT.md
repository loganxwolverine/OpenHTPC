# OPENHTPC — contrat générique d'action média bornée

Statut : **décisions d'architecture prises** le 2026-10-15 par Steve Dehanne (décision 1) et par
Hermes/DeepSeek (décisions 2 et 3, techniques et réversibles), après pré-revue statique sur base
vérifiée par empreinte. **Aucune implémentation n'est commencée** par ce document.

Autorité : ce document enregistre des décisions de conception. Il n'autorise ni commit, ni
déploiement, ni qualification physique, et il ne remplace ni `AGENTS.md`, ni la roadmap.

## 1. Principe directeur

> Un plugin dont l'état résolu est `AVAILABLE` peut **contribuer une action bornée** à un canal
> d'action de Core. Il n'en gagne **jamais** l'autorité : Core frappe la clé, tient le verrou,
> possède le cycle de vie du worker, choisit le verbe et exécute le dispatch.

Conséquence opérationnelle, valable pour toute la suite du chantier :

- le plugin **nomme** (identifiant, libellé, jeton contraint) et déclare ses dépendances ;
- le plugin ne fournit **jamais** de chemin, d'argument, de commande, de PID, de descripteur, ni de
  clé de manifeste ;
- le vocabulaire d'action est **fermé** (`accept`, `replace`, `reject`) : l'étendre est une
  modification de Core, donc hors de toute tranche plugin ;
- le gating réutilise l'instance d'état résolue qui sert déjà Doctor et `Système → Extensions` —
  jamais une recollecte, jamais un second calcul.

## 2. Faits mesurés qui fondent les décisions

Relevés le 2026-10-15 sur le dépôt canonique (branche `feature/magnificence-sd-auto`, HEAD
`312ceb8`), par lecture directe du code :

| Réf. | Fait | Emplacement |
| --- | --- | --- |
| F1 | Trois hooks déclarés et jamais consommés (`ui_menu`, `media_handler`, `dispatcher`) | `payload/openhtpc-plugin-registry.py:18` |
| F2 | Le contrôleur n'interprète rien : un seul entrypoint codé en dur, le jeton est relayé tel quel | `payload/openhtpc-media-action-control.py`, `_launch()` |
| F3 | Le jeton n'est pas décodé : il est cherché comme **clé** du manifeste courant | `payload/openhtpc-media-match-ui:553-575` |
| F4 | Vocabulaire d'action fermé : `accept` / `replace` / `reject`, sinon `UNKNOWN_ACTION` | `payload/openhtpc-media-match-ui:577-632` |
| F5 | La protection anti-péremption réellement en place est `expected_revision` | `…media-match-ui:580`, `:614-628` ; `payload/openhtpc-media-match.py:588-596` |
| F6 | `manifest_generation` est écrit par le moteur de session et lu nulle part ailleurs | `payload/openhtpc-session-engine.py:337-350` |
| F7 | Le manifeste est un document de Core, remplacé atomiquement, versionné par génération | `payload/openhtpc-session-engine.py:337-350` |
| F8 | Deux familles de jetons coexistent : `iact_` (action de candidat) et `mact_` (navigation/lancement) | `…media-match-ui:407` ; `…session-engine.py:323` ; `…openhtpc-play:64` |
| F9 | `origin` est codé en dur à `"UI"` | `payload/openhtpc-media-action-control.py:260` |
| F10 | Aucune chaîne shell : zéro `os.system`, zéro `exec(` sur les artefacts d'action | comptages |

## 3. Décision 1 — canal retenu : les actions de candidat (`iact_`)

**Décision.** Le premier contrat générique s'attache au canal `iact_` : un plugin `AVAILABLE` peut
faire inscrire par Core une action bornée portant sur une **proposition de correspondance**
(`accept` / `replace` / `reject`). Le canal `mact_` (activation de menu et lancement de lecture)
**n'est pas** visé par cette tranche.

**Raison.** C'est le seul canal dont le risque est déjà borné par un mécanisme mesuré
(`expected_revision`, F5) et dont le vocabulaire est déjà fermé (F4). Le plugin y contribue donc
sans gagner d'autorité — exactement le principe directeur du §1.

**Conséquences.** Le canal `mact_` reste hors périmètre : l'y étendre supposerait de définir une
garde de péremption au dispatch, ce que le §5 exclut explicitement tant que le besoin n'est pas
démontré.

**Condition de retournement.** Si la priorité produit devient `plugin.dvd-menu` (le lancement
plutôt que la correspondance), alors le canal `mact_` devient la cible et la décision 3 doit être
reprise **avant** la conception, pas après.

## 4. Décision 2 — origine des entrées : `origin = UI | plugin:<id>`, écrit par Core

**Décision.** L'entrée de manifeste porte un champ `origin` renseigné **par Core** au moment où il
frappe la clé : `"UI"` pour une origine interface, `"plugin:<identifiant>"` pour une origine
plugin. Le champ est propagé à l'état d'action et au journal, et **n'est pas affiché** dans
l'interface dans un premier temps.

**Raison.** Dès qu'une entrée peut venir d'ailleurs, l'état et le journal deviennent muets sur son
origine — au moment précis où l'audit en a besoin. C'est un besoin de traçabilité, pas de
sécurité : personne ne gagne de pouvoir ici.

**Ce que la décision n'est pas.** Ce n'est pas une modification du contrat public des plugins : le
plugin ne déclare pas ce champ, Core l'écrit sur sa propre production. Aucune nouvelle grammaire de
jeton n'est introduite (une troisième famille de préfixes a été écartée : elle donnerait au plugin
une prise sur le nommage).

**Condition de retournement.** Si l'origine doit devenir **visible** pour l'utilisateur (par
exemple « action fournie par une extension »), la décision redevient produit et remonte à Steve.

## 5. Décision 3 — fraîcheur : aucune nouvelle garde au dispatch

**Décision.** On **ne compare pas** `manifest_generation` à la génération courante au moment du
dispatch. La fraîcheur reste garantie par les deux mécanismes déjà en place : le remplacement
atomique du manifeste (F7) — qui invalide toute clé de l'ancien modèle — et `expected_revision`
(F5) pour les actions de candidat.

**Raison.** Une comparaison de `manifest_generation` au dispatch serait une **garde décorative** :
la génération attendue devrait venir du même document relu par la clé, ou d'une source qu'il
faudrait inventer. Une garde qui ne peut pas échouer est pire qu'aucune garde, parce qu'elle fait
croire que le chemin est couvert.

**Amélioration différée, non décidée ici.** Si le canal `mact_` devient la cible, la clé `iact_`
porte déjà la génération : Core pourrait rendre un motif distinct (`ACTION_MANIFEST_STALE`) au lieu
de `INVALID_ACTION_TOKEN`. Ce serait un progrès de diagnostic et de télémétrie, sans changer la
décision de refus — mais cela modifie un message visible, donc remonte à Steve avant implémentation.

## 6. Forme d'une contribution (proposition, non implémentée)

Le plugin déclare une action de façon purement **nominative** : identifiant, libellé, jeton
contraint, dépendances requises. Aucune valeur libre n'est promue, aucune n'atteint une ligne de
commande ni un fichier exécutable. Core résout le jeton dans son vocabulaire d'action existant et
n'expose l'action que si le plugin est `AVAILABLE`, activé, et ses `requires` satisfaits.

## 7. Hors périmètre de ce document

- L'implémentation elle-même, et toute tranche de code : ce document n'en autorise aucune.
- Le canal `mact_` et le lancement de lecture (§3).
- La visibilité de l'origine dans l'interface (§4).
- L'installation, la mise à jour, la désactivation et la retrait des extensions first-party : objet
  d'une tranche ultérieure.
- `plugin.dvd-menu`, qui reste de plus conditionné au support des menus DVD par MPV (0.42).

## 8. Références

- Pré-revue détaillée et options écartées : `docs/audits/2026-10-15-media-action-3-decisions-hermes.md`
- Analyses antérieures : `docs/audits/2026-10-13-media-action-contract-hermes.md`,
  `docs/audits/2026-10-13-media-action-dispatch-hermes.md`,
  `docs/audits/2026-10-13-media-action-cartography-hermes.md`
- Point de reprise et état consolidé : `docs/OPENHTPC_CONTINUITY.md`
- Priorités et journal : `OPENHTPC-ROADMAP.md`, `OPENHTPC-PLUGIN-ROADMAP.md`

## 9. Limites de ce document

- Pré-revue **statique** : aucun test exécuté pour elle, et le corps complet de
  `openhtpc-media-action-control.py` et `openhtpc-media-match-ui` a été lu par extraits et par
  comptages, pas intégralement.
- Le canal `mact_` n'a été qu'entrevu.
- L'exposition côté interface et le côté Flex d'une contribution n'ont pas été lus.
