# OPENHTPC — transmission après publication RC2 et décisions roadmap (2026-10-18)

**Statut : documentation de reprise en cours, sans implémentation produit.** Ce checkpoint remplace les anciens « prochains pas » pour la reprise, mais conserve les historiques et les preuves. **Provenance :** dépôt réel `.79` et qualification/release documentées ; les quatre demandes de backlog sont celles de Steve dans la conversation courante. Aucune conversation ChatGPT n'est déplacée automatiquement dans un Projet par cette écriture.

## Vérité opérationnelle vérifiée

- Contrôle : `openhtpc-control` / `192.168.1.79` ; dépôt `/home/steve/OpenHTPC/github-openhtpc-rc2-integration` ; branche `feature/magnificence-sd-auto` ; HEAD `1764b8e77c5bd591bd163d3d1bdab1e36ea277ae` ; `VERSION=1.3.2-rc2`.
- Release GitHub **publique en préversion** : https://github.com/loganxwolverine/OpenHTPC/releases/tag/v1.3.2-rc2 ; tag annoté `v1.3.2-rc2` → HEAD exact. Trois fichiers : `OpenHTPC-1.3.2-RC2.tar.gz`, `.tar.gz.sha256` et `-report.json` ; GitHub confirme le SHA-256 de l'archive `abc8bd96bfa06c9e172fab26a0402846684f268b3c4e59f86e422ab956791ec1`. RC2 **n'est PAS** une version stable finale.
- Validation logiciel RC2 : **2414 PASS / 12 FAIL identiques à la RC1 / 23 SKIP** ; FAIL = tests KDE launcher sur `.79` (Fedora 44 sans Plasma). À ne pas réécrire comme une suite entièrement verte.
- Matériel `.59` = GEEKOM IT13 Max, Fedora 44 KDE/Wayland Intel Arc Meteor Lake `8086:7d55`. Purge ancienne 1.3.1, installation propre RC1 puis mise à jour RC1→RC2 avec configuration et réponses du Passport conservées. RC2 fonctionne, autostart actif, HOME et Flex uniques, Doctor `Overall READY`, cycle arrêt/KDE/relance qualifié. Steve a physiquement confirmé une **séance DVD intégrale sous RC2**, image et son corrects et retour Flex correct.
- Référence optique `.229` : V11 correctif testé physiquement avec `The Perfect Storm` avant RC2 ; ne pas toucher sans mandat. Validateur `.67` RX5700XT également historique.
- Limitation acceptée et mentionnée publiquement : le désinstallateur RC2 laisse **23 caches `.pyc` générés**, alors que les fichiers gérés sont retirés. Fix isolé expérimenté (11 tests + reproduction sur copie vraie), **non intégré** ; pas de RC3 uniquement pour cet effet. Menus DVD interactifs non promis ; attente MPV amont/Plugin `plugin.dvd-menu` distincte.
- Publication : tag poussé, assets publiés, mais **branche de développement distante non poussée** (diff historique de 21 commits au moment de la publication). Ne jamais déduire que `main` ou la branche distante contiennent le code de la RC2 ; le tag a sa propre autorité.
- À l'ouverture de ce checkpoint : deux stashes protégés `pre-sync stale RTX experiment 2026-10-02` et `RC7 T5 network deferred` ; quatre fichiers de continuité du 17/10 non suivis conservés. La documentation roadmap/continuity du présent handoff est modifiée localement **sans commit**, et doit donc être revue, validée et commitée sur autorisation séparée pour garantir sa présence au prochain clone.
- `OPENHTPC_CURRENT_STATE.json` décrit un vieux workstream P2/RC5/RC7 et est **STALE** par rapport à la RC2 ; ne pas l'utiliser pour donner un GO, ne pas changer son schéma opportunément.

## Acteurs : distinguer identité, capacités, permissions et rôle

