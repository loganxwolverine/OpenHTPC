# OPENHTPC — Contrôle .79 : validation logicielle (2026-10-11)
La duplication initiale et ses empreintes restent dans [le checkpoint initial](2026-10-11-control-migration-79.md). Ce jalon qualifie les outils de contrôle ; aucune qualification physique du lecteur n'est ajoutée.

Dernière contre-vérification : 2026-10-11, directement depuis `openhtpc-control` (`192.168.1.79`).

## Mandat et état
Steve a autorisé la migration par duplication avec .229 opérationnel comme secours. .79 est utilisable pour les prochains travaux CLI. La documentation de migration existe seulement sur .79 ; aucune synchronisation inverse du dépôt .229.
Branche feature/magnificence-sd-auto, HEAD 975402945376618db56e29945074ea30ddcd2cb8, VERSION 1.3.1. Dirty worktree et deux stashes protégés conservés. Aucun commit, push, déploiement produit ou exécution Autopilot.
Le state historique reste STALE ; la vieille note .git/OPENHTPC_STATE.md ne doit pas supplanter les checkpoints récents.

## Preuves
| Vérification | Résultat |
| --- | --- |
| Dépendances installées par Steve puis relues par SSH | Node 22.23.1, npm 10.9.8, pytest 8.4.2 ; Python .79 3.14.8 versus .229 3.14.6 |
| CLI | Codex 0.162.1 / AGY 1.3.3 sur `.79` ; AGY 1.2.14 sur `.229` |
| Production Autopilot doctor online | antigravity_online=True, codex_online=True ; heartbeat AGY plan / Codex read-only ephemeral |
| Garde de worktree avant/après les probes | require_workspace_unchanged PASS |
| CodeGraph reindex local | Exit 0, 228 fichiers, 6148 nœuds, 10769 arêtes à la contre-vérification ; requête de graphe réussie |
| Codex → CodeGraph MCP réel | codegraph_get_dependency_graph started/completed ; CODEGRAPH_MCP_OK, 14 dépendances directes de tools/autopilot/openhtpc_autopilot.py |
| Tests existants Autopilot | 85 PASS, 0 FAIL en 0,20 s à la contre-vérification : `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tools/autopilot/tests -p no:cacheprovider` |
| Gate | Doctor exit 1 attendu : canonical_state_applicable=False, worktree DIRTY ; aucun contournement |
| Build Flex propre `.79` | PASS dans `/tmp`, GCC 16.2.1, CMake 4.3.0, Ninja 1.13.2, SDL2/SDL2_image/SDL2_ttf/inih liés ; ELF x86-64 avec build-id |
| Tests ciblés build/migration | 192 PASS puis 6/6 PASS après installation PySide6/FFmpeg/DVD |
| Régression applicable `.79` | 2276 PASS, 23 SKIP, 1 test d'empreinte dépendant de l'ordre ; après restauration des artefacts ignorés, ce test isolé PASS. Les 14 cas de `test_rc7_kde_launcher.py` sont non applicables à la VM sans Plasma (11 échecs attendus, 3 skips lors du run exhaustif). |
| SSH .79 → salon .229 | PASS hostname fedora / utilisateur steve |
| SSH .79 → IT13 .59 | PASS hostname IT13Max / utilisateur steve |
| SSH .79 → Hermes .10 | PASS ; `Tower`, conteneur `hermes-agent` actif, Hermes 0.21.6 |
| Hermes → OpenRouter → DeepSeek | PASS contrôlé : réponse exacte `HERMES_OPENROUTER_DEEPSEEK_OK`, snapshot root-owned en lecture seule, aucun secret affiché |
| Codex → CodeGraph, contre-vérification | PASS : session éphémère/read-only, appel MCP réel terminé, 14 arêtes, réponse `CODEX_CODEGRAPH_MCP_OK` |
| AGY, contre-vérification | PASS : 1.3.3, sandbox, prompt sans outil, réponse `AGY_133_ONLINE_OK` |
| .67 | Injoignable depuis .79 et .229 ; cause non établie |
Preuves privées : ~/.local/state/openhtpc-control-migration/20261011/validation/autopilot-tests.log, codegraph-query.json/stderr, online-*-agy/codex.stdout/stderr, codex-codegraph.txt/stdout/stderr et validation-summary.json. Ne pas publier ces logs sans revue.
Le premier probe MCP artisanal supposait à tort symbol_search dans le profil graph ; le catalogue ne l'exposait pas. Le probe direct Codex a ensuite établi l'appel de dépendances réel. Un premier appel shell attendait stdin : timeout sans action ; appel corrigé avec stdin fermé, exit 0. Aucun correctif produit n'en a été déduit.

