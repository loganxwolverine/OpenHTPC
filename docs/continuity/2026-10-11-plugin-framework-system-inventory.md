# OPENHTPC — Framework plugins, inventaire Système — 2026-10-11

Consolidation : 2026-10-11, Europe/Brussels.

## Reprise et autorité

- Dépôt canonique : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`.
- Branche : `feature/magnificence-sd-auto` ; HEAD `975402945376618db56e29945074ea30ddcd2cb8`, un commit devant `origin/feature/magnificence-sd-auto` au prévol.
- `VERSION` et `payload/VERSION` : `1.3.1` ; worktree propre avant cette tranche.
- Stashes préservés : `pre-sync stale RTX experiment 2026-10-02` et le stash protégé `RC7 T5 network deferred`.
- `OPENHTPC_CURRENT_STATE.json` décrit P2/1.2.0 RC5/RC7 et reste **STALE** ; il n'autorise aucune action.
- Autorisation utilisateur initiale : poursuivre le chantier plugins après vérification Git/artifact. Steve a ensuite autorisé explicitement le déploiement borné sur `.229` pour constater la rampe Système compacte. Aucun commit, push, tag ni publication n'est autorisé.

## Artifact OPENHTPC 1.3.1 revérifié

Artifact : `artifacts/OpenHTPC-1.3.1.tar.gz`, 114875864 octets.

- rapport : version `1.3.1`, build `public-release-1.3.1`, commit source exact `975402945376618db56e29945074ea30ddcd2cb8` ;
- SHA-256 rapport/sidecar/calcul : `933ce9a780bfc901c8cb90ca72e7973da088b87e294d0c2bb0b73e2aa608837c` ;
- `sha256sum -c` : PASS ;
- `tools/openhtpc-devctl verify` : PASS ;
- `MANIFEST.sha256` extrait : PASS intégral ;
- métadonnée Flex extraite : schema 2, produit 1.3.1, source commit exact, binaire SHA-256 `7d8ce4fb5cadf145ad9053282288dd352b4a09bf47bfb5cf705910ccc06d4f79` ;
- `install.sh --check` avec HOME/XDG temporaires isolés : PASS, aucune modification.

Ces contrôles réétablissent l'intégrité de l'artifact existant. Ils ne reconstruisent pas l'artifact et ne constituent ni publication ni nouvelle qualification physique.

## Tranche implémentée

Première tranche bornée de l'étape 1 de `OPENHTPC-PLUGIN-ROADMAP.md` :

- ajout de `Système → Extensions` dans la configuration Flex produite par le moteur de session ;
- page 1080p générée depuis le registre V2 réel, sans liste de plugins codée en dur et sans chargement d'entrypoint ;
- projection du nom, de la version, de l'état, de l'origine, des hooks, des dépendances déclarées et du diagnostic ;
- état XDG explicite observé de `DISABLED` vers `AVAILABLE` par le même inventaire ;
- manifest utilisateur invalide isolé et présenté `BROKEN`, sans rendre Core indisponible ;
- validation du manifest renforcée : `plugin_api` exige un entier exact et les listes JSON contenant des objets/listes non hashables échouent fermé au lieu de faire tomber le registre.

La frontière P2 gelée est conservée : Core reste propriétaire du registre, de la projection/rendu Système, de Flex, de la sécurité, des I/O et du lifecycle. Aucun plugin n'exécute de commande ni n'acquiert de nouvelle autorité.

### Ajustement esthétique de la rampe Système

Steve constate que les catégories Système ne tiennent plus sur une seule page après l'ajout d'Extensions et exige une présentation sans scroll. La cause est le plafond global Flex `MaxButtons=9`, encore appliqué à la rampe verticale `SYSTEME` malgré sa géométrie dédiée.

Correction bornée :

- taille de page propre à `SYSTEME`, égale à ses onze entrées Core ; les autres menus conservent le plafond et la densité globaux ;
- hauteur de ligne 90→64 ‰, espacement 10→7 ‰, icône 68→46 ‰, texte plafonné à 32 ‰ de la hauteur d'écran et rail 42→38 % ;
- à 1920×1080, la dernière ligne finit calculée à 937 px ; à 3840×2160, à 1884 px : les onze entrées tiennent dans l'écran ;
- libellés raccourcis `COMPATIBILITÉ VIDÉO` → `VIDÉO` et `MÉDIAS & OPTIQUE` → `MÉDIAS & DISQUES` ;
- `SYSTEM_EXTENSIONS` et `SYSTEM_ABOUT` utilisent désormais explicitement la géométrie des sous-pages Système.

Le binaire `payload/flex/bin/flex-launcher` a été reconstruit depuis les sources de ce worktree afin que le chemin normal d'installation déploie effectivement la correction. SHA-256 : `ee1b2a2940eae383d19880904f2e6e713cdc926022d559246b2dcac984641e4b`. Sa métadonnée schema 1 de worktree porte le fingerprint source exact `79db448d3f2f9569c7b15c75c68fb175db8fa6c6ef90b1eec70a57e9f247f715` et ne prétend pas être un artifact exact-commit. Le futur build officiel devra comme prévu reconstruire Flex et produire la provenance schema 2 depuis son commit exact.

## Vérifications

- compilation Python des quatre composants modifiés et du nouveau test : PASS ;
- registre + inventaire générique : **32 PASS, 1 SKIP** (`OBSOLETE_FROZEN_SOURCE_IDENTITY`, historique et non promu) ;
- suite plugin P2/protected UI : **232 PASS, 10 SKIP** historiques ;
- modèle/rendu Système : **26 PASS** ;
- génération/session Flex voisine : **27 PASS** ;
- gate combiné registre/inventaire/Système/KDE launcher/About : **76 PASS, 1 SKIP** ;
- aperçu 1920×1080 rendu et inspecté : lisible, `plugin.bluray` 0.10.0 désactivé avec hooks et dépendance déclarée ;
- build CMake Flex depuis la source modifiée : PASS ;
- UI compacte/About/polish : **21 PASS** ;
- devctl et cohérence de construction/artifact : **77 PASS** ;
- lifecycle Flex/1.3.1 : **26 PASS** ;
- binaire payload, SHA de métadonnée et fingerprint source : concordants ;
- `git diff --check` : PASS après consolidation documentaire.

Les ensembles se recouvrent et ne doivent pas être additionnés. Le gate canonique complet 2284/18 de 1.3.1 n'a pas été rejoué pour cette tranche.

## Déploiement borné sur `.229`

Prévol du 2026-10-11 : l'hôte local porte bien `192.168.1.229/24`, aucun `mpv` n'est actif, les verrous globaux et DVD sont libres, une seule instance Flex et un seul moniteur optique sont présents, et Doctor est `READY`. L'installation précédente est `1.3.1-rc2-validator` avec le binaire Flex qualifié SHA-256 `7d8ce4fb5cadf145ad9053282288dd352b4a09bf47bfb5cf705910ccc06d4f79`.

Snapshot de sécurité créé avant mutation : `/home/steve/dev/snapshots/openhtpc-pre-plugin-system-20261011T070104Z`, 408 fichiers, manifeste SHA-256 `fbd2decc1397695cfc4f5d6143df602a5ae9c25d2d84e9aca9a7430b98474d75`. Le candidat dirty-worktree est conservé sous `/home/steve/OpenHTPC/validator-builds/OpenHTPC-1.3.1-plugin-system-validator-20261011T0702Z`. Il porte une identité explicitement non officielle `1.3.1-plugin-system-validator` / `plugin-system-worktree-validator`, le HEAD de base, le status, le patch binaire et un manifeste de 616 fichiers vérifié ; SHA-256 du manifeste : `406b0a703a2b2dd0261828b4116e5e7da1867533a2a8454c280cd90d13f8ae79`.

`./update.sh --check` : PASS. `./update.sh` : PASS, Hardware Passport conservé, runtime régénéré et session relancée. Le premier Doctor, lu pendant la fenêtre normale de régénération, était transitoirement `DEGRADED` sans PID Flex et voyait encore l'ancienne configuration à dix entrées ; aucun échec persistant n'en est déduit. Après stabilisation, les preuves installées sont :

- version/build : `1.3.1-plugin-system-validator` / `plugin-system-worktree-validator` ;
- binaire Flex installé SHA-256 `ee1b2a2940eae383d19880904f2e6e713cdc926022d559246b2dcac984641e4b` ;
- moteur de session installé SHA-256 `2ad752e55e01cfbd1a8ccce5b186ec6cdd9a1144c1a51c4996c220c528e9f610` ;
- session autoritaire `session-20261011T070213-1556789`, Flex PID `1557135`, génération UI `440` ;
- exactement une instance Flex et un moniteur optique, aucun `mpv`, verrous playback/DVD libres ;
- Doctor `READY`, runtime ownership `PASS`, Wayland/KDE `RUNNING` ;
- configuration publiée avec exactement onze entrées : `VIDÉO`, `MÉDIAS & DISQUES`, `EXTENSIONS` en entrée 8 et `RETOUR` en entrée 11.

Le code et la configuration compacte sont donc **INSTALLED / SOFTWARE-VERIFIED** sur `.229`.

### Validation physique opérateur

Steve confirme ensuite sur le téléviseur de `.229` que tout est correct et « impeccable ». Ce retour qualifie physiquement le point esthétique demandé : les onze catégories Système, `RETOUR` inclus, sont visibles sur une seule page sans scroll obligatoire, et la réduction coordonnée des lignes, icônes, textes et libellés reste harmonieuse. Le jalon **rampe Système compacte `.229`** est donc **PHYSICALLY_QUALIFIED**. Cette validation porte sur la présentation de la rampe ; elle ne qualifie pas les futures fonctions de résolution de dépendances ou d'actions plugins, encore non implémentées.

## Limites et prochaine action

- La page affiche les dépendances **déclarées** ; leur résolution générique et l'identification précise des dépendances manquantes restent **NON IMPLÉMENTÉES**.
- La vérité Doctor/capabilities commune, l'action média bornée et le handler média générique restent **NON IMPLÉMENTÉS**.
- Aucun contrôle d'activation n'est ajouté à Flex dans cette tranche ; l'API persistante `set_enabled` existante est seulement exercée hermétiquement.
- État installé `.229` : **INSTALLED / SOFTWARE-VERIFIED**.
- Présentation réelle sur téléviseur et absence de scroll : **PHYSICALLY_QUALIFIED sur `.229`**, confirmation de Steve le 2026-10-11.

Prochaine action bornée recommandée : définir une entrée de faits Core explicite pour résoudre les dépendances plugin/capability/system sans probe implicite dans le registre, puis réutiliser cette vérité pour Doctor et Système avant d'ouvrir le contrat d'action média.

## Worktree transmis

Modifiés :

- `OPENHTPC-PLUGIN-ROADMAP.md`
- `OPENHTPC-ROADMAP.md`
- `docs/OPENHTPC_CONTINUITY.md`
- `payload/openhtpc-plugin-registry.py`
- `payload/openhtpc-session-engine.py`
- `payload/openhtpc-system-model.py`
- `payload/openhtpc-ui.py`
- `payload/flex/BUILD-METADATA.json`
- `payload/flex/bin/flex-launcher`
- `tests/test_plugin_framework_p2_registry.py`
- `tests/test_rc7_about_ux.py`
- `vendor/flex-launcher/src/launcher.c`

Non suivis :

- `docs/continuity/2026-10-11-plugin-framework-system-inventory.md`
- `tests/test_plugin_framework_generic_system.py`

Les payloads modifiés sont déjà couverts par les autorités d'installation et `payload/managed-files.txt`; aucun nouveau payload de production n'a été ajouté. Le binaire Flex distribué représente désormais la source modifiée. HEAD reste `975402945376618db56e29945074ea30ddcd2cb8`. Aucun commit n'a été créé. Aucun push, tag ni publication n'a été effectué.
