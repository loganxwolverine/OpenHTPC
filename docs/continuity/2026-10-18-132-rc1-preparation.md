# OPENHTPC — préparation locale 1.3.2 RC1 (18 octobre 2026)

## Décision de périmètre
Le responsable du projet retient une RC publique DE STABILISATION sans développement
de fonctions nouvelles, de recettes GPU ou de recalibration du lecteur optique.
Graphiphy est un acteur important du dispositif ; ses capacités et permissions
concrètes restent à attester, distinctes de CodeGraph.

## Provenance vérifiée
- Branche : feature/magnificence-sd-auto.
- Base consolidée : 85b6de66a572aa13270305d27ffbfa0dceb15e9b.
- V11 optique local : 5b8bb7f3fa9096ba67173111c23acd1dda06e0ee.
- Fixture Devctl : a740084441c30240e47d69c649b37a401a45696b.
- Gouvernance Graphiphy : 85b6de66a572aa13270305d27ffbfa0dceb15e9b.
- VERSION du candidat proposé : 1.3.2-rc1, build public-release-1.3.2-rc1.
- Identité propagée à VERSION, payload/VERSION, payload/version.json et
  installateur via l'outil de release-metadata existant.
- Le fichier historique OPENHTPC_CURRENT_STATE.json reste relatif à un ancien
  workstream P2/RC5/RC7 : il n'accorde aucune autorisation RC 1.3.x.
- Deux stashes protégés et quatre documents optiques non suivis à conserver.

## Gates logiciels et matériels
- 131 tests optiques V11 ciblés : PASS ; 77 tests Devctl : PASS.
- Métadonnées + release + contexte graphique + Devctl + système : 147 PASS
  dans un clone isolé après préparation de l'identité RC1.
- Suite complète native Fedora 44 avec Flex reconstruit, code V11 et
  fixture Devctl corrigée : 2 406 PASS / 12 FAIL / 23 SKIP.
- La suite identique sur le candidat 1.3.2-rc1 : 2 406 PASS / 12 FAIL /
  23 SKIP ; les 12 identifiants en échec sont STRICTEMENT identiques.
- Les 12 sont dans les tests d'intégration du lanceur KDE. Le contrôle .79
  Fedora 44 ne contient pas plasma-workspace : ce test n'est pas une
  qualification d'installation propre sur une vraie session KDE/Wayland.
- DVD The Perfect Storm vu entièrement après V11 sur .229, preuve physique
  opérateur seulement pour cette lecture (pas une preuve d'installation RC1).
- IT13 Max .59 : qualification Magnificence historique bornée conservée ;
  aucune promotion nouvelle, aucun déploiement RC1.

## Release gate
La RC n'est PAS publiée. L'archive doit être reconstruite depuis le commit
exact portant cette identité et vérifier son empreinte/manifeste/provenance.
L'installation fraîche, la mise à jour, le premier lancement KDE, les
retours Flex et les parcours audio/vidéo doivent être validés dans un vrai
banc Fedora 44 KDE Plasma/Wayland. Les qualifications matérielles restent
du ressort de Steve. Push, tag et publication réclament un GO distinct.

Les SHA-256 et le rapport de build sont des artefacts générés : les reporter
dans le journal de release externe APRÈS build, et ne pas les insérer dans
ce même commit (évite une dépendance circulaire d'identité).
