# OPENHTPC UX-M1 / UX-M2 — candidat technique V0.1

Date de qualification locale : 2026-11-03

## Résultat livré

Le candidat ajoute un layout de section explicite `Layout=MediaWall`. Les
sections qui ne le déclarent pas gardent le rendu Flex existant.

- Rangée `Récemment ajoutés` : les 12 premières entrées au maximum, dans
  l'ordre du manifeste.
- Rangée `Tous les films A-Z` : toutes les entrées, tri stable sans tenir
  compte de la casse.
- Navigation horizontale bornée et navigation verticale par flèches ou
  commandes `:up` / `:down`; `:left` / `:right` restent acceptées.
- La position et le scroll de chaque rangée sont indépendants et le retour
  depuis une fiche vers un MediaWall force `reset_position=false`.
- A/OK suit exclusivement `Entry.cmd`; la fixture n'emploie que
  `:submenu MEDIA_D_...`. Aucun lancement direct de MPV n'a été ajouté.
- Affiches 2:3, fond nuit, focus +14 %, translation vers le haut, ombre,
  contour `#3D8BFF`, rendu du focus en dernière passe, atténuation des autres
  affiches et bandeau bas titre/aide.
- Chargement paresseux des affiches visibles; cache plafonné à 20 textures
  d'affiche avec éviction LRU des textures hors écran. Les menus classiques
  conservent leur chemin de rendu historique.

## Fichiers

- `src/media_wall.h`, `src/media_wall.c` : modèle pur (tri, bornes, rangée,
  sélection, scroll, index de manifeste et politique de retour).
- `src/launcher.h` : type de layout, commandes `:up`/`:down`, état SDL du mur.
- `src/util.c` : parsing opt-in de `Layout=MediaWall` et initialisation de
  l'état associé.
- `src/launcher.c` : intégration navigation/retour, rendu SDL, footer et cache
  borné. L'exécution de la sélection réutilise `execute_command(entry->cmd)`.
- `src/CMakeLists.txt` : ajout du module au binaire.
- `CMakeLists.txt` : activation des deux tests CTest locaux.
- `tests/test_media_wall.c` : bornes, scroll, mémoire par rangée, tri, index
  sans action et politique de conservation au retour.
- `tests/check_fixture.cmake` : contrat `Layout=MediaWall`, 13 sous-menus de
  fiche et rejet de `mpv`, `:tracked` ou `:fork` dans la fixture.
- `tests/fixtures/media-wall.ini` : manifeste inoffensif de 13 films utilisant
  seulement des icônes locales et `:submenu MEDIA_D_...`.

## Commandes de qualification et résultats observés

Configuration initiale :

```sh
cmake -S . -B build-ux-m1m2 -DBUILD_TESTING=ON -DEXTRA_WARNINGS=ON -DCMAKE_BUILD_TYPE=Debug
```

Résultat : configuration réussie; SDL 2.32.74, SDL_image 2.8.12,
SDL_ttf 2.24.0 et inih 62 détectés.

Reconstruction finale :

```sh
cmake --build build-ux-m1m2 --clean-first -j2
```

Résultat : `flex-launcher` et `media-wall-model-tests` construits. Deux
warnings ont été observés : retour de `write()` ignoré dans
`src/platform/unix.c:151`, et conversion `int` vers `unsigned int` dans
`src/launcher.c:2099`. La compilation n'a pas été déclarée sans warning.

Tests finaux :

```sh
ctest --test-dir build-ux-m1m2 --output-on-failure
```

Résultat : 2/2 tests réussis (`media-wall-model`,
`media-wall-fixture-contract`), 0 échec, 0,01 s.

Smoke SDL sans bureau actif, lancé depuis `tests/fixtures` :

```sh
mkdir -p /tmp/candidate-flex-ui-home/.local/share/flex-launcher /tmp/candidate-flex-ui-home/.local/state/openhtpc/media-actions
timeout -s KILL 2s env HOME=/tmp/candidate-flex-ui-home OPENHTPC_HOME=/tmp/candidate-flex-ui-home SDL_VIDEODRIVER=offscreen ../../build-ux-m1m2/flex-launcher --config media-wall.ini --debug
```

Résultat : le journal indique `Video driver: offscreen`,
`Loading menu 'MEDIA_WALL_TEST'` et `Begin program loop`. Sortie 137 attendue
car le processus interactif est arrêté volontairement après 2 s. Ce smoke
n'est donc pas compté comme un test UI interactif PASS. La fixture réduite ne
contient pas la section CORE `DISQUE`; le polling existant journalise en boucle
`Menu 'DISQUE' not found`, sans empêcher l'initialisation du mur.

## Limites honnêtes V0.1

- Le décodage SDL_image est synchrone lors de la première apparition d'une
  affiche. Le lot borne le nombre d'images chargées et les charge à la demande,
  mais n'implémente pas de thread de décodage asynchrone.
- Le test headless valide l'initialisation et l'entrée dans la boucle de rendu,
  pas une capture pixel ni l'injection d'événements SDL. La navigation est
  couverte au niveau du modèle déterministe.
- Le tri A-Z est un tri `strcasecmp` stable : il traite correctement la casse
  ASCII, mais ne constitue pas une collation linguistique complète des titres
  Unicode.
- La fixture utilise l'icône locale DVD comme substitut d'affiche afin de ne
  dépendre d'aucun cache externe. La géométrie de destination reste 2:3.
- Aucun genre, badge HDR, PLAY ou autre métadonnée non contractuelle n'est
  affiché.
