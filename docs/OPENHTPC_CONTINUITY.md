# OPENHTPC — Point de reprise entre conversations

Dernière consolidation : 2026-10-13, Europe/Brussels.
But : reprendre le projet depuis les fichiers persistants, sans dépendre d'un prompt ou de la mémoire d'une conversation.

## Lecture obligatoire au démarrage

1. Lire AGENTS.md (limites et autorité).
2. Lire ce fichier.
3. Lire OPENHTPC-ROADMAP.md.
4. Lire le dernier checkpoint listé ci-dessous et les documents/preuves qu'il référence.
5. Vérifier le dépôt réel : branche, HEAD, status, stash, VERSION. Comparer aux relevés enregistrés.
6. Lire .git/OPENHTPC_STATE.md si accessible : une note plus récente doit être consolidée ici avant transmission.
7. Lire OPENHTPC_CURRENT_STATE.json en tenant compte de son applicabilité : un état STALE n'autorise rien.

Ne pas reprendre un état ancien si le code, les fichiers ou les gates ont évolué.
Avant d'agir, énoncer brièvement : état retrouvé, travaux ouverts, preuves/limites, prochaine action autorisée.

## Dernier checkpoint opérationnel

- [Hermes — accès ingénierie canonique direct — 2026-10-13](continuity/2026-10-13-hermes-direct-engineering-access.md) : Steve remplace explicitement la restriction clone-only pour une voie distincte `hermes-eng`. Compte SSH, ACL canonique, Git et toolchain vérifiés depuis le conteneur Hermes ; 5 tests PASS, `openhtpc-devctl --help` PASS et build Flex PASS. Aucun sudo, groupe Docker, push, tag, déploiement ou autorité physique/produit. Codex ou Steve relit tout changement Hermes ; la voie audit immuable reste séparée.

- [Continuité opérationnelle Codex ↔ Hermes — 2026-10-11](continuity/2026-10-11-codex-hermes-operational-handoff.md) : Hermes devient second ingénieur dans un clone isolé sans remote, tout en conservant sa voie d'audit immuable. Handoff réel PASS : mémoire canonique et six skills lues, CodeGraph MCP task-local interrogé, 24 tests PASS/1 SKIP, build Flex PASS, export inverse limité au delta Hermes. Aucun accès canonique direct, push, merge, déploiement ou secret général. Verdict borné : **HERMES HANDOFF READY**.

- [Hermes — matrice Magnificence et accès opérateur sans sudo manuel — 2026-10-11](continuity/2026-10-11-hermes-magnificence-matrix-and-operator-access.md) : les lanceurs Hermes utilisent automatiquement l'appartenance existante de `steve` au groupe Docker via `sg docker` lorsque la session ne l'a pas héritée ; `hermes --version` PASS sans sudo manuel. Aucun `sudoers` ni droit global ajouté. L'audit contradictoire de la matrice GPU est préservé : huit lignes essentiellement corroborées, RX 580 et politique familiale partiellement corroborées, findings C1–C7 ouverts sans modification de preset.

- [Priorité du plugin Navigation menus DVD — 2026-10-11](continuity/2026-10-11-dvd-menu-plugin-priority.md) : Steve désigne `plugin.dvd-menu` comme premier vrai plugin installable depuis OPENHTPC. Faisabilité conditionnelle : MPV stable 0.41 ne prend pas en charge les menus DVD ; MPV master les expose depuis la PR #18080 ciblée 0.42. Ordre fixé : action média bornée, installation first-party transactionnelle, gate runtime MPV/libdvdnav, implémentation puis qualification multi-disques. Veille MPV/Fedora obligatoire au moins mensuelle ; état initial `UPSTREAM_NO_DATE`, aucune date officielle ni paquet Fedora 0.42 observé. Documentation seulement, aucun runtime/preset/hôte modifié.

- [Extensions — prérequis optique externe et état prêt à tenter — 2026-10-11](continuity/2026-10-11-extensions-protected-optical-readiness.md) : la page ne présente plus tout manifest comme « installé ». `plugin.bluray` devient **Support optique avancé** ; Core corrige `NOT_CONFIGURED` en prérequis absent et la vue distingue fourni/local, détection automatique et `READY_TO_ATTEMPT`. Tests PASS. Delta borné installé sur `.59` après sauvegarde : Doctor READY, état absent correctement rendu, Magnificence inchangé. Aucun lien/téléchargement/exécution externe ; `.229` non modifié. Snapshot Hermes immuable vérifié, revue externe bloquée avant transmission faute d'autorisation OpenRouter explicite.

