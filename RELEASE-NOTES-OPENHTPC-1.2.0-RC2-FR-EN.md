# OPENHTPC 1.2.0 RC2

Pre-release: **Yes**  
Physical validation: **NO-GO — AVR STEREO in BITSTREAM mode**

## Français

RC2 est un candidat de stabilisation sans nouvelle fonctionnalité. Il applique
à la lecture Blu-ray protégée la même politique audio persistante que les
fichiers locaux et DVD, actualise le contexte du lecteur sélectionné, expose
les diagnostics d'ouverture sans dégrader Doctor, et contient les erreurs
transitoires de rendu de fiche disque.

Le correctif bitstream est validé par logiciel mais requiert la validation
physique de Steve. L'échec UHD reproduit hors OPENHTPC reste une limitation
AACS externe par disque/environnement, non bloquante pour RC2.

## English

RC2 is a stabilization-only candidate with no new features. Protected Blu-ray
now applies the same persistent audio policy as local files and DVD, records
the selected-drive context, exposes open diagnostics without degrading Doctor,
and contains transient disc-sheet rendering failures.

The bitstream fix has software PASS status but still requires Steve's physical
validation. The UHD failure reproduced outside OPENHTPC remains an external
per-disc/environment AACS limitation and is non-blocking for RC2.
