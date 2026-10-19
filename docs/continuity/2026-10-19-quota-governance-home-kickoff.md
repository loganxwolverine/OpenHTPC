# OPENHTPC — Reprise du 19 octobre 2026 : quotas IA et HOME réseau

Statut : politique agents ajoutée au dépôt ; chantier HOME réseau sélectionné
par Steve pour cadrage/ingénierie bornée après sécurisation documentaire.
Ce document ne prétend ni installer ni qualifier l'indicateur réseau.

## Faits préalables (contrôle direct .79, 2026-10-19)

- Hôte `openhtpc-control`, dépôt `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`.
- HEAD avant consolidation `1764b8e77c5bd591bd163d3d1bdab1e36ea277ae`,
  branche `feature/magnificence-sd-auto`, VERSION `1.3.2-rc2`.
- RC2 tag public `v1.3.2-rc2` prérelease (ne pas le déplacer).
- Quatre fichiers documentaires suivis modifiés ; checkpoint du 18/10 non
  suivi ; quatre documents optiques historiques du 17/10 non suivis.
- Index vide ; deux stashes protégés intacts
  (`pre-sync stale RTX experiment 2026-10-02`,
  `RC7 T5 network deferred`).
- Une archive de sauvegarde documentaire **seulement**, avec hash et relevé
  Git, créée et vérifiée avant édition :
  `/home/steve/.local/state/openhtpc-continuity/docs-pre-quota-20261019T060400/`.
  Elle contient neuf documents, sans prétendre sauvegarder intégralement Git
  (stash/reflog compris).
- Exécutables Codex CLI 0.162.1 et AGY CLI 1.4.0 disponibles. Hermes :
  conteneur `hermes-agent` actif au contrôle précédent. Ne pas extrapoler
  des versions CLI des quotas ou facturations.

## Décision Steve — gouvernance IA

Conserver les agents actuels, sans privilèges ajoutés ; tenir compte de la fin
de renouvellement Google AI/Gemini ; utiliser éventuellement la formule
individuelle gratuite Antigravity si accessible et suffisante ; organiser une
revue hebdomadaire des quotas réels en préservant les usages personnels et
autres projets. Détail : `docs/OPENHTPC_AGENT_QUOTA_POLICY.md`.
La date d'expiration effective et les crédits encore disponibles ne sont
pas PROUVÉS à ce checkpoint. Ne jamais confondre AGY, Gemini, OpenRouter,
DeepSeek, Codex CLI, CodeGraph et Graphiphy.

## HOME — indicateur réseau/IP : entrée sélectionnée

Objectif produit : icône discrète mais lisible en bas à droite du menu HOME,
état LAN connecté/déconnecté/inconnu et adresse locale si disponible.
Aucun test Internet implicite ; observer interfaces multiples, IPv4/IPv6,
modifications à chaud, cas sans IP ; ne pas modifier le réseau Fedora.

Audit initial : HOME controller = `payload/openhtpc-home.py` ;
publication et configuration Flex = `payload/openhtpc-session-engine.py` ;
rendu du launcher = `vendor/flex-launcher/src/`.
Le renderer possède une horloge mais aucun composant réseau natif retrouvé
à cette lecture. L'ancien stash `RC7 T5 network deferred` est protégé et
n'a pas été appliqué/modifié.

Avant implémentation : documenter le choix de la source de vérité réseau,
la stratégie d'affichage dynamique sans republier abusivement l'optique,
les priorités d'adresse et les tests hermétiques. Puis exécuter une tranche
unique après prévol et valider physiquement dans un mandat séparé. La
sélection du chantier n'est pas un GO de déploiement.

## À préserver

- RC2 publique inchangée et distincte des futures modifications du dépôt.
- Correctif optique V11 / tests : ne pas toucher.
- 2414 PASS / 12 FAIL KDE historiques / 23 SKIP consignés, non réexécutés.
- .59 IT13 RC2 READY et DVD complet validé par Steve ; .229 et .67 intacts.
- `OPENHTPC_CURRENT_STATE.json` toujours STALE (P2/1.2.0).
- Contrat `iact_` décidé/non implémenté ; `plugin.dvd-menu` dépendances
  propres ; quatre entrées post-RC2 documentées.
- Toute qualification HOME/IP et décision de commit produit doivent être
  consignées séparément, avec résultats et autorisation de Steve.
