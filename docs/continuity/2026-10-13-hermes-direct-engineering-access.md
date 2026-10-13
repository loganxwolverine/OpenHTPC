# OPENHTPC — Accès ingénierie canonique direct de Hermes — 2026-10-13

Date : 2026-10-13, Europe/Brussels.

## Décision et autorité

Steve autorise explicitement la création du compte SSH `hermes-eng` et son
accès direct en écriture au dépôt canonique. Pour cette voie seulement, cette
décision remplace les règles antérieures imposant exclusivement un clone isolé
sans autorité Git canonique.

Les bornes conservées sont : aucun push, tag ou publication sans autorisation
explicite ; aucune réécriture d'historique partagé ; validation physique et
décisions produit réservées à Steve ; tout code écrit par Hermes est relu par
Codex ou Steve avant qualification. Le §6 du mandat est exclu : aucun socket
Docker, accès root ou sudoers n'est accordé.

La voie d'audit contradictoire reste techniquement immuable et séparée. Elle ne
reçoit ni cette clé ni ce compte.

## État source au prévol

- hôte : `openhtpc-control` / `.79` ;
- branche : `feature/magnificence-sd-auto` ;
- HEAD : `53798dd4e479bebe78ca640e3e76817a67928005` ;
- VERSION : `1.3.1` ;
- worktree préexistant : 29 entrées modifiées et 41 non suivies ;
- `OPENHTPC_CURRENT_STATE.json` : STALE, schéma P2/1.2.0 ;
- stashes préservés : expérience RTX stale et `RC7 T5 network deferred`.

## Installation observée

- compte : `uid=1001(hermes-eng) gid=1001(hermes-eng)`, shell `/bin/bash` ;
- paire ED25519 créée par l'identité Hermes dans son volume privé ; clé privée
  mode `0600`, jamais affichée ;
- empreinte publique :
  `SHA256:X0NnmzkZwbUnkbpEXnjfmQ1Poooy1TkUMNOD+d4pS1g` ;
- clé publique installée dans `/home/hermes-eng/.ssh/authorized_keys` ;
- ACL `rwX` récursive et par défaut sur le dépôt ;
- traversée `--x` seulement sur `/home/steve` et `/home/steve/OpenHTPC`, requis
  parce que ces deux répertoires sont `0700` ;
- identité effective Git auteur/committer :
  `Hermes Agent <hermes@openhtpc.local>` ;
- aucun fichier `/etc/sudoers.d/openhtpc-hermes-eng`, aucun groupe `docker`,
  aucun sudo sans mot de passe.

Le dépôt contient une identité locale appartenant à Steve, prioritaire sur une
simple configuration Git globale. Elle n'a pas été modifiée. L'identité Hermes
est donc imposée dans l'environnement du compte via
`~hermes-eng/.bashrc.d/openhtpc-git-identity.sh`; `git var GIT_AUTHOR_IDENT` et
`git var GIT_COMMITTER_IDENT` ont retourné l'identité Hermes attendue.

## Vérifications fraîches depuis le conteneur Hermes

La connexion réelle a utilisé la clé `/opt/data/.ssh/hermes_eng_ed25519` vers
`hermes-eng@192.168.1.79` avec `BatchMode=yes`. L'alias persistant
`canonical-eng` a ensuite été installé dans la configuration SSH du gateway et
retesté avec succès ; il reste distinct de `canonical`, le canal forcé en
lecture seule.

- branche et HEAD canonique lus exactement ;
- création puis suppression de sondes dans le worktree et `.git` : PASS ;
- groupe Docker absent : PASS ;
- `sudo -n true` refusé : PASS ;
- Python 3.14.8, pytest 8.4.2, CMake, Ninja et GCC disponibles ;
- `python3 -m pytest -q -p no:cacheprovider
  tests/test_hermes_engineer_handoff.py` : **5 passed in 0.70s** ;
- `python3 tools/openhtpc-devctl --help` : PASS ;
- configuration et compilation CMake/Ninja de `vendor/flex-launcher` dans un
  répertoire temporaire : **FLEX_BUILD_PASS** ; seul le warning préexistant sur
  la valeur de retour de `write` ignorée a été observé.

Une vérification Git destructive uniquement dans un worktree/branche Hermes
temporaire a ensuite prouvé : création de branche et worktree, `git add`, commit,
`commit --amend`, `stash create` sans mutation de `refs/stash`, et rebase. Auteur
et committer étaient `Hermes Agent <hermes@openhtpc.local>`. La branche et le
worktree de test ont été supprimés ; le checkout partagé est resté exactement
`feature/magnificence-sd-auto@53798dd4e479bebe78ca640e3e76817a67928005`
et les deux stashes préexistants sont restés identiques. L'objet non référencé
créé par `stash create` est laissé au ramasse-miettes Git normal afin de ne pas
pruner d'autres objets non référencés du dépôt dirty.

Le relevé final `git worktree list --porcelain` expose huit entrées historiques
préexistantes marquées `prunable` (`dev32` à `dev38` et
`post-rc3-plugin-framework-v1-p1`). Elles n'ont pas été créées ni modifiées par
ce test et n'ont pas été élaguées sans mandat séparé.

Ces preuves qualifient la capacité logicielle du compte. Elles ne qualifient
aucun changement produit, déploiement, média ou résultat physique.

## Workflow obligatoire

Hermes relève branche, HEAD, VERSION, status et stashes avant chaque chantier.
Il utilise sa propre branche et son propre worktree afin de ne pas basculer le
checkout partagé sous Codex ou Steve. Il consigne fichiers, commandes, résultats
et limites. Codex ou Steve relit le delta et rejoue les tests pertinents avant
qualification. Un commit Hermes n'autorise jamais push, tag, publication,
déploiement ou manipulation des stashes protégés.

## État final de ce jalon

Capacité : **INSTALLED / SOFTWARE_VERIFIED**, y compris branche, worktree,
commit, amend et rebase locaux.

Aucun commit, push, tag, publication, déploiement, opération physique, décision
produit ou modification de stash n'a été effectué.

## Note ajoutée le 2026-10-13 après coup

Le commit `10e4330` cité ci-dessus a été **amendé** le jour même : son message annonçait
« record Hermes read-only canonical channel » alors qu'il contenait aussi le fichier entier
`docs/OPENHTPC_ACTORS.md` et les modifications antérieures de `docs/OPENHTPC_HERMES_AUDITOR.md`.
Le message décrit désormais son contenu réel.

- avant : `10e43308f1120cdbd97bf7604c5447fc0eefd8f7`
- après : `53798dd4e479bebe78ca640e3e76817a67928005`
- arbre Git : **strictement identique** avant et après (`5e992f5aa5ea23540ba44fff56409a3008f76f00`)
- auteur préservé (`loganxwolverine`), commiteur `Hermes Agent <hermes@openhtpc.local>`
- non publié : `origin/feature/magnificence-sd-auto` est resté à
  `6cdaef763c593215550c241e70e13c773ac799d0` (dernier fetch le 2026-10-02) — l'amend n'a touché
  que l'histoire locale.

Les deux références à l'ancien SHA dans ce document ont été mises à jour en conséquence.
