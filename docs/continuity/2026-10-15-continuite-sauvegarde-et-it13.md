# Hermes — sauvegarde d'état complète, découverte bundle/stash, essai IT13 — 2026-10-15

Écrit par Hermes. **Destiné à être déposé** dans `docs/continuity/` par le canal borné
(`put continuity 2026-10-15-continuite-sauvegarde-et-it13.md`) — pas encore déposé, sur
instruction explicite de Steve (« prépare et signale seulement »).

## Reprise et autorité

- Dépôt `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`, branche
  `feature/magnificence-sd-auto`, HEAD `312ceb84eac7764ec360d6d52a628e64734206f4`, VERSION `1.3.1`.
- Empreinte d'arbre : `19541911ee828c2d675956a99c5c4b46176cc10aefaece7cf41d96f9af11f82a`,
  inchangée du début à la fin de cette session (aucune écriture Hermes dans le dépôt, index vide).
- Autorité : lecture seule et préparation. **Aucun commit, aucun index touché, aucun stash
  manipulé, aucune opération destructive.** L'écriture canonique reste à Steve/Codex.

## Finding 1 — `git bundle create --all` n'est PAS une sauvegarde suffisante (mesuré)

**Constat, mesuré sur ce dépôt le 2026-10-15 :**

- `git bundle create - --all` transporte `refs/stash`, donc **`stash@{0}` seulement** ;
- `stash@{1}` (`RC7 T5 network deferred`, `d900682dd6b734b7b11c35c064596a6e1948bae2`) **n'est
  pas dans le paquet** — il n'est atteignable que par le reflog, qu'un bundle ne transporte pas ;
- un bundle ne transporte **aucun reflog** : après restauration, `git stash list` est **vide** et
  `refs/stash@{n}` ne résout pas, même si l'objet `refs/stash` est présent.

**Conséquence pour le projet :** une sauvegarde « bundle seul » ne protège pas les stashes
protégés d'OPENHTPC. Elle donne l'illusion d'une sauvegarde complète : c'est le pire des cas.

**Règle à retenir (à ne pas reperdre au prochain changement d'agent) :**

> Pour OPENHTPC, une sauvegarde d'état doit contenir **quatre** choses, et non une :
> (1) les refs, (2) **les entrées de stash au-delà de la première** (ajoutées comme têtes
> explicites du bundle), (3) **les reflogs** (`.git/logs`), (4) **l'arbre de travail non commité**
> plus `.git/index` — sinon l'état « sale » n'est pas reproductible.
> Restaurer par `git bundle unbundle` + `update-ref`, **jamais** par `git clone` (qui range les
> branches sous `refs/remotes/origin/*` et perd le nommage).

## Finding 1 bis — le chemin des identifiants NAS : un seul fichier, deux vues

Deux chemins ont circulé et il n'y en a qu'**un** :

| Côté | Chemin |
| --- | --- |
| Hôte `.79` (ce que Steve écrit) | `/home/steve/.local/share/hermes-agent/.smbcreds-tools` |
| Conteneur Hermes (ce que le script lit) | `/opt/data/.smbcreds-tools` |

Ce n'est pas une convention : c'est le **même fichier**. `/proc/self/mountinfo` du conteneur montre
`… /home/steve/.local/share/hermes-agent /opt/data rw …` — `/opt/data` est le montage liant du
répertoire hôte. Un fichier créé à l'un des chemins apparaît à l'autre. **Aucun emplacement
concurrent ne doit être créé.**

Emplacement canonique : **`/home/steve/.local/share/hermes-agent/.smbcreds-tools`** côté hôte
(= `/opt/data/.smbcreds-tools` côté conteneur), format `username=` / `password=`, mode `0600`,
propriétaire `10000:10000`.

L'outillage accepte un chemin configurable (`OPENHTPC_SMB_CREDS`, et `CREDS` pour `openhtpc-backup.sh`)
afin qu'aucun emplacement ne soit codé en dur. **Les identifiants ne sont jamais copiés dans le
dépôt, ni inclus dans une sauvegarde** : le script d'envoi ne prend que l'arbre `backup-<date>/`,
qui ne contient aucune donnée d'authentification.

## Correctif proposé — outillage de sauvegarde

`/opt/data/workspace/hermes-real-01/openhtpc-backup.sh` (modes `prepare` / `verify` / `upload`) et
`openhtpc-nas-upload.py` (écriture SMB par morceaux de 1 Mio + relecture sha256 **depuis la
destination**, un fichier à la fois). Copie de travail : `backup-20261015/` (247 Mio) — historique
complet (42 refs), arbre de travail réel (fichiers modifiés **et** non suivis), `index`, reflogs,
note opérateur, couche d'identité des artifacts (rapports/empreintes ; les paquets de ~110 Mio
pièce, 13 Gio au total, ne sont pas copiés car reconstructibles).