- **Steve** : autorité produit, arbitrages UX, GO Git/physique, validation perceptuelle image/son.
- **ChatGPT** : cadrage, cohérence technique/produit, transmission, roadmap ; accès aux outils selon autorisation réelle, jamais autorité automatique.
- **Codex CLI** : ingénieur principal, code, tests, Git et preuves selon mandat ; **CodeGraph** est son outil MCP d'analyse structurelle.
- **AGY / Antigravity CLI** : planificateur/relecteur borné, notamment via Autopilot ; Autopilot = orchestrateur Python avec politique déterministe, pas un agent autonome autorisé à pousser/déployer.
- **Hermes Agent** sur `.79`, avec **DeepSeek** servi via **OpenRouter** : second ingénieur et auditeur contradictoire. Voie audit techniquement immuable/read-only distincte de la voie ingénierie isolée ou compte `hermes-eng`. Travail sur propre branche/worktree avec revue Codex ou Steve avant intégration ; aucune autorisation implicite sudo/push/tag/publication/déploiement.
- **Graphiphy** : acteur jugé important par Steve et **distinct de CodeGraph** ; capacité, installation, interface, accès et fonctions concrètes **non encore prouvés dans les fichiers canoniques**. Étude de raccordement oui, attribution de permissions présumées non.
- **Desktop Commander** : accès distant effectivement utilisé pour les dernières preuves .79→.59→GitHub ; sa ligne de rôle historique dans `docs/OPENHTPC_ACTORS.md` est datée et peut être actualisée après revue, pas utilisée pour inventer un mandat.
- Autres noms historiques : Gemini CLI, OpenAI, OpenRouter, skills projet ; aucun n'obtient des droits par mention dans un prompt.

Références : `AGENTS.md` ; `docs/OPENHTPC_ACTORS.md` ; `docs/OPENHTPC_HERMES_AUDITOR.md` ; `docs/OPENHTPC_AUTOPILOT_POLICY.md` ; `docs/OPENHTPC_MEDIA_ACTION_CONTRACT.md`.

## Nouvelles demandes Steve : QUATRE TRAVAUX FUTURS, PAS ENCORE CODÉS

1. **MEDIA** : abandon de la liste horizontale au profit de jaquettes/icônes plus larges en grille ; « Changer l'identification » par clic droit/appui long dans un menu contextuel ; pour les médias non identifiés, icône générique + action contextuelle « Identifier ». Prévoir voie équivalente télécommande/clavier, focus et préservation des identités et de la base TMDb.
2. **INSTALLATION** : proposer explicitement soit saisie habituelle du mot de passe, soit autologin KDE/OPENHTPC. Choix volontaire, expliqué et réversible ; préserver sudo et sécurité des autres comptes. Gestionnaires KDE/Fedora à auditer avant choix technique, aucune configuration changée.
3. **MAGNIFICENCE FULL HD/BLU-RAY** : continuer simultanément DVD/SD et créer une étude distincte 1080p/HD haute résolution (Blu-ray et films proches). Comparer PURE et recettes adaptées par GPU/source/sortie, tests perceptuels + télémétrie, pas de transposition automatique de l'upscaling SD, aucun empiètement sur la frontière `plugin.bluray`/Core ni KEYDB.
4. **HOME / RÉSEAU** : revenir au témoin réseau en bas à droite de Flex, discret mais visible, avec IP locale ; distinguer connexion LAN, déconnexion, inconnu, et ne pas prétendre prouver Internet. Multiconnexions, IPv4/IPv6, mises à jour sans blocage. Ne jamais modifier réseau Fedora.

Ces demandes figurent dans `OPENHTPC-ROADMAP.md` (statut prévu) ; la recherche haute résolution également dans `OPENHTPC-MAGNIFICENCE-ROADMAP.md`. Aucune priorité relative n'a été imposée par Steve.

## Autres chantiers déjà présents, à ne pas perdre

