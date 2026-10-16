# OPENHTPC — Installation 1.3.1 sur GEEKOM IT13 Max — 2026-10-11

Consolidation : 2026-10-11, Europe/Brussels.

## Autorisation et provenance

- Steve a fourni l'adresse `192.168.1.59`, activé SSH et explicitement demandé l'installation fraîche d'OPENHTPC sur le IT13.
- Source installée : artifact officiel `OpenHTPC-1.3.1.tar.gz`, construit depuis le HEAD exact `975402945376618db56e29945074ea30ddcd2cb8`.
- SHA-256 vérifié localement puis sur le IT13 : `933ce9a780bfc901c8cb90ca72e7973da088b87e294d0c2bb0b73e2aa608837c`.
- Le `MANIFEST.sha256` interne a été vérifié intégralement avant installation.
- Le worktree canonique dirty du chantier plugins/Système n'a pas servi de source et a été préservé.
- Aucun commit, push, tag, merge ni publication n'a été effectué.

## Prévol observé

- Machine/hostname : GEEKOM IT13 Max / `IT13Max`.
- OS : Fedora Linux 44 KDE Plasma Desktop Edition, session Wayland.
- Kernel : `7.2.9-200.fc44.x86_64`.
- CPU : Intel Core Ultra 9 185H.
- GPU : Intel Meteor Lake-P / Arc, `8086:7d55`, PCI persistant `0000:00:02.0`, pilote kernel `i915`.
- Stockage : environ 457 Go libres sur `/` et `/home` au prévol.
- Aucune installation OPENHTPC antérieure n'a été détectée.

## Installation

L'installateur officiel a été ouvert dans la session graphique locale afin que Steve saisisse le mot de passe `sudo` et valide les transactions prévues. Il a installé les dépendances manquantes, le support DVD, RPM Fusion Free/Tainted, `libdvdcss` et les compléments multimédias Intel proposés par le produit. Le run `20261011T095613-5519` s'est terminé avec :

- `result=PASS` ;
- `failed_stage=NONE` ;
- version `1.3.1` ; build `public-release-1.3.1` ; build date `2026-10-10` ;
- Hardware Passport PASS, Generated Runtime PASS, Flex provenance PASS ;
- Doctor final d'installation : `Overall: READY`.

## Faits runtime observés

- Mesa DRI/Vulkan : `26.2.4` ; Vulkan Instance `1.4.341`, device Intel Arc MTL API `1.4.354`.
- UUID Vulkan opaque observé : `8680557d-0800-0000-0002-000000000000`. Il ne sert pas à déduire l'identité PCI.
- VAAPI Intel iHD `26.1.5` expose notamment MPEG-2, H.264, HEVC/Main10, VP9 et AV1. Cela ne prouve pas l'identité physique du GPU de décodage.
- MPV `0.41.0`, libplacebo `7.360.1`, FFmpeg runtime `8.1.3`.
- Sortie active HDMI-A-1 : 3840×2160 @ 60 Hz ; profondeur courante annoncée 10 bits ; HDR inactif/non qualifié.
- Les fichiers effectifs `runtime/mpv/pure.conf` et `reference.conf` demandent `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=vaapi`.
- Après `openhtpc start` : une instance Flex autoritaire, un moniteur optique, `Appliance state RUNNING`, session Wayland/KDE reconnue et Doctor `Overall: READY`.

## Limites et prochaine action

Cette intervention prouve l'installation et la disponibilité logicielle de base. Elle ne prouve pas encore :

- une lecture MPV réelle ni la liaison Vulkan post-mortem T8.5 ;
- le GPU physique de décodage, qui reste `NOT_PROVEN` ;
- la qualité visuelle ou sonore ;
- les temps de rendu, dropped/delayed frames, températures, consommation ou marge ;
- une classe ou un profil Magnificence ;
- une endurance film.

TMDb reste non configuré, la calibration absente et les plugins optionnels désactivés. La prochaine action est une qualification bornée suivant `docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md`, en commençant par Pure et une preuve de lecture MPV avant les shaders. Aucun preset ne doit être modifié sur la seule base de cette installation.

## État Git canonique au jalon

- Branche : `feature/magnificence-sd-auto`.
- HEAD : `975402945376618db56e29945074ea30ddcd2cb8`.
- Worktree : modifications plugins/Système et documentation non commitées préservées ; ce checkpoint s'y ajoute.
- Stashes à préserver : `pre-sync stale RTX experiment 2026-10-02` et `RC7 T5 network deferred`.
- `OPENHTPC_CURRENT_STATE.json` reste `STALE` pour le workstream courant et n'a autorisé aucune action.