## Preuves réexécutées (pas citées)

Restauration réelle dans un bac à sable, puis comparaisons :

| Contrôle | Résultat |
| --- | --- |
| Empreintes de la sauvegarde (`sha256sum -c`) | 13/13 concordent |
| Refs du bundle vs refs du dépôt | 42/42 identiques |
| Refs restaurées sous leur nom d'origine | 42/42 |
| `git stash list` restauré | 2/2 entrées énumérées, **objets présents** (`cat-file -e`) |
| HEAD restauré | `312ceb84…` identique |
| Empreinte de l'arbre restauré | `19541911…` identique |
| `git status --porcelain` restauré | 58/59 identiques ; l'écart est `?? .hermes/`, échafaudage de l'agent, exclu par conception et **chiffré** par la vérification |
| Code restauré | `payload/openhtpc-core.py`, `-ui.py`, `-plugin-registry.py` : syntaxe valide |

Résultat : **restauration vérifiée localement**. Le transfert vers le NAS (`\\192.168.1.10\Tools\htpc
project\hermes-20261015\`) est **préparé mais non effectué** : les identifiants SMB ont été retirés
du conteneur. Tant que la relecture côté NAS n'a pas eu lieu, le risque « disque unique » **n'est
pas levé** et doit être écrit comme tel.

## Finding 2 — le référencement des livrables est en retard

Mesuré le 2026-10-15 (et non déduit) : `docs/continuity/` contient **41** documents, dont **19 ne
sont référencés nulle part** dans `docs/OPENHTPC_CONTINUITY.md` — tous datés du 2026-10-13 : le
correctif de portée PAL, la préparation de version, l'accès et le mandat Hermes, la gouvernance,
les états machine, les dispositions de findings, le travail d'ergonomie et le point de reprise du
soir. Aucun lien de checkpoint n'est cassé (23 liens vérifiés un à un), c'est bien un défaut de
**référencement**, pas de cible.

Le journal d'évolution de la roadmap, lui, ne contient **qu'une seule entrée** pour le 2026-10-13
(la voie d'ingénierie `hermes-eng`) alors que **sept commits** ont été posés ce jour-là — dont un
correctif produit (portée PAL) — et que le travail du soir n'existe qu'en non commité.

Correction d'une affirmation antérieure de ce document : j'avais écrit que le journal « s'arrête au
2026-10-11 ». C'est faux — le journal est en ordre **décroissant**, sa première ligne est bien datée
du 2026-10-13. La lecture fautive venait d'un `tail` sur un tableau trié du plus récent au plus
ancien. Le défaut réel est le nombre d'entrées manquantes, pas une absence d'entrée.

Référencement **appliqué** le 2026-10-15 par la voie d'ingénierie, par édition **en place** (même
inode : la propriété `steve` des deux fichiers est préservée). La modification reste séparable et
réversible : son patch est déposé sous `docs/continuity/2026-10-15-continuite-doc-edits.patch.md`.
Le contenu inséré est exactement celui des trois blocs ci-dessous :

À ajouter **en tête** de « Dernier checkpoint opérationnel » dans `docs/OPENHTPC_CONTINUITY.md` :

    - [Hermes — sauvegarde d'état complète, découverte bundle/stash, essai IT13 — 2026-10-15](continuity/2026-10-15-continuite-sauvegarde-et-it13.md) :
      une sauvegarde d'état OPENHTPC exige refs + entrées de stash au-delà de la première + reflogs + arbre
      non commité + index ; `git bundle create --all` seul ne suffit pas et laisse `git stash list` vide après
      restauration. Restauration vérifiée localement (42 refs, 2 stashes, HEAD, arbre, état sale) ; transfert
      NAS en attente des identifiants. Cartographie du worktree 1.3.2, protocole d'essai physique IT13 et
      trois décisions du contrat d'action média préparés, aucun commit.

À ajouter dans le tableau « Point de situation vérifié » (ligne nouvelle) :

    | Sauvegarde d'état et découverte bundle/stash | Outillage écrit et restauration vérifiée localement ; transfert NAS en attente | Refus mesuré : `git bundle create --all` ne conserve pas `stash@{1}` ni les reflogs | Transférer vers le NAS et relire chaque fichier ; voir `docs/continuity/2026-10-15-continuite-sauvegarde-et-it13.md` |

À ajouter dans le **journal d'évolution** de `OPENHTPC-ROADMAP.md` :

    | 2026-10-15 | Sauvegarde d'état complète : `git bundle --all` déclaré insuffisant | Mesuré : `stash@{1}` absent du bundle, reflogs non transportés, `git stash list` vide après restauration. Recette de sauvegarde à quatre composantes écrite ; restauration vérifiée dans un bac à sable (42 refs, 2 stashes, HEAD, arbre, état sale) ; transfert NAS non effectué (identifiants retirés). Aucun commit. Voir `docs/continuity/2026-10-15-continuite-sauvegarde-et-it13.md`. |

## Références des livrables du 2026-10-15 (à conserver avec ce checkpoint)

Emplacement de travail (volume Hermes sur `.79`, hors dépôt) :
`/home/steve/.local/share/hermes-agent/workspace/hermes-real-01/deliverables/`

| Document | Objet |
| --- | --- |
| `2026-10-15-cartographie-worktree-1.3.2.md` | Les 59 entrées du worktree, attribuées par chantier ; points ambigus ; obstacle de séquencement |
| `2026-10-15-plan-de-decoupage-commits.md` | Découpage A (framework plugins / page Extensions) puis B (ergonomie), lots C hors périmètre, hunks, tests, messages |
| `2026-10-15-protocole-essai-physique-it13.md` | Protocole de la lecture physique post-installation sur `.59`, instrumentation, ce qui reste `NOT_PROVEN` |
| `docs/audits/2026-10-15-media-action-3-decisions-hermes.md` | Trois décisions du contrat générique d'action média bornée, avec conséquences et réversibilité |
| `2026-10-15-continuite-sauvegarde-et-it13.md` | Le présent document |
| `openhtpc-backup.sh`, `openhtpc-nas-upload.py` | Outillage de sauvegarde et de transfert vérifié |

Outillage de mesure IT13 (sur `.59`, `~/openhtpc-qualification/`) : sonde
`it13_installed_profile_probe.py` et son auto-contrôle `it13_probe_selftest.py`. Le harnais du
2026-10-11 (`/tmp/openhtpc_it13_strong_probe.py`) a été **perdu** (`/tmp` non durable) ; la sonde
reconstruite a été **validée en recalculant** le résumé conservé du 11/10 — les sept métriques
concordent à la 6e décimale.

## Limites

- Le transfert NAS n'a pas eu lieu : le risque « disque unique » n'est **pas** levé.
- L'essai physique sur `.59` n'était pas déclenché au moment d'écrire ; ses résultats ne sont donc
  pas dans ce document.
- Le contrat d'action média reste une **pré-revue statique** : aucun test exécuté pour lui.
- Le découpage A/B a été vérifié sur la batterie voisine (172 puis 173 tests selon l'état) ; le gate
  complet (≈ 2 284 tests) reste à rejouer au moment du gel.

## Prochaine action

1. Retransférer les identifiants SMB, puis `bash openhtpc-backup.sh upload` et la relecture NAS.
2. Déposer ce document (`put continuity …`), puis appliquer les trois insertions de référencement.
3. Déclencher l'essai physique IT13 sur `.59` et en écrire le verdict point par point.
4. Décider du canal de la tranche « action média » (décision 1 du document dédié).