- `plugin.dvd-menu` futur premier plugin installable : dépend d'un contrat d'action média `iact_` borné, d'une installation first-party transactionnelle et de disponibilité effective MPV/libdvdnav. Ne pas affirmer qu'il est terminé ou que MPV stable permet déjà les menus DVD.
- Contrat d'action média `iact_` décidé/documenté mais **non implémenté** ; Core conserve l'autorité du dispatch, plugins déclaratifs.
- Magnificence exacts SD et protocole GPU/MPV : `OPENHTPC-MAGNIFICENCE-ROADMAP.md`, `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md`, `payload/assets/magnificence_profiles.json`. Ne pas modifier sans campagne ciblée et consentement. Distinction décodeur matériel observé/lié PCI physiquement prouvé.
- Correctif `.pyc` un jour en maintenance ; pas de modification de l'archive publiée sous le même tag ou SHA.
- Les roadmaps et qualifications historiques (Blu-ray/UHD protégés, 1.2.0, 1.3.0, 1.3.1, IT13, .229, .67, CodeGraph/Hermes, migration Unraid→.79) restent conservées.

## Reprise sans perte : protocole de la prochaine conversation

1. Examiner ce checkpoint puis `AGENTS.md`, `docs/OPENHTPC_CONTINUITY.md`, `OPENHTPC-ROADMAP.md`, `OPENHTPC-MAGNIFICENCE-ROADMAP.md`, `docs/OPENHTPC_ACTORS.md` et les documents spécialisés cités ; ne pas utiliser seulement le transcript.
2. Vérifier en direct `hostname`, `git branch --show-current`, `git rev-parse HEAD`, `cat VERSION`, `git status --short`, `git stash list`, tag et publication ; détecter les écarts et les documenter sans écraser le plus récent.
3. Vérifier que les changements docs de ce handoff sont présents et s'ils sont commités ou seulement locaux. Ne pas les perdre lors d'un checkout, merge, reset ou de l'arrivée d'un autre agent. Ne pas toucher aux quatre documents non suivis historiques.
4. Restituer clairement ce qui est public, installé, logiciellement testé, physiquement qualifié, uniquement planifié et non prouvé. Préserver la validation RC2 actuelle.
5. Faire préciser l'ordre de priorité des quatre chantiers, puis sélectionner une seule tranche bien bornée, demander le mandat nécessaire, collaborer avec Codex/AGY/Hermes et vérifier la place de Graphiphy.
6. Ne jamais supposer qu'une tâche de documentation autorise automatiquement commit, push, tag, release, reboot, déploiement ou changement système. Sauvegarder et mettre à jour ce checkpoint et le journal de roadmap après chaque jalon.

### Conversations et rattachement ChatGPT

Conversations repérées par titre dans l'historique disponible : `Validation finale RC4`, `Conseil modèle OPENHTPC`, `OPENHTPC V4 terminé`, `Mandat de réconciliation OpenHTPC`, `Choisir l'agent approprié`, `Migration vers Unraid`, `Comparer DeepSeek Codex Hermes`, `Portage OPENHTPC Debian` et présente conversation RC2. **Liste indicative, pas inventaire exhaustif.** Le rattachement réel de chats au projet ChatGPT exige l'action UI « Déplacer vers le projet » par Steve ; écrire ce checkpoint n'exécute aucun déplacement.

## Provenance durable

Release et notes : https://github.com/loganxwolverine/OpenHTPC/releases/tag/v1.3.2-rc2

Journal de publication réel (.79) :
`/home/steve/.local/state/openhtpc-agent-watch/prerc-20261018/rc2-publication-kit-20261018/PUBLICATION_STATUS.md`.

Rapport de validation RC2 (.79) :
`/home/steve/.local/state/openhtpc-agent-watch/prerc-20261018/rc2-qualification-20261018/RC2_QUALIFICATION_HANDOFF.md`.

La sauvegarde des checkpoints et la documentation canonique réduisent la perte de contexte mais ne signifient ni une importation automatique de tous les messages ni une synchronisation des conversations ChatGPT.
