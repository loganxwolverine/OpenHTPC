# OPENHTPC — Roadmap Plugins et modularité

Dernière mise à jour : 2026-10-11 (Europe/Brussels).
Responsable des décisions produit et validations physiques : Steve Dehanne.

## Vision produit

OPENHTPC doit conserver un Core stable et volontairement limité, puis permettre d'ajouter des fonctions spécialisées sous forme de plugins détectables, activables et diagnostiquables sans modifier directement le Core.

Un plugin correctement installé doit pouvoir être identifié par OPENHTPC, exposer un état clair dans Système, déclarer ses dépendances et capacités, contribuer uniquement aux zones autorisées de l'interface, et échouer de manière isolée sans casser la lecture de base ni l'interface.

Le principe UX cible est simple : installation/activation du plugin → détection par le registre → état visible dans Système → nouvelles actions exposées uniquement lorsque le plugin est réellement opérationnel.

## Socle déjà présent

Le dépôt contient déjà Plugin Framework P2 :

- registre déclaratif `openhtpc-plugin-registry.py` ;
- contrats bornés `openhtpc-plugin-contracts.py` ;
- manifests `openhtpc-plugin-v2` ;
- états `DISABLED`, `AVAILABLE`, `INCOMPATIBLE`, `BROKEN` et `NOT_INSTALLED` ;
- catégories `optical`, `media`, `service`, `presentation`, `system` ;
- hooks déclarés `capability`, `doctor`, `ui_menu`, `media_handler`, `dispatcher` ;
- emplacements XDG séparés pour plugins utilisateur, données, cache et état runtime ;
- `plugin.bluray` comme première implémentation first-party / référence de migration.

Le framework actuel protège volontairement les frontières : le Core conserve le matériel, les I/O, la sécurité des actions, le rendu Flex et l'exécution générique. Les plugins fournissent des contributions bornées et validées.

## Écart à combler après 1.3.1

Le socle P2 est réel mais reste fortement spécialisé autour de l'optique protégée. OPENHTPC n'offre pas encore l'expérience générique complète attendue pour les extensions futures.

À généraliser :

1. **Inventaire Système / Extensions** : inventaire et résolution générique implémentés et vérifiés logiciellement le 2026-10-11. La page est issue du registre résolu par Core et sépare provenance, activation et capacité observée. Elle n'appelle plus « installé » un manifest simplement fourni par le projet. Plugins, capabilities et dépendances système partagent des faits stricts et des motifs canoniques ; aucun tableau codé en dur ne fait autorité.
2. **Contrat générique d'actions média** : permettre à un plugin AVAILABLE de proposer une action bornée sur une fiche/disque (`OUVRIR LE MENU DVD`, `EXTRAIRE LE DISQUE`, etc.) sans injecter de commande shell arbitraire dans Flex.
3. **Installation depuis OPENHTPC** : présenter un catalogue first-party borné dans `Système → Extensions`, puis installer, activer, mettre à jour, désactiver ou retirer un paquet d'extension vérifié par une transaction Core-owned. Le catalogue ne confère aucun droit d'exécuter un script ou une commande arbitraire. Toute dépendance Fedora passe par un plan explicite, le consentement utilisateur et les autorités d'installation existantes ; OPENHTPC ne remplace pas le MPV fourni par Fedora.
4. **Contrat générique de media handler** : un plugin peut déclarer qu'il sait traiter un type de média supplémentaire ; Core reste propriétaire de la détection matérielle, du lifecycle, de la validation et du dispatch sécurisé.
5. **Activation/désactivation maîtrisée** : l'état actif doit être explicite et persistant ; plugin absent, cassé ou incompatible = fonctionnalité non exposée, Core sain.
6. **Doctor/capabilities unifiés** : la vérité de disponibilité et son motif sont désormais calculés une fois dans le registre résolu puis consommés à l'identique par Doctor et Système. L'enrichissement futur des producteurs de faits reste explicite et Core-owned.
7. **Installation séparée du Core** : les plugins utilisateur restent hors du nettoyage des fichiers gérés par les mises à jour OPENHTPC.

## Extensions prioritaires envisagées

### 1. Navigation menus DVD — premier vrai plugin utilisateur

Nom retenu : `plugin.dvd-menu`.

Décision produit du 2026-10-11 : **Navigation menus DVD** devient la première extension réellement installable depuis OPENHTPC et la première preuve complète du framework générique. Le chemin actuel « insérer → lire le film principal » reste disponible et reste le comportement simple par défaut. Après installation et seulement lorsque toutes les capacités sont satisfaites, la fiche du DVD ajoute **OUVRIR LE MENU DVD** pour accéder aux chapitres, bonus, langues et autres choix réellement présents sur le disque.

