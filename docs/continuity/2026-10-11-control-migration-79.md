# OPENHTPC — Duplication du contrôle .229 vers .79, première étape

Observation : 2026-10-11T10:25:47.071101+02:00.

## Mandat et limites

Steve autorise la migration par duplication et demande explicitement de conserver .229 opérationnel si .79 échoue. La source canonique demeure .229 tant que la validation et la bascule ne sont pas établies. Aucun commit, push, déploiement OPENHTPC, arrêt de service, changement de clé API ou modification Hermes n'est autorisé par ce jalon. Aucun de ces actes n'a été effectué.

Les opérations sont pilotées par Desktop Commander sur le poste Fedora .229, puis SSH vers .79. Cet accès opérateur ne donne aucun nouveau droit à Hermes. Aucun fichier KEYDB n'a été transféré.

## Source et destination observées

- Source : steve@192.168.1.229, Fedora ; dépôt /home/steve/OpenHTPC/github-openhtpc-rc2-integration.
- Destination : steve@192.168.1.79, hostname openhtpc-control, Fedora 44, KVM/Q35, Europe/Brussels, SSH actif, racine XFS/LVM 61,41 GiB.
- HEAD : 975402945376618db56e29945074ea30ddcd2cb8, branche feature/magnificence-sd-auto, VERSION 1.3.1.
- Le worktree source est volontairement dirty ; ses modifications et nouveaux fichiers ont été copiés, pas remplacés par un clone.
- Stashes conservés : c7e45ab9802980de417922754950a2c71fdb73aa et d900682dd6b734b7b11c35c064596a6e1948bae2. Aucun apply/drop.
- La note .git/OPENHTPC_STATE.md demeure historiquement stale ; les checkpoints 2026-10-10/11 et les preuves réelles sont plus récents. OPENHTPC_CURRENT_STATE.json reste STALE et ne donne aucune autorisation.

## Preuves de duplication

- Rsync dépôt : 7 115 fichiers réguliers, 13 219 605 863 octets transférés, exit 0 ; aucun delete. Verrous transitoires exclus.
- Manifest Git : 549 fichiers suivis/non ignorés vérifiés par SHA-256 ou cible symlink et modes ; zéro écart.
- HEAD, status porcelain initial et diff binaire identiques ; SHA-256 du diff : 509653ccc511e654ee64c60be293b5b5c5856b6ab830e8b12363b277fa2c5e18.
- Artifact OpenHTPC-1.3.1.tar.gz sur .79 : SHA-256 933ce9a780bfc901c8cb90ca72e7973da088b87e294d0c2bb0b73e2aa608837c, conforme à la preuve officielle.
- Preuves conservées dans /home/steve/.local/state/openhtpc-control-migration/20261011 : source-head, source-status, source-diff, source-stashes, source-worktree-manifest.json et worktree-verification.json. Ce dossier opérateur privé contient également des sauvegardes de bases ; il ne doit pas être publié.
- Les trois fichiers de continuité/roadmap modifiés par ce jalon sur .79 constituent un delta documentaire intentionnel postérieur à cette vérification. Aucun retour de synchronisation vers .229 n'a été effectué.

## Acteurs : établi et restant

| Acteur | État établi sur .79 | Limite |
| --- | --- | --- |
| Codex CLI | Binaire exact 0.162.1, configuration copiée, login status « Logged in using ChatGPT » | Appel modèle et session interactive non testés |
| AGY | Binaire exact 1.2.14, configuration et credential copiés par SSH privé | Appel modèle et authentification distante non prouvés |
| CodeGraph MCP | Package exact 0.20.1, moteur natif et modèle static copiés, config Codex conservée | Node.js absent : lancement et réindexation non testés ; index vivant .229 non copié |
| Historiques Codex/AGY | Sessions, cerveau AGY et 70 sauvegardes SQLite cohérentes copiés | Pas de synchronisation permanente ; ne pas faire diverger les deux worktrees sans nouveau relevé |
| Hermes/DeepSeek/OpenRouter | SSH opérateur .79 → Tower réussi, conteneur hermes-agent running | Aucun nouvel audit, configuration inchangée ; MCP persistant Hermes→CodeGraph toujours NOT_ESTABLISHED |
| Autopilot du dépôt | Doctor local détecte Python, Codex, AGY, fichiers/schémas/prompts | Exit 1 attendu : canonical_state_applicable=False et worktree DIRTY ; aucune action Autopilot lancée |
| Validateurs physiques | Identités opérateur copiées sous .ssh, accès Hermes effectivement testé | Tentative SSH .79→.67 : exit 255, « No route to host » ; disponibilité de .67 non établie. Autres validateurs non testés ; aucune lecture physique ni déploiement |

Les données d'authentification ont été transférées uniquement dans le compte steve de la VM, avec fichiers sensibles 0600 ; jamais affichées dans la conversation ou copiées dans Hermes. Ni serveur Codex local, ni daemons, ni services de lecture/Flex, ni configuration matérielle salon n'ont été clonés.

## Blocage concret et prochaine action

sudo -n true sur .79 exige un mot de passe. L'agent n'a pas ce mot de passe et n'a pas changé sudoers. Node.js et pytest sont absents. Steve doit exécuter dans son terminal .79 :

```bash
sudo dnf install -y nodejs22-bin nodejs22-npm-bin python3-pytest
```

Ces paquets correspondent à la famille installée sur .229 (Node 22.23.1/npm 10.9.8 observés ; version effective .79 à relever après transaction). Python .79 est déjà 3.14.8, contre 3.14.6 sur .229 ; aucune rétrogradation imposée.

Après cette étape : vérifier versions, réindexer CodeGraph dans un nouvel index local .79, tester sa connexion MCP, effectuer les smokes réseau Codex/AGY et un gate Autopilot hermétique. Ne pas corriger ni contourner le gate STALE. Documenter les preuves avant décision de bascule.

## Retour au .229

Aucune désactivation ni suppression de Codex/AGY/CodeGraph ou du dépôt .229. Aucun service source arrêté. L'état HEAD/status/diff source a été revérifié identique au relevé initial ; Flex salon a été observé actif. En cas d'échec, continuer sur .229 ; .79 reste une copie de travail. Aucune bascule n'est établie à ce jalon.

## Vérification finale avant intervention sudo

Les SHA-256 des trois exécutables transférés (Codex, AGY, moteur CodeGraph) correspondent aux exécutables source ; fichiers d’authentification contrôlés 0600. `git diff --check` sur .79 PASS. Source .229 : status et diff revérifiés sans écart. Espace libre .79 : environ 44 Go. AGY `mcp list` confirme zéro serveur configuré, comme sur la source ; aucune nouvelle connexion AGY→CodeGraph inventée. `codegraph-mcp --help` échoue concrètement car `node` est absent.

Contrôle complémentaire .229→.67 : SSH timeout, exit 255. .67 est donc également non joignable depuis la source au moment du test ; cela ne prouve pas une régression de routage propre à la VM. Cause non établie.
