# OPENHTPC — Extensions : prérequis optique externe et état prêt à tenter

Date : 2026-10-11, Europe/Brussels.

## Autorité et état du dépôt

- Dépôt canonique : `/home/steve/OpenHTPC/github-openhtpc-rc2-integration`.
- Branche : `feature/magnificence-sd-auto`.
- HEAD observé : `975402945376618db56e29945074ea30ddcd2cb8`.
- VERSION : `1.3.1`.
- Worktree volontairement dirty, préservé.
- Stashes protégés non appliqués, non modifiés : `pre-sync stale RTX experiment 2026-10-02` et `RC7 T5 network deferred`.
- `OPENHTPC_CURRENT_STATE.json` reste STALE pour ce chantier.
- Autorité initiale : implémenter l'adaptation de `Système → Extensions`. Steve a ensuite autorisé explicitement son déploiement borné sur `.59`, sans autoriser de commit, push ou publication et sans autoriser de modification de `.229`.

## Décision opérateur

Pour le seul prérequis externe associé à la lecture optique protégée, l'utilisateur obtient et exécute lui-même son provisionneur hors OPENHTPC. Au prochain rafraîchissement canonique des capacités — notamment celui exécuté par l'installation/mise à jour — OPENHTPC détecte automatiquement uniquement la présence métadonnée attendue. Aucune surveillance continue pendant une session déjà ouverte n'est implémentée dans cette tranche.

OPENHTPC ne fournit, ne lie, ne télécharge, n'exécute, ne met à jour, ne copie, ne lit, n'analyse et ne modifie ni le provisionneur ni une base de clés utilisateur. L'état positif signifie `READY_TO_ATTEMPT`, jamais une garantie de lecture pour chaque disque.

## Implémentation dépôt

- Le libellé public `plugin.bluray` devient **Support optique avancé**.
- La page remplace le compteur trompeur « installée(s) » par les provenances fournies/ajoutées et le nombre de capacités prêtes à tenter.
- Le cas spécial affiche **Détection automatique**, **Prérequis externe absent** ou **Prérequis externe détecté**, puis **Prêt à tenter la lecture** lorsque le dernier fait Core rafraîchi est satisfait. Le pied de page précise que l'état provient du dernier relevé de capacités.
- `NOT_CONFIGURED`, `NOT_AVAILABLE` et `UNAVAILABLE` deviennent une dépendance `NOT_AVAILABLE`; `BLOCKED` et `UNKNOWN` restent inconnus/fail-closed.
- Le détecteur existant `external_key_database()` reste l'autorité : `lstat`, type de fichier et lisibilité seulement, sans ouverture du contenu ni chemin publié.
- Le validateur de nom de manifest accepte les lettres Unicode pour rendre le libellé français correctement, tout en refusant toujours les séparateurs de chemin.

## Preuves exécutées

- TDD initial : 3 échecs et 3 erreurs attendus avant implémentation.
- Suites framework/plugins ciblées : 99 tests PASS, 3 SKIP.
- Régression `test_protected_optical*.py` : 184 tests PASS, 6 SKIP.
- Tests finaux inventaire/registre/détecteur : 60 tests PASS, 1 SKIP.
- Rendus `/tmp/openhtpc-extensions-absent.png` et `/tmp/openhtpc-extensions-detected.png` générés en 1920×1080 et inspectés visuellement.
- Avant déploiement, `.59` était `Doctor READY`, sans MPV actif. Le prérequis externe y était absent : `libaacs NOT_AVAILABLE`, fichier attendu `NOT_CONFIGURED`.
- Sauvegarde récupérable créée sur `.59` : `/home/steve/.local/state/openhtpc/backups/pre-extensions-readiness-20261011.tar.gz`, SHA-256 `61a01298afe017abaded9d4bb447192db7e2f328f384151aba1066e4145bc9b3`.
- Paquet borné de cinq fichiers vérifié avant installation, SHA-256 `20521751597485ff048cfa71b3762c7dd4f8492d09ce7834bd3f4713bbb62625`.
- Les cinq fichiers ont été remplacés atomiquement sur `.59`, puis capacités, registre et pages Système ont été rafraîchis.
- Post-déploiement `.59` : `Doctor READY`; modèle Extensions = `Support optique avancé`, `external_prerequisite=ABSENT`, `Prérequis externe absent`, `ready=0`; image installée inspectée en 1920×1080.
- Magnificence préservé : `CINEMA_AUTO`, profil exact `intel_meteor_lake_8086_7d55_sd_2160p`, recette `RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD`, classe `STRONG`, confiance `OPENHTPC_PHYSICAL_QUALIFICATION`.
- Une instance Flex autoritaire reste active, aucun MPV actif. Aucun test physique de lecture optique n'a été exécuté.
- `.229` n'a reçu aucune commande distante ni mutation pendant ce chantier.

## Correction du rendu live `.59`

Steve a précisé que la capture de 16:25 montrant encore « Blu-ray UHD / 1 installée / Désactivé » provenait de `.59`, pas de `.229`. Le fichier PNG corrigé avait été régénéré, mais le Flex déjà lancé conservait l'ancienne texture en mémoire.

Une première relance a rencontré une course de lifecycle : `cleanup-legacy` avait arrêté contrôleur/Flex/moniteur, mais le wrapper de session détenait encore brièvement le verrou ; la tentative immédiate a journalisé `START_ALREADY_ACTIVE` et laissé l'appliance `STOPPED`. Cet état a été détecté sans le présenter comme un succès. Après libération réelle du verrou, OPENHTPC a été relancé depuis la session KDE existante.

État final vérifié sur `.59` : Doctor `READY`, appliance `RUNNING`, runtime ownership `PASS`, Flex autoritaire unique PID `74443`, un moniteur optique, zéro MPV. La configuration active `SYSTEM_EXTENSIONS` pointe sur `/home/steve/.cache/openhtpc/system-extensions.png`, régénérée avec la nouvelle présentation. `.229` reste non modifié.

## Hermes

Snapshot borné créé sous `/home/steve/.local/share/hermes-agent/audits/openhtpc-extensions-truth-20261011/project`, avec provenance branche/HEAD/dirty et sans `.git` ni identifiants. Montage read-only et canari UID 10000 vérifiés : tentative d'écriture refusée.

La revue Hermes/DeepSeek via OpenRouter est **NON EXÉCUTÉE** : le contrôle de sécurité a refusé la transmission externe du snapshot faute d'une autorisation explicite couvrant cet envoi. Aucun contournement n'a été tenté.

## Fichiers du delta

- `payload/openhtpc-core.py`
- `payload/openhtpc-plugin-registry.py`
- `payload/openhtpc-system-model.py`
- `payload/openhtpc-ui.py`
- `payload/plugins/available/plugin.bluray/plugin.json`
- `payload/plugins/README.md`
- tests plugins/optique associés
- roadmap plugins, roadmap globale et continuité

## Prochaine action

1. Obtenir, si souhaité, l'autorisation explicite de transmettre ce snapshot borné à Hermes/OpenRouter pour contre-revue.
2. Steve exécute lui-même, s'il le souhaite, son provisionneur externe sur `.59`.
3. Rafraîchir ensuite les capacités et vérifier l'état réel détecté, sans que OPENHTPC n'acquière ni n'exécute aucun contenu externe.
