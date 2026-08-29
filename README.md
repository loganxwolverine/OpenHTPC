<img width="1254" height="1254" alt="ChatGPT Image 12 août 2026, 14_42_40" src="https://github.com/user-attachments/assets/696bd719-3e75-4512-bc53-e0f5527436f1" />
# 🎬 Qu'est-ce qu'OPENHTPC ?

**OPENHTPC est un projet open source visant à transformer un PC sous Linux en véritable système Home Cinema de salon.**

L'objectif n'est pas simplement de lancer un lecteur multimédia dans une distribution Linux classique.

OPENHTPC cherche à proposer une expérience pensée dès le départ pour une utilisation **depuis un canapé, sur un téléviseur ou un vidéoprojecteur**, avec une interface simple, lisible et adaptée au Home Cinema.

Le projet repose actuellement sur **Fedora KDE Plasma / Wayland**, avec une interface pilotable depuis le salon et une chaîne de lecture basée notamment sur **MPV**.

---

## 🏠 Une interface pensée pour le salon

OPENHTPC masque autant que possible la complexité habituelle d'un environnement Linux de bureau.

Une fois lancé, l'utilisateur accède directement aux principales fonctions Home Cinema :

- lecture des médias locaux ;
- gestion des sources multimédias ;
- lecture de DVD ;
- détection des disques optiques ;
- récupération de métadonnées ;
- gestion du système ;
- arrêt d'OPENHTPC et retour propre vers KDE.

L'objectif est de pouvoir utiliser la machine comme un **véritable appareil Home Cinema**, et non comme un PC nécessitant constamment clavier, terminal ou manipulations techniques.

---

## 🎞️ Une base de lecture centrée sur MPV

La lecture vidéo repose principalement sur **MPV**, choisi pour sa flexibilité, ses performances et ses possibilités de configuration.

OPENHTPC génère automatiquement une configuration adaptée à la machine sur laquelle il est installé.

Cette génération prend notamment en compte :

- le GPU ;
- les capacités de décodage matériel ;
- VA-API ;
- Vulkan ;
- les capacités vidéo disponibles ;
- les politiques audio ;
- les caractéristiques détectées par OPENHTPC.

Le but est d'éviter autant que possible les configurations MPV génériques copiées d'une machine à une autre.

---

## 🧬 Hardware Passport

OPENHTPC utilise un système appelé **Hardware Passport**.

Lors de l'installation ou de la configuration, OPENHTPC analyse la machine afin de construire une représentation de ses capacités matérielles.

Ces informations servent ensuite à générer le runtime adapté au matériel réellement présent.

Cela permet notamment à OPENHTPC de distinguer différentes configurations Intel, AMD ou NVIDIA et d'adapter son comportement lorsque cela est nécessaire.

---

## 💿 Médias locaux et supports physiques

OPENHTPC ne se limite pas aux fichiers stockés sur un disque.

Le projet vise progressivement à réunir plusieurs formes de médias dans une même expérience :

- fichiers MKV et autres médias locaux ;
- bibliothèques stockées sur le réseau ;
- DVD physiques ;
- Blu-ray ;
- UHD lorsque leur identification et leur lecture peuvent réellement être démontrées et qualifiées.

Une attention particulière est portée à la fiabilité des actions.

Lorsqu'un média est affiché dans l'interface, OPENHTPC utilise un système d'identités et de tokens afin de s'assurer que l'action demandée correspond bien au média, à la source et à la génération actuellement autorisés.

---

## 🎬 Métadonnées TMDb

OPENHTPC peut également utiliser **TMDb** pour enrichir l'expérience autour des supports physiques.

Lorsqu'un disque est reconnu, OPENHTPC peut récupérer notamment :

- le titre du film ;
- son année ;
- son affiche ;
- différentes métadonnées associées.

Lorsque l'identification automatique n'est pas suffisante, une recherche manuelle peut également être proposée.

L'association choisie peut ensuite être mémorisée afin de reconnaître plus facilement le même disque lors d'une prochaine insertion.

---
<img width="1920" height="1080" alt="Screenshot 2026-08-27 19-24-44" src="https://github.com/user-attachments/assets/f6708a9d-4ddc-4267-ab6f-f7c0f6a15310" />

## 🔊 Une approche Home Cinema de l'audio

OPENHTPC ne considère pas l'audio comme un simple détail de lecture.

Le projet prévoit une véritable politique audio adaptée aux environnements Home Cinema.

Le mode **PCM** constitue actuellement la base la plus sûre et la plus largement applicable.

Le bitstream peut également être utilisé lorsque le matériel et la chaîne audio le permettent.

Les formats sont progressivement qualifiés physiquement plutôt que simplement déclarés comme fonctionnels parce qu'ils existent dans une configuration logicielle.

---

## 🩺 OPENHTPC Doctor

