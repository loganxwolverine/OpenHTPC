# OPENHTPC — Résolution générique des dépendances plugins — 2026-10-11

Date : 2026-10-11, Europe/Brussels. Développement manuel sur `openhtpc-control` après le prévol GO.

## Verdict du jalon

**JALON LOGICIEL COMPLET pour la résolution générique des dépendances et la vérité commune registre / Doctor / Système → Extensions.**

Ce verdict ne vaut ni installation, ni qualification physique, ni autorisation de commit, push, tag, publication ou release. Les installations `.229` et `.67` n'ont pas été contactées ou modifiées. Autopilot reste fermé sur `OPENHTPC_CURRENT_STATE.json` STALE et le worktree dirty ; aucun contournement n'a été tenté. Aucun code n'a été exporté vers Hermes, DeepSeek ou OpenRouter.

## Identité et préservation

- dépôt : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration` ;
- branche : `feature/magnificence-sd-auto` ;
- HEAD : `975402945376618db56e29945074ea30ddcd2cb8` ;
- VERSION : `1.3.1` ;
- worktree volontairement dirty, changements antérieurs préservés ;
- stashes préservés sans application ni modification : `pre-sync stale RTX experiment 2026-10-02` et le stash protégé `RC7 T5 network deferred`.

## Cartographie réellement vérifiée

CodeGraph a été interrogé sur le worktree courant, puis les résultats ont été confirmés par lecture des sources :

- `registry()` : cinq callees directs (`discover`, validation/état activé, chemins et lecture) et quatre consommateurs structuraux (`publish`, `load_entrypoint`, `resolve_resource`, `set_enabled`) ;
- `_plugin_inventory` : consommé uniquement par la construction du modèle Système ;
- `plugin_status` Core : alimente `capability_state`, `installed_plugins`, Doctor/health et les projections optiques ;
- Doctor : `health_report` → `capability_state` → registre et `optional_plugin_states` ;
- dépendances résumées : graphe registre 8 nœuds/7 arêtes, graphe modèle Système 7 nœuds/6 arêtes.

CodeGraph ne recensait pas les imports dynamiques et les tests ; `rg` et la lecture des appels les ont complétés. La divergence prouvée était que Doctor recevait `plugin_status`, alors que Système rechargeait le registre séparément dans `_plugin_inventory`.

## Contrat implémenté

Core construit `openhtpc-plugin-dependency-facts-v1` à partir de faits déjà persistés. Le contrat possède exactement `schema`, `capabilities` et `system`. Chaque fait est un token strict portant exactement un `status` parmi `AVAILABLE`, `NOT_AVAILABLE`, `UNKNOWN` et une `source` non vide. Le registre ne sonde ni matériel ni système et n'exécute aucun plugin pour résoudre ces faits.

Le producteur actuel adapte explicitement le fait canonique `capabilities.optical.protected_media` vers `protected-optical-state`. Une section explicite `plugin_dependency_facts` dans le snapshot est transmise telle quelle à la validation stricte ; aucune donnée malformée n'est réparée ou promue silencieusement. Les futurs faits système devront être ajoutés par un producteur Core autorisé et explicite.

Le résolveur central traite :

- dépendances vers d'autres plugins, avec propagation d'un plugin désactivé, incompatible, invalide ou lui-même indisponible ;
- capabilities et dépendances système depuis les faits Core ;
- références absentes, faits inconnus, schéma/type invalide et cycles ;
- graphe pathologiquement profond, qui échoue fermé sans publier de provider.

Les états produits sont distincts : `AVAILABLE`, `DEPENDENCY_MISSING`, `DEPENDENCY_UNKNOWN`, `DEPENDENCY_INVALID` et `DEPENDENCY_CYCLE`. Chaque résultat contient un motif canonique et le détail des dépendances. Seul un plugin final `AVAILABLE` peut apparaître comme provider.

`plugin_status` transmet toujours ces faits au registre. Doctor et `Système → Extensions` consomment ensuite la même instance résolue : `_plugin_inventory` ne recharge plus le registre et n'effectue aucune collecte. Le motif affiché par Doctor et celui de la page Extensions sont identiques. Les appels historiques P2 d'entrée/action restent hors de cette tranche ; le contrat d'action média générique n'est pas ouvert.

## Fichiers produit et tests de cette tranche

- `payload/openhtpc-plugin-registry.py` ;
- `payload/openhtpc-core.py` ;
- `payload/openhtpc-system-model.py` ;
- `payload/openhtpc-ui.py` ;
- `payload/openhtpc` ;
- `tests/test_plugin_framework_generic_system.py` ;
- `tests/test_optical_presentation_plugin_p2.py` ;
- `tests/test_optical_asset_plugin_p2.py` ;
- continuité et roadmaps.

Aucun nouveau payload n'est ajouté. Les fichiers produit modifiés sont déjà couverts par les autorités d'installation existantes. Aucun fichier Flex, manifest ou frontière optique P2 n'a été modifié par cette tranche.

## Preuves exécutées maintenant

- gate fonctionnel final registre/inventaire/P2 : **75 PASS, 3 SKIP, 1 contrôle Flex voisin désélectionné** ;
- régressions registre, optique protégée et modèle Système : **209 PASS, 8 SKIP, 1 contrôle Flex voisin désélectionné** ;
- première suite globale applicable : **2188 PASS, 23 SKIP, 12 FAIL** ; onze échecs provenaient de l'interdiction de créer des sockets dans le bac à sable ;
- reprise hors bac à sable des seuls fichiers hermétiques concernés : **98 PASS**, confirmant que ces onze cas ne sont pas des régressions produit ;
- couverture nouvelle : satisfaites/manquantes/inconnues, référence plugin absente, cible invalide isolée, cycles, schéma et statut malformés, graphe profond fail-closed, cohérence Doctor/Extensions, absence d'exécution d'entrypoint et absence de collecte dans la projection ;
- rendu logiciel `Système → Extensions` 1920×1080 inspecté avec `DEPENDENCY_MISSING`, SHA-256 `02c32bdaa48b77ca5a608b315e6693e2b9767a00d2d47f723e6d85887088bcce` ; lisibilité et géométrie conservées.

Le douzième échec global est un contrôle voisin de provenance Flex : le SHA-256 du binaire distribué concorde avec `payload/flex/BUILD-METADATA.json`, mais le `flex_source_fingerprint` schema 1 ne peut plus être reproduit depuis l'ensemble actuel, notamment parce que la fonction historique inclut les artefacts ignorés de `vendor/flex-launcher/build/`. Le répertoire a été déplacé temporairement puis restauré intact pour le diagnostic. Cette dérive préexistante ne concerne aucun fichier de la tranche, ne bloque pas la logique plugins et devra être corrigée lors du prochain rebuild Flex autorisé ou par un fingerprint limité aux sources stables ; aucune métadonnée ni aucun binaire n'a été réécrit ici.

Les preuves historiques de présentation compacte sur `.229` restent valides uniquement pour le jalon précédent. Elles ne qualifient pas la nouvelle résolution.

## Auto-revue adversariale

- fait absent ou inconnu : jamais promu `AVAILABLE` ;
- fait au mauvais type, y compris valeur non hachable : `DEPENDENCY_INVALID`, sans crash ;
- manifest invalide : isolé dans `errors`, dépendant marqué invalide ;
- cycle : tous les membres concernés échouent fermé ;
- plugin désactivé/incompatible ou dépendance transitive indisponible : propagation canonique ;
- provider : uniquement publié après résolution `SATISFIED` ;
- inventaire : lecture des manifests et faits persistés seulement, aucun entrypoint, commande, installation, probe matériel ou collecte implicite ;
- Doctor/Extensions : même objet registre, état et motif identiques ;
- frontières gelées P2, lifecycle, GPU, audio et lecture : inchangées.

## Limites et prochaine action

- Aucun fait système de production supplémentaire n'a été inventé : une dépendance système déclarée sans producteur explicite reste `UNKNOWN`.
- Aucun contrôle d'activation Flex, installateur de plugin, action média ou handler générique n'est ajouté.
- Aucun déploiement ni test physique n'a été effectué ; aucune validation physique n'est nécessaire pour clore cette tranche logique. Une inspection future sur écran réel pourra vérifier les nouveaux libellés après déploiement explicitement autorisé, sans remettre en cause la preuve logicielle.

Prochaine tranche autorisable : définir le **contrat générique d'action média bornée**. Première tâche Codex recommandée : cartographier les contributions UI/action P2 existantes, définir une structure déclarative allowlistée sans commande shell, puis faire contribuer un plugin factice `AVAILABLE` et vérifier que Core valide, expose, refuse lorsqu'indisponible et conserve le lifecycle/exécution.

## Autorisations

Aucun commit, push, tag, publication, release ou déploiement n'a été effectué. Les stashes et artefacts ont été préservés. Steve reste l'autorité pour toute installation et qualification physique.
