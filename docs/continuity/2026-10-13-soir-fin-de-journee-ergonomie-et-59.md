# OPENHTPC — Fin de journée : ergonomie Extensions corrigée, .59 réinstallé à neuf — 2026-10-13 (soir)

Écrit par Hermes à la demande de Steve (« on reprendra nos points pour évoluer demain »).
Ce document complète `2026-10-13-point-de-reprise.md` (rédigé à 16:27, donc **avant** le travail
du soir) : pour l'état Git, `.59` et la tranche en cours, c'est celui-ci qui fait foi.

## État mesuré (relevé sur `.79`, pas déduit)

| | |
| --- | --- |
| Branche | `feature/magnificence-sd-auto` |
| HEAD | `312ceb8` — « docs: end-of-day resume point… » (2026-10-13 16:27) |
| VERSION | `1.3.1` |
| Distant | `origin` = 8 commits en retard, 0 en avance. Rien n'est publié. |
| Worktree | 58 entrées non committées (chantier de Codex + le correctif du soir + les documents déposés) |
| Stashes protégés | intacts (`pre-sync stale RTX experiment 2026-10-02`, `RC7 T5 network deferred`) |
| Commits / tags | aucun par Hermes |

## Fait ce soir

1. **Correctif d'ergonomie de la page Système → EXTENSIONS**, appliqué dans le dépôt canonique
   (voie d'ingénierie `hermes-eng`, sans commit) : `payload/openhtpc-ui.py`, un hunk, +11/−8.
   `43e9025b…` → `91d8fd86…`. Les deux lignes de détail ont désormais une position et un sens
   fixes pour toutes les extensions ; « Prérequis » ne désigne plus que le prérequis système.
2. **Garde de test ajoutée** : `test_extensions_detail_lines_have_one_fixed_meaning_per_line`
   dans `tests/test_plugin_framework_generic_system.py` (`c6629cc4…` → `219fb4e5…`). Elle passe
   sur le code corrigé et échoue sur le code d'origine (mord là où elle doit).
   Batterie rejouée : 52 passed. Patchs déposés dans `docs/continuity/` avec leurs empreintes.
3. **`.59` purgé puis réinstallé à neuf**, sans sauvegarde (choix explicite de Steve), sur le
   candidat worktree `worktree-ergonomie-config-20261013` : installation sans sudo (le socle
   Fedora était déjà présent), passeport matériel reconstruit, runtime généré, doctor
   **READY**, appliance RUNNING, une seule instance Flex.
   Vérification faite sur la page réellement rendue par `.59` : lignes alignées, rien de
   tronqué, un seul élément orange (le prérequis optique externe absent, à juste titre).
4. **Documents déposés** dans `docs/continuity/` (propriété `steve`) :
   `ergonomie-config-extensions.patch.md` (`dfbf4098…`), `ergonomie-config-garde-test.patch.md`
   (`2f4def08…`), `2026-10-13-ergonomie-section-config-extensions.md` (rapport),
   `2026-10-13-ergonomie-section-config-extensions-c2.md` (corrections C2/C3).

## Ce qui attend une décision — nos points pour demain

1. **Commit de la tranche `payload/openhtpc-ui.py`** : correctif **et** sa garde ensemble
   (contrat AGENTS.md : autorisation explicite requise ; correctif et test ne se séparent pas).
   Attention : ce fichier porte aussi du travail non committé de Codex.
2. **Identité de version** de la tranche worktree (framework plugins étape 1, inventaire
   Système, présentation Extensions, profil IT13) : `1.3.2` est une tranche d'identité séparée
   (VERSION, changelog, métadonnées), et aucun artifact officiel ne contient ces changements.
3. **Rapport d'ergonomie** : appliquer ou refuser les remplacements C2/C3 (§6 faux, garde) ; le
   rapport appartient à Steve, Hermes ne peut pas le réécrire.
4. **Chantiers produit restants** (repris du point de reprise) : contrat générique d'action média
   bornée ; modernisation des états machine périmés (`OPENHTPC_CURRENT_STATE.json` P2/RC5/RC7 et
   `.openhtpc-autopilot/state.json` du 2026-09-01) ; décision de Steve sur le catalogue de
   plugins (seul audit préparé sans réponse) ; Magnificence : endurance A310, A/B `vaapi-copy`
   sur `.59`, lecture physique post-installation IT13, corrections documentaires D1-D3/D6.
5. **`.59` à finir depuis le canapé** : sortie audio et mode (revenus à « sortie système
   Fedora » / PCM), sources média (vides), TMDb (non configuré), préférences de lecture par
   défaut. La lecture physique d'un DVD PAL sur cette installation neuve reste **à faire** — le
   profil exact IT13 est en place, mais la sélection réelle ne se prouve qu'en lisant.
6. **`.59` : ne pas oublier que l'identité installée est non officielle.** Le candidat est
   conservé sur la machine (`~/openhtpc-fresh-20261013`, archive `d6b414d6…`) ; la reprendre
   suppose de rejouer la composition depuis le worktree.

## Fragilités à ne pas perdre de vue

- **Tout vit sur `.79`** : historique, worktree non committé (dont le correctif du soir) et
  artifacts. La sauvegarde NAS est en retard d'une journée. Avant toute tranche neuve :
  `git bundle --all` frais + copie des artifacts.
- **Trois documents de `docs/` appartiennent encore à `hermes-eng`** (déposés par la voie
  d'ingénierie) : `docs/audits/2026-10-13-media-action-dispatch-hermes.md`,
  `docs/continuity/2026-10-13-execution-du-mandat-hermes.md`,
  `docs/continuity/2026-10-13-point-de-reprise.md`. Steve peut les lire, pas les modifier ;
  le `chown` appliqué aux fichiers de code ne les couvre pas.
- Laissé volontairement intact sur `.59` : `~/.local/state/openhtpc-it13-qualification`,
  `~/Downloads/openhtpc-install-1.3.1-20261011`, le dossier et l'archive du candidat.

## Reprendre demain — commandes

    ssh canonical status
    bash /opt/data/workspace/hermes-real-01/openhtpc-pull.sh
    ssh canonical-eng 'cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration && git log --oneline -5'

## Rien à moitié fait

Aucun commit, index vide, aucun stash touché, aucun processus laissé en course. L'installation de
`.59` est terminée (doctor READY) ; ce qui reste sur cette machine est de la configuration
utilisateur, pas du travail interrompu.
