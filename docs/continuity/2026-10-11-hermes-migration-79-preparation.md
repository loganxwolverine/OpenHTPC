# Hermes Unraid → contrôle .79 : préparation de migration

Statut historique : préparation remplacée par [la migration validée](2026-10-11-hermes-migration-79.md). Source désormais arrêtée ; Hermes actif sur .79. Les constats suivants décrivent la préparation initiale.

Date : 2026-10-11, Europe/Brussels. Statut : PREPARED / NON BASCULÉ.

## Autorisation et état du dépôt

Steve demande explicitement de migrer Hermes, actuellement dockerisé sur Unraid, vers .79. Cette demande autorise la migration du service et de ses données ; elle ne promeut pas Hermes au rôle d'implémenteur et n'autorise aucun commit/push/release.
Dépôt .79 : feature/magnificence-sd-auto, HEAD 975402945376618db56e29945074ea30ddcd2cb8, VERSION 1.3.1. Delta plugins/Système et deux stashes protégés présents ; aucune modification de code produit dans cette préparation.

## Faits vérifiés indépendamment

- Source : Tower, 192.168.1.10, conteneur hermes-agent actif. Volume bind /mnt/user/appdata/hermes-agent → /opt/data ; 3,7 Go observés par du.
- Hermes 0.21.6 (2026.9.24), upstream 818c13be, Python du conteneur 3.14.7. Version lue par la CLI Python réelle.
- Image source : nousresearch/hermes-agent:latest, image ID sha256:373ddd5e6649f525b17993e1c885cdf1352127f8e98fd329140a73237125e52f ; taille image 3189612827 octets.
- Digest registry : nousresearch/hermes-agent@sha256:9774f4f39a9bb8c2f68ce728ed5e99ddbad282163be56764afacf88ed952b784. Réutiliser ce digest/image ID plutôt que tirer latest.
- Docker diff : 284 chemins modifiés, aucun sous /opt/hermes ; la couche de travail contient notamment des temporaires. Les données durables restent la priorité de migration.
- Conteneur non privilégié, réseau bridge, port source 8642 publié, restart policy source no. La disponibilité d'un port n'établit pas une interface de contrôle approuvée.
- Consommation mémoire ponctuelle source : environ 1010 MiB.
- .79 : openhtpc-control, environ 3896 MiB RAM, 2376 MiB disponibles et 40 Go de disque libres lors du relevé. Docker et Podman absents ; sudo non interactif refusé.
- Transaction Fedora simulée : moby-engine + docker-cli et dépendances, neuf paquets, 62 MiB à télécharger, 235 MiB installés. Aucune transaction exécutée par cette préparation.

## Préparation et données privées

Métadonnées complètes source et image capturées sur .79 dans ~/.local/state/openhtpc-hermes-migration/20261011, répertoire 0700 et fichiers 0600. Elles contiennent des paramètres sensibles : ne pas les publier ni les ajouter au dépôt.
Export exact de l'image lancé vers ce même répertoire ; ne considérer l'archive valide qu'après fin de processus et empreinte SHA-256. Le digest registry est une alternative exacte disponible.
Le conteneur Unraid n'a été ni arrêté, ni supprimé, ni reconfiguré. Aucun Hermes cible n'est lancé et aucune copie live SQLite n'est déclarée cohérente.

## Suite autorisée

1. Installer Docker/Moby sur .79 avec sudo, puis démarrer le service. Donner l'accès Docker à l'opérateur steve, jamais au conteneur Hermes.
2. Vérifier moteur, image exacte et destination avant toute bascule.
3. Préparer puis transférer les données persistantes avec un arrêt source bref pour une capture cohérente des SQLite/WAL ; conserver le conteneur et les données source pour rollback.
4. Préserver config, mémoire, sessions, skills, rapports et snapshots. Capturer les credentials nécessaires dans des fichiers privés sans les afficher ; ne pas monter les clés opérateur .79/.229 dans Hermes.
5. Recréer l'isolation : snapshots d'audit sans .git, techniquement read-only, pas de dépôt canonique ni socket Docker dans Hermes. Préserver les clés internes historiques dans la sauvegarde, les isoler du runtime d'audit avant validation.
6. Valider version, intégrité, refus d'écriture des snapshots, réponse réelle DeepSeek/OpenRouter, accès opérateur et redémarrage. Éviter deux gateways actives avec la même identité ; rollback source si la cible échoue.
7. Actualiser les acteurs, la procédure Hermes, la continuité et la roadmap après preuves. Aucun accès MCP persistant Hermes → CodeGraph n'est établi par cette migration.

Prochaine intervention humaine : installation privilégiée Docker sur .79. Répondre dans la conversation ChatGPT qui prépare Hermes, distincte de l'ancien mandat Codex de migration .229 → .79.
