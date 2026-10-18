# OPENHTPC — Acteurs, outils et autorités

Dernière mise à jour : 2026-10-18, Europe/Brussels.

## Objet et portée

Ce document est la source canonique pour savoir qui intervient dans OPENHTPC, avec quelles permissions et sous quelle autorité. Il décrit l'organisation du projet ; il ne donne à aucun acteur une autorisation implicite de commit, merge, push, déploiement, publication ou opération physique.

L'ordre d'autorité technique reste celui de `AGENTS.md` : code/tests/artifacts, état courant applicable, qualifications/architectures, roadmaps, puis historique. Steve conserve l'autorité produit et la validation humaine finale. Les permissions effectives d'une mission sont toujours limitées par le mandat explicite, `AGENTS.md`, les politiques applicables et les protections techniques du contexte d'exécution.

## Distinctions essentielles

- **Steve** est l'autorité humaine finale ; aucun modèle, agent ou benchmark ne le remplace pour l'image, le son ou l'expérience réelle.
- **ChatGPT** et **Codex CLI** sont deux rôles différents : cadrage/architecture produit d'un côté, exécution technique dans le dépôt de l'autre. Steve peut mandater Codex directement pour une tâche technique claire.
- **CodeGraph** est un outil d'analyse structurelle utilisé notamment par Codex. Il ne décide pas et ne modifie pas le projet.
- **Hermes Agent** est le second ingénieur opérationnel et l'auditeur contradictoire ; **DeepSeek** est le modèle actuellement utilisé derrière lui ; **OpenRouter** est la couche de fourniture/routage. Ces trois noms ne sont pas interchangeables.
- **AGY** désigne dans le dépôt le CLI Google Antigravity utilisé par Autopilot comme planner/reviewer borné. **Autopilot** est l'orchestrateur Python local, pas un modèle.
- Une recommandation d'agent est un avis. Une preuve logicielle n'est pas une qualification physique.
- **Graphiphy** est identifié par Steve comme acteur important de la combinaison d’agents (2026-10-18). Son rôle technique n’étant pas prouvé localement, cette reconnaissance organisationnelle **n’autorise aucun accès ni attribution fonctionnelle présumée**, en particulier celle de CodeGraph.

## Hôte de contrôle et Hermes — vérifié le 2026-10-13

Codex, AGY et CodeGraph sont disponibles sur .79. Hermes Agent 0.21.6 y fonctionne désormais dans Docker avec ses historiques et rapports ; DeepSeek reste distant via OpenRouter. Le conteneur Unraid .10 est arrêté/secours. Les audits OPENHTPC passent par un conteneur one-shot UID10000, snapshot read-only et SSH masqué. Le gateway conserve son canal de lecture seule à commande forcée pour les contrôles de fraîcheur. Depuis le 2026-10-13, Steve a aussi autorisé une voie ingénierie directe distincte : compte Unix/SSH `hermes-eng`, écriture canonique et Git complet, sans sudo, groupe Docker, déploiement ou publication. La voie par clone autonome reste disponible. Voir le checkpoint `docs/continuity/2026-10-13-hermes-direct-engineering-access.md`.

## Matrice des responsabilités et permissions

`Mandat requis` signifie que la capacité technique éventuelle n'est pas une autorisation permanente.

