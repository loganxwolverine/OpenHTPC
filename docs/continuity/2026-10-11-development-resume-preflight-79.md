# OPENHTPC — Prévol de reprise du développement sur `.79` — 2026-10-11

Date : 2026-10-11, Europe/Brussels. Contrôles frais exécutés depuis `openhtpc-control`.

## Verdict et portée

**GO pour reprendre manuellement le développement OPENHTPC par Codex, exactement au chantier framework plugins laissé ouvert.**

Ce GO ne vaut ni qualification physique, ni autorisation de déploiement, commit, push, tag, publication ou release. Autopilot reste volontairement fermé par son gate déterministe ; le circuit utilisable est `Steve → Codex CLI → CodeGraph/outils → tests → rapport`, avec AGY et Hermes comme reviewers optionnels selon le risque.

## État produit retrouvé

- Hôte : `openhtpc-control`, `192.168.1.79/24`, Fedora 44, noyau `7.2.9-200.fc44.x86_64`.
- Dépôt : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`.
- Branche : `feature/magnificence-sd-auto`, un commit devant son remote.
- HEAD : `975402945376618db56e29945074ea30ddcd2cb8`.
- `VERSION` : `1.3.1`.
- Worktree : volontairement dirty ; les changements produit et documentaires retrouvés correspondent au checkpoint inventaire Système. Ils ont été préservés.
- Stashes préservés : `pre-sync stale RTX experiment 2026-10-02` et le stash protégé `RC7 T5 network deferred`.
- Artifact stable : `artifacts/OpenHTPC-1.3.1.tar.gz`, SHA-256 `933ce9a780bfc901c8cb90ca72e7973da088b87e294d0c2bb0b73e2aa608837c`, rapport lié au même HEAD. `sha256sum -c` depuis `artifacts/` et `tools/openhtpc-devctl verify` : PASS. Un premier `sha256sum -c` lancé depuis la racine avait échoué uniquement parce que le sidecar utilise un chemin relatif ; ce n'était pas un défaut de l'artifact.
- `OPENHTPC_CURRENT_STATE.json` décrit encore P2/1.2.0 RC5/RC7. Il est **STALE** face à HEAD/VERSION/workstream et n'autorise aucune action.

La tranche terminée reste : registre renforcé, `Système → Extensions`, projection générique de l'inventaire et rampe Système compacte à onze catégories. Le candidat dirty-worktree correspondant est `INSTALLED / SOFTWARE-VERIFIED` sur `.229`; Steve a qualifié physiquement la présentation sans scroll. Ce prévol n'a ni relu ni modifié l'installation `.229` et n'a pas contacté `.67`.

Restent ouverts : résolution générique des dépendances plugin/capability/system, vérité Doctor/capabilities commune, action média bornée et handler média générique. La prochaine tranche autorisée est la première de cette liste : une entrée de faits Core explicite, sans probe implicite dans le registre, réutilisable par Doctor et Système.

## Matrice des acteurs — preuves fraîches

| Acteur | Rôle | Emplacement | Test effectué | Résultat | Reprise manuelle |
| --- | --- | --- | --- | --- | --- |
| Codex CLI | Exécution technique | `.79`, `~/.local/bin/codex` | Mission éphémère/read-only : lire VERSION et appeler réellement CodeGraph | 0.162.1 ; `CODEX_CODEGRAPH_PREFLIGHT_OK`, VERSION 1.3.1 | Requis, **PASS** |
| CodeGraph | Graphe structurel | `.79`, MCP Codex / 0.20.1 | `codegraph_get_dependency_graph` sur `payload/openhtpc-plugin-registry.py` | Appel réel ; 7 dépendances directes | Requis pour le circuit retenu, **PASS** |
| AGY | Planner/reviewer borné | `.79`, `~/.local/bin/agy` | Prompt online sans outil, sandbox/plan/effort low | 1.3.3 ; `AGY_PREFLIGHT_OK` | Optionnel, **PASS** |
| Hermes Agent | Auditeur externe | Docker `.79`, conteneur `hermes-agent` | Version, gateway, inspect et process | 0.21.6 ; running ; `restart=unless-stopped`; volume persistant `/opt/data` | Optionnel, service **PASS** |
| DeepSeek | Modèle Hermes | Distant | Canary réel sans outil | `deepseek/deepseek-v4.1-flash`, réponse attendue | Optionnel, **PASS** |
| OpenRouter | Fournisseur Hermes | Distant | Même canary réel | Routage/provider réel réussi | Optionnel, **PASS** |
| Voie audit Hermes | Snapshot contradictoire read-only | `.79`, volume Hermes | Snapshot frais + test UID10000 ; tentative d'audit borné | Isolation **PASS** ; invocation avec code refusée par le contrôle de sécurité externe, donc audit frais end-to-end **NON ÉTABLI** | Optionnel, non bloquant pour Codex manuel |
| Hermes Unraid | Secours | `.10`, `Tower` | SSH read-only + état Docker | `running=false`, `restart=no`, conteneur conservé | Sécurité de bascule **PASS** |
| Autopilot | Orchestrateur local | dépôt `.79` | Doctor offline réel | exit 1 attendu : `git_status=DIRTY`, `canonical_state_applicable=False` | Mode Autopilot **FERMÉ**, non contourné |
| Desktop Commander | Relais externe | device `fedora` sur `.229` | Inventaire device + hostname/IP | Device `.229` online ; device direct `.79` **NON ÉTABLI** | Optionnel |
| Hermes → CodeGraph persistant | Connecteur direct | Aucun prouvé | Aucun test probant nouveau | **NON ÉTABLI** | Optionnel |
| Graphiphy | Rôle inconnu | Aucun emplacement prouvé | Aucun | **NON ÉTABLI** | Non requis |

La session Codex courante avait été ouverte avant l'ajout de `steve` au groupe Docker : `id` n'exposait pas encore ce groupe alors que `getent group docker` contient bien `steve`. Les probes Hermes ont été exécutés dans un sous-processus `sg docker`, sans changement système. Une nouvelle connexion utilisateur héritera normalement du groupe.

## Voie d'audit fraîche

Snapshot : `openhtpc-preflight-20261011T105147Z-9754029`.

- provenance : branche, HEAD, VERSION, dirty status, noms des stashes et patch tracked consignés dans `AUDIT_PROVENANCE.md` ;
- 676 fichiers ; `.git` et `artifacts/` exclus ;
- propriétaire/modes : `root:root`, dossiers 0555, fichiers 0444 ;
- tentative d'écriture UID/GID 10000 refusée ;
- `.git`, dépôt canonique, socket Docker et clés SSH absents ;
- `CapEff=0`, `NoNewPrivs=1` ;
- empreinte agrégée avant audit : `dbce03a80d96a75d8f40d9b3e1999f15e93c9072afcff1548ff2116ec13a3cd6`.

L'empreinte a été recalculée après les probes et la tentative refusée : elle reste strictement identique.

Le canary Hermes→OpenRouter→DeepSeek sans code a répondu `HERMES_DEEPSEEK_OPENROUTER_PREFLIGHT_OK`. L'appel suivant, qui aurait transmis le snapshot privé complet à OpenRouter malgré un prompt limité à trois fichiers, a été refusé par le contrôle de sécurité externe. Aucun contournement n'a été tenté. Il n'existe donc pas d'empreinte post-audit ni de rapport DeepSeek frais pour ce snapshot ; l'end-to-end est **NON ÉTABLI**, sans être une panne de la gateway ou du modèle.

## Build, tests et applicabilité

- dépendances présentes : Python 3.14.8, pytest 8.4.2, Node 22.23.1, npm 10.9.8, CMake 4.3.0, GCC 16.2.1, Ninja 1.13.2 ; SDL2, SDL2_image, SDL2_ttf et inih détectés par CMake ;
- gate ciblé inventaire/registre/About : **36 PASS, 1 SKIP** historique ;
- tests Autopilot : **85 PASS** ;
- build Flex Release propre sous `/tmp` : PASS, ELF x86-64 ; un warning préexistant signale le retour de `write()` ignoré dans `ui_action_trace_event` ;
- preuve récente réutilisée car même HEAD, même worktree produit et mêmes versions : gate applicable `.79` **2276 PASS, 23 SKIP**, puis test d'empreinte isolé PASS ;
- les 14 tests d'intégration KDE de `test_rc7_kde_launcher.py` restent non applicables à cette VM sans Plasma. L'absence KDE/Wayland ne bloque pas le développement logiciel ;
- image, son, lecture, GPU et matériel ne sont pas requalifiés par ce prévol et restent sous l'autorité de Steve sur les hôtes concernés.

## Point exact de reprise

Première mission Codex : définir et tester une structure de faits Core explicite et strictement typée qui résout les dépendances déclarées `plugins`, `capabilities` et `system_dependencies`, échoue fermé sur les entrées malformées, n'exécute aucun entrypoint et n'effectue aucun probe implicite dans le registre ; brancher ensuite la même vérité dans Doctor et la projection `Système → Extensions`, sans ouvrir encore le contrat d'action média.

Avant toute implémentation, CodeGraph doit cartographier les producteurs/consommateurs actuels du registre, de `_plugin_inventory` et des faits Doctor. La tranche doit rester hermétique et préserver la frontière P2 gelée.

## Interventions humaines restantes

- Aucune pour commencer la tranche manuelle Codex ci-dessus.
- Ouvrir une nouvelle session utilisateur sur `.79` pour hériter directement du groupe Docker est recommandé, mais `sg docker` constitue un chemin fonctionnel déjà vérifié.
- Une autorisation explicite et informée serait nécessaire pour transmettre ultérieurement un snapshot privé complet à DeepSeek/OpenRouter.
- Réauthentifier `gh` seulement si une opération GitHub privée est ensuite demandée ; cela n'autorise aucun push.
- Toute qualification image/son/lecture/matériel et tout déploiement restent des interventions séparées de Steve.

## Autorisations et mutations

Aucune fonctionnalité produit, installation `.229`/`.67`, stash, commit, push, tag, publication ou release n'a été modifié. Les seules écritures persistantes de ce prévol sont ce checkpoint, les liens de continuité/roadmap et le snapshot d'audit immuable. Les appels Codex/AGY/Hermes peuvent ajouter leur historique propre hors dépôt.
