--- a/docs/OPENHTPC_CONTINUITY.md
+++ b/docs/OPENHTPC_CONTINUITY.md
@@ -1,6 +1,6 @@
 # OPENHTPC — Point de reprise entre conversations
 
-Dernière consolidation : 2026-10-13, Europe/Brussels.
+Dernière consolidation : 2026-10-15, Europe/Brussels.
 But : reprendre le projet depuis les fichiers persistants, sans dépendre d'un prompt ou de la mémoire d'une conversation.
 
 ## Lecture obligatoire au démarrage
@@ -17,6 +17,10 @@
 Avant d'agir, énoncer brièvement : état retrouvé, travaux ouverts, preuves/limites, prochaine action autorisée.
 
 ## Dernier checkpoint opérationnel
+
+- [Hermes — sauvegarde d'état complète, découverte bundle/stash, essai IT13 — 2026-10-15](continuity/2026-10-15-continuite-sauvegarde-et-it13.md) : une sauvegarde d'état OPENHTPC exige **quatre** composantes (refs, entrées de stash au-delà de la première, reflogs, arbre non commité + index) ; `git bundle create --all` seul ne suffit pas et laisse `git stash list` vide après restauration. Restauration vérifiée localement (42 refs, 2 stashes, HEAD, arbre, état sale reproduits) ; transfert NAS en attente des identifiants. Les 59 entrées du worktree sont cartographiées et attribuées par chantier, le découpage A → B est démontré et testé, le protocole de l'essai physique IT13 est écrit, les trois décisions du contrat d'action média sont documentées. Aucun commit.
+
+- [Lot 2026-10-13 — rattrapage de référencement — 2026-10-15](continuity/2026-10-13-point-de-reprise.md) : **dix-neuf** documents de `docs/continuity/` n'étaient référencés nulle part ; ils le sont désormais depuis ce point. Le lot couvre : le correctif de portée PAL et son point de reprise (`2026-10-13-magnificence-pal-source-scope-fix.md`, `2026-10-13-point-de-reprise.md`), la préparation de version et la reprise de version (`2026-10-13-release-readiness-131.md`, `2026-10-13-milestone-verified-version.md`, `2026-10-13-release-build-runbook.md`), l'accès et le mandat Hermes (`2026-10-13-hermes-access-model.md`, `2026-10-13-mandate-hermes-capabilities.md`, `2026-10-13-execution-du-mandat-hermes.md`), la gouvernance (`2026-10-13-actors-auditor-alignment.md` et `2026-10-13-actors-auditor-alignment.patch.md`), les états machine (`2026-10-13-current-state-schema-proposal.md`, `2026-10-13-current-state-schema2-draft.md`), les dispositions de findings et les décisions déléguées (`2026-10-13-openhtpc-findings-dispositions.md`, `2026-10-13-decisions-deleguees-magnificence.md`), et le travail du soir sur `.59` (`2026-10-13-ergonomie-section-config-extensions.md`, `2026-10-13-ergonomie-section-config-extensions-c2.md`, `2026-10-13-soir-fin-de-journee-ergonomie-et-59.md`, `ergonomie-config-extensions.patch.md`, `ergonomie-config-garde-test.patch.md`).
 
 - [Hermes — accès ingénierie canonique direct — 2026-10-13](continuity/2026-10-13-hermes-direct-engineering-access.md) : Steve remplace explicitement la restriction clone-only pour une voie distincte `hermes-eng`. Compte SSH, ACL canonique, Git et toolchain vérifiés depuis le conteneur Hermes ; 5 tests PASS, `openhtpc-devctl --help` PASS et build Flex PASS. Aucun sudo, groupe Docker, push, tag, déploiement ou autorité physique/produit. Codex ou Steve relit tout changement Hermes ; la voie audit immuable reste séparée.
 
@@ -60,6 +64,12 @@
 - Aucun nouveau PASS physique, déploiement, commit ou release n'est établi par sa création.
 
 ## État consolidé initial — à actualiser à chaque jalon
+
+- 2026-10-15 — état mesuré : branche `feature/magnificence-sd-auto`, HEAD `312ceb8`, VERSION `1.3.1`, arbre `19541911…` (59 entrées non commitées, index vide). Sept commits ont été posés le 2026-10-13 ; le distant reste en retard de huit commits et rien n'est publié.
+- 2026-10-15 — travail non commité à connaître : la tranche « framework plugins / page Système → Extensions » (dix-huit entrées, travail de Codex) **et**, par-dessus, le correctif d'ergonomie de la page Extensions avec sa garde (deux hunks, Hermes). Le second ne peut pas être commité avant le premier : la page n'existe pas à HEAD.
+- 2026-10-15 — Magnificence / IT13 : profil exact `8086:7d55` installé et software-verified sur `.59`, **non physiquement qualifié** ; l'essai de lecture post-installation est armé, pas encore déclenché. L'endurance film complet reste un test distinct.
+- 2026-10-15 — contrat d'action média : les trois décisions de conception sont documentées ; le canal des actions de candidat (`iact_`) est retenu, les deux décisions techniques sont tranchées par Hermes. Aucune implémentation n'est commencée.
+
 
 - Base : 1.3.0 Patina, HEAD 6cdaef7 lors du relevé ; worktree 1.3.1 non commité.
 - Travaux ouverts : stabilisation MEDIA/Flex, recherche manuelle, récupération update, waitpid/EINTR, et rejet de l'ancien état P2 par Autopilot.
--- a/OPENHTPC-ROADMAP.md
+++ b/OPENHTPC-ROADMAP.md
@@ -1,6 +1,6 @@
 # OPENHTPC — Roadmap globale
 
-Dernière mise à jour : 2026-10-13 (Europe/Brussels).
+Dernière mise à jour : 2026-10-15 (Europe/Brussels).
 Responsable des décisions et validations physiques : Steve Dehanne.
 
 ## Rôle et autorité
@@ -17,6 +17,15 @@
 - Le changelog décrit 1.3.0 Patina. Cela ne prouve pas à lui seul une publication publique.
 - Travaux 1.3.1 présents dans le worktree, non commité au relevé : stabilisation du cycle MEDIA/Flex, récupération après échec/interruption de mise à jour, recherche manuelle et couverture comportementale.
 - Écart documentaire : `OPENHTPC_CURRENT_STATE.json` porte encore le workstream P2, une phase RC5 et un candidat RC7. Il ne décrit pas le jalon Patina ni les travaux 1.3.1. Sa réconciliation est à traiter avec le propriétaire du workstream et le schéma strict ; aucune autorisation ne doit être déduite de cette roadmap pour contourner ses gates.
+
+## Point de situation au 2026-10-15 (mesuré, pas déduit)
+
+- Base Git relevée : branche `feature/magnificence-sd-auto`, HEAD `312ceb84eac7764ec360d6d52a628e64734206f4`, VERSION `1.3.1`. Empreinte d'arbre `19541911ee828c2d675956a99c5c4b46176cc10aefaece7cf41d96f9af11f82a`.
+- Écart avec la ligne « Point de situation vérifié » ci-dessus : celle-ci décrit l'état **à la création de la roadmap** (HEAD `6cdaef7`, nommage 1.3.0). Elle n'est pas fausse, elle est historique ; c'est ce paragraphe qui décrit l'état courant.
+- Worktree : 59 entrées non commitées, index **vide**. Deux chantiers s'y superposent dans les mêmes fichiers (tranche Extensions, puis correctif d'ergonomie), ce qui impose un ordre de commit.
+- Distant `origin` : huit commits en retard, zéro en avance. Rien n'est publié. La sauvegarde hors machine est donc la seule protection de l'historique.
+- Machines : `.79` héberge le dépôt canonique ; `.59` (IT13 Max) porte l'installation 1.3.1, Doctor READY, profil IT13 exact en place, DVD PAL « Alexander » dans le lecteur.
+- Référencement : dix-neuf documents de `docs/continuity/` du 2026-10-13 n'étaient référencés nulle part ; ils le sont depuis ce jour (voir le point de reprise).
 
 ## Jalons et chantiers
 
