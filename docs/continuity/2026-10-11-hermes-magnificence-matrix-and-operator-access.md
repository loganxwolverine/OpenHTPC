# Hermes — matrice Magnificence et accès opérateur sans sudo manuel

Date : 2026-10-11, Europe/Brussels.

## État vérifié

- Dépôt canonique : branche `feature/magnificence-sd-auto`, HEAD
  `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`.
- Worktree volontairement dirty conservé ; aucun commit, push, déploiement ou
  publication effectué.
- Stashes protégés inchangés : `pre-sync stale RTX experiment 2026-10-02` et
  `RC7 T5 network deferred`.
- `steve` appartient déjà au groupe système `docker`, mais la session Codex
  courante ne l'avait pas hérité. `sg docker` a été vérifié : le conteneur
  `hermes-agent` est accessible et actif sans `sudo`.

## Changement opérateur borné

Les lanceurs installés `~/.local/bin/hermes` et
`~/.local/bin/openhtpc-hermes-audit` utilisent désormais directement le socket
Docker lorsqu'il est accessible et, sinon, basculent automatiquement par
`sg docker`. Les arguments sont échappés avec `shlex.join`. La source locale de
migration `~/.local/state/openhtpc-hermes-migration/20261011/audit-wrapper.py`
a été alignée.

Les versions précédentes ont été sauvegardées avec le suffixe
`.before-docker-group-fallback-20261011`. Aucun fichier `sudoers`, service
Docker, secret, conteneur ou droit global `NOPASSWD` n'a été modifié.

Vérification réelle : `hermes --version` retourne Hermes Agent `0.21.6`, image
Docker, sans commande `sudo` manuelle depuis la session non rafraîchie.

Cette facilité ne donne aucune autorisation OPENHTPC supplémentaire. Le groupe
Docker reste une capacité système privilégiée déjà accordée ; les opérations
de déploiement, commit, push, publication et qualification physique conservent
leurs gates explicites.

## Audit contradictoire de la matrice Magnificence

- Snapshot : `openhtpc-magnificence-matrix-20261011T162911Z`.
- Rapport importé :
  `docs/audits/2026-10-11-magnificence-gpu-matrix-hermes.md`.
- SHA-256 :
  `10c53e526ce15c09d545e461c964ea015971bde3f2d875f517bb82bd9db44e84`.
- Hermes est resté lecture seule, sans `.git`, hôte physique, credentials ou
  autorité de modification.

Hermes corrobore les huit identités/classes/recettes exactes, avec une réserve
sur RX 580, et classe la politique familiale globale
`PARTIALLY_CORROBORATED`. Les principaux points ouverts sont : BWDIF logiciel
sans `vaapi-copy` dans plusieurs chemins, portée DVD PAL insuffisamment
discriminée, preuve longue A310 portant sur FSRCNNX-8 et non sur la recette
sélectionnée FSRCNNX-16 complète, et prose IT13 devenue obsolète. Ce sont des
findings à vérifier contre le dépôt complet et les hôtes ; ils n'autorisent
aucune correction automatique ni promotion de recette.

## Prochaine action

Disposer séparément les findings C1 à C7 contre les sources complètes et les
preuves installées, puis proposer une tranche bornée. Ne pas modifier les
presets Magnificence dans ce checkpoint.
