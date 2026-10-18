# OPENHTPC 1.3.2 RC1 — Patina
Release Candidate / Candidat de publication — EN PRÉPARATION, NON PUBLIÉ

## Français

Cette RC est consacrée à la stabilité d'OPENHTPC. Elle conserve les fonctionnalités, recettes Magnificence et limites matérielles de la branche 1.3.1, sans introduire de nouvelle fonctionnalité.

### Correction principale
Le correctif V11 rétablit une publication cohérente de la génération optique et du menu Flex après insertion d'un DVD. Il sécurise la cadence et le nettoyage des tâches de régénération sans perdre le contrôle de la session HOME.

La lecture complète du DVD The Perfect Storm a été confirmée par le responsable du projet sur la machine de validation .229 après application de ce correctif.

### Contrôles réalisés
Le correctif V11 a été accepté par les deux revues indépendantes AGY et Codex. Sur le canonique, 131 tests optiques ciblés et 77 tests Devctl ont réussi. Sur un clone isolé Fedora 44, 2 406 tests ont réussi, 23 ont été ignorés et 12 tests du lanceur KDE ont échoué sur un hôte sans Plasma : la qualification KDE réelle est donc encore à faire.

### Limites et prérequis
Plateforme cible : Fedora 44 KDE Plasma/Wayland. La RC n'est pas encore qualifiée pour une installation publique ; le contrôle d'installation et de mise à jour, l'audio, la vidéo et le retour à l'interface doivent être validés sur un système KDE conforme.

La navigation interactive dans les menus DVD n'est pas revendiquée ; son éventuel plugin MPV fait partie d'un chantier ultérieur. Les capacités Blu-ray/UHD sont conditionnées par le disque, la configuration et les composants réellement disponibles. Les profils Magnificence ne sont qualifiés que dans leur périmètre matériel et vidéo documenté.

La publication est soumise à une décision explicite du responsable du projet. Aucun téléchargement public n'est annoncé dans ces notes.

## English

This release candidate focuses on stability, preserving the existing 1.3.1 media features and qualified Magnificence recipes without introducing new features.

### Main correction
The V11 optical fix restores coherent DVD generation and Flex menu publication and hardens bounded regeneration, pacing and cleanup under the authoritative HOME session lock. The project owner completed a real movie session with The Perfect Storm on the .229 validation system.

### Evidence and release gate
AGY and Codex independently accepted V11. Canonical targeted tests: 131 optical tests and 77 Devctl tests passed. An isolated Fedora 44 test run recorded 2,406 passes, 23 skips and 12 KDE-launcher integration failures on a non-Plasma control machine. Installation and update validation on real Fedora 44 KDE/Wayland, and final physical qualification, remain outstanding.

Interactive DVD menus are not claimed; future MPV-related plugin work is deferred. Blu-ray/UHD support and Magnificence quality are limited to documented disc/hardware/environment capabilities.

This candidate has NOT been released or published. The final GO decision belongs to the project owner.
