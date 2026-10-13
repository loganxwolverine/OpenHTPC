--- a/docs/OPENHTPC_ACTORS.md
+++ b/docs/OPENHTPC_ACTORS.md
@@ -19,7 +19,7 @@
 
 ## Hôte de contrôle et Hermes — vérifié le 2026-10-11
 
-Codex, AGY et CodeGraph sont disponibles sur .79. Hermes Agent 0.21.6 y fonctionne désormais dans Docker avec ses historiques et rapports ; DeepSeek reste distant via OpenRouter. Le conteneur Unraid .10 est arrêté/secours. Les audits OPENHTPC passent par un conteneur one-shot UID10000, snapshot read-only et SSH masqué. La voie ingénierie utilise une image dérivée locale, un HOME propre et un clone autonome sans remote ni autorité `.git` canonique. Voir docs/continuity/2026-10-11-hermes-migration-79.md et le checkpoint de handoff opérationnel.
+Codex, AGY et CodeGraph sont disponibles sur .79. Hermes Agent 0.21.6 y fonctionne désormais dans Docker avec ses historiques et rapports ; DeepSeek reste distant via OpenRouter. Le conteneur Unraid .10 est arrêté/secours. Les audits OPENHTPC passent par un conteneur one-shot UID10000, snapshot read-only et SSH masqué. Depuis le 2026-10-13, le gateway de Hermes dispose en outre d'un **canal de lecture seule vers le dépôt canonique** (identité SSH dédiée, commande forcée, opérations `status|digest|export|bundle|artifacts`, plus le dépôt de documents `.md` neufs : aucune écriture dans l'arbre existant, aucun `.git` mutable, ni push ni fetch) ; il sert à *vérifier* et à tirer une base fraîche, jamais à travailler. La voie ingénierie utilise une image dérivée locale, un HOME propre et un clone autonome sans remote ni autorité `.git` canonique. Voir docs/continuity/2026-10-11-hermes-migration-79.md et le checkpoint de handoff opérationnel.
 
 ## Matrice des responsabilités et permissions
 
@@ -32,7 +32,7 @@
 | Codex CLI | Agent d'exécution principal | Analyse, CodeGraph, implémentation, tests, diagnostic et opérations Git bornées | Oui | Oui, dans le périmètre mandaté | Oui | Inspection ; commit/push/merge seulement si explicitement autorisés | Seulement sur autorisation explicite et après prévol | Technique déléguée, pas produit | Service OpenAI, `AGENTS.md`, outils locaux/MCP, CodeGraph |
 | AGY / Google Antigravity CLI | Agent planner/reviewer | Planifier et relire les tâches Autopilot en mode headless borné | Oui, en lecture seule | Non dans le contrat Autopilot | Analyse des preuves, pas exécution libre | Non | Non | Avis borné soumis à la politique | Exécutable `agy`, authentification Google externe, schémas Autopilot |
 | CodeGraph | Outil d'analyse structurelle | Callers/callees, dépendances, chemins d'appel, blast radius, tests associés | Index structurel | Non | Identifie les tests ; ne les exécute pas comme autorité | Non | Non | Aucune | Index local/MCP ; snapshot dédié lorsqu'utilisé par Hermes |
