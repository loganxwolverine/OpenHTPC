# OPENHTPC — Roadmap Plugins et modularité

Dernière mise à jour : 2026-10-10 (Europe/Brussels).
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

1. **Inventaire Système / Extensions** : liste issue du registre réel, avec nom, version, état, capacités, dépendances manquantes et diagnostic. Aucun tableau codé en dur ne doit faire autorité.
2. **Contrat générique d'actions média** : permettre à un plugin AVAILABLE de proposer une action bornée sur une fiche/disque (`EXTRAIRE LE DISQUE`, `MENU DVD`, etc.) sans injecter de commande shell arbitraire dans Flex.
3. **Contrat générique de media handler** : un plugin peut déclarer qu'il sait traiter un type de média supplémentaire ; Core reste propriétaire de la détection matérielle, du lifecycle, de la validation et du dispatch sécurisé.
4. **Activation/désactivation maîtrisée** : l'état actif doit être explicite et persistant ; plugin absent, cassé ou incompatible = fonctionnalité non exposée, Core sain.
5. **Doctor/capabilities unifiés** : chaque plugin publie une vérité opérationnelle compréhensible (`Prêt`, `Dépendance manquante`, `Désactivé`, `Incompatible`) réutilisée par Système.
6. **Installation séparée du Core** : les plugins utilisateur restent hors du nettoyage des fichiers gérés par les mises à jour OPENHTPC.

## Extensions prioritaires envisagées

### 1. Protected Optical / Blu-ray / UHD

Base existante : `plugin.bluray`.

Objectif produit : OPENHTPC doit pouvoir indiquer clairement si le support Blu-ray/UHD est installé, activé et prêt à tenter une lecture protégée, avec visibilité des prérequis (`libbluray`, `libaacs`, éventuel `libbdplus`, présence de la configuration AACS utilisateur).

Le Core conserve la détection matérielle et les faits de capacité. Le plugin reste l'autorité de la fonctionnalité optionnelle et de ses contributions UI/Doctor selon les frontières P2.

L'ancien outil Fedora AACS/KEYDB peut être traité comme un **provisionneur séparé de prérequis utilisateur** ou comme une étape d'installation associée, mais ne doit pas être confondu avec le registre de capacités lui-même. OPENHTPC doit pouvoir constater le résultat sans incorporer de secrets dans ses rapports.

### 2. Extraction de disque / archivage local

Nom de travail : `plugin.disc-extract`.

Objectif UX : lorsqu'un DVD/Blu-ray/UHD compatible est présent et que le backend du plugin est AVAILABLE, la fiche peut proposer une action du type **EXTRAIRE LE DISQUE** en plus de la lecture.

Le plugin peut utiliser un backend spécialisé (par exemple MakeMKV si présent/configuré) et une destination explicitement choisie/configurée. Le Core conserve le dispatch sécurisé, le suivi du processus, le retour UI et la protection contre les opérations concurrentes.

État attendu dans Système : installé/activé, backend disponible, destination configurée, disponibilité pour le média courant.

### 3. Lecture HD DVD

Nom de travail : `plugin.hddvd`.

Cible matérielle de qualification : lecteur HD DVD Xbox 360 en USB et disques HD DVD originaux.

Objectif : étendre la classification optique et le handler de lecture sans transformer le Core DVD/Blu-ray en code spécifique HD DVD. Le plugin doit publier sa capacité réelle et n'exposer **LIRE LE HD DVD** que lorsque le média et les dépendances nécessaires sont effectivement reconnus.

Toute gestion de clés/configuration nécessaire reste séparée des rapports/support bundles et doit respecter les mêmes règles de confidentialité que la configuration AACS existante.

### 4. Navigation menus DVD

Nom de travail : `plugin.dvd-menu`.

Objectif : préserver le chemin actuel « insérer → lire le film » comme comportement simple par défaut, tout en permettant à ceux qui le souhaitent d'ouvrir le menu DVD et d'accéder aux bonus, chapitres ou contenus supplémentaires.

`libdvdnav` est déjà une dépendance connue du socle Fedora, mais l'existence de la bibliothèque ne signifie pas que l'UX menus est aujourd'hui qualifiée. Le plugin devra posséder le comportement optionnel, tandis que Core garde le lifecycle, le lecteur physique et le retour sûr vers Flex.

## Ordre de travail retenu

### Étape 0 — fermer OPENHTPC 1.3.1

Priorité actuelle. Aucun élargissement du framework plugins ne doit retarder la stabilisation 1.3.1, la qualification de `.67`, le passage sur `.229` et la promotion finale.

### Étape 1 — généraliser le framework P2

Premier chantier après 1.3.1 : rendre le registre réellement générique dans le produit, notamment **Système → Extensions/Plugins**, vérité Doctor commune, contribution d'actions média bornées et contrat de handler générique.

Le critère de réussite n'est pas d'avoir beaucoup de plugins : c'est qu'un plugin factice minimal puisse être installé, détecté, activé, affiché, contribuer une action autorisée puis être désactivé/retiré sans laisser de résidu ni casser Core.

### Étape 2 — qualifier `plugin.bluray` comme plugin de référence

Utiliser la fonctionnalité protégée déjà très avancée pour prouver la généralisation : état Système cohérent, feature gating, UI contribution, négatifs absent/désactivé/cassé, et validation physique Blu-ray/UHD.

### Étape 3 — plugins concrets

Ordre initial proposé, révisable par Steve selon le matériel disponible :

1. `plugin.dvd-menu` — périmètre borné et `libdvdnav` déjà présent ;
2. `plugin.disc-extract` — nouvelle action et lifecycle long, excellent test de la modularité ;
3. `plugin.hddvd` — nouvelle famille média nécessitant qualification matérielle dédiée ;
4. enrichissements futurs (services média, intégrations réseau, autres formats) uniquement après validation du modèle.

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

**DIRECTION CONFIRMÉE — IMPLEMENTATION GÉNÉRIQUE DIFFÉRÉE APRÈS 1.3.1.**

Le framework n'est donc pas abandonné. Au contraire, la fin de la base 1.3.1 doit marquer le moment où OPENHTPC cesse d'accumuler des fonctions spécialisées dans Core et commence à faire vivre cette architecture de plugins comme mécanisme normal d'extension.
