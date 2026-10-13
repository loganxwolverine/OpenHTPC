# Point de reprise — OPENHTPC — 2026-10-13 fin de journée

Écrit par Hermes avant arrêt, à la demande de Steve : « on reprendra demain à cet endroit ».
Ce document est le seul à lire pour reprendre. Tout le reste est de la preuve.

## 1. Où est le projet, mesuré

| | |
| --- | --- |
| Hôte | `openhtpc-control` / `.79` |
| Dépôt | `/home/steve/OpenHTPC/github-openhtpc-rc2-integration` |
| Branche | `feature/magnificence-sd-auto` |
| HEAD | `7f988bc` (dernier commit du jour) |
| VERSION | `1.3.1` |
| Distant | `origin` GitHub — **en retard de 6 commits**, dernier fetch 2026-10-02. Rien n'est publié. |
| Arbre de travail | 54 entrées non committées — c'est le **chantier de code de Codex**, pas le mien |

## 2. Les commits du jour (dans l'ordre)

| Commit | Auteur | Objet |
| --- | --- | --- |
| `6b2046e` | Steve | correctif de portée PAL (commit posé par Steve) |
| `53798dd` | Hermes (amend) | message du commit de gouvernance corrigé ; arbre inchangé |
| `87629d35` | Hermes | 16 documents du 2026-10-13 (accès, mandat, gouvernance, version, revue média) |
| `8aff888` | Hermes | correction du diagnostic des fichiers d'état |
| `e84a2c8` | nous deux | gouvernance `hermes-eng` (contenu Codex/Steve, committé par Hermes) |
| `7f988bc` | Hermes | dispatch du canal d'action média + deux corrections |

## 3. Ce qui a été accompli aujourd'hui

- Version corrigée construite et vérifiée (`OpenHTPC-1.3.1-Patina-PalScope.tar.gz`,
  empreinte `80edb155…`, `VERIFY PASS`), **et vérifiée par Hermes sur les octets**.
- Sauvegarde hors machine sur le NAS `\\192.168.1.10\Tools\htpc project\hermes-20261013\` :
  historique complet (bundle 51 références), worktree entier, paquets 1.3.1, mesures IT13,
  documents — 44 fichiers, 486 Mio, tous relus et vérifiés.
- Accès ingénierie direct autorisé et opérationnel : compte `hermes-eng`, ACL, Git complet,
  sans sudo ni Docker. Gouvernance mise à jour (revue de Hermes par Codex ou Steve).
- Deux erreurs de diagnostic corrigées par mesure : les fichiers d'état (gelés par conception,
  pas périmés) et le dispatch du canal média (clé de manifeste, pas jeton décodé).

## 4. Ce qui attend une décision — rien d'autre ne bloque

1. **Rouvrir Autopilot sur la ligne 1.3.x ?** Non recommandé : aucun contrat d'état n'existe pour
   cette ligne, et le fichier actuel est gelé **par conception** avec deux tests qui l'exigent.
   Si oui, c'est Codex qui conçoit le nouveau contrat.
2. **Tranche « action média » : quel canal ?** Les actions de candidat (bornées, révisées,
   testées — recommandé) ou le canal de lancement de lecture avec son dispatcher (entrevu seulement).
3. **Comment distinguer une action d'origine plugin** d'une action d'interface, `origin` étant
   codé en dur à `"UI"`.

## 5. Reprendre demain — les commandes

    ssh canonical-eng 'cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration && git log --oneline -8'
    ssh canonical-eng 'cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration && git status --short | wc -l'
    ssh canonical             status            # canal lecture seule, toujours en place

Documents à relire, dans cet ordre :
`docs/continuity/2026-10-13-mandate-hermes-capabilities.md` (mandat et ses bornes) →
`docs/continuity/2026-10-13-execution-du-mandat-hermes.md` (état mesuré, règles que je m'impose) →
`docs/audits/2026-10-13-media-action-dispatch-hermes.md` (dispatch mesuré) →
le présent document.

## 6. Deux fragilités à ne pas oublier

- **La sauvegarde NAS est en retard d'une journée.** Elle a été faite avant les six commits du
  jour. L'histoire du projet n'existe donc qu'à **un seul endroit** : le disque de `.79`.
  Remède bon marché : un `git bundle --all` frais vers le NAS (une minute). Je ne l'ai pas fait
  seul parce que le mot de passe NAS a été retiré du conteneur, volontairement.
- **Le distant est en retard de six commits.** Tant qu'aucun push n'est autorisé, cette avance
  n'existe que localement. C'est cohérent avec le projet, mais cela fait de `.79` le point unique
  de défaillance — c'est la raison de la ligne ci-dessus.

## 7. Rien n'est à moitié fait

Aucune modification préparée dans l'index, aucun `commit --amend` en cours, aucun processus lancé,
aucun stash touché, aucun fichier de code modifié par moi. Le chantier de code de Codex est intact.