| Acteur | Type | Mission principale | Lecture dépôt | Écriture dépôt | Tests | Git | Déploiement | Autorité décisionnelle | Dépendances principales |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Steve Dehanne | Humain / propriétaire produit | Choix produit, arbitrage UX, validation image/son/matériel, autorisations sensibles | Oui | Oui | Peut demander/opérer | Autorité finale sur intégration/publication | Oui, décision explicite | **Finale** | Matériel réel, preuves du dépôt et avis des outils |
| ChatGPT | Assistant de cadrage | Architecture, produit, UX, cohérence, préparation des décisions et continuité conceptuelle | Selon contexte fourni | Seulement si un outil et un mandat le permettent | Peut proposer/interpréter | Aucune autorité Git implicite | Non sans mandat explicite et outil autorisé | Conseil, jamais finale | Service OpenAI ; contexte courant et mémoire canonique du dépôt |
| Codex CLI | Agent d'exécution principal | Analyse, CodeGraph, implémentation, tests, diagnostic et opérations Git bornées | Oui | Oui, dans le périmètre mandaté | Oui | Inspection ; commit/push/merge seulement si explicitement autorisés | Seulement sur autorisation explicite et après prévol | Technique déléguée, pas produit | Service OpenAI, `AGENTS.md`, outils locaux/MCP, CodeGraph |
| AGY / Google Antigravity CLI | Agent planner/reviewer | Planifier et relire les tâches Autopilot en mode headless borné | Oui, en lecture seule | Non dans le contrat Autopilot | Analyse des preuves, pas exécution libre | Non | Non | Avis borné soumis à la politique | Exécutable `agy`, authentification Google externe, schémas Autopilot |
| CodeGraph | Outil d'analyse structurelle | Callers/callees, dépendances, chemins d'appel, blast radius, tests associés | Index structurel | Non | Identifie les tests ; ne les exécute pas comme autorité | Non | Non | Aucune | Index local/MCP ; snapshot dédié lorsqu'utilisé par Hermes |
| Hermes Agent | Second ingénieur + auditeur externe | Reprendre un chantier borné ; contre-audit adversarial séparé | Snapshot audit, clone ingénierie, canal lecture seule, ou compte direct `hermes-eng` | Oui dans le clone ou, depuis le 2026-10-13, directement via `hermes-eng` | Oui | Branches/commits locaux ; aucun push/tag/publication implicite | **Non** sans mandat séparé | Technique déléguée, jamais finale ; ses changements sont relus par Codex ou Steve | Conteneurs isolés ou compte SSH dédié, skills projet, CodeGraph, modèle DeepSeek via OpenRouter |
| DeepSeek | Modèle | Moteur d'analyse actuellement sélectionné pour Hermes | Via le contexte Hermes | Non par lui-même | Non par lui-même | Non | Non | Aucune | Hermes Agent et fournisseur OpenRouter |
| OpenRouter | Fournisseur / routeur de modèles | Acheminer l'accès au modèle DeepSeek pour Hermes | Non | Non | Non | Non | Non | Aucune | Configuration/identifiants externes au dépôt |
| OPENHTPC Autopilot | Orchestrateur Python local | Enchaîner plan AGY, politique déterministe, exécution Codex, review et gates | Oui | État de run borné ; modifications via Codex | Valide les preuves déclarées | Peut accepter un **commit local** uniquement selon politique ; jamais push | Jamais automatique | Politique/gate, pas autorité produit | `agy`, `codex`, schémas/prompts, état canonique applicable |
| OpenAI | Fournisseur | Fournir ChatGPT et Codex selon l'environnement utilisé | Non | Non | Non | Non | Non | Aucune | Comptes et services externes au dépôt |
| Graphiphy | **ACTEUR IMPORTANT (DÉCISION OPÉRATEUR) / CAPACITÉS À QUALIFIER** | Inclure dans la combinaison d’agents OPENHTPC ; contrat opérationnel non attesté localement | Non établie | Non autorisée implicitement | À qualifier | Aucun accès implicite | Non autorisé implicitement | Avis à établir ; Steve arbitre | **Distinct de CodeGraph** ; identifier installation, interface et rôle avant délégation |
| Desktop Commander | **ROLE À CLARIFIER** | Aucune occurrence probante trouvée dans le dépôt au 2026-10-11 ; usage actuel non établi | À clarifier | À clarifier | À clarifier | À clarifier | À clarifier | Aucune établie | **ROLE À CLARIFIER** |
| Gemini CLI | Outil historique/non requis actuellement | Le runtime Autopilot vérifié appelle `agy`, pas `gemini` ; `GEMINI.md` reste un fichier d'instructions | Lecture potentielle | Non établie | Non établie | Non | Non | Aucune | Statut opérationnel courant non établi |

## Circuits de travail recommandés

Ces circuits sont des chemins usuels, pas une obligation bureaucratique. Le contrôle est proportionnel au risque.

### Tâche technique claire

```text
Steve → Codex CLI → CodeGraph/outils → modification bornée → tests → rapport
```

