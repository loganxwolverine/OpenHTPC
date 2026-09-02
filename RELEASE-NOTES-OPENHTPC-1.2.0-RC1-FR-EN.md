<!--
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
-->

# OPENHTPC 1.2.0 RC1

Pre-release: **Yes**
RC1 physical release gate: **PENDING**

## Français

OPENHTPC 1.2.0 RC1 promeut sans changement fonctionnel la baseline Dev14
qualifiée sur Intel/ZimaBoard 2, AMD/Ryzen et NVIDIA/RTX 3050.

Le Plugin Framework P2 réalise le cutover de production. `plugin.bluray`,
activé explicitement, porte la politique et la présentation Blu-ray/UHD ; le
Core conserve les services génériques d’acquisition, sécurité, rendu et
exécution, ainsi que le DVD. Le défaut UI gating révélé par Dev13 est corrigé :
un plugin désactivé n’expose ni badge ni action de lecture Blu-ray/UHD.

Pour les médias protégés, `AVAILABLE` signifie `READY_TO_ATTEMPT`, jamais une
garantie universelle par disque. OPENHTPC ne fournit, télécharge, met à jour,
lit, copie ou référence aucun contenu KEYDB ; seule la métadonnée de présence
et lisibilité est détectée.

Limitations non bloquantes : `openhtpc rebuild-passport` est actuellement
requis lorsque les dépendances protected optical sont ajoutées après la
génération du snapshot ; les dropped frames UHD observées sur ZimaBoard 2
restent une limitation de performance différée.

## English

OPENHTPC 1.2.0 RC1 promotes the Dev14 baseline physically qualified on
Intel/ZimaBoard 2, AMD/Ryzen and NVIDIA/RTX 3050 without functional changes.

Plugin Framework P2 completes the production cutover. Explicitly enabled
`plugin.bluray` owns Blu-ray/UHD policy and presentation; Core retains generic
acquisition, security, rendering and execution services, and continues to own
DVD. The UI-gating defect exposed by Dev13 is fixed: a disabled plugin exposes
neither a Blu-ray/UHD badge nor a play action.

For protected media, `AVAILABLE` means `READY_TO_ATTEMPT`, never universal
per-disc success. OPENHTPC does not provide, download, update, read, copy or
link to KEYDB content; it detects presence/readability metadata only.

Non-blocking limitations: `openhtpc rebuild-passport` is currently required
when protected-optical dependencies are added after snapshot generation; UHD
dropped frames observed on ZimaBoard 2 remain a deferred performance limit.