@@ -40,6 +49,8 @@
 | Acteurs et orchestration | Documentation canonique créée | Matrice Steve/ChatGPT/Codex/AGY/CodeGraph/Hermes/DeepSeek/OpenRouter/Autopilot ; Graphiphy et Desktop Commander marqués `ROLE À CLARIFIER` faute de preuve locale | Maintenir lors de tout changement réel de rôle, permission ou fournisseur |
 | GPU legacy / Pascal P2000 | Différé | Pas de profil P2000 promu ; limites pilote/plateforme documentées | Qualification sur plateforme PCIe stable, sans modifier les pilotes Fedora |
 | Restauration dépendant de la source | Exploration future | Bruit MPEG-2, sources difficiles ; ne remplace pas les recettes actuelles | Définir une tranche et une qualification séparées |
+| Sauvegarde d'état et continuité | Outillage écrit, restauration vérifiée localement ; transfert NAS **en attente** | Refus mesuré : `git bundle create --all` ne conserve pas les stashes au-delà du premier et ne transporte aucun reflog ; l'arbre non commité et l'index sont nécessaires à la reproductibilité | Transférer vers le NAS, relire chaque fichier, rapatrier et restaurer depuis les octets du NAS ; voir `docs/continuity/2026-10-15-continuite-sauvegarde-et-it13.md` |
+| Contrat générique d'action média bornée | Décisions prises, **aucune implémentation** | Trois décisions documentées : canal `iact_` retenu ; `origin = UI \| plugin:<id>` écrit par Core sans affichage ; pas de garde `manifest_generation` décorative au dispatch tant que `expected_revision` et le remplacement atomique couvrent le besoin | Première tâche Core bornée, après clôture de la tranche en cours ; voir `docs/OPENHTPC_MEDIA_ACTION_CONTRACT.md` |
 
 ## Points à examiner, sans décision automatique
 
