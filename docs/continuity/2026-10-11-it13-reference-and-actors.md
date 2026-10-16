# OPENHTPC — Référence IT13 Max et acteurs canoniques — 2026-10-11

Consolidation : 2026-10-11, Europe/Brussels.

## Autorité et prévol

- Dépôt : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`.
- Branche : `feature/magnificence-sd-auto` ; HEAD `975402945376618db56e29945074ea30ddcd2cb8`, 0 commit derrière / 1 devant l'amont au prévol.
- VERSION : `1.3.1`.
- Le worktree contenait déjà le chantier plugins/Système non commité ; toutes ses modifications ont été préservées.
- Stashes inchangés : `pre-sync stale RTX experiment 2026-10-02` et le stash protégé `RC7 T5 network deferred`.
- Autorisation : documentation et préparation du futur banc IT13 seulement. Aucun déploiement, commit, push, tag, merge, publication, changement de preset ou opération matérielle n'est autorisé ou réalisé.
- `OPENHTPC_CURRENT_STATE.json` reste **STALE** : son workstream P2/1.2.0 et ses gates RC5/RC7 ne représentent ni HEAD 1.3.1 ni le chantier actuel.

## Audit documentaire

Les noms `CURRENT_STATE.md`, `ARCHITECTURE.md`, `DECISIONS.md` et `KNOWN_ISSUES.md` n'existent pas dans ce dépôt. Leurs responsabilités sont déjà réparties entre :

- `OPENHTPC_CURRENT_STATE.json` pour l'état machine lorsqu'il est applicable — il ne l'est pas actuellement ;
- `AGENTS.md` et les architectures spécialisées pour les invariants ;
- `KNOWN_LIMITATIONS.md` pour les limitations, malgré son titre encore lié à 1.2.0 ;
- les roadmaps et checkpoints pour décisions, progression et preuves.

Aucun doublon générique n'a été créé. Les nouvelles sources canoniques sont reliées depuis `AGENTS.md`, `README.md`, la roadmap et la continuité.

Recherche des acteurs :

- AGY/Antigravity, Codex CLI, CodeGraph, Hermes, DeepSeek, OpenRouter et Autopilot ont des preuves explicites dans le dépôt ;
- ChatGPT reçoit le rôle de cadrage demandé par Steve, identifié comme décision opérateur et non comme permission technique implicite ;
- aucune occurrence probante de `Graphiphy` ni de `Desktop Commander` n'a été trouvée ; leurs rôles restent `ROLE À CLARIFIER` ;
- le runtime Autopilot appelle `agy`, pas `gemini`; `GEMINI.md` demeure une instruction historique/applicable à Antigravity, mais Gemini CLI n'est pas une dépendance runtime démontrée.

## CodeGraph

CodeGraph a été utilisé avant modification pour cartographier Magnificence :

- module payload : 58 fichiers, 894 fonctions indexées ;
- `_magnificence_choice` dans `openhtpc-playback-policy.py` est appelée directement par `resolve`, puis par `main` ;
- elle dépend de la classe de source, du GPU sélectionné, de la normalisation des identités, de la règle de famille et du baseline de capacités ;
- blast radius structurel annoncé : 2 impacts directs, risque `low` pour la fonction isolée ;
- CodeGraph n'a associé automatiquement aucun test à cette fonction, alors que la recherche textuelle établit les suites réelles `test_magnificence_policy.py` et `test_magnificence_static_auto.py` ; cette limite de graphe/dynamic loading est conservée ;
- `run_calibration_pass` est appelé par `calibrate_scope`, puis `run_calibration`, puis `main` et consomme MPV IPC, `vo-passes`, compteurs drops/delayed, fréquence et verdict de stabilité.

Aucun de ces chemins de code n'a été modifié dans cette intervention.

## Livrables

### Acteurs

`docs/OPENHTPC_ACTORS.md` devient la source canonique pour les rôles, permissions, fournisseurs et workflows. Sa matrice distingue explicitement humain, agent, modèle, fournisseur, orchestrateur et outil d'analyse. Steve reste l'autorité finale ; Hermes reste read-only sur snapshot isolé ; CodeGraph n'est pas une autorité ; OpenRouter n'est pas un agent ; DeepSeek n'est pas Hermes.

### Plateformes de référence

`docs/OPENHTPC_REFERENCE_PLATFORMS.md` crée le registre commun et une fiche `GEEKOM_IT13_MAX_ARC`. Seuls les faits fournis par Steve sont marqués `OPERATOR_DECLARED` : GEEKOM IT13 Max, Core Ultra 9 185H, Arc Xe-LPG intégré 8 Xe-Cores et 24 Go LPDDR5. IP, hostname, Fedora, kernel, Mesa, PCI, Vulkan, VAAPI, MPV, sortie et résultats restent `À MESURER`.

Le NiPoGi E3B / Ryzen 5 7530U / Vega 7 est enregistré comme comparateur demandé, également sans résultat inventé. Les profils A310/RX5700XT/HD630 et autres profils exacts existants restent inchangés.

### Protocole Magnificence

`docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md` formalise : environnement aligné, corpus et scènes, Pure → lissage → piqué → upscale → shaders individuels → combinaisons → Magnificence complet, métriques MPV/GPU, validation visuelle, cible indicative de 25 % de réserve, endurance et critères de promotion.

Budgets consignés : 24 fps 41,67 ms (cible réserve 31,25 ms), 25 fps 40 ms (30 ms), 60 fps 16,67 ms (12,50 ms). Rester juste sous le budget nominal ne qualifie pas un profil. `Alerte.mkv` reste une référence lorsqu'il est disponible, avec hash/scènes/timestamps à enregistrer sans distribuer le média.

## Incohérences et limites découvertes

1. `OPENHTPC_CURRENT_STATE.json` est incompatible avec HEAD/workstream et reste historique.
2. `.git/OPENHTPC_STATE.md` décrit encore le pré-commit 1.3.1 du 2026-10-09 ; les checkpoints suivis plus récents font autorité pour la reprise.
3. `KNOWN_LIMITATIONS.md` porte encore le titre OPENHTPC 1.2.0 ; son contenu n'a pas été réécrit sans audit de chaque limitation.
4. La roadmap globale avait encore la ligne plugins « non déployé » malgré le déploiement/retour physique `.229`; elle est corrigée dans ce lot.
5. `openhtpc-benchmark.py` contient des fallbacks d'identité/runtime historiques et `openhtpc-calibrate.py::_read_gpu_freq_mhz` parcourt `card1/card0`. Ces outils sont des briques diagnostiques, pas une autorité multi-GPU conforme tant que l'instrumentation n'est pas liée au PCI validé.
6. CodeGraph ne relie pas automatiquement les tests Magnificence chargés dynamiquement à `_magnificence_choice`; les suites associées doivent rester explicitement maintenues.
7. Graphiphy et Desktop Commander : `ROLE À CLARIFIER`.

## Roadmap IT13 — état

La roadmap contient désormais l'étape explicite `Qualification GEEKOM IT13 Max / Intel Arc Xe-LPG pour Magnificence Auto` avec les quatorze gates demandés : Fedora, hardware, Vulkan, VAAPI, gpu-next, Pure, shaders, Magnificence actuel, comparaisons A310/Vega 7, marge, classe éventuelle, film longue durée et intégration Auto éventuelle.

État : **PLANNED / DOCUMENTATION READY / HARDWARE RUNTIME NOT_PROVEN**. Aucun profil IT13, classe Magnificence ou résultat n'a été ajouté aux JSON runtime.

## Prochaine action autorisable

Lorsque Fedora sera réellement installé sur le IT13, commencer par une collecte read-only et remplir la fiche plateforme avec faits bruts/provenance. Toute installation OPENHTPC, benchmark physique ou modification des profils demandera alors un mandat explicite séparé. Le chantier plugins non commité reste par ailleurs ouvert à son prochain jalon générique de résolution des dépendances/Doctor.

## Vérifications documentaires

- CodeGraph : appels, dépendances et blast radius Magnificence inspectés avant modification ; aucune source runtime changée.
- Liens Markdown locaux des documents créés/modifiés : PASS.
- Recherche IT13/185H/Xe-LPG/NiPoGi/7530U/Vega 7 dans les deux JSON runtime Magnificence : aucune entrée, comme exigé.
- Contrôle des 14 gates IT13 dans la roadmap spécialisée : PASS.
- Régressions de sélection statique Magnificence : **40 PASS** (`test_magnificence_policy.py` + `test_magnificence_static_auto.py`).
- `git diff --check`, y compris les nouveaux fichiers non suivis vérifiés séparément : PASS.

## Fichiers de ce lot documentaire

Créés :

- `docs/OPENHTPC_ACTORS.md` ;
- `docs/OPENHTPC_REFERENCE_PLATFORMS.md` ;
- `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md` ;
- ce checkpoint.

Modifiés :

- `AGENTS.md` et `README.md` pour les points d'entrée ;
- `OPENHTPC-ROADMAP.md` ;
- `OPENHTPC-MAGNIFICENCE-ROADMAP.md` ;
- `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` ;
- `docs/OPENHTPC_CONTINUITY.md`.

Les modifications antérieures du chantier plugins/Système restent présentes et n'ont pas été écrasées. HEAD reste inchangé ; aucun commit, push, tag, merge, publication ou déploiement n'a été effectué.