Faisabilité amont, vérifiée le 2026-10-11 :

- `OFFICIAL` — le manuel stable MPV 0.41 indique explicitement que les menus DVD ne sont pas pris en charge ; le payload OPENHTPC actuel utilise donc correctement `dvd://longest` et ne doit pas recevoir `--disc-menu` ;
- `OFFICIAL` — le support des menus DVD/Blu-ray a été fusionné dans MPV `master` le 2026-08-25 par la PR amont `#18080`, ciblée pour MPV 0.42 ; le manuel `master` documente `--disc-menu`, `dvd://menu`, la commande `discnav` et ses actions de navigation ;
- `REPO_FACT` — OPENHTPC 1.3.1 est qualifié avec MPV 0.41 et `libdvdnav`; cette présence ne rend pas les menus disponibles ;
- `HYPOTHESIS` — l'intégration devrait pouvoir réutiliser le dispatcher DVD, la politique MPV, le matching de fréquence, l'audio et le lifecycle exact-child existants, mais cela doit être prouvé par tests et lectures physiques.

Conséquence : le plugin est **FAISABLE SOUS CONDITION**, mais **BLOQUÉ POUR UNE ACTIVATION EFFECTIVE SUR MPV 0.41**. OPENHTPC ne distribuera pas une nightly MPV et ne remplacera pas le paquet Fedora. Le gate d'activation devra constater la capacité runtime réelle — option `disc-menu`, commande `discnav`, backend `dvdnav` et dépendances — plutôt que faire confiance au seul numéro de version.

Critères de réussite :

1. entrée **Navigation menus DVD** visible dans le catalogue Extensions avec provenance, version, état et motif ;
2. installation first-party déclenchée explicitement depuis OPENHTPC, vérifiée, atomique et réversible ;
3. activation refusée proprement si le MPV effectif ne fournit pas les primitives de menu ou si `libdvdnav` est absent ;
4. contribution déclarative de **OUVRIR LE MENU DVD**, sans commande shell fournie par le plugin ;
5. lancement par Core sous le même verrou et le même suivi exact-child que la lecture DVD actuelle ;
6. navigation clavier, souris et contrôleur qualifiée sans permettre de contourner le garde lifecycle ;
7. sortie réelle de MPV, restauration Flex et état runtime canonique vérifiés ;
8. matrice physique sur plusieurs DVD PAL/NTSC et menus simples, animés, multi-pages/multilingues ; un disque qui fonctionne ne généralise pas la compatibilité ;
9. désactivation, retrait, échec d'installation et mise à jour interrompue ne laissent ni action fantôme ni résidu actif ;
10. aucune modification implicite de Magnificence, de la politique audio ou du chemin **LIRE LE DVD** existant.

