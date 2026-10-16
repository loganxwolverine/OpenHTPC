# Continuité opérationnelle Codex ↔ Hermes — 2026-10-11

## Verdict

**HERMES HANDOFF READY** pour un chantier logiciel borné dans un clone isolé.

Ce verdict ne donne aucune autorité de push, merge vers le canonique, déploiement,
release, opération physique ou manipulation des stashes protégés. La voie d'audit
Hermes immuable reste disponible et distincte.

## Provenance vérifiée

- hôte : `openhtpc-control`, `192.168.1.79` ;
- branche source : `feature/magnificence-sd-auto` ;
- HEAD source : `975402945376618db56e29945074ea30ddcd2cb8` ;
- VERSION : `1.3.1` ;
- worktree canonique dirty préservé ; aucun fichier existant restauré ou écrasé ;
- stashes observés et non touchés : `stash@{0}` expérience RTX stale et
  `stash@{1}` **RC7 T5 network deferred** protégé ;
- `OPENHTPC_CURRENT_STATE.json` : **STALE**, workstream P2/1.2.0 incompatible
  avec HEAD/VERSION ; il n'autorise ni Autopilot ni action physique ;
- `.git/OPENHTPC_STATE.md` : historique plus ancien, non autoritaire.

Le checkpoint précédent comportait une faute de transcription du HEAD
(`...dddc2cb8`) ; le dépôt vérifié donne `...ddcd2cb8`.

## Matrice mesurée

| Capacité | Codex CLI sur `.79` | Hermes ingénierie | AGY | Autres acteurs / action nécessaire |
| --- | --- | --- | --- | --- |
| Filesystem / dépôt | canonique lisible et writable dans le mandat | clone autonome writable ; dépôt canonique non monté ; skills canoniques montées read-only | lecture projet dans le contrat Autopilot | ChatGPT selon connecteur ; Steve final |
| Git | 2.56.0, inspection et opérations mandatées | 2.47.3, branche et commit locaux ; aucun remote | pas d'autorité Git | intégration du patch par Codex/Steve après revue |
| Shell / Python / pytest | bash, Python 3.14.8, pytest 8.4.2 | bash, Python 3.14.7, pytest 8.3.5 | CLI headless borné | aucun écart bloquant |
| Node / npm | 22.23.1 / 10.9.8 | 26.7.0 / 12.0.2 | non mesuré, non requis par son contrat | versions différentes à signaler si un test est sensible |
| Compilation | GCC 16.2.1, CMake 4.3.0, Ninja 1.13.2, Meson 1.11.2 | GCC 14.2.0, CMake 3.31.6, Ninja 1.12.1, Meson 1.7.0 ; build Flex réel PASS | non établie | Hermes couvre le build C/SDL demandé |
| FFmpeg | 8.1.3 | présent dans l'image dérivée | non mesuré | skill partagée disponible |
| CodeGraph | MCP canonique 0.20.1 ; requête réelle 7 arêtes/8 nœuds | MCP task-local 0.20.1 ; index réel 232 fichiers et 7 imports du registre | aucun MCP configuré observé | indices séparés, jamais d'autorité d'écriture |
| Skills / mémoire | `.agents/skills/` et mémoire canonique | même répertoire monté read-only ; symlinks `.hermes/skills` résolus ; manifeste impose la lecture de la continuité | `GEMINI.md` inclut `AGENTS.md` et impose désormais continuité, acteurs, roadmap et dernier checkpoint ; aucune capacité skill équivalente établie | futures skills automatiquement visibles si ajoutées au répertoire canonique |
| Réseau / fournisseur | réseau de l'hôte selon sandbox/mandat | sortie réseau du conteneur ; seule clé OpenRouter nécessaire injectée | authentification Google externe existante, détails non promus | Hermes → OpenRouter → DeepSeek validé ; aucun secret affiché |
| SSH / machines de test | OpenSSH 10.2 ; `.229` joignable, `.59` timeout, `.67` no route lors du prévol | client SSH présent mais HOME `.ssh` vide, aucune clé hôte | non établi | aucun accès machine ou opération physique accordé à Hermes |
| Logs / diagnostics | dépôt, services et hôtes dans le mandat | dépôt, sorties de tests, logs fournis au clone ; aucun journal hôte monté | analyse des preuves Autopilot | fournir explicitement tout log externe nécessaire |
| Agents / services | Codex 0.162.1 ; Docker/outils hôte | Hermes Agent 0.21.6 one-shot, modèle `deepseek/deepseek-v4.1-flash` via OpenRouter | AGY 1.3.3 planner/reviewer | Graphiphy et Desktop Commander : **ROLE À CLARIFIER** |