- [IT13 Max — Système figé et recette Magnificence installée — 2026-10-11](continuity/2026-10-11-it13-system-magnificence-deployment.md) : la rampe Système physiquement qualifiée sur `.229` a été reprise depuis ses payloads installés, puis combinée à un profil exact `8086:7d55` limité au DVD PAL→4K60. Candidat borné vérifié et mis à jour sur `.59` après snapshot : Doctor `READY`, onze entrées Système, `CINEMA_AUTO` résout `vaapi-copy + BWDIF + FSRCNNX-16 + Krig + Vibrance`. Aucun commit, push ou publication ; aucune nouvelle lecture physique post-installation.

- [Skill projet `openhtpc-mpv-rendering` — 2026-10-11](continuity/2026-10-11-openhtpc-mpv-rendering-skill.md) : référence procédurale créée sous `.agents/skills/` et validée par `quick_validate.py`. Elle sépare sources officielles, faits dépôt, expériences, observations opérateur et hypothèses ; couvre pipeline gpu-next/Vulkan/VAAPI, hooks/scalers/shaders, budgets 24/25/50/60 fps, A/B, plateformes et gate Magnificence Auto. Aucun preset, profil runtime, déploiement ou qualification physique modifié.

- [IT13 Max — essai ressources DVD avec candidat STRONG — 2026-10-11](continuity/2026-10-11-it13-strong-dvd-resource-test.md) : lecture réelle muette de 12 min sur l'installation 1.3.1, sans changement de profil. La voie directe a révélé l'incompatibilité BWDIF/VAAPI; la variante isolée `vaapi-copy` a exercé la chaîne complète avec zéro perte, rendu moyen 51,64 %, p95 21,20 ms/40 ms et package moyen 55,96 °C/p95 57 °C. Steve a assisté visuellement au résultat et valide la recette lourde : `OPERATOR_PHYSICALLY_QUALIFIED` pour ce DVD PAL et cette sortie 4K60. Bruit ventilateur, autres sources, film complet et intégration Auto restent ouverts.

- [IT13 Max — inventaire graphique et préparation Magnificence — 2026-10-11](continuity/2026-10-11-it13-magnificence-assessment.md) : iGPU Arc Meteor Lake `8086:7d55`, pile Fedora/MPV/Vulkan/VAAPI, sortie 4K60 et binding Vulkan vérifiés sur `.59`. La recette effective est le fallback prudent LIGHT/Krig, pas le profil A310. Audit Hermes/DeepSeek isolé terminé et dispositions indépendantes consignées; deux candidats et un protocole réfutable sont prêts, sans lecture ni changement de profil. Steve fige l'affichage Système installé 1.3.1/`9754029`. Prochaine action : fournir/identifier Alerte et une scène sombre, puis autoriser la campagne physique.

- [Framework plugins — résolution générique des dépendances — 2026-10-11](continuity/2026-10-11-plugin-dependency-resolution.md) : jalon logiciel complet non commité. Core adapte des faits persistés stricts, le registre résout plugins/capabilities/système et échoue fermé sur absent, invalide ou cycle ; Doctor et `Système → Extensions` consomment le même registre résolu et le même motif. 209 tests voisins PASS (8 SKIP), rendu 1080p inspecté, aucune installation ni qualification physique. Prochaine tranche : contrat générique d'action média bornée. Autopilot demeure fermé.

- [Prévol de reprise du développement sur `.79` — GO manuel — 2026-10-11](continuity/2026-10-11-development-resume-preflight-79.md) : contexte produit/dirty/stashes/artifact retrouvé ; Codex+CodeGraph, AGY, build/tests et Hermes→OpenRouter→DeepSeek vérifiés réellement. Autopilot reste fermé comme attendu sur l'état STALE/dirty. Snapshot d'audit frais techniquement isolé ; audit avec code refusé par le contrôle externe, donc end-to-end NON ÉTABLI et optionnel. Reprise exacte : faits Core de résolution des dépendances plugins, puis Doctor/Système.

- [Hermes Unraid → .79 : migration validée — 2026-10-11](continuity/2026-10-11-hermes-migration-79.md) : image exacte, parité intégrale, six bases intègres, gateway/CLI et DeepSeek/OpenRouter réels PASS, isolation et redémarrage PASS. Source .10 arrêtée/conservée ; lancement sur .79 : hermes.