## État mesuré et matrice de migration

Destination : Fedora 44 x86_64, noyau 7.2.9, KVM/Q35, Intel Core 3 N350 (4 cœurs), 3,8 GiB de RAM, racine XFS 62 GiB dont 42 GiB libres. Source : Fedora 44 x86_64, noyau 7.1.8, i5-6500 (4 cœurs), 7,6 GiB de RAM, racine Btrfs 236 GiB dont 183 GiB libres. Les deux interfaces et routes ont été mesurées ; `.79` porte bien `192.168.1.79/24` et `.229` porte `192.168.1.229/24`.

| Composant | Présent `.229` | Présent `.79` | Version source | Version destination | Classe / action | Risque | Validation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Git / dépôt OPENHTPC | Oui | Oui | Git 2.55.0 | Git 2.56.0 | B — dépôt dirty et stashes préservés | Écrasement du travail local | Même branche/HEAD/remote ; diff hors docs de migration SHA-256 identique ; stashes identiques |
| Codex CLI | Oui | Oui | 0.162.1 | 0.162.1 | B — binaire/config/auth déjà migrés | Credential sensible | Chemin réel sous `~/.codex/packages/standalone`; login ChatGPT et requête online PASS |
| AGY | Oui | Oui | 1.2.14 | 1.3.3 | A/B — installé puis auto-mis à jour sur `.79` | Compatibilité de version | Login et prompt sandbox online PASS ; aucun MCP configuré des deux côtés |
| CodeGraph MCP | Oui | Oui | 0.20.1 | 0.20.1 | A/C — package propre, index local recréé | Index stale / modèle absent | 228 fichiers, 6148 nœuds, 10769 arêtes ; appel direct et Codex MCP PASS |
| Python / pytest | Oui | Oui | 3.14.6 / 8.4.2 | 3.14.8 / 8.4.2 | A — paquets Fedora | Faible | 85 tests Autopilot PASS |
| pip | Oui | Oui | 26.0.1 | 26.0.1 | A — paquet Fedora | Faible | Version et import Python vérifiés |
| Node / npm | Oui | Oui | 22.23.1 / 10.9.8 | 22.23.1 / 10.9.8 | A — paquets Fedora installés | Faible | Versions et CodeGraph PASS |
| Chaîne C/C++ | Oui | Oui | GCC 16.1.1, make 4.4.1, CMake 4.3.0 | GCC 16.2.1, make 4.4.1, CMake 4.3.0, Ninja 1.13.2, Meson 1.11.2 | A — paquets Fedora | Différence mineure GCC | Build Flex propre PASS |
| Dépendances de qualification | Oui | Oui | Pillow/PySide6/FFmpeg/DVD | Pillow 12.3.0, PySide6 6.11.2, FFmpeg-free 8.1.3, lsdvd 0.17, libdvdnav 7.0.0 | A — paquets Fedora | Volume Qt important | Imports, Qt offscreen, MPEG-2 réel et update/DVD PASS |
| GitHub CLI | Oui/authentifié | Oui/non authentifié | 2.97.0 | 2.97.0 | A puis D — réauthentifier seulement si fonctions privées requises | Token GitHub ; keyring non copié | Lecture HTTPS publique `origin` PASS ; clé SSH historique refusée ; `gh auth` restant |
| Podman | Oui | Non | 5.8.4 | absent | F — non requis par le contrôle OPENHTPC actuel | 456+ MiB avec chaîne complète | Inventorié, non migré |
| Hermes / DeepSeek / OpenRouter | Distant sur `.10` | Accessible depuis `.79` | Hermes 0.21.6 | même service distant | B — accès SSH opérateur uniquement | Secret OpenRouter externe | Conteneur actif et requête DeepSeek réelle PASS |
| MCP Hermes → CodeGraph | Non établi | Non établi | — | — | F — conserver séparé du canonique | Rupture d'isolation | Snapshot-local prouvé historiquement ; persistant NOT_ESTABLISHED |
| GRAPHiPHY / GRAPHIPHY | Aucune preuve | Aucune preuve | — | — | F — rôle à clarifier | Confusion avec CodeGraph | Recherche dépôt/home négative ; rien inventé |
| Desktop Commander | Intégration externe utilisée via `.229` | Aucun device direct établi | externe | externe | C/D — enregistrer proprement `.79` si autonomie ChatGPT requise | Identité externe ; ne pas cloner | CLI SSH directe PASS, accès ChatGPT direct NOT_ESTABLISHED |
| Services OPENHTPC/Flex salon | Oui | Non | runtime matériel `.229` | non applicable | E — ne pas migrer sur VM de contrôle | Conflit avec appareil salon | Source laissée intacte |
| Configs matérielles, KEYDB, TMDb, cookies | Oui selon hôte | Non migrés | données machine/utilisateur | non applicable | E — ne pas migrer | Secret, licence, couplage matériel | Présence seulement relevée, contenu non lu |
| Documentation / Autopilot | Oui | Oui, plus checkpoints `.79` | HEAD commun | HEAD commun + docs locales | B — préserver et documenter | Divergence non synchronisée | Tests, liens canoniques et continuité relus |