Hermes est l'agent. OpenRouter est le fournisseur/routeur. DeepSeek est le
modèle. CodeGraph est un outil d'analyse et ne constitue pas un acteur de décision.

## Implémentation et garde-fous

- `tools/hermes-engineer/Dockerfile` dérive une image locale et ajoute les outils
  de test/build manquants ;
- `tools/hermes-engineer/openhtpc-hermes-engineer.py` prépare, exécute, inspecte
  et exporte un handoff ;
- le snapshot exact du worktree dirty est figé dans un commit baseline local dont
  le parent est le HEAD source ; le clone n'a aucun remote ;
- le delta exporté est calculé depuis cette baseline : il ne réexporte pas le
  dirty préexistant de Codex ;
- seuls le clone et son HOME sont writable ; les skills canoniques et le binaire
  CodeGraph sont read-only ; Docker socket, `.git` canonique et SSH hôte absents ;
- capacités Linux supprimées et `no-new-privileges` ;
- un helper hors réseau extrait seulement `OPENROUTER_API_KEY` vers un fichier
  task-local mode 0600 ; aucune autre variable secrète n'est transmise ;
- `HERMES_WRITE_SAFE_ROOT=/workspace` bloque les écritures hors clone.

Skills réellement lisibles : `shader-programming`, `ffmpeg-skill`,
`python-testing-patterns`, `verification-before-completion`, `skill-creator` et
`openhtpc-mpv-rendering`. Les futures `openhtpc-gpu-qualification`,
`openhtpc-magnificence` et `openhtpc-release-validation` sont **ABSENT** ; aucune
skill fictive n'a été créée. Leur futur ajout sous `.agents/skills/` les rendra
accessibles sans duplication.

## Test réel de handoff

Tâche : `handoff-validation-r2-20261011`.

Hermes a lu le manifeste et la mémoire canonique, retrouvé branche/HEAD/VERSION,
distingué HEAD source et baseline isolée, confirmé l'absence de remote, stashes,
socket Docker et clés SSH, puis produit
`HERMES_HANDOFF_VALIDATION.md` sans modifier le code produit.

Preuves fraîches :

- relation réelle Hermes → OpenRouter → DeepSeek : exit 0 ;
- CodeGraph MCP task-local 0.20.1 : index de 232 fichiers ; requête
  `payload/openhtpc-plugin-registry.py` = 7 imports stdlib, aucun `importedBy`
  statique, complexité 18 fonctions / maximum 48 / grade C ;
- complément CodeGraph réel sur `resolve_dependencies` : 5 callers, 23 callees
  retournés, graphe 28 nœuds/28 arêtes, blast radius direct 2, tests liés
  statiquement 0 et traversée réelle. La contre-vérification source a identifié
  21 callees faux positifs dus à une collision de nom `resolve` et l'absence de
  liens tests due au chargement dynamique `importlib` ; ces limites sont
  conservées, pas masquées ;
- `pytest -q tests/test_plugin_framework_p2_registry.py` : **24 passed,
  1 skipped**, exit 0, 0,37 s ;
- compilation hors réseau dans l'image Hermes : configuration CMake/Ninja et
  build `vendor/flex-launcher` **PASS** (un warning préexistant `write` ignoré) ;
- gate finale Autopilot + lanceur + registre : **114 passed, 1 skipped** ;
  les cinq tests hermétiques du lanceur sont inclus ;