OPENHTPC intègre son propre outil de diagnostic :

```bash
openhtpc doctor

```

Doctor permet de vérifier l'état général de l'installation et de plusieurs composants importants du système.

Sur une machine correctement configurée et prête à utiliser OPENHTPC, l'objectif est d'obtenir :

```text
Overall: READY
```

Cela permet également de faciliter considérablement les diagnostics lorsqu'un utilisateur rencontre un problème.

---

<img width="1920" height="1080" alt="Screenshot 2026-08-15 16-13-14" src="https://github.com/user-attachments/assets/29450bb7-adb5-4600-8474-eb80627c63bf" />

## 🔄 Installation et mises à jour

OPENHTPC dispose de son propre mécanisme d'installation et de mise à jour.

Le projet cherche à éviter les procédures composées de dizaines de commandes manuelles.

Lors d'une installation, OPENHTPC peut notamment :

- vérifier l'environnement ;
- installer les dépendances nécessaires avec l'accord de l'utilisateur ;
- créer le Hardware Passport ;
- générer le runtime ;
- installer l'interface ;
- préparer la configuration ;
- configurer son démarrage dans la session KDE.

Lors d'une mise à jour, les données persistantes de l'utilisateur sont conservées et le runtime peut être régénéré afin d'éviter de conserver une configuration devenue obsolète.

Une installation existante peut être mise à jour directement depuis une archive OPENHTPC :

```bash
./update.sh
```

Il n'est normalement **pas nécessaire de désinstaller la version précédente** avant d'effectuer une mise à jour.

Après installation ou mise à jour, deux commandes permettent de contrôler rapidement l'état du système :

```bash
openhtpc version
```

et :

```bash
openhtpc doctor
```

---

# 🧩 Un Core fixe et des plugins

C'est l'un des principes fondamentaux du projet.

OPENHTPC n'a pas vocation à devenir un énorme logiciel monolithique contenant toutes les fonctions imaginables.

L'architecture recherchée est plutôt :

```text
OPENHTPC CORE
│
├── Interface
├── Hardware Passport
├── Runtime
├── MEDIA
├── Audio
├── Diagnostic
├── Cycle de vie
└── Fonctions essentielles
        │
        ├── Plugin Blu-ray
        ├── Plugin UHD
        ├── Plugin Cinema
        ├── Plugin Streaming
        ├── Plugin Gaming
        └── ...
```

Le **Core** doit rester aussi stable, prévisible et qualifiable que possible.

Les fonctionnalités plus spécialisées viendront progressivement sous forme de **plugins**, afin que chacun puisse construire l'OPENHTPC correspondant réellement à son installation.

Cette philosophie permet également d'éviter qu'une nouvelle fonctionnalité spécialisée fragilise l'ensemble du système.

---

## 🎯 Pourquoi créer OPENHTPC ?

Il existe déjà Kodi, MPV, VLC et de nombreuses distributions Linux multimédias.

OPENHTPC n'a pas pour objectif de remplacer chacun de ces projets.

L'idée est différente :

> **Assembler les meilleures briques disponibles dans un environnement Home Cinema Linux cohérent, automatisé et réellement pensé pour le salon.**

OPENHTPC cherche notamment à résoudre les problèmes qui apparaissent lorsque l'on construit soi-même un HTPC Linux :

- configuration des pilotes ;
- accélération matérielle ;
- comportement de MPV ;
- audio HDMI ;
- gestion des lecteurs optiques ;
- métadonnées ;
- retour propre vers l'interface ;
- changements de matériel ;
- mises à jour ;
- diagnostics ;
- cohérence entre l'interface et le lecteur.

L'utilisateur ne devrait pas avoir besoin de comprendre toute cette chaîne technique simplement pour regarder un film.

---

## 🐧 Pourquoi Linux ?

Parce qu'un HTPC ne devrait pas nécessairement devenir obsolète simplement parce que son système d'exploitation commercial ne le supporte plus.

Linux permet de construire une plateforme :

- ouverte ;
- modifiable ;
- documentable ;
- durable ;
- indépendante d'un constructeur ;
- capable de fonctionner sur du matériel très différent.

OPENHTPC s'inscrit pleinement dans cette philosophie.

L'idée est aussi de pouvoir **réutiliser du matériel que l'on possède déjà**, plutôt que d'imposer une plateforme matérielle unique.

---

# 🛋️ Une appliance Home Cinema plutôt qu'un simple logiciel

À terme, OPENHTPC doit se comporter davantage comme un **appareil Home Cinema** que comme une application Linux traditionnelle.

L'utilisateur allume son PC.

Fedora démarre.

La session KDE s'ouvre.

OPENHTPC se lance automatiquement.

L'utilisateur retrouve alors son interface Home Cinema :