- [Hermes Unraid → .79 : préparation historique, remplacée par la migration validée — 2026-10-11](continuity/2026-10-11-hermes-migration-79-preparation.md) : migration explicitement demandée ; source Unraid active, image/version et données inventoriées. Docker absent sur .79, transaction simulée ; intervention sudo nécessaire avant transfert cohérent et validation.
- [Contrôle `.79` : validation CLI/API/MCP, build et matrice finale — 2026-10-11](continuity/2026-10-11-control-migration-79-validation.md) : nouvelle machine de contrôle READY. Codex 0.162.1, AGY 1.3.3, CodeGraph MCP et Hermes→OpenRouter→DeepSeek PASS ; build Flex propre PASS ; 192 tests ciblés PASS ; gate applicable 2276 PASS/23 SKIP et test d'empreinte isolé PASS. Parité Git/stashes confirmée et `.229` intact. `gh` privé requiert une réauthentification propre ; Desktop Commander direct `.79` reste externe/optionnel.
- [Duplication contrôle `.229` → `.79`, étape initiale — 2026-10-11](continuity/2026-10-11-control-migration-79.md) : dépôt dirty/stashes/artifacts vérifiés, CLI et historiques copiés, accès opérateur Hermes testé. Node/pytest et smokes restent ouverts ; `.229` reste canonique/opérationnel, aucune bascule. Ce checkpoint existe uniquement sur la copie `.79` pour préserver la source.
- [Installation OPENHTPC 1.3.1 sur IT13 Max — 2026-10-11](continuity/2026-10-11-it13-installation-131.md) : installation explicitement autorisée depuis l'artifact officiel vérifié. Fedora 44/KDE/Wayland, Intel Arc MTL PCI `0000:00:02.0`, Vulkan/VAAPI et runtime `gpu-next` observés ; installateur PASS, Doctor READY, appliance RUNNING. Aucune qualification Magnificence, image/son ou lecture MPV encore établie.
- [Référence IT13 Max et acteurs canoniques — 2026-10-11](continuity/2026-10-11-it13-reference-and-actors.md) : documentation uniquement, aucun déploiement ni changement runtime. Registre des plateformes et protocole GPU/MPV/Magnificence créés ; IT13 et NiPoGi/Vega 7 restent `OPERATOR_DECLARED`/`À MESURER`. Matrice des acteurs créée ; Graphiphy et Desktop Commander restent `ROLE À CLARIFIER`. CodeGraph a cartographié le chemin Magnificence sans modification de code. Roadmaps et liens canoniques alignés.
- [Framework plugins — inventaire Système — 2026-10-11](continuity/2026-10-11-plugin-framework-system-inventory.md) : reprise validée depuis le commit/artifact 1.3.1 exact. Première tranche non commitée de l'étape 1 : registre renforcé, page générique `Système → Extensions` et rampe compacte à onze entrées. Candidat non officiel déployé sur `.229` après snapshot ; Doctor READY, session/Flex autoritaires et configuration à onze entrées vérifiés. Steve confirme physiquement les onze catégories sur une page sans scroll et un rendu harmonieux : jalon esthétique PHYSICALLY_QUALIFIED sur `.229`. Résolution des dépendances, Doctor commun, actions média et handlers restent ouverts. Aucun commit, push, tag ni publication.
- [Reprise / qualification 1.3.1 — 2026-10-10](continuity/2026-10-10-131-reprise-qualification.md) : gates `.67` RX5700XT et `.229` A310 fermés/physiquement qualifiés. Gate logiciel : 2284 PASS, 18 SKIP, 0 FAIL ; audit Hermes final terminé. Steve a autorisé l'identité stable, l'artifact et le commit 1.3.1 : commit créé, artifact exact-commit reconstruit avec Flex schema 2, verify/métadonnées/checksum/install-check PASS. Rapport et sidecar sous `artifacts/` font autorité pour commit/SHA. Aucun push, tag ni publication. Prochain chantier produit après gel : généralisation du framework plugins.
- [DVD / refresh / audio ordering — 2026-10-10](continuity/2026-10-10-dvd-refresh-audio-ordering.md) : cause finale, invariant modeset/settle → résolution/préparation audio → mpv, fallback PCM temporaire ; démarrage physique confirmé par Steve et restauration 60 Hz vérifiée.
- [DVD/audio/multi-GPU — 2026-10-10](continuity/2026-10-10-validator-131-dvd-audio-multigpu.md) : qualification DVD précédente, publication PCI→PCI et gate 378 PASS ; complète le checkpoint initial du 09/10.

## Checkpoint initial partagé

- [Note opérateur préservée](continuity/2026-10-09-operator-state.md) : copie de la note locale .git, capturée à l'heure UTC indiquée dans son en-tête.
- [Relevé Git](continuity/2026-10-09-git-observation.json) : branche, HEAD, VERSION, état dirty, stashes et empreinte de la note capturée.
- Ce checkpoint contient des résultats de tests CONSIGNÉS par l'opérateur ; ils n'ont pas été réexécutés lors de cette consolidation.
- Aucun nouveau PASS physique, déploiement, commit ou release n'est établi par sa création.

## État consolidé initial — à actualiser à chaque jalon

