# OpenHTPC — Portée PAL du classifieur Magnificence SD : correctif — 2026-10-13

Consolidation : 2026-10-13, Europe/Brussels.
Origine : audit Hermes `hermes-real-01` (finding F1) et revue contradictoire Magnificence
`openhtpc-magnificence-matrix-20261011T162911Z` (finding C5), trouvés indépendamment.
Préparé par Hermes ; posé et vérifié par l'opérateur.

## Défaut corrigé

`payload/openhtpc-playback-policy.py :: _magnificence_source_scope` retournait la classe
`DVD_PAL_FILM` pour **tout** SD sous 720×576 (branche `local`) et pour tout
`kind == "dvd"`, **sans aucun test PAL**. Or chaque profil livré déclare une portée
pal-only (`source_scope = {class: DVD_PAL_FILM, resolution: 720x576, fps: 25.0}`) que le
matcher n'applique jamais : il ne compare que la chaîne de classe.

Conséquence prouvée : un fichier **NTSC 720x480/29.97** — et 640x480, 352x288 —
sélectionnait un profil déclaré PAL et résolvait `RECIPE_C2_DVD_KRIG_BILATERAL` au lieu
de `PURE`. Aucun impact lifecycle ni sécurité ; le défaut est une application de chaîne
qualifiée sur une géométrie non qualifiée, plus une `source_scope` inexacte dans le JSON
de décision.

## Correctif

Un seul changement sémantique dans la branche SD, avec commentaire documentant
l'invariant et la limite restante :

    -    if width and height and width <= 720 and height <= 576:
    +    if width and height and width <= 720 and height == 576:

La géométrie 576 lignes reste PAL, y compris déclarée entrelacée (les recettes
famille/HD portent BWDIF précisément pour ça). Les géométries non-PAL échouent
**fermé** vers `PURE`, conformément à `AGENTS.md` (« prefer safe fallback », « do not
fold unknown into a profile »).

Patch d'application : `pal-fix-code-only.patch`, SHA-256
`10b60baddfb21b67e987f707adf9ed977619db52e24bdc0ea52e940c67dc2be1`
(2 fichiers : le module ci-dessus + le nouveau test garde).

Fichiers concernés par ce lot :

- ` M payload/openhtpc-playback-policy.py` — empreinte du fichier corrigé
  `255225a0adb4e172f73c2b1c05098910a178ab509828c0b6bc82ea8d15564fbf`
  (avant correctif : `45974d63baf7b00ae0ae0a81ac75fe7ac67ed0b0801d66295ba6176cb09a3cc2`) ;
- `?? tests/test_magnificence_source_scope_guard.py` — nouveau test hermétique,
  SHA-256 `7546692c3162e31f087b905eadad2624bb9408fe7e29d49bf79710009e095858`.

Le test garde encode l'invariant : classe PAL réservée à la géométrie 625 lignes
(720x576, 704x576, entrelacé compris) ; NTSC 720x480/640x480 et 352x288 **ne doivent
pas** revendiquer la classe PAL ; et un contrôle bout-en-bout vérifie qu'un fichier NTSC
retombe sur `PURE` pendant que son homologue PAL résout toujours le profil qualifié.
Il est hermétique : ni `/sys`, ni `/dev/dri`, ni Wayland, ni ffprobe réel.

## Preuves d'exécution

Sur le code d'origine (instantané read-only), le test garde donnait **3 échecs sur 4** —
le défaut était donc réel et non théorique.

Après application dans le dépôt canonique, relevé opérateur du 2026-10-13 :

- `sha256sum` du patch avant application : conforme à l'empreinte ci-dessus ;
- `git apply --check` puis `git apply` : PASS ;
- `grep -n 'height == 576' payload/openhtpc-playback-policy.py` → ligne 89 ;
- `python3 -m pytest -q tests/test_magnificence_source_scope_guard.py tests/test_magnificence_policy.py tests/test_magnificence_static_auto.py`
  → **46 passed** ;
- `git diff --check` : muet ;
- `git status --short` : ` M payload/openhtpc-playback-policy.py` et
  `?? tests/test_magnificence_source_scope_guard.py` ;
- `git stash list` : les deux stashes préexistants intacts.

Régression du périmètre pertinent (les 24 fichiers de test qui touchent la politique de
lecture), sur copie isolée du même instantané : **476 passed, 6 skipped, 17 failed**.
Ces 17 échecs sont exactement l'ensemble du baseline déjà consigné, tous dans les
familles `dev32-38` / `rc7` audio-optique-lifecycle (limitations d'environnement), aucun
dans le périmètre Magnificence touché. **Aucune régression introduite.**

## Limites — ce que ce correctif ne fait pas

- `kind == "dvd"` (support optique sans sonde) **conserve** son hypothèse PAL
  documentée : aucun `ffprobe` n'est disponible à ce point d'appel. Limite assumée et
  écrite dans le commentaire du correctif.
- **Aucun support NTSC n'est ajouté.** Le comportement non-PAL est un repli fermé vers
  `PURE`. Si un support NTSC devenait une cible produit, il exigerait une classe et un
  jeu de profils propres — décision séparée, non autorisée ici.
- Aucun commit, push, tag ni publication. L'artifact 1.3.1 construit depuis le HEAD
  `975402945376618db56e29945074ea30ddcd2cb8` **ne contient pas** ce correctif ; toute
  publication ultérieure devra l'embarquer dans un artifact reconstruit depuis le commit
  exact correspondant.
- La qualification physique d'une chaîne PAL n'est pas requalifiée : le correctif ne
  modifie aucune recette, aucun profil et aucune chaîne qualifiée.

## État Git

Branche `feature/magnificence-sd-auto`, HEAD `975402945376618db56e29945074ea30ddcd2cb8`,
VERSION `1.3.1`, worktree volontairement dirty. Stashes protégés préservés :
`pre-sync stale RTX experiment 2026-10-02` et `RC7 T5 network deferred`. Aucun commit.

## Suite

Décision produit ouverte, sans blocage : support NTSC oui/non (si oui, classe et profils
dédiés). Le cas `kind == "dvd"` reste à rouvrir si une source de géométrie devient
disponible à ce point d'appel.
