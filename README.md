
• # Guide d’installation — OPENHTPC Basic V1.0.0

  ## Prérequis

  OPENHTPC Basic V1.0.0 a été validé sur :

  - Fedora 44
  - KDE Plasma
  - session Wayland
  - architecture x86_64

  Avant l’installation, Fedora doit impérativement être entièrement à jour.

  ## 1. Mettre Fedora à jour

  Ouvrez Konsole puis exécutez :

  sudo dnf upgrade --refresh

  Lorsque la mise à jour est terminée, redémarrez l’ordinateur :

  systemctl reboot

  Après le redémarrage, connectez-vous à une session KDE Plasma utilisant Wayland.

  ## 2. Télécharger OPENHTPC

  Téléchargez l’archive suivante depuis la page GitHub Releases du projet :

  OpenHTPC-Basic-V1.0.0.tar.gz

  Téléchargez également le fichier de contrôle :

  OpenHTPC-Basic-V1.0.0.tar.gz.sha256

  Placez les deux fichiers dans le même dossier, par exemple Téléchargements.

  ## 3. Vérifier l’archive

  Dans Konsole :

  cd ~/Téléchargements
  sha256sum -c OpenHTPC-Basic-V1.0.0.tar.gz.sha256

  Le résultat attendu est :

  OpenHTPC-Basic-V1.0.0.tar.gz: OK

  N’installez pas l’archive si la vérification échoue.

  ## 4. Extraire OPENHTPC

  tar -xzf OpenHTPC-Basic-V1.0.0.tar.gz
  cd OpenHTPC-Basic-V1.0.0

  ## 5. Lancer l’installation

  ./install.sh

  L’installateur suit une procédure contrôlée :

  Vérifier → Expliquer → Demander → Installer → Confirmer

  Il peut demander l’autorisation d’installer les dépendances multimédias nécessaires et d’activer certains dépôts Fedora/RPM Fusion.

  Lisez chaque demande puis confirmez uniquement si vous l’acceptez. Le mot de passe administrateur peut être demandé par Fedora.

  L’installateur ne réalise pas de mise à niveau générale de Fedora.

  ## 6. Configurer OPENHTPC

  Pendant la configuration :

  1. Vérifiez les informations détectées par le Hardware Passport.
  2. Configurez l’affichage.
  3. Laissez OPENHTPC configurer automatiquement l’audio.
  4. Ajoutez un ou plusieurs dossiers contenant vos médias.
  5. Configurez éventuellement TMDb.

  TMDb est facultatif. OPENHTPC peut lire les médias locaux et NAS sans clé API.

  Exemples de sources média :

  /home/utilisateur/Vidéos
  /home/utilisateur/NAS/Films
  /mnt/medias/Films

  Les sources doivent être accessibles par votre utilisateur avant de démarrer OPENHTPC.

  ## 7. Vérifier l’installation

  Contrôlez la version :

  openhtpc version

  Résultat attendu :

  1.0.0

  Lancez ensuite le diagnostic :

  openhtpc doctor

  Une installation saine doit se terminer par :

  Overall: READY

  Lors du tout premier diagnostic, certains éléments liés à une session précédente peuvent légitimement apparaître comme FIRST_RUN, NOT_TESTED,
  NOT_INITIALIZED ou INACTIVE.

  ## 8. Démarrer OPENHTPC

  openhtpc start

  OPENHTPC peut également démarrer automatiquement lors de l’ouverture de la session KDE, selon la configuration installée.

  ## Commandes utiles

  openhtpc start
  openhtpc stop
  openhtpc setup
  openhtpc doctor
  openhtpc support-bundle
  openhtpc version

  - openhtpc setup permet notamment de modifier les sources média.
  - openhtpc doctor vérifie l’état de l’installation.
  - openhtpc support-bundle crée un paquet de diagnostic assaini.
  - Quittez normalement OPENHTPC depuis son interface pour revenir au bureau KDE.

  ## Mise à jour d’une installation existante

  Depuis le dossier extrait de la nouvelle version :

  ./update.sh

  La mise à jour conserve notamment la configuration utilisateur et les sources média.

  ## Désinstallation

  Depuis le dossier de la version installée :

  ./uninstall.sh

  La désinstallation standard conserve la configuration et ne supprime jamais les fichiers multimédias.

  Pour supprimer également la configuration, le cache et l’état OPENHTPC :

  ./uninstall.sh --purge-config

  Cette option ne supprime toujours pas vos films ou autres médias.
