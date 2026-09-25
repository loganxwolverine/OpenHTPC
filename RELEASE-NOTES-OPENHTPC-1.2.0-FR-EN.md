# OPENHTPC 1.2.0

Pre-release: **No**
Reference physical validation: **PASS**

Stable promotion basis: **RC9 qualified behavior, no product-behavior change**

## English

### Stable promotion
- OPENHTPC 1.2.0 promotes the qualified RC9 behavior to stable without changing the media, playback or couch-UX contracts.
- The stable package is rebuilt from its exact source commit with deterministic archive generation and Flex schema-2 provenance.

### Couch library UX
- The MEDIA root now shows an authoritative library summary: total media, identified media and items still requiring review.
- A completed library update reports found, identified and to-review counts instead of a generic success message.
- The `À identifier` queue prioritizes the decision state with compact `À rechercher`, `1 proposition` or `N propositions` labels.
- Long filenames keep more useful title space by omitting the redundant file extension in this review queue.

### Sources and NAS
- Already-mounted CIFS/SMB, NFS and SSHFS filesystems are exposed as `NAS / RÉSEAU`.
- Local folders remain labelled `LOCAL`.
- OPENHTPC does not create, own or modify network mounts; it only discovers mounted filesystems.
- Network filesystems mounted behind systemd autofs are resolved to the effective network filesystem.

### First-use guidance
- With no configured source, MEDIA starts with `+ AJOUTER UNE SOURCE MÉDIA`.
- With a source but no indexed media yet, the primary action becomes `ANALYSER MES MÉDIAS`.
- Once the library exists, the normal action becomes `METTRE À JOUR LA MÉDIATHÈQUE`.

### Reference validation
Validated on:
- Fedora 44 KDE Plasma / Wayland
- Intel Core i5-6500
- Intel Arc A310
- Denon AVR-X1800H

The real reference library contained 150 available media versions: 92 identified and 58 requiring review. RC9 Dev8 was installed from its generated artifact, the couch UI was visually checked at 4K, network-source classification was verified on a real CIFS source, and `openhtpc doctor` returned `Overall: READY`.

The current-tree regression suite collected 2182 tests. RC9 produced 2164 PASS, 2 SKIP and 16 historical failures. Running those exact 16 test nodes on the frozen RC8 release commit produced the same 16 failures, so RC9 introduces no new full-suite regression relative to RC8.

### Preserved from RC8
- Persistent local Media Foundation database and incremental scanning.
- Movie matching, manual TMDb search, cached artwork and detail pages.
- Asynchronous library, enrichment and search operations with live activity feedback.
- Unicode/CJK fallback rendering.
- Existing local, DVD and protected-optical playback behavior.

## Français

### Passage en stable
- OPENHTPC 1.2.0 promeut le comportement qualifié de RC9 en version stable sans modifier les contrats média, lecture ou interface canapé.
- Le paquet stable est reconstruit depuis son commit source exact avec archive déterministe et provenance Flex schema 2.

### Médiathèque pensée pour le canapé
- La racine MEDIA affiche désormais un résumé autoritaire : nombre total de médias, médias identifiés et éléments restant à vérifier.
- Une mise à jour terminée affiche les nombres trouvés, identifiés et à vérifier au lieu d'un simple message générique.
- La vue `À identifier` place l'état de décision en premier avec des libellés compacts : `À rechercher`, `1 proposition` ou `N propositions`.
- Les noms de fichiers longs disposent de davantage de place utile grâce à la suppression de l'extension redondante dans cette file de vérification.

### Sources et NAS
- Les systèmes de fichiers CIFS/SMB, NFS et SSHFS déjà montés sont présentés comme `NAS / RÉSEAU`.
- Les dossiers locaux restent identifiés comme `LOCAL`.
- OPENHTPC ne crée, ne possède et ne modifie aucun montage réseau : il se contente de découvrir les systèmes de fichiers déjà montés.
- Les montages réseau placés derrière systemd autofs sont résolus vers le véritable système de fichiers réseau.

### Premier usage guidé
- Sans source configurée, MEDIA commence par `+ AJOUTER UNE SOURCE MÉDIA`.
- Avec une source mais sans média encore indexé, l'action principale devient `ANALYSER MES MÉDIAS`.
- Une fois la médiathèque créée, l'action normale devient `METTRE À JOUR LA MÉDIATHÈQUE`.

### Validation de référence
Validé sur :
- Fedora 44 KDE Plasma / Wayland
- Intel Core i5-6500
- Intel Arc A310
- Denon AVR-X1800H

La médiathèque réelle du banc de référence contenait 150 versions média disponibles : 92 identifiées et 58 à vérifier. RC9 Dev8 a été installée depuis son artefact généré, l'interface canapé a été contrôlée visuellement en 4K, la détection de la source réseau a été vérifiée sur un vrai montage CIFS et `openhtpc doctor` a retourné `Overall: READY`.

La suite courante contient 2182 tests. RC9 obtient 2164 PASS, 2 SKIP et 16 échecs historiques. L'exécution de ces 16 tests exactement sur le commit RC8 gelé produit les mêmes 16 échecs : RC9 n'introduit donc aucune nouvelle régression globale par rapport à RC8.

### Préservé depuis RC8
- Base locale Media Foundation persistante et scan incrémental.
- Identification des films, recherche TMDb manuelle, affiches en cache et fiches détaillées.
- Mise à jour, enrichissement et recherche asynchrones avec retour d'activité.
- Fallback Unicode/CJK.
- Comportement existant des lectures locale, DVD et optique protégée.