- Base : 1.3.0 Patina, HEAD 6cdaef7 lors du relevé ; worktree 1.3.1 non commité.
- Travaux ouverts : stabilisation MEDIA/Flex, recherche manuelle, récupération update, waitpid/EINTR, et rejet de l'ancien état P2 par Autopilot.
- Les validations logicielles consignées et leurs limites sont détaillées dans le checkpoint.
- Qualification physique et déploiement 1.3.1 : non établis dans le checkpoint.
- La lecture salon a été observée active dans une note précédente : revérifier son état avant toute opération, ne pas présumer qu'elle est toujours active ou terminée.
- Hermes/DeepSeek : audits lecture seule immuables, voie de second ingénieur isolé et voie directe `hermes-eng` opérationnelles. La voie directe écrit le canonique sur branche/worktree Hermes, sans sudo/Docker/déploiement, et exige une revue Codex ou Steve.
- CodeGraph : raccordé à Codex sur Fedora ; exécution graph-only dans le snapshot Hermes R3 consignée comme réussie.
- CodeGraph Hermes : MCP task-local de la voie ingénierie PROVEN sur un clone isolé ; aucune connexion à l'index canonique Codex. Le statut historique R3 concernait la voie audit et reste historique.
- AGY : installé ; connexion MCP CodeGraph absente lors de notre vérification. Disponibilité après expiration Gemini non prouvée.
- Autorisations : ne pas déduire commit/push/publication d'une tâche de documentation ou d'un avis d'audit.

## Mémoire commune à conserver

| Information | Où la conserver | Règle |
| --- | --- | --- |
| Progression et priorités | OPENHTPC-ROADMAP.md | Statut, preuve, suite et journal daté |
| Décisions et raisons | Journal de roadmap + document spécialisé | Conserver aussi les options rejetées et leur raison |
| Travail interrompu | Checkpoint daté sous docs/continuity/ | Réalisé / restant / fichiers / gates / autorisations |
| Résultats de tests | Checkpoint + référence au log réel | Commande, date, version/empreinte, résultat, limites ; pas de PASS inventé |
| Audits externes | docs/OPENHTPC_HERMES_AUDITOR.md + rapports | Snapshot, provenance, findings acceptés/rejetés/ouverts |
| État installé | Note de qualification distincte | Ne pas confondre dépôt et installation |
| Incidents | Document de chantier + checkpoint | Reproduction, cause prouvée ou hypothèse, correctifs essayés |
| Historique des versions | CHANGELOG.md | Ne pas confondre préparation et publication |
| Acteurs, permissions et fournisseurs | docs/OPENHTPC_ACTORS.md | Maintenir les rôles prouvés ; marquer les inconnues plutôt que les inventer |
| Plateformes GPU de référence | docs/OPENHTPC_REFERENCE_PLATFORMS.md | Séparer déclaré, observé, prouvé, qualifié et à mesurer |
| Méthode Magnificence | docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md | Mesures comparables + décision visuelle humaine avant promotion |

Les rapports locaux Hermes (désormais sur .79, source Unraid conservée) ou les logs ignorés doivent être référencés par leur emplacement et sauvegardés selon le workflow du projet. Un lien seul ne protège pas contre l'effacement du fichier cible.
Ne jamais enregistrer de clés privées, tokens complets, mots de passe ou données de configuration sensibles dans ces documents.

## Obligation de transmission

À chaque jalon et avant de clôturer/transmettre un travail :
- actualiser les faits du point de reprise et la roadmap ;
- créer un checkpoint daté quand des résultats, décisions ou travaux nouveaux doivent survivre ;
- conserver les checkpoints précédents ; ne pas remplacer l'historique ;
- enregistrer branche/HEAD, modifications non commitées, preuves, blocages, autorisations et prochaine action ;
- indiquer ce qui est vérifié, consigné sans réexécution, installé, ou NOT_PROVEN ;
- si une interruption empêche cette consolidation, le dire explicitement à la reprise.

Hermes audit ne les écrit pas. Hermes ingénierie peut les proposer dans son clone ;
Codex ou Steve revoit l'export avant toute consolidation canonique.
Cette procédure réduit les pertes ; elle n'enregistre pas automatiquement toutes les conversations et ne recrée pas les informations passées qui n'ont jamais été sauvegardées.

## Phrase de reprise utilisable dans une nouvelle conversation

« Reprends OPENHTPC depuis le dépôt canonique /home/steve/OpenHTPC/github-openhtpc-rc2-integration. Lis AGENTS.md, docs/OPENHTPC_CONTINUITY.md, OPENHTPC-ROADMAP.md et le dernier checkpoint référencé. Vérifie leur fraîcheur contre le dépôt et les preuves réelles. Présente l'état retrouvé et les informations manquantes avant de poursuivre. »

Si l'agent n'a pas accès au dépôt, il doit demander ces fichiers et signaler l'absence d'accès ; ne pas reconstruire un état supposé depuis sa mémoire.