Sources amont : [manuel MPV stable](https://mpv.io/manual/stable/), [manuel MPV master](https://mpv.io/manual/master/) et [PR MPV #18080](https://github.com/mpv-player/mpv/pull/18080).

### 2. Protected Optical / Blu-ray / UHD

Base existante : `plugin.bluray`.

Objectif produit : sous le libellé public neutre **Support optique avancé**, OPENHTPC indique séparément que l'extension est fournie par le projet, que la détection du prérequis externe est automatique et que le système est ou non prêt à tenter une lecture protégée. `READY_TO_ATTEMPT` ne garantit jamais la lecture d'un support donné.

Le Core conserve la détection matérielle et les faits de capacité. Le plugin reste l'autorité de la fonctionnalité optionnelle et de ses contributions UI/Doctor selon les frontières P2.

Décision opérateur du 2026-10-11 : pour ce prérequis uniquement, l'utilisateur obtient et exécute lui-même son provisionneur externe, hors OPENHTPC. OPENHTPC ne fournit, ne lie, ne télécharge, n'exécute, ne met à jour, ne copie, ne lit, n'analyse et ne modifie ni ce provisionneur ni une base de clés utilisateur. Au prochain rafraîchissement canonique des capacités — dont celui de l'installation/mise à jour — Core constate uniquement la présence métadonnée attendue et la page affiche soit **Prérequis externe absent**, soit **Prérequis externe détecté — Prêt à tenter la lecture**. Une surveillance continue pendant une session déjà ouverte n'est pas implémentée.

### 3. Extraction de disque / archivage local

Nom de travail : `plugin.disc-extract`.

Objectif UX : lorsqu'un DVD/Blu-ray/UHD compatible est présent et que le backend du plugin est AVAILABLE, la fiche peut proposer une action du type **EXTRAIRE LE DISQUE** en plus de la lecture.

Le plugin peut utiliser un backend spécialisé (par exemple MakeMKV si présent/configuré) et une destination explicitement choisie/configurée. Le Core conserve le dispatch sécurisé, le suivi du processus, le retour UI et la protection contre les opérations concurrentes.

État attendu dans Système : installé/activé, backend disponible, destination configurée, disponibilité pour le média courant.

### 4. Lecture HD DVD

Nom de travail : `plugin.hddvd`.

Cible matérielle de qualification : lecteur HD DVD Xbox 360 en USB et disques HD DVD originaux.

Objectif : étendre la classification optique et le handler de lecture sans transformer le Core DVD/Blu-ray en code spécifique HD DVD. Le plugin doit publier sa capacité réelle et n'exposer **LIRE LE HD DVD** que lorsque le média et les dépendances nécessaires sont effectivement reconnus.

Toute gestion de clés/configuration nécessaire reste séparée des rapports/support bundles et doit respecter les mêmes règles de confidentialité que la configuration AACS existante.

## Ordre de travail retenu

### Étape 0 — conserver le gel OPENHTPC 1.3.1

Les gates techniques 1.3.1 sont fermés et l'artifact exact-commit est vérifié. Aucun chantier plugin ne vaut autorisation de push, tag ou publication, et aucune régression du lifecycle qualifié n'est acceptable.

### Priorité 1 — contrat générique d'action média bornée

Cartographier les contributions P2 existantes et définir une action déclarative allowlistée. Core valide l'identifiant d'action et construit lui-même le dispatch ; le plugin ne fournit jamais une ligne de commande. Un plugin factice doit pouvoir contribuer une action, puis être désactivé ou rendu indisponible sans laisser l'action visible.

### Priorité 2 — installation et cycle de vie des extensions first-party

Définir le catalogue, le format de paquet, les empreintes, la compatibilité API, la transaction atomique, le rollback et les états `NOT_INSTALLED`, `INSTALLED_DISABLED`, `AVAILABLE`, `INCOMPATIBLE` et `BROKEN`. L'installation est initiée depuis `Système → Extensions`, mais reste exécutée par une autorité Core bornée. Une dépendance système ne peut être installée qu'après plan visible et consentement explicite ; aucun manifest ne peut injecter un dépôt, une URL ou une commande shell.

### Priorité 3 — gate de compatibilité MPV pour les menus DVD

Sur une version Fedora stable candidate, vérifier par introspection runtime la présence de `--disc-menu`, `dvd://menu`, `discnav` et du backend DVD. MPV 0.41 doit rester explicitement `INCOMPATIBLE`, sans faux bouton. Un build amont isolé peut servir à l'étude technique, jamais être promu comme dépendance produit ou installé par OPENHTPC sans décision d'architecture distincte.

Cette dépendance fait l'objet d'une **veille obligatoire mensuelle**, ainsi que d'un relevé supplémentaire lors de chaque annonce/release MPV et avant la préparation d'un candidat OPENHTPC. Chaque relevé daté consulte uniquement les sources officielles : release et jalon MPV 0.42, manuel stable, paquets Fedora 44 et branches Fedora ultérieures/Rawhide, puis capacités du binaire réellement installé. Les états ne sont pas interchangeables :

1. `UPSTREAM_NO_DATE` — développement ou jalon sans date officielle ;
2. `UPSTREAM_SCHEDULED` — date publiée officiellement, jamais déduite d'un pourcentage de jalon ;
3. `UPSTREAM_RELEASED` — tag stable MPV 0.42 publié ;
4. `FEDORA_CANDIDATE` — build/update Fedora disponible mais pas encore stable pour la cible ;
5. `FEDORA_STABLE` — paquet stable disponible pour la Fedora cible ;
6. `OPENHTPC_READY_TO_TEST` — introspection runtime et tests logiciels OPENHTPC satisfaits ;
7. `PHYSICALLY_QUALIFIED` — navigation réelle validée par Steve sur la matrice DVD prévue.

Relevé initial du 2026-10-11 : `UPSTREAM_NO_DATE`. Le jalon MPV 0.42 est ouvert sans échéance officielle ; Fedora 44 publie `mpv-0.41.0-5.fc44`, Fedora 45 `0.41.0-8.fc45` et Rawhide `0.41.0-9.fc46`. Aucune date de disponibilité ne peut donc être annoncée. Une progression amont ou Fedora n'autorise jamais une installation automatique.

### Priorité 4 — implémenter et qualifier `plugin.dvd-menu`

Le plugin DVD Menu est le premier vrai plugin utilisateur. Il exerce ensemble installation, activation, dépendances, contribution UI, handler borné, input, lifecycle et retrait. Sa promotion exige les négatifs logiciels et une qualification physique multi-disques.

### Priorité 5 — qualifier `plugin.bluray` comme référence migrée

La fonctionnalité optique protégée reste une excellente référence d'architecture, mais n'est plus présentée comme le premier plugin utilisateur installable. Elle doit prouver état Système cohérent, feature gating, contribution UI et négatifs absent/désactivé/cassé dans le framework généralisé, sans franchir la politique KEYDB.

### Priorité 6 — plugins suivants

1. `plugin.disc-extract` — nouvelle action et lifecycle long ;
2. `plugin.hddvd` — nouvelle famille média nécessitant qualification matérielle dédiée ;
3. enrichissements futurs uniquement après validation du modèle.

## Invariants à ne pas casser

- Aucun plugin ne monkey-patche Core ni ne remplace globalement la configuration mpv.
- Aucun plugin ne peut injecter une commande shell arbitraire dans Flex.
- Core reste propriétaire du lifecycle, de la sécurité des actions, des tokens/dispatchers, du rendu UI et de l'accès matériel générique.
- Une panne de plugin optionnel ne rend pas OPENHTPC globalement indisponible.
- L'absence du plugin n'expose pas silencieusement sa fonctionnalité par un fallback Core complet une fois la migration terminée.
- La section Système reflète le registre et les capacités réellement observées, jamais une simple liste statique.
- Toute extension touchant un média physique ou un backend externe exige tests logiciels puis validation physique appropriée.
- Les données sensibles/configurations de clés ne sont pas copiées dans les bundles diagnostics ni affichées en clair.

## Statut actuel

**PRIORITÉ 1 À OUVRIR — ACTION MÉDIA BORNÉE, PUIS INSTALLATION FIRST-PARTY ; `plugin.dvd-menu` EST LE PREMIER VRAI PLUGIN CIBLE.**

Le prévol post-migration du 2026-10-11 a donné **GO au circuit manuel Codex + CodeGraph sur `.79`**. La tranche suivante est maintenant terminée logiciellement : Core fournit au registre une structure `openhtpc-plugin-dependency-facts-v1` strictement validée, sans probe implicite ; le résolveur traite dépendances de plugins, capabilities et système, propage les indisponibilités, détecte les cycles et sépare `MISSING`, `UNKNOWN`, `INVALID` et `CYCLE`. Doctor et `Système → Extensions` projettent la même instance de registre et le même motif. Autopilot reste fermé comme attendu sur l'état canonique STALE et le worktree dirty ; cela n'autorise ni déploiement ni publication.

Le worktree ajoute `Système → Extensions`, alimenté à chaque rendu par le registre V2 sans exécuter les entrypoints. Le même plugin factice/réel est observé désactivé puis disponible après mutation explicite de l'état XDG ; un manifest invalide reste isolé et visible `BROKEN`. Les listes JSON mal typées, les faits malformés et `plugin_api` non entier échouent fermé. Après constat esthétique opérateur, la rampe `SYSTÈME` a été compactée spécifiquement : ses onze catégories, `RETOUR` inclus, tiennent sur une page sans densifier les menus Média ; les libellés longs deviennent notamment `VIDÉO` et `MÉDIAS & DISQUES`. Un candidat antérieur dirty-worktree explicitement non officiel est installé sur `.229` : Doctor READY, lifecycle autoritaire sain et configuration à onze entrées vérifiés. Steve confirme physiquement l'absence de scroll et l'harmonie du rendu sur le téléviseur. La nouvelle résolution n'a pas été déployée sur `.229` ou `.67` et ne fournit pas encore d'action média générique ; aucun I/O/lifecycle n'est transféré au plugin.

L'adaptation de présentation suivante est implémentée dans le dépôt et installée de manière bornée sur `.59` : le faux compteur « installée(s) » devient un inventaire des extensions fournies/ajoutées et capacités prêtes ; `plugin.bluray` est présenté comme **Support optique avancé** avec détection automatique du seul prérequis externe. Le mapping Core corrige `NOT_CONFIGURED` en dépendance absente au lieu de disponible. La détection reste strictement métadonnée ; aucun lien ni mécanisme d'acquisition/exécution n'est ajouté. Sur `.59`, l'état réel est actuellement **Prérequis externe absent** ; Doctor reste READY et Magnificence inchangé. `.229` n'a pas été modifié.

Preuves : `tests/test_plugin_framework_generic_system.py`, suites P2 protégées et Système, pages 1080p « absent »/« détecté » rendues et inspectées ; checkpoints `docs/continuity/2026-10-11-plugin-framework-system-inventory.md`, `docs/continuity/2026-10-11-plugin-dependency-resolution.md` et `docs/continuity/2026-10-11-extensions-protected-optical-readiness.md`.
