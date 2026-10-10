# OPENHTPC — Point de reprise entre conversations

Dernière consolidation : 2026-10-10, Europe/Brussels.
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
- Hermes/DeepSeek : audits lecture seule opérationnels.
- CodeGraph : raccordé à Codex sur Fedora ; exécution graph-only dans le snapshot Hermes R3 consignée comme réussie.
- Connexion MCP persistante Hermes → CodeGraph : NON ÉTABLIE ; la note R3 décrit un blocage de contrôle externe.
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

Les rapports stockés seulement sur Unraid ou les logs ignorés doivent être référencés par leur emplacement et sauvegardés selon le workflow du projet. Un lien seul ne protège pas contre l'effacement du fichier cible.
Ne jamais enregistrer de clés privées, tokens complets, mots de passe ou données de configuration sensibles dans ces documents.

## Obligation de transmission

À chaque jalon et avant de clôturer/transmettre un travail :
- actualiser les faits du point de reprise et la roadmap ;
- créer un checkpoint daté quand des résultats, décisions ou travaux nouveaux doivent survivre ;
- conserver les checkpoints précédents ; ne pas remplacer l'historique ;
- enregistrer branche/HEAD, modifications non commitées, preuves, blocages, autorisations et prochaine action ;
- indiquer ce qui est vérifié, consigné sans réexécution, installé, ou NOT_PROVEN ;
- si une interruption empêche cette consolidation, le dire explicitement à la reprise.

Hermes lecture seule n'écrit pas ces fichiers : son opérateur consolide le rapport.
Cette procédure réduit les pertes ; elle n'enregistre pas automatiquement toutes les conversations et ne recrée pas les informations passées qui n'ont jamais été sauvegardées.

## Phrase de reprise utilisable dans une nouvelle conversation

« Reprends OPENHTPC depuis le dépôt canonique /home/steve/OpenHTPC/github-openhtpc-rc2-integration. Lis AGENTS.md, docs/OPENHTPC_CONTINUITY.md, OPENHTPC-ROADMAP.md et le dernier checkpoint référencé. Vérifie leur fraîcheur contre le dépôt et les preuves réelles. Présente l'état retrouvé et les informations manquantes avant de poursuivre. »

Si l'agent n'a pas accès au dépôt, il doit demander ces fichiers et signaler l'absence d'accès ; ne pas reconstruire un état supposé depuis sa mémoire.
