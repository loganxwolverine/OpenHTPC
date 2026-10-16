# OPENHTPC — Priorité du plugin Navigation menus DVD

Date : 2026-10-11, Europe/Brussels.

## Décision opérateur

Steve demande que la navigation depuis le menu du DVD inséré, rendue par MPV, devienne le premier vrai plugin utilisateur OPENHTPC. L'extension doit être visible et installable depuis `Système → Extensions`, puis devenir effective uniquement lorsque ses dépendances et capacités réelles sont satisfaites.

Cette décision modifie l'ordre produit de la roadmap. Elle n'autorise pas encore l'implémentation, l'installation d'un MPV expérimental, un déploiement, un commit, un push ou une publication.

## Faisabilité et sources

### Documentation officielle

- Le [manuel stable MPV](https://mpv.io/manual/stable/) correspondant à la série 0.41 dit explicitement pour `dvd://` que les menus DVD ne sont pas pris en charge.
- La [PR amont MPV #18080](https://github.com/mpv-player/mpv/pull/18080), fusionnée dans `master` le 2026-08-25 et associée au jalon 0.42, ajoute les menus DVD/Blu-ray et la navigation de disque.
- Le [manuel MPV master](https://mpv.io/manual/master/) documente `--disc-menu`, `dvd://menu`, `discnav up/down/left/right/select/menu/title-menu/popup/prev`, la section d'input `{discnav}` et la propriété `disc-menu-active`.
- Le dernier release amont observé le 2026-10-11 reste [MPV 0.41.0](https://github.com/mpv-player/mpv/releases/tag/v0.41.0).

### Faits OPENHTPC

- OPENHTPC 1.3.1 et les plateformes actuellement documentées utilisent MPV 0.41.
- Le dispatcher DVD de production lance `dvd://longest` sous politique vidéo/audio, matching de fréquence et lifecycle exact-child.
- `libdvdnav` est déjà une dépendance connue et détectée par OPENHTPC, mais sa présence seule ne prouve pas le support interactif des menus par MPV.
- Les tests historiques imposent l'absence de `--disc-menu` parce que MPV 0.41 le rejette. Ils restent corrects pour cette baseline et ne doivent pas être affaiblis avant un changement explicite de dépendance et de contrat.

### Verdict

`plugin.dvd-menu` est **FAISABLE SOUS CONDITION**, mais **NON DISPONIBLE sur la baseline MPV 0.41**. Le support amont existe dans `master`, ce qui transforme l'ancien obstacle structurel en gate de version/capacité et de qualification. Une disponibilité dans `master` n'est ni une disponibilité Fedora, ni une preuve de robustesse OPENHTPC.

OPENHTPC ne doit pas installer une nightly ni remplacer le MPV Fedora. Le plugin ne peut devenir `AVAILABLE` que lorsque le binaire MPV effectif expose par introspection les primitives requises et que le backend `dvdnav` est disponible.

## Ordre prioritaire retenu

1. **Contrat générique d'action média bornée** : identifiant allowlisté, payload validé, commande construite par Core.
2. **Installation first-party depuis Extensions** : paquet vérifié, compatibilité API, transaction atomique, rollback, activation/désactivation/mise à jour/retrait et états explicites ; aucune URL ou commande arbitraire issue d'un manifest.
3. **Gate MPV menu DVD** : vérifier `--disc-menu`, `dvd://menu`, `discnav`, `disc-menu-active`, backend DVD et `libdvdnav` sur un paquet Fedora candidat. MPV 0.41 échoue fermé.
4. **Implémentation de `plugin.dvd-menu`** : contribution **OUVRIR LE MENU DVD**, conservation de **LIRE LE DVD** par défaut, dispatcher Core-owned et lifecycle exact-child.
5. **Qualification** : clavier, souris et contrôleur ; menus simples/animés/multi-pages ; DVD PAL et NTSC ; audio, fréquence, rendu, sortie MPV, retour Flex et négatifs indisponible/cassé/désactivé.
6. **Migration de `plugin.bluray` comme référence secondaire**, puis `plugin.disc-extract` et `plugin.hddvd`.

## Veille MPV 0.42 et Fedora

La disponibilité est suivie au minimum une fois par mois, à chaque annonce/release MPV pertinente et avant tout nouveau candidat OPENHTPC. Le relevé doit être daté dans cette roadmap ou dans un checkpoint successeur et consulter :

- releases et jalon officiels MPV 0.42 ;
- manuel MPV stable pour confirmer que les primitives ont réellement atteint une release ;
- paquets officiels Fedora 44, Fedora ultérieures et Rawhide ;
- après disponibilité Fedora, introspection du binaire effectif puis tests OPENHTPC.

États autorisés : `UPSTREAM_NO_DATE`, `UPSTREAM_SCHEDULED`, `UPSTREAM_RELEASED`, `FEDORA_CANDIDATE`, `FEDORA_STABLE`, `OPENHTPC_READY_TO_TEST`, `PHYSICALLY_QUALIFIED`. Une date n'est consignée que si elle est annoncée par l'autorité amont ou Fedora ; le pourcentage d'un jalon ne permet aucune extrapolation.

Relevé du 2026-10-11 :

- jalon MPV 0.42 ouvert, sans date officielle : `UPSTREAM_NO_DATE` ;
- Fedora 44 : `mpv-0.41.0-5.fc44` ;
- Fedora 45 : `mpv-0.41.0-8.fc45` ;
- Fedora Rawhide : `mpv-0.41.0-9.fc46` ;
- disponibilité produit OPENHTPC : `NOT_AVAILABLE`.

Ce suivi n'autorise ni mise à jour automatique, ni dépôt tiers, ni build nightly sur une machine OPENHTPC.

## Limites et invariants

- Core reste propriétaire du lecteur, des I/O, des verrous, du dispatch, du PID suivi, de MPV et de la restauration Flex.
- Le plugin ne fournit pas une commande shell et ne contourne aucun garde d'interaction.
- Le chemin simple de lecture du titre principal reste présent et inchangé.
- Aucun preset Magnificence, profil GPU ou politique audio n'est modifié par cette décision.
- Une compatibilité sur un DVD ne vaut pas qualification universelle ; les échecs spécifiques à l'authoring doivent rester observables et isolés.
- Les dépendances Fedora nécessitent un plan visible et un consentement explicite ; la politique « Fedora possède la pile système » demeure.

## État Git et autorisations

- Branche observée : `feature/magnificence-sd-auto`.
- HEAD observé : `975402945376618db56e29945074ea30ddcd2cb8`.
- VERSION : `1.3.1`.
- Worktree volontairement dirty et deux stashes protégés préservés.
- `OPENHTPC_CURRENT_STATE.json` reste STALE pour ce chantier.
- Documentation seulement : aucun code produit, test, preset, hôte installé ou runtime modifié.

## Prochaine mise en chantier autorisable

Prévol et conception du **contrat générique d'action média bornée**, avec `plugin.dvd-menu` comme cas cible mais un plugin factice hermétique comme première preuve. Une contre-revue Hermes pourra examiner le contrat depuis un snapshot immuable en lecture seule après autorisation explicite de transmission externe.
