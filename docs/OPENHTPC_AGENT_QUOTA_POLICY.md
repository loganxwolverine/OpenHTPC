# OPENHTPC — Politique de gestion stratégique des agents et quotas IA

Date de décision : 2026-10-19 (Europe/Brussels). Autorité produit : Steve.
Statut : politique de gouvernance adoptée ; capacités/quota individuels à mesurer, aucun changement automatisé de fournisseur ni de permissions.

## Objectif et principe non négociable

OPENHTPC ne doit pas monopoliser les quotas des agents partagés avec les autres
projets et usages personnels de Steve. Une tâche, même techniquement possible,
n'est pas automatiquement prioritaire sur la préservation de ces ressources.

Cette politique complète AGENTS.md et docs/OPENHTPC_ACTORS.md. Elle ne donne
aucune permission Git, déploiement, élévation, achat, crédit/API ou réaffectation
d'agents. Steve arbitre le calendrier, les dépenses et toute exception.

## Inventaire distinct : outil, moteur, offre, facturation

- Codex CLI : ingénieur principal. Les capacités et plafonds exacts du compte
  sont à vérifier par les vues d'usage officielles, pas à inférer de la version
  installée ou du taux de tests PASS.
- Hermes Agent : second ingénieur/auditeur, exécuté avec DeepSeek via OpenRouter.
  Les coûts OpenRouter éventuels sont distincts des quotas Gemini/Codex. Aucun
  crédit « gratuit » ni coût nul ne doit être présumé sans vérification.
- AGY / Google Antigravity CLI : planification et revue limitée par politique
  Autopilot. Steve a mis fin au renouvellement de son abonnement Gemini/Google AI.
  La date de fin des avantages payants et le quota restant ne sont PAS établis
  par l'observation CLI du 2026-10-19. L'offre individuelle gratuite Antigravity
  existe officiellement, avec des quotas de base hebdomadaires. Après l'arrêt de
  l'offre payante, tester sans dépense imprévue si AGY peut conserver une fonction
  utile de planner/reviewer. Ne pas supprimer AGY, modifier Autopilot ou substituer
  un modèle sans revue de contrat et décision de Steve.
- CodeGraph : outil d'analyse structurelle, distinct d'un modèle et de Graphiphy.
  Préférer ses requêtes structurelles locales aux grandes discussions IA quand
  le besoin est de cartographier les impacts.
- Graphiphy : acteur souhaité, capacités réelles non prouvées ; aucune mission
  ni coût attribué par hypothèse.
- ChatGPT : cadrage/coordination ; son contexte et sa consommation éventuelle
  ne sont pas une vue exhaustive des quotas des autres comptes.

## Règle de capacité et de réserve hebdomadaire

- Fenêtre de gestion : lundi–dimanche, heure Europe/Brussels, sauf cycle
  différent effectivement exposé par le fournisseur. Les cycles API/payants
  peuvent être quotidiens, glissants, horaires ou monétaires : ne jamais
  supposer qu'ils se réinitialisent le lundi.
- Réserve de planification **provisoire** : OPENHTPC cible au maximum 50 % du
  quota/du budget hebdomadaire disponible de chaque service partagé ; 50 % sont
  conservés pour les autres projets et l'usage personnel de Steve.
  Ce n'est PAS une lecture automatique du solde fournisseur ni une garantie
  quand celui-ci est inconnu. Steve peut ajuster explicitement ce seuil.
- Sans mesure fiable de quota : ne pas afficher de pourcentage consommé ou
  annoncer un solde ; réduire les délégations coûteuses, privilégier analyse
  locale/hors modèle, solliciter Steve pour un relevé officiel avant une
  campagne multi-agents. Ne pas déclencher des appels API payants pour sonder
  l'existence d'un quota.
- À 75 % de l'enveloppe **OPENHTPC** effectivement mesurée : alerte et
  réévaluation des tâches à forte consommation. À 100 % : report des tâches
  facultatives et demande d'arbitrage Steve ; jamais de contournement de
  quotas par comptes alternatifs ou achats automatiques.
- Pour les services payants à la consommation, aucun plafond monétaire nouveau
  n'est inventé. Toute dépense significative ou hausse de plafond nécessite
  un plafond approuvé séparément par Steve.

## Choix intelligent de l'agent

1. Préparer d'abord une demande courte, une définition de terminé et les
   fichiers réellement concernés ; réutiliser rapports et preuves existants.
2. Tâches purement mécaniques : Git local, CodeGraph, scripts/tests hermétiques,
   recherche dans le dépôt, sans invocation LLM non nécessaire.
3. Codex : changements structurants, risques de régression, intégration et
   tests, seulement après prévol et dans le budget.
4. Hermes/DeepSeek : seconde implémentation bornée ou audit contradictoire
   lorsque le coût/les risques justifient réellement une seconde opinion ;
   respecter strictement voie audit immuable / voie ingénierie séparée.
5. AGY : préparation ou revue courte lorsque l'offre disponible et le
   contrat Autopilot le permettent. Si l'accès gratuit devient insuffisant,
   réduire son rôle à une consultation facultative ou le mettre en veille ;
   ne jamais faire échouer la continuité du projet parce qu'AGY est absent.
6. Graphiphy : uniquement après qualification technique et budgétaire.
7. Éviter l'envoi du dépôt entier, la répétition des mêmes audits, les
   boucles d'agents ouvertes et les sessions à effort maximal par défaut.

## Revue hebdomadaire et traçabilité

Chaque début de semaine, établir pour chaque compte/modèle : accès encore
valide ou non établi, type de forfait, quota restant source officielle,
date de réinitialisation si connue, consommation OPENHTPC documentée,
réserve personnelle, budget restant pour OPENHTPC, missions proposées et
reportées, risques de facturation et degré de confiance des chiffres.

La revue est informative et en lecture seule. Une automatisation ChatGPT de
bilan hebdomadaire est créée le 2026-10-19 ; sa présence n'accorde PAS
d'accès autonome au dépôt, ne garantit PAS des relevés de quotas fournisseurs,
et ne modifie jamais directement les fichiers canoniques.

Un relevé durable accepté est référencé par un checkpoint daté et une entrée
de roadmap, sans écrire d'identifiants, jetons, adresses privées ou secrets.

## Contrôle AGY de référence

Le 2026-10-19 : exécutable agy 1.4.0 trouvé et `agy --help`
fonctionnel. Une liste de modèles/état de compte dans le terminal non
interactif n'a pas permis de prouver l'expiration effective de l'abonnement
ni les quotas disponibles. La documentation Antigravity propose le panneau
interactif `/usage` (alias `/quota`) pour un relevé du backend.
La gestion/expiration de l'abonnement se vérifie séparément sur le compte
Google de Steve, sans communiquer les codes/jetons à un agent.

Références officielles consultées :
- https://www.antigravity.google/pricing
- https://www.antigravity.google/docs/plans
- https://www.antigravity.google/docs/cli/commands/usage