@@ -89,6 +100,12 @@
 
 | Date | Événement / décision | État et preuve |
 | --- | --- | --- |
+| 2026-10-15 | Sauvegarde d'état : `git bundle --all` déclaré insuffisant | Mesuré : `stash@{1}` absent du bundle et reflogs non transportés, donc `git stash list` vide après restauration. Recette à quatre composantes écrite ; sauvegarde de 245 Mio préparée et **restauration vérifiée** dans un bac à sable (42 refs, 2 stashes, HEAD, arbre, état sale reproduits). Transfert NAS non effectué (identifiants retirés) : le risque « disque unique » n'est pas levé. Aucun commit. Voir `docs/continuity/2026-10-15-continuite-sauvegarde-et-it13.md`. |
+| 2026-10-15 | Worktree 1.3.2 cartographié et découpage A → B démontré | Les 59 entrées sont attribuées : A = framework plugins et page Système → Extensions (18 entrées), B = correctif d'ergonomie de la page Extensions avec sa garde (2 hunks dans 2 fichiers partagés), C = Magnificence/IT13, gouvernance, continuité. Dépendance prouvée dans un bac à sable : B ne s'applique pas sans A. Tests mesurés : état A 172 passed/5 skipped, état B 173 passed/5 skipped. **Aucun commit.** Voir `docs/continuity/2026-10-15-plan-de-decoupage-commits.md`. |
+| 2026-10-15 | Contrat d'action média : trois décisions d'architecture prises | Canal des actions de candidat (`iact_`) retenu : le plugin contribue une action bornée, Core garde l'autorité du dispatch. `origin = UI \| plugin:<id>` enregistré par Core, non affiché. Aucune nouvelle garde `manifest_generation` au dispatch. Aucune implémentation commencée. Voir `docs/OPENHTPC_MEDIA_ACTION_CONTRACT.md` et `docs/audits/2026-10-15-media-action-3-decisions-hermes.md`. |
+| 2026-10-13 | Correctif de portée Magnificence PAL promu par Steve | `payload/openhtpc-playback-policy.py` restreint `DVD_PAL_FILM` à la géométrie PAL 625 lignes (`<= 576` → `== 576`), avec sa garde `tests/test_magnificence_source_scope_guard.py` (100 lignes). Commit `6b2046e`. Aucune conséquence sur les profils qualifiés. |
+| 2026-10-13 | Documents du 2026-10-13 et correction du diagnostic des états machine | Commits `87629d3` (accès, mandat, gouvernance, version, revue média), `8aff888` (les fichiers d'état sont **gelés par conception**, pas périmés), `7f988bc` (dispatch du canal d'action média et deux corrections d'hypothèses), `312ceb8` (point de reprise de fin de journée). Les identifiants NAS ont été retirés du conteneur à la fin de la journée. |
+| 2026-10-13 | `.59` réinstallé à neuf et ergonomie de la page Extensions corrigée (non commité) | `.59` purgé puis réinstallé sans sauvegarde sur le candidat worktree : Doctor READY, appliance RUNNING. Correctif d'ergonomie de `payload/openhtpc-ui.py` (+11 −8) et sa garde dans `tests/test_plugin_framework_generic_system.py` (+24), patchs déposés sous `docs/continuity/`. **Non commité** — il dépend de la tranche Extensions non commitée. |
 | 2026-10-13 | Steve autorise et installe la voie ingénierie canonique directe Hermes | Compte SSH `hermes-eng`, ACL `rwX`, identité Git dédiée et toolchain vérifiés depuis le conteneur Hermes. Branche/worktree, commit, amend et rebase temporaires PASS ; checkout partagé et stashes préservés. Sondes retirées, 5 tests PASS, devctl PASS, build Flex PASS. Aucun sudo, groupe Docker, push, tag, déploiement ou autorité physique/produit ; audit immuable séparé et revue Codex/Steve obligatoire. Voir checkpoint dédié. |
 | 2026-10-11 | Hermes promu second ingénieur opérationnel isolé | Image dérivée et lanceur borné créés ; snapshot dirty figé dans une baseline locale sans remote, skills canoniques read-only, secret OpenRouter minimal, CodeGraph task-local. Handoff réel exit 0 : six skills lues, index 232 fichiers/7 imports, 24 PASS/1 SKIP, build Flex PASS, export sans contamination du dirty. Audit immuable conservé ; aucun commit canonique, push, merge, déploiement ou publication. |
 | 2026-10-11 | Accès Hermes sans sudo manuel et audit contradictoire de la matrice GPU | Les lanceurs `.79` utilisent automatiquement le groupe Docker déjà accordé ; `hermes --version` 0.21.6 PASS depuis la session non rafraîchie. Aucun `sudoers` ou droit global ajouté. Rapport immuable importé sous `docs/audits/2026-10-11-magnificence-gpu-matrix-hermes.md` : huit recettes exactes corroborées, réserves C1–C7, aucune modification de preset ou promotion physique. |
