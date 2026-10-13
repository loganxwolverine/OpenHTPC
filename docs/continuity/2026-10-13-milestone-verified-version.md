# OPENHTPC — Jalon : version corrigée construite et vérifiée — 2026-10-13

Rédigé par Hermes. Consigne un jalon atteint, pas une autorisation.

## Le jalon

| Élément | Valeur |
| --- | --- |
| Commit | `6b2046eeb422d95a94cf7113f453c5f44d74e0ad` — « fix(magnificence): restrict DVD_PAL_FILM to 625-line PAL geometry » |
| Contenu du commit | 2 fichiers, +107 / −1 (`payload/openhtpc-playback-policy.py`, `tests/test_magnificence_source_scope_guard.py`) |
| Artifact | `artifacts/OpenHTPC-1.3.1-Patina-PalScope.tar.gz` |
| SHA-256 de l'archive | `80edb1552f664f28db83e4a741d80cbe75f873ec0c6eed94ab2ba83ee77c1481` |
| Source de construction | commit `6b2046e` ; Flex **reconstruit depuis la source exportée** |
| Vérification | `tools/openhtpc-devctl verify` → **VERIFY PASS** |
| Stash protégé | préservé (`stash@{1}`) |

Un artifact release/RC cohérent et vérifié existe donc pour la première fois **avec** le
correctif de portée PAL. L'ancienne archive `OpenHTPC-1.3.1.tar.gz` (construite depuis
`9754029`) ne contenait pas ce correctif : elle est conservée comme historique, jamais
publiée, et donc non trompeuse. Le choix d'identité retenu — version produit `1.3.1` +
nom d'archive distinct — est celui recommandé dans `2026-10-13-release-build-runbook.md`.

## Ce qu'il faut comprendre de cet artifact — et c'est décisif

Le build l'a écrit lui-même : « Working tree is dirty. Archive is built from **committed
files only**. Untracked/modified files will NOT be included in the artifact. »

Conséquence, à ne pas confondre :

- l'**artifact** contient la base commitée + le correctif PAL. C'est un état cohérent, vérifié, installable ;
- le **worktree** contient, en plus, du travail **non commité** : framework plugins étape 1
  (inventaire Système, résolution des dépendances), rampe Système compacte et **binaire Flex
  reconstruit**, profil exact IT13, documentation. **Rien de tout cela n'est dans l'artifact.**

Deux états divergent donc, c'est normal et assumé — mais cela doit être dit, sinon la prochaine
personne croira que l'artifact contient « tout le projet ».

## Limite de ma propre vérification

Je **n'ai pas** vérifié l'archive moi-même : `artifacts/` est exclu de mon canal lecture seule,
par la même règle que celle des snapshots d'audit (« product artifact integrity checked
separately »). La vérification citée est celle de l'outil du projet (`devctl verify`), qui
rehache le binaire, contrôle son identité ELF, l'empreinte source, le manifeste et le commit
annoncé. Elle est plus forte que la mienne ne le serait à la main, mais elle n'est pas mienne —
je le dis pour que la distinction reste claire.

## Le risque de continuité le plus élevé, dit franchement

**Tout vit sur une seule machine.** L'historique Git, le worktree (dont le travail non commité),
les artifacts et les rapports privés sont sur `.79` et nulle part ailleurs : je n'ai constaté
**aucune réplication**, aucun remote configuré sur lequel compter, aucune copie hors machine.

Si ce disque meurt, le projet meurt avec lui — y compris le travail non commité, qui n'existe
qu'à un seul endroit et n'est protégé par rien.

C'est, de loin, le premier sujet de continuité, avant toute nouvelle tranche produit. Et il est
bon marché : un `git bundle` contient tout l'historique dans un fichier unique, et une copie des
`artifacts/` suffit pour les versions.

## Décision prise pour la suite, dans cet ordre

1. **Répliquer hors machine** (avant toute nouvelle tranche). Une copie de l'historique et des
   artifacts sur un autre support — clé, partage réseau, ou dépôt privé. C'est la seule action
   qui protège ce qui a été construit aujourd'hui.
2. **Moderniser l'état machine** (schéma 2) : le brouillon prêt à l'emploi existe. Il débloque
   Autopilot, qui est fermé depuis le 2026-10-11 à cause de l'état périmé.
3. **Tranche produit suivante** : contrat générique d'action média bornée. L'entrée d'analyse
   est déjà déposée (pré-revue + cartographie) ; la première tâche est de localiser le dispatch
   interne du `ActionController`.
4. **Aligner deux documents** : `OPENHTPC_ACTORS.md` et `OPENHTPC_HERMES_AUDITOR.md` décrivent
   encore « aucun accès canonique pour Hermes ». Voir `2026-10-13-hermes-access-model.md`.

## Ce que je ne peux pas faire, et pourquoi

- Répliquer l'historique ou les artifacts : mon canal n'a **aucune** écriture Git, et `artifacts/`
  ne m'est pas exportable.
- Créer le fichier d'état schéma 2 : `put` n'écrit que des `.md` neufs, jamais un `.json` ni un
  fichier existant. C'est une action d'opérateur/Codex, par construction.
- Publier : non autorisé, et je ne le souhaite pas — un artifact local vérifié suffit.

## État Git au jalon

Branche `feature/magnificence-sd-auto`, HEAD `6b2046e`, VERSION `1.3.1`, worktree dirty
(travaux plugins/Système, binaire Flex reconstruit, profil IT13, documentation), stashes
protégés intacts. Aucun push, tag, publication ni déploiement.
