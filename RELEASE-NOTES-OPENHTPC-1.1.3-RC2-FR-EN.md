# OPENHTPC 1.1.3 RC2

Pre-release: **Yes**  
Qualified platform family: **Fedora 44 KDE Plasma / Wayland**

## Français

OPENHTPC 1.1.3 RC2 conserve l’ensemble fonctionnel qualifié de RC1 et ajoute
le chemin NVIDIA natif stabilisé : rendu `gpu-next` Vulkan et décodage NVDEC,
sans pont VA-API ni offload forcé. Sur le validateur RTX 3050 qualifié, les
fichiers MEDIA MPEG-2, H.264 et HEVC Main 10 utilisent NVDEC.

Les chemins Intel et AMD restent inchangés avec Vulkan et VA-API. La gestion
MEDIA à chaud, le DVD, les métadonnées optiques TMDb, le mode audio PCM sûr par
défaut, le retour vers KDE et la régénération du runtime lors d’une mise à jour
restent ceux déjà qualifiés.

Le contournement SDDM testé concerne un problème externe de Plasma Login
Manager avec Fedora 44 et le pilote NVIDIA 610.57.04. SDDM n’est pas imposé par
l’installateur OPENHTPC.

Les plugins Blu-ray/UHD protégés, Jellyfin, Plex et streaming ne sont pas
intégrés. La qualification de fichiers MEDIA UHD ne qualifie pas la lecture de
disques UHD protégés.

## English

OPENHTPC 1.1.3 RC2 preserves the qualified RC1 feature set and adds the
stabilized native NVIDIA path: `gpu-next` Vulkan rendering and NVDEC decoding,
without a VA-API bridge or forced offload. On the qualified RTX 3050 validator,
MPEG-2, H.264, and HEVC Main 10 MEDIA files use NVDEC.

Intel and AMD paths remain unchanged with Vulkan and VA-API. Live MEDIA source
management, DVD playback, TMDb optical metadata, safe PCM-by-default audio,
return to KDE, and update-time runtime regeneration retain their previously
qualified behavior.

The tested SDDM workaround addresses an external Plasma Login Manager issue
with Fedora 44 and NVIDIA driver 610.57.04. The OPENHTPC installer does not
require SDDM.

Protected Blu-ray/UHD, Jellyfin, Plex, and streaming plugins are not integrated.
Qualification of UHD MEDIA files does not qualify protected UHD-disc playback.
