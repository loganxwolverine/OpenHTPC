# OPENHTPC 1.3.1 — Patina — Release notes / Notes de version

> Stabiliser la chaîne réelle, préserver l’image.

## Français

OPENHTPC 1.3.1 est la mise à jour de stabilisation de Patina. Elle conserve les recettes Magnificence déjà retenues et corrige les chemins réels qui entourent la lecture : publication multi-GPU par adresse PCI, adaptation de fréquence, préparation audio après modeset, ownership exact des processus, retour Flex, recherche TMDb et rendu Unicode des fiches disque.

Sur le validateur Radeon RX 5700 XT, OPENHTPC sépare désormais les capacités de la RX et de l’Intel HD 630 au lieu de recopier l’union de la machine dans chaque GPU. L’interface distingue aussi une capacité matérielle de sa disponibilité dans le backend VA-API installé. L’identité physique du GPU de décodage reste honnêtement `NOT_PROVEN` tant qu’aucune source runtime indépendante ne l’établit.

Pour les DVD PAL, le cycle impose maintenant l’ordre suivant : changement d’affichage, stabilisation et vérification, nouvelle résolution/préparation audio, puis lancement MPV. Une préférence BITSTREAM est conservée, mais la lecture courante passe temporairement en PCM si le passthrough n’est pas prouvé sur la sortie réellement disponible après le changement HDMI. Un AVR HDMI qualifié conserve le bitstream.

La validation physique a été terminée sur RX 5700 XT et Intel Arc A310. Elle couvre notamment Magnificence, le passage 60 vers 50 Hz puis le retour exact à 60 Hz, la fermeture et le retour Flex, la recherche manuelle TMDb, les caractères CJK/Hangul et Santé globale. Le gate logiciel final compte 2284 tests réussis, 18 ignorés explicitement et aucun échec.

## English

OPENHTPC 1.3.1 is the Patina stabilization update. It preserves the selected Magnificence recipes while correcting the real playback paths around them: per-PCI multi-GPU capability publication, refresh matching, post-modeset audio preparation, exact process ownership, Flex restoration, TMDb search windows and Unicode disc-sheet rendering.

On the Radeon RX 5700 XT validator, OPENHTPC now keeps the RX and Intel HD 630 capability sets separate instead of copying the machine-wide union into each GPU. The UI also distinguishes hardware capability from availability through the installed VA-API backend. Physical decode-GPU identity honestly remains `NOT_PROVEN` until an independent runtime authority can establish it.

For PAL DVD playback, the lifecycle now enforces display switching, settle and verification, fresh audio resolution/preparation, and only then MPV launch. A BITSTREAM preference is retained, while the current playback temporarily falls back to PCM if passthrough cannot be proven on the output available after the HDMI transition. Qualified HDMI AVR output keeps passthrough.

Physical qualification completed on Radeon RX 5700 XT and Intel Arc A310. It covers Magnificence, 60-to-50 Hz switching and exact 60 Hz restoration, clean exit and Flex return, manual TMDb search, CJK/Hangul characters and Overall Health. The final software gate contains 2284 passed tests, 18 explicit skips and zero failures.