ChatGPT n'est pas un relais obligatoire. Codex doit toutefois remonter tout conflit avec une règle gelée ou toute décision produit manquante.

Lorsque Codex n'est pas disponible, le même chantier peut être remis à Hermes
dans le clone isolé ou via `hermes-eng`. Dans la voie directe, Hermes travaille
sur sa propre branche/worktree, consigne ses tests et soumet ses changements à
Codex ou Steve avant qualification.

### Handoff standard bidirectionnel

Codex → Hermes : vérifier et documenter branche/HEAD/VERSION/status/stashes,
objectif, décisions, tests et reste à faire ; lancer `prepare`, puis `run`. Le
manifeste task-local et le checkpoint remplacent toute dépendance au transcript.

Hermes → Codex : arrêter les changements dans le clone, consigner commandes et
preuves, puis lancer `export`. Codex revalide le canonique et revoit
`changes.patch`, `status.txt`, `untracked.paths.z` et le rapport avant toute
application. Aucun import automatique n'existe.

Les skills actuelles sont partagées depuis `.agents/skills/` en lecture seule.
Les noms futurs `openhtpc-gpu-qualification`, `openhtpc-magnificence` et
`openhtpc-release-validation` sont réservés mais absents au 2026-10-11 ; ils ne
doivent pas être simulés. Leur futur ajout canonique les rendra visibles à Hermes
sans copie supplémentaire.

### Changement significatif ou risqué

```text
Steve et/ou ChatGPT → cadrage
                         ↓
                      Codex CLI → CodeGraph → implémentation → tests
                                                   ↓
                              AGY review si pertinente
                              Hermes/DeepSeek contre-audit si pertinent
                                                   ↓
                              validation humaine → intégration autorisée
```

AGY et Hermes ne sont pas exigés pour chaque petite modification. Hermes reste hors du chemin de commit Autopilot. Sa voie audit reçoit toujours un snapshot techniquement immuable. Sa voie ingénierie peut utiliser le clone autonome sans remote ou le compte direct `hermes-eng`; ce dernier n'est jamais utilisé pour l'audit contradictoire.

### Décision produit ou UX

```text
Steve → ChatGPT (analyse/cadrage) → décision de Steve → Codex CLI (implémentation)
```

Les validations visuelles et sonores reviennent à Steve. Les mesures automatiques préparent et étayent cette décision sans s'y substituer.

## Règles Git, déploiement et publication

- Une tâche de documentation n'autorise pas un commit.
- Un commit autorisé n'autorise pas push, tag, merge, rebase ou publication.
- Une implémentation validée logiciellement n'autorise pas un déploiement.
- Un déploiement nécessite un mandat explicite, un prévol de l'hôte et la préservation de l'état utilisateur.
- Autopilot ne déploie jamais automatiquement et ne pousse jamais.
- Hermes peut modifier et committer dans son clone isolé ou sur ses propres branches/worktrees via `hermes-eng`. Il ne pousse, ne tague, ne publie, ne réécrit une branche partagée, ne déploie et ne manipule les stashes protégés sans mandat séparé de Steve. Codex ou Steve relit son travail avant qualification.
- CodeGraph produit des faits structurels, pas une permission d'agir.

## Provenance et points à clarifier

Rôles démontrés par le dépôt : `AGENTS.md`, `docs/OPENHTPC_AUTOPILOT.md`, `docs/OPENHTPC_AUTOPILOT_POLICY.md`, `docs/OPENHTPC_HERMES_AUDITOR.md`, les sources/tests Autopilot et les checkpoints de continuité.

Les rôles de ChatGPT demandés ici sont une décision opérateur du 2026-10-11 et non une capacité technique déduite du dépôt. La présence technique, les permissions et les fonctionnalités de Graphiphy demeurent non établies localement ; son importance organisationnelle a été confirmée par Steve le 2026-10-18. Le rôle technique de Desktop Commander reste à actualiser dans ce registre. Aucun rôle Graphiphy ne peut être déduit de CodeGraph. CodeGraph est configuré par tâche dans le HOME isolé de la voie ingénierie ; cela ne crée aucun connecteur vers l'index canonique Codex.
