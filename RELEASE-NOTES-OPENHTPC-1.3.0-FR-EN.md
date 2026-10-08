# OPENHTPC 1.3.0 — Patina — Release notes / Notes de version

> Préserver le caractère. Sublimer l’image.

## Français

OPENHTPC 1.3.0 **Patina** fait de Magnificence une chaîne vidéo plus cohérente pour les sources DVD/SD tout en privilégiant la stabilité d'un véritable HTPC de salon.

Sur le profil physiquement qualifié Intel Arc A310 en sortie 4K, Magnificence applique désormais un nettoyage léger à résolution native (`hqdn3d=1.4:1.0:0.05:0.05`) avant la reconstruction FSRCNNX-16 + KrigBilateral puis Vibrance Mild. Le décodage MPEG-2 reste matériel via VA-API copy. Le réglage CLEAN a été retenu pour son lissage discret sans rendu cireux ni plastique.

Les étapes DETAIL supplémentaires étudiées (Adaptive Sharpen, SSimSuperRes et RCAS isolé) ne sont pas activées par défaut sur l'Arc A310 : leur amélioration visuelle à distance normale de visionnage ne justifie pas leur coût GPU. OPENHTPC conserve ainsi une marge saine pour Wayland, les sous-titres, les changements de fréquence et les pointes de charge.

Le cycle DVD conserve aussi les correctifs validés en usage réel : ownership `:tracked` du lancement et verrou `flock` empêchant plusieurs dispatchers DVD concurrents. Plusieurs films ont été regardés sur plusieurs jours sur la machine salon A310 sans incident bloquant observé.

Magnificence n'est pas limité à l'Intel Arc A310 : OPENHTPC continue de sélectionner une recette Magnificence en fonction du profil matériel qualifié lorsqu'il en existe une, avec repli vers PURE lorsqu'aucun profil adapté n'est disponible. Dans Patina, c'est uniquement le nouveau traitement CLEAN qui reste volontairement limité au profil exact Intel Arc A310 DVD/SD vers 2160p. Les autres GPU conservent leur propre recette Magnificence qualifiée lorsqu'elle existe.

Le mécanisme de mise à jour a également été renforcé : `update.sh --check` est désormais non destructif, une mise à jour est refusée proprement pendant une lecture DVD active, et une session OPENHTPC précédemment active est relancée automatiquement après une mise à jour réussie.

## English

OPENHTPC 1.3.0 **Patina** makes Magnificence a more coherent DVD/SD video pipeline while prioritizing real living-room HTPC stability.

On the physically qualified Intel Arc A310 4K profile, Magnificence now applies a restrained native-resolution cleanup (`hqdn3d=1.4:1.0:0.05:0.05`) before FSRCNNX-16 + KrigBilateral reconstruction and Vibrance Mild. MPEG-2 decoding remains hardware-accelerated through VA-API copy. The CLEAN setting was retained for its subtle smoothing without waxy or plastic rendering.

Additional DETAIL stages evaluated for the A310 (Adaptive Sharpen, SSimSuperRes and isolated RCAS) are not enabled by default: their perceptual improvement at normal viewing distance did not justify their GPU cost. This preserves useful headroom for Wayland, subtitles, refresh switching and transient load.

The DVD lifecycle also retains field-validated fixes: `:tracked` playback ownership and a single-instance `flock` guard preventing concurrent DVD dispatchers. Multiple films were watched across several days on the salon A310 system without an observed blocking incident.

Magnificence is not limited to the Intel Arc A310: OPENHTPC still selects a Magnificence recipe according to the qualified hardware profile when one exists, with a PURE fallback when no suitable profile is available. In Patina, only the new CLEAN stage is intentionally scoped to the exact Intel Arc A310 DVD/SD-to-2160p profile. Other GPUs keep their own qualified Magnificence recipe where available.

The updater was also hardened: `update.sh --check` is now non-mutating, updates are refused cleanly while DVD playback is active, and a previously running OPENHTPC session is automatically restored after a successful update.