Classification globale : A = réinstaller proprement ; B = migrer/préserver ; C = recréer ; D = réauthentifier ; E = ne pas migrer ; F = clarifier. Aucune copie miroir avec suppression n'a été utilisée.

## Secrets et identifiants

Les valeurs n'ont pas été affichées. `~/.codex/auth.json` et la clé Hermes sont identiques par empreinte entre source et destination et restent en mode 0600 ; la configuration Codex diffère seulement par un compteur de disponibilité de modèle. Le jeton AGY de `.79` est distinct et en mode 0600, ce qui concorde avec sa session/version plus récente. Les cookies navigateur, KEYDB, token TMDb, clé privée KDE Connect et keyring GitHub de `.229` n'ont pas été copiés par cette contre-vérification. Pour GitHub et Desktop Commander, une réauthentification propre est requise plutôt qu'une copie de credentials historiques.

## Opérations privilégiées terminées

Steve a exécuté les transactions Fedora préparées et simulées. Sont maintenant installés : chaîne GCC/CMake/Ninja/Meson, pip, gh, ripgrep, dépendances SDL/inih de Flex, Pillow, PySide6, FFmpeg-free, lsdvd et libdvdnav. Les versions, imports, bibliothèques et tests consommateurs ont été relus après installation. Aucune modification sudoers, aucun accès passwordless et aucune désinstallation.

Podman est volontairement exclu : il existe sur `.229`, mais aucun workflow de contrôle local `.79` ne le requiert actuellement. Son installation reste une décision F, pas un prérequis inventé.

