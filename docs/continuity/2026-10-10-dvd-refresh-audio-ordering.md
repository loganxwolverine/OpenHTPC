# OPENHTPC — Checkpoint DVD / refresh / audio ordering — 2026-10-10

## Symptôme physique à ne jamais reclassifier comme normal

Sur le validateur `.67` (RX 5700 XT), lancement d'un DVD PAL 25 fps avec adaptation de fréquence : écran noir ; la vidéo ne devient visible qu'après une pression sur la flèche droite / seek.

Ce symptôme a déjà existé et avait été diagnostiqué le 2026-09-10. Il doit être traité comme une régression critique de séquencement display/audio, pas comme un comportement acceptable de HDMI, de mpv ou de Magnificence.

## Cause historique et invariant obligatoire

Cause prouvée historique : un modeset HDMI exécuté après la préparation du bitstream PipeWire peut recréer/réinitialiser le sink audio. mpv démarre alors avec `video-sync=audio` mais le sink/PTS audio n'est plus valable ; la vidéo peut rester noire/figée jusqu'à ce qu'un seek force le redémarrage des décodeurs.

Invariant de lancement :

1. effectuer toutes les mutations d'affichage (refresh/HDR) ;
2. attendre le settle et vérifier le mode obtenu ;
3. réidentifier/repréparer la cible audio HDMI/PipeWire pour le bitstream ;
4. lancer mpv immédiatement après la préparation audio ;
5. restaurer le mode d'affichage après la terminaison exacte du lecteur.

Ne jamais préparer le bitstream avant un modeset qui reste à effectuer. Ne pas contourner cet invariant par une préparation audio séparée dans un dispatcher.

## Régression observée le 2026-10-10

`payload/openhtpc-refresh-match.py` possédait toujours le bon mécanisme dans `run_playback(..., decision=...)` : modeset/settle puis `prepare_audio_target_bitstream(...)` puis mpv.

Mais `payload/openhtpc-play-dvd` préparait explicitement le bitstream avec `prepare-bitstream` avant d'appeler `openhtpc-refresh-match.py`. Le dispatcher DVD contournait donc l'invariant malgré les tests unitaires du matcher.

Preuve physique/log sur `.67` : pendant la lecture noire, mpv répétait `Stream state changed ... state=error error=no target node available` sur `AO: [pipewire] ... spdif-ac3`. Cela confirme l'invalidation de la cible audio après la mutation d'affichage.

## Correction locale 1.3.1 candidate

- `payload/openhtpc-refresh-match.py` accepte désormais `--decision-json` et transmet la décision résolue à `run_playback()`.
- `payload/openhtpc-play-dvd` ne prépare plus le bitstream avant le matcher.
- Le DVD transmet `--decision-json "$policy_json"` au matcher ; le matcher possède donc l'ordre modeset -> settle -> audio prep -> mpv.
- Si le matcher est absent, le fallback DVD prépare le bitstream immédiatement avant mpv, sans mutation d'affichage intermédiaire.
- La politique de cadence introduite le même jour reste : DVD PAL 25 fps préfère 50 Hz plutôt que 25 Hz quand les deux existent.

## Tests et installation

Gate ciblé après correction : `96 passed` sur les suites cadence/modeset/audio/routage/télémétrie concernées.

Nouveaux garde-fous :
- test d'intégration de source imposant que `openhtpc-play-dvd` délègue la décision audio au matcher et n'exécute pas `prepare-bitstream` avant lui ;
- test CLI imposant que `--decision-json` arrive dans `run_playback()`.

Déployé manuellement sur `.67` pour validation physique :
- `openhtpc-refresh-match.py` SHA256 `094e0031effe8d1803ad33dc905948ac7692a7c8a6fee3daac46f11754d5f731`
- `openhtpc-play-dvd` SHA256 `0e7202e0c200f90d10bc3ee6aa3cba4516700204fa431db3eea71e4c12daf51b`
- sauvegarde précédente : `/home/steve/.local/state/openhtpc/manual-backups/20261010T134235/`
- smoke de la nouvelle CLI en `refresh_matching=OFF` : RC=0.

## Qualification finale du 2026-10-10

Le rétablissement de l'ordre modeset -> settle -> audio prep -> mpv était nécessaire mais n'a pas suffi sur le validateur `.67`. Le diagnostic final a montré que la préférence utilisateur `BITSTREAM` était conservée alors que la sortie réellement active après repli était `ALC1150 Digital` / IEC958 S/PDIF. Sur ce sink précis, mpv en passthrough AC3 échouait avec `no target node available`, même lorsque le sink était explicitement épinglé. Un smoke PCM envoyé vers ce même sink a au contraire réussi.

Correction finale : après le modeset et la résolution de la sortie audio, OPENHTPC conserve la préférence utilisateur BITSTREAM mais bascule **cette lecture** en PCM lorsque le passthrough n'est pas prouvé. Quand une sortie qualifiée (par exemple un AVR HDMI disponible et préparé avec succès) est réellement présente, le bitstream reste autorisé.

Dernier lancement contrôlé :
- DVD PAL 25 fps -> cible 3840x2160 @ 50 Hz ;
- `--audio-device=pipewire/alsa_output.pci-0000_00_1f.3.iec958-stereo` ;
- `--audio-spdif=` (fallback PCM pour cette lecture) ;
- `AO: [pipewire] 48000Hz 5.1(side) 6ch floatp` ;
- PipeWire `connecting -> paused -> streaming`, `audio ready` présent ;
- aucune occurrence de `no target node available` ;
- première image vidéo reçue normalement ; `vaapi-copy` et BWDIF actifs ;
- utilisateur : film démarré automatiquement sans pression sur flèche droite, puis second essai manuel confirmé OK ;
- état transactionnel final observé : `RESTORED`, `playback_started=true`, `playback_exit_code=0`, `restore_requested=true`, `restore_verified=true`, `effective_audio_mode=PCM`, raison `passthrough_unproven_post_modeset` ;
- fréquence courante après retour : 3840x2160 @ 60 Hz ; Flex seul actif.

Gate ciblé final autour du fail-safe PCM : `93 passed`. Le précédent gate cadence/modeset/audio/routage/télémétrie était `96 passed`.

## Limites / état de qualification

- Aucun commit/push/tag/release n'est autorisé ni réalisé par ce checkpoint.
- Le démarrage DVD automatique et le retour de transaction sont physiquement/techniquement validés sur `.67` pour ce cas.
- Il reste à terminer la qualification end-to-end générale du candidat 1.3.1 sur `.67` (autres chemins UI, capacités multi-GPU publiées, recherche manuelle, updater/lifecycle, etc.) avant tout déploiement `.229` ou demande d'autorisation de commit.
- Un échec indépendant d'un test du backend Blu-ray protégé concernant son diagnostic `argv`/socket IPC a été observé dans une suite élargie ; il n'a pas été traité dans ce chantier DVD et ne doit pas être confondu avec cette correction.
