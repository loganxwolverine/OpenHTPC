# OPENHTPC 1.1.3 RC1

Pre-release: **Yes**  
Qualified platform: **Fedora 44 KDE Plasma / Wayland**

## Français

OPENHTPC 1.1.3 RC1 fournit une interface home-cinéma locale avec lecture des
fichiers MEDIA, DVD, métadonnées optiques TMDb et gestion à chaud des sources
MEDIA. Après ajout, retrait ou réajout d’une source, l’interface Flex active
utilise immédiatement la même génération MEDIA que le manifeste de lecture,
sans redémarrage d’OPENHTPC.

Le mode audio sûr par défaut reste **PCM**. AC3 / Dolby Digital en BITSTREAM
reste physiquement qualifié uniquement dans le périmètre HDMI → AVR Denon déjà
validé. Les autres codecs bitstream restent non qualifiés physiquement.

Les capacités AMD qualifiées couvrent le chemin Ryzen observé avec rendu
Vulkan, décodage VA-API et runtime MPV généré. Elles ne constituent pas une
promesse pour tout GPU ou pilote AMD.

Limites connues : les plugins Blu-ray, UHD, Jellyfin, Plex et streaming sont
optionnels. Les lectures de fichiers MEDIA « 300 » et « Romulus UHD » ne
qualifient pas la lecture de disques UHD protégés. Aucun support de disque UHD
protégé n’est revendiqué par cette RC.

## English

OPENHTPC 1.1.3 RC1 provides a local home-theater interface with MEDIA file
playback, DVD playback, TMDb optical metadata, and live MEDIA source management.
After adding, removing, or re-adding a source, the running Flex UI immediately
uses the same MEDIA generation as playback authority, without restarting
OPENHTPC.

The safe default audio mode remains **PCM**. AC3 / Dolby Digital BITSTREAM
remains physically qualified only for the previously validated HDMI → Denon AVR
scope. Other bitstream codecs remain physically unqualified.

Qualified AMD capability is bounded to the observed Ryzen path with Vulkan
rendering, VA-API decoding, and generated MPV runtime. It is not a blanket claim
for every AMD GPU or driver.

Known limitations: Blu-ray, UHD, Jellyfin, Plex, and streaming plugins are
optional. Playback of the “300” and “Romulus UHD” MEDIA files does not qualify
protected UHD optical-disc playback. This RC makes no protected UHD-disc claim.