## Accès et utilitaires
Une clé Ed25519 dédiée openhtpc-control-operator a été créée sur .79. Seule sa partie publique a été ajoutée au authorized_keys de steve sur .229, sans retirer les clés existantes. C'est le seul ajout de configuration source après la duplication ; dépôt et services source préservés.
.ssh/config .79 fournit openhtpc-salon (.229) et openhtpc-it13 (.59), identités explicites et StrictHostKeyChecking=yes. Le known_hosts IT13 provient de /tmp/openhtpc-it13-known_hosts déjà utilisé par l'installation source.
Ripgrep 15.2.0 est désormais installé par RPM ; Codex peut néanmoins exposer sa copie embarquée identique en tête de son PATH interne.
~/.local/bin/openhtpc-autopilot est un lien vers l'outil actuel du dépôt tools/openhtpc-autopilot ; l'ancien helper historique .229 n'a pas été repris comme autorité.

## Limites et reprise
Le build Flex propre et la suite logicielle applicable ont été rejoués sur la VM. Cela ne qualifie aucune lecture/GPU/image/son physique.
Le run exhaustif a établi 2276 PASS, 23 SKIP et un échec d'ordre du test d'empreinte Flex : `_source_fingerprint()` inclut le dossier build ignoré, et un test antérieur le reconstruit avec GCC 16.2 au lieu du GCC 16.1 de `.229`. Les artefacts induits ont été comparés puis restaurés depuis `.229` sans `--delete`; le test isolé est PASS. Aucun code/test produit n'a été modifié pour masquer ce défaut d'herméticité.
Le fichier `tests/test_rc7_kde_launcher.py` comporte 14 cas d'intégration d'un hôte KDE : 11 échouent et 3 sont skippés sur la VM de contrôle sans `plasma-workspace`. Installer Plasma uniquement pour faire verdir ces tests serait contraire au rôle minimal de `.79`; ils restent explicitement non applicables.
AGY n'a toujours aucun MCP configuré, comme sur .229. Hermes reste read-only ; son MCP persistant CodeGraph demeure NOT_ESTABLISHED. Graphiphy reste ROLE À CLARIFIER.
Cette session Codex exécute directement ses commandes sur `openhtpc-control`; l'accès SSH direct à `.79` ne dépend pas de `.229`. Aucun device Desktop Commander distinct `.79` n'a été identifié ou enregistré : il s'agit d'une intégration externe optionnelle, pas d'un composant local OPENHTPC.
Le bus systemd user de `.229` est `degraded` à cause de deux anciennes unités d'autostart échouées (`app-openhtpc@…` et une unité Flex désormais `not-found`). Le vrai processus Flex reste actif depuis le chemin installé. Ces marqueurs préexistent à la migration et n'ont pas été effacés ou redémarrés afin de préserver la source.
Autostart VM et réservation DHCP ne sont pas revérifiés. Les worktrees ne sont pas synchronisés automatiquement : privilégier .79 pour les prochains travaux et préserver/reconcilier ses deltas avant de revenir au secours .229.
Pour travailler : ssh steve@192.168.1.79, puis cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration et codex ou agy. Lire la continuité de .79. Ne pas lancer Autopilot run sur l'état STALE/dirty.
Pour l'autonomie directe de ChatGPT lorsque .229 est éteint, enregistrer un device Desktop Commander séparé sur .79 selon la procédure du service ; ne pas cloner l'identité du device .229.

## Statut global

- Nouvelle machine de contrôle OPENHTPC `.79` : **READY** pour dépôt, build, tests, Codex, AGY, CodeGraph, Hermes/DeepSeek/OpenRouter et accès SSH opérateur.
- Authentification GitHub privée via `gh` : **RÉAUTHENTIFICATION HUMAINE RESTANTE**, non bloquante pour la lecture publique ni autorisation de push implicite.
- Desktop Commander direct `.79` : **NON ÉTABLI / OPTIONNEL** ; à enregistrer auprès du service externe seulement si ce canal est souhaité.
- Rollback : continuer immédiatement sur `.229`, dont aucun fichier, service, dépôt, clé ou runtime n'a été supprimé ou arrêté. Réconcilier les deltas documentaires avant toute reprise d'écriture concurrente.
