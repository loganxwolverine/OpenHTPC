# OPENHTPC 1.3.2 RC3 — Patina

**Candidat de publication EN PRÉPARATION — NON PUBLIÉ / Release Candidate IN PREPARATION — NOT PUBLISHED**

## Français

Cette RC3 prend pour base la RC2 publiée le 18 octobre 2026. Notre objectif est de consolider les améliorations d'ergonomie déjà développées, sans lancer de nouveau chantier ni modifier les recettes d'image Magnificence.

### Ce qui change

- **Accueil HOME :** un indicateur discret présente l'état de la liaison réseau et l'adresse IP locale lorsqu'elle est disponible. Une liaison active ne garantit pas l'accès à Internet.
- **Interface Flex :** navigation à la manette dans les menus HOME et MEDIA, en complément du clavier et des autres méthodes existantes.
- **Lecture MPV :** un profil SDL2 géré par OPENHTPC pour les films locaux et les DVD, avec lecture, recherche, volume et commandes de l'affichage Stats ainsi que de ses pages.
- **Installation et mise à jour :** ce profil de manette rejoint les fichiers gérés par l'installateur et le manifeste de désinstallation.
- **Stabilité :** conservation des corrections RC2 de génération optique, de régénération du menu DVD et de gestion des sessions HOME.

### Ce que nous avons vérifié

Le nouvel affichage HOME/IP et la navigation Flex à la manette ont été vérifiés physiquement sur le GEEKOM IT13 Max avant son retrait du projet. Des commandes MPV/DVD ont été essayées sur des configurations provisoires de QA. **Ces essais ne constituent pas une validation du paquet RC3 complet** ni de tous les modèles de manette.

Avant consolidation de l'identité RC3, le code source a passé **240 tests ciblés sur 240 le 22 octobre 2026**. Une campagne antérieure a réussi 321 tests ciblés, partiellement communs : ces chiffres ne représentent pas 561 tests distincts.

Il reste à faire : suite complète, fabrication de l'archive depuis un commit Git exact, installation propre, mise à niveau RC2 → RC3 et qualification physique sur une machine Fedora 44 KDE Plasma/Wayland différente du GEEKOM.

### Limitations

Aucun menu DVD interactif n'est promis. La grille MEDIA, la reprise de lecture, le choix d'autologin et l'étude Magnificence Full HD/Blu-ray restent hors de cette RC. Nous ne modifions pas les pilotes graphiques Fedora. Les limites existantes de la lecture optique protégée et des profils matériels restent applicables.

**La RC3 n'est pas publiée.** Aucune archive officielle ni date de sortie ne sont annoncées avant qualification du paquet exact.

## English

RC3 builds on the RC2 prerelease published on October 18, 2026. Its purpose is to consolidate previously implemented living-room usability improvements without starting additional feature projects or changing qualified Magnificence image recipes.

### Changes integrated into the source

- **HOME:** a discreet network-link indicator shows the local IP address when available. Link state is not proof of Internet access.
- **Flex:** gamepad navigation in HOME and MEDIA, while preserving existing keyboard and other control paths.
- **MPV:** an OPENHTPC-managed SDL2 gamepad profile for local videos and DVDs, providing playback, seeking, volume, and Stats overlay/page controls.
- **Install and update:** the gamepad profile joins the managed installation and removal manifest.
- **Stability:** preserve RC2 optical-generation/menu-publication safeguards and authoritative HOME session ownership.

### Evidence and remaining gates

The revised HOME/IP display and Flex gamepad navigation were exercised physically on the GEEKOM IT13 Max before its retirement. Earlier MPV/DVD gamepad trials used QA configurations and do **not** qualify the entire final RC3 package or all controller models.

The code passed **240 of 240 targeted tests on October 22, 2026**, before RC3 identity preparation. Another 321 earlier targeted tests passed, with partial overlap; the totals must not be treated as 561 distinct tests.

Still required: full regression, artifact construction from an exact Git commit, clean installation, RC2-to-RC3 update and physical validation on a separate Fedora 44 KDE Plasma/Wayland system.

### Limitations

Interactive DVD menus are not claimed. MEDIA grid changes, playback resume, optional autologin and Full HD/Blu-ray Magnificence research are deferred. Fedora GPU drivers are not modified. Existing limitations for protected discs and GPU-specific image profiles remain in effect.

**This RC3 is NOT PUBLISHED.** No official archive or availability date is claimed before the exact final package has passed qualification.