- export inverse final : `changes.patch` 0 octet, manifeste NUL-safe contenant
  seulement `HERMES_HANDOFF_VALIDATION.md` et
  `HERMES_CODEGRAPH_VALIDATION.md` ; le dirty source n'est pas réexporté ;
- une tentative scratch hors `/workspace` a été refusée : garde-fou d'écriture
  effectivement exercé ; l'écriture demandée dans `/workspace` a réussi.
- un second `run` sur la même tâche a d'abord révélé puis fait corriger
  l'idempotence du fichier credential task-local ; la reprise suivante a terminé
  exit 0 sans élargir les capacités ou secrets.

Le MCP Hermes est task-local et indexe le clone, pas l'index canonique Codex.
Hermes a utilisé le serveur configuré via une session MCP stdio réelle. La surface
de tools du modèle n'exposait pas directement les totaux nœuds/arêtes ; cette limite
de présentation ne remet pas en cause les appels MCP observés.

Rapports locaux :

- `~/.local/state/openhtpc-hermes-engineering/tasks/handoff-validation-r2-20261011/reports/hermes-20261011T181357Z.md` ;
- `~/.local/state/openhtpc-hermes-engineering/tasks/handoff-validation-r2-20261011/reports/hermes-20261011T182332Z.md` ;
- livrables du clone : `HERMES_HANDOFF_VALIDATION.md` et
  `HERMES_CODEGRAPH_VALIDATION.md`.

## Procédure Codex → Hermes

1. Codex exécute le prévol obligatoire et met à jour continuité/checkpoint.
2. Préparer :
   `openhtpc-hermes-engineer prepare TASK 'objectif et périmètre bornés'`.
3. Le manifeste enregistre branche, HEAD, VERSION, status, stashes, objectif,
   permissions, baseline et fichiers non suivis sûrs.
4. Exécuter :
   `openhtpc-hermes-engineer run TASK 'lire le handoff, agir, tester, rapporter'`.
5. Contrôler : `openhtpc-hermes-engineer status TASK` puis lire le rapport.

## Procédure Hermes → Codex

1. Hermes consigne décisions, fichiers, tests exacts, limitations et reste à faire
   dans le clone, puis s'arrête sans intégration canonique.
2. Exporter : `openhtpc-hermes-engineer export TASK`.
3. Codex lit `status.txt`, `changes.patch`, `untracked.paths.z` et le rapport ; il
   vérifie à nouveau branche/HEAD/status/stashes canoniques.
4. Codex revoit le patch et l'applique seulement après décision explicite ; aucune
   application automatique n'existe.
5. Codex relance tests et met à jour checkpoint/roadmap. Un commit local Hermes
   n'autorise jamais un push ou merge.

## Rollback

La voie audit et le gateway Hermes n'ont pas été remplacés. Pour désactiver la voie
ingénierie, cesser d'utiliser le lanceur ; après archivage explicite, l'opérateur
peut supprimer le lanceur local, l'image dérivée et les tâches sous
`~/.local/state/openhtpc-hermes-engineering/`. Aucun rollback produit, hôte de test,
stash ou dépôt canonique n'est requis. Toute suppression reste une opération
séparée à autoriser.

## Limites restantes et prochaine action

- AGY n'a ni MCP CodeGraph ni parité d'outils d'ingénierie prouvée ; son rôle reste
  planner/reviewer Autopilot.
- Hermes n'a volontairement aucun accès canonique direct, secret général, SSH de
  machine, déploiement ou validation physique.
- versions Node et compilateurs diffèrent de l'hôte Codex ; signaler toute
  dépendance à une version exacte.
- Graphiphy et Desktop Commander restent **ROLE À CLARIFIER**.
- l'état courant machine reste STALE ; il doit être modernisé par une tranche
  dédiée, pas silencieusement dans ce handoff.
- prochaine action sûre : utiliser cette procédure sur un vrai chantier borné,
  puis faire revoir et intégrer son export par Codex/Steve.

Aucun commit, push, merge, déploiement ou publication n'a été effectué.