-| Hermes Agent | Second ingénieur + auditeur externe | Reprendre un chantier borné dans un clone isolé ; contre-audit adversarial séparé | Snapshot audit ou clone ingénierie | Oui dans le clone isolé ; **jamais directement sur le canonique** | Oui dans l'image ingénierie | Branche/commit local isolé ; aucun remote ni `.git` canonique | **Non** sans mandat séparé | Technique déléguée, jamais finale | Conteneurs isolés, skills projet, CodeGraph local au clone, modèle DeepSeek via OpenRouter |
+| Hermes Agent | Second ingénieur + auditeur externe | Reprendre un chantier borné dans un clone isolé ; contre-audit adversarial séparé | Snapshot audit, clone ingénierie, ou canal lecture seule vers le canonique (opérations bornées, sans écriture dans l'arbre) | Oui dans le clone isolé ; **jamais directement sur le canonique** | Oui dans l'image ingénierie | Branche/commit local isolé ; aucun remote ni `.git` canonique | **Non** sans mandat séparé | Technique déléguée, jamais finale | Conteneurs isolés, skills projet, CodeGraph local au clone, modèle DeepSeek via OpenRouter |
 | DeepSeek | Modèle | Moteur d'analyse actuellement sélectionné pour Hermes | Via le contexte Hermes | Non par lui-même | Non par lui-même | Non | Non | Aucune | Hermes Agent et fournisseur OpenRouter |
 | OpenRouter | Fournisseur / routeur de modèles | Acheminer l'accès au modèle DeepSeek pour Hermes | Non | Non | Non | Non | Non | Aucune | Configuration/identifiants externes au dépôt |
 | OPENHTPC Autopilot | Orchestrateur Python local | Enchaîner plan AGY, politique déterministe, exécution Codex, review et gates | Oui | État de run borné ; modifications via Codex | Valide les preuves déclarées | Peut accepter un **commit local** uniquement selon politique ; jamais push | Jamais automatique | Politique/gate, pas autorité produit | `agy`, `codex`, schémas/prompts, état canonique applicable |
@@ -87,7 +87,7 @@
                               validation humaine → intégration autorisée
 ```
 
-AGY et Hermes ne sont pas exigés pour chaque petite modification. Hermes reste hors du chemin de commit Autopilot. Sa voie audit reçoit un snapshot techniquement immuable ; sa voie ingénierie reçoit un clone autonome sans remote.
+AGY et Hermes ne sont pas exigés pour chaque petite modification. Hermes reste hors du chemin de commit Autopilot. Sa voie audit reçoit un snapshot techniquement immuable ; sa voie ingénierie reçoit un clone autonome sans remote. Depuis le 2026-10-13, elle lit aussi le canonique par un canal SSH de lecture seule (opérations bornées, sans écriture dans l'arbre existant, sans push ni commit) : cela étend sa **lecture**, jamais son autorité.
 
 ### Décision produit ou UX
 
--- a/docs/OPENHTPC_HERMES_AUDITOR.md
+++ b/docs/OPENHTPC_HERMES_AUDITOR.md
@@ -83,10 +83,38 @@
 
 The snapshot in the active .79 data volume is owned by root and exposed 0555 for directories / 0444 for files. Hermes runs as UID 10000. A write-attempt test must fail before an audit is accepted as isolated.
 
-One-shot `-z` auto-bypasses approval prompts and is therefore NOT a safety boundary. Initial audits explicitly restrict Hermes to the `terminal` toolset and rely on OS permissions plus container isolation. No Docker socket, Fedora filesystem, OPENHTPC runtime path, SSH private key, deployment credential, or canonical repository is mounted into Hermes.
+One-shot `-z` auto-bypasses approval prompts and is therefore NOT a safety boundary. Initial audits explicitly restrict Hermes to the `terminal` toolset and rely on OS permissions plus container isolation. No Docker socket, Fedora filesystem, OPENHTPC runtime path, SSH private key, deployment credential, or canonical repository is mounted into Hermes. Since 2026-10-13 the canonical repository is nevertheless reachable from the *gateway* through a separate read-only forced-command channel (documented below): nothing is mounted and no write, Git or deployment authority is granted, but the sentence above must no longer be read as "Hermes has no access to the canonical repository".
 
 Reports are captured outside the read-only snapshot under `/opt/data/reports/` (host: /home/steve/.local/share/hermes-agent/reports/). A report must separate FACT / HYPOTHESIS / OPEN QUESTION and cite file:line evidence.
 
+## Read-only canonical channel — 2026-10-13
+
+The **gateway** (not the audit one-shot) holds a dedicated read-only channel to the canonical
+repository on `.79`, authorized by Steve on 2026-10-13. It exists so that verification and
+base-pulling measure the **real** state instead of a possibly stale audit copy — the failure mode
+it was created to remove.
+
+- Identity: dedicated key `~/.ssh/hermes_readonly_ed25519`, alias `canonical` -> `steve@192.168.1.79`,
+  forced command `/usr/local/bin/openhtpc-readonly.sh` with
+  `restrict,no-port-forwarding,no-agent-forwarding,no-pty,no-user-rc`.
+- Operations, exact and exhaustive: `status`, `digest`, `export`, `bundle`, `artifacts` — all
+  read to stdout and write nothing anywhere — plus `put <continuity|audits> <name>.md`, which
+  creates a **new** `.md` file in `docs/continuity/` or `docs/audits/` only; it refuses to
+  overwrite an existing file and refuses any other path or extension.
+- No Git authority: no `commit`, `push`, `fetch` or `merge`, and no mutable `.git`. Git runs with
+  `--no-optional-locks`; a read was verified to leave the index untouched (an ordinary
+  `git status` does rewrite it, which is why the flag is mandatory).
+- Refusals reproduced: `push`, `fetch`, `commit` and argument injection (`bundle --all`,
+  `artifacts;id`) are rejected — the whitelist accepts no arguments.
+- Exercised against the canonical repository on 2026-10-13: `bundle` produced a complete-history
+  bundle of 51 references (`git bundle verify`: "records a complete history", stashes included);
+  `artifacts` streamed the 1.3.1 packages, whose SHA-256 for
+  `OpenHTPC-1.3.1-Patina-PalScope.tar.gz` matched the build report independently
+  (`80edb1552f664f28db83e4a741d80cbe75f873ec0c6eed94ab2ba83ee77c1481`).
+- Authority: this extends Hermes **reading** only. The responsibility matrix in
+  `OPENHTPC_ACTORS.md` is unchanged for writing, Git, deployment and product authority.
+  Revocation is a single line: remove the `authorized_keys` entry on `.79`.
+
 ## Invocation pattern
 On .79, after preparing an immutable snapshot:
 ~~~sh