```text
ALLUMAGE
   ↓
Fedora
   ↓
KDE Plasma
   ↓
OPENHTPC
   ↓
HOME
   ↓
Films / DVD / Médias / Plugins
```

Le bureau Linux reste disponible lorsque cela est nécessaire, mais il ne doit pas être au centre de l'expérience quotidienne.

OPENHTPC peut être quitté proprement afin de revenir vers KDE.

---

# 🔐 Fiabilité avant fonctionnalités

Un autre principe important d'OPENHTPC consiste à ne pas confondre :

**« le code sait théoriquement le faire »**

et :

**« nous avons réellement démontré que cela fonctionne ».**

Les différentes fonctions sont donc progressivement :

1. implémentées ;
2. testées automatiquement ;
3. testées sur du matériel réel ;
4. qualifiées ;
5. seulement ensuite annoncées comme supportées.

Cette approche est particulièrement importante pour :

- l'accélération matérielle ;
- l'audio bitstream ;
- les lecteurs optiques ;
- Blu-ray et UHD ;
- HDR ;
- les pilotes GPU ;
- les comportements dépendant du matériel.

OPENHTPC préfère annoncer une limitation plutôt que prétendre supporter une fonction qui n'a pas encore été réellement validée.

---

# 🧪 Plusieurs niveaux de validation

Le développement d'OPENHTPC utilise plusieurs niveaux de validation.

### Tests automatisés

Ils permettent de vérifier les comportements internes du Core, du runtime, de MEDIA, des actions et des différents composants.

### Tests physiques

Les versions importantes sont également installées sur de véritables machines.

Cela permet de vérifier des éléments impossibles à démontrer uniquement avec des tests logiciels :

- affichage réel ;
- audio HDMI ;
- comportement du GPU ;
- lecteur DVD ;
- téléviseur ou amplificateur ;
- démarrage KDE ;
- retour vers le bureau ;
- mise en veille ;
- interactions avec les périphériques.

### Fresh Install

Certaines versions sont également testées depuis une installation Fedora totalement fraîche afin de vérifier que le fonctionnement ne dépend pas accidentellement de fichiers provenant d'une ancienne version.

---

# 🚧 Un projet encore en développement

OPENHTPC est un projet actif.

Les versions **Release Candidate** sont justement là pour permettre de tester le système sur davantage de configurations matérielles avant de considérer certaines fonctions comme définitivement stabilisées.

Certaines fonctions sont déjà physiquement qualifiées.

D'autres sont encore expérimentales, en développement ou volontairement reportées afin de ne pas fragiliser le Core.

Parmi les futurs chantiers figurent notamment :

- amélioration du framework de plugins ;
- qualification audio avancée ;
- sélection intelligente des pistes audio ;
- sélection automatique du français / TrueFrench ;
- gestion des sous-titres français forcés ;
- adaptation automatique de la fréquence d'affichage ;
- HDR et tone mapping ;
- amélioration de la lecture Blu-ray et UHD ;
- amélioration de l'expérience TMDb ;
- fonctions Cinema avancées ;
- amélioration de l'expérience utilisateur ;
- prise en charge et qualification d'un plus grand nombre de configurations matérielles.

---

# ❤️ La philosophie OPENHTPC

OPENHTPC repose sur quelques principes simples.

### ♻️ Utiliser ce que l'on possède déjà

Un ancien PC, une workstation, un Mini PC ou une machine récupérée peut encore devenir une excellente plateforme Home Cinema.

### 🧱 Un Core stable

Les fonctions essentielles doivent être fiables et prévisibles.

### 🧩 Des plugins pour aller plus loin

Les fonctions spécialisées doivent pouvoir évoluer sans transformer le Core en logiciel monolithique.

### 🔍 Ne pas masquer les problèmes

L'automatisation doit simplifier l'expérience sans empêcher le diagnostic.

Des outils comme :

```bash
openhtpc doctor
```

doivent permettre de comprendre rapidement l'état du système.

### ✅ Ne revendiquer que ce qui a été démontré

Une fonction présente dans le code n'est pas automatiquement considérée comme qualifiée.

### 🐧 Faire de Linux une véritable plateforme Home Cinema

Pas simplement un bureau Linux sur lequel on lance occasionnellement un film.

Mais une expérience conçue autour du téléviseur, du vidéoprojecteur, de l'amplificateur et du canapé.

---

# 🎯 En une phrase

> **OPENHTPC est une plateforme Home Cinema open source basée sur Linux, conçue pour transformer un PC en véritable lecteur multimédia de salon, avec une interface dédiée, une configuration adaptée au matériel et une architecture évolutive basée sur un Core stable et des plugins.**

---

# 🔗 Projet

Le développement d'OPENHTPC est public et open source.

Les versions, Release Candidates, notes de publication et sources du projet sont disponibles sur GitHub :

**https://github.com/loganxwolverine/OpenHTPC**

