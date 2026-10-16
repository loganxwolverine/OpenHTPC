# OPENHTPC — IT13 : Système figé et Magnificence installé — 2026-10-11

Consolidation : 2026-10-11, Europe/Brussels.

## Décision opérateur et limites d'autorité

Steve demande de figer sur le GEEKOM IT13 Max `.59` la mise en page Système physiquement qualifiée sur `.229` et la recette Magnificence qu'il a physiquement validée sur `.59`. Cette demande autorise l'implémentation et la mise à jour bornée de `.59`. Elle n'autorise aucun commit, push, tag, publication ni modification de `.229`.

Le dépôt canonique reste sur `feature/magnificence-sd-auto`, HEAD `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`, avec worktree volontairement dirty et deux stashes protégés. `OPENHTPC_CURRENT_STATE.json` reste `STALE`. Le SHA attendu fourni initialement finissait par `...dddc2cb8`; le HEAD et les checkpoints prouvent `...ddcd2cb8`.

## Implémentation

Un profil exact `intel_meteor_lake_8086_7d55_sd_2160p` est ajouté dans `payload/assets/magnificence_profiles.json`. Il ne s'applique qu'au PCI vendor/device `8086:7d55`, à la classe `DVD_PAL_FILM` et à la sortie `3840x2160`.

Recette :

- `--hwdec=vaapi-copy` ;
- BWDIF `send_frame`, seulement sur les trames entrelacées ;
- `rgba16hf`, `ewa_lanczossharp`, `mitchell`, sigmoid upscaling ;
- ordre shader : FSRCNNX-16 → KrigBilateral → OpenHTPC Vibrance Mild ;
- aucun SSimSuperRes, HQDN3D, RAVU, CAS/RCAS ou ArtCNN.

La recommandation traite le manque de détail luma et la reconstruction chroma du DVD, puis applique une vibrance légère. Les risques restent l'accentuation des défauts MPEG/source et le coût GPU ; la réfutation exige comparaison A/B, temps VO et compteurs de pertes. Le run qualifié précédent fournit 634 mesures, p95 21,20 ms sur un budget 40 ms et zéro perte observée. Le GPU Vulkan est PROVEN, le backend VAAPI-copy OBSERVED, le GPU physique de décodage NOT_PROVEN.

Deux tests verrouillent la sélection exacte, l'ordre des shaders, les arguments MPV, l'absence de SSim/HQDN3D et le refus hors 4K/source qualifiée. La rampe Système existante reste couverte par son test à onze entrées, page unique et empreinte Flex.

## Candidat borné et déploiement `.59`

Pour ne pas embarquer les travaux plugins plus récents, le candidat est composé depuis l'artifact officiel 1.3.1 puis reçoit :

- les payloads Système et le binaire Flex relus directement depuis l'installation `.229` qualifiée ;
- le moteur de session identique au hash installé `.229` ;
- le profil Magnificence exact IT13 ;
- la source Flex de la rampe compacte pour la traçabilité.

Identité non officielle : build `it13-system-magnificence-validator-20261011`. Archive temporaire SHA-256 `0f35a456b63a1d4919fc9450df24a4a220aeccd8b4a08e6b6e9b04ff083cdc02`; manifeste interne intégralement vérifié. `update.sh --check` sur `.59` : PASS, non mutatif.

Avant mutation, snapshot récupérable créé sur `.59` : `/home/steve/.local/state/openhtpc/backups/pre-it13-system-magnificence-20261011T-current.tar.gz`, SHA-256 `50b4de82fd330b754d1a9a16e1d1c9d44fc007a58b249aca4f643e697fbf3160`.

`update.sh` : PASS ; Hardware Passport et configuration préservés, runtime régénéré, session précédemment active relancée automatiquement.

## Vérifications post-installation

- Doctor : `READY` ; version `1.3.1`, build validator daté du 2026-10-11 ;
- une instance Flex autoritaire et un moniteur optique selon Doctor ; aucun MPV actif ;
- hashes des quatre payloads Système et du binaire Flex identiques à `.229` ;
- configuration publiée : exactement onze entrées Système, dont `EXTENSIONS` en 8 et `RETOUR` en 11 ;
- préférence conservée : `presentation_mode=CINEMA_AUTO` ;
- sélection : profil exact IT13, classe STRONG, source `STATIC_PROFILE_DB` ;
- arguments résolus : `vaapi-copy`, BWDIF, FSRCNNX-16 → Krig → Vibrance, sans SSim.

Ces preuves établissent `INSTALLED / SOFTWARE_VERIFIED`. Elles ne remplacent pas une nouvelle lecture physique depuis le profil installé. La validation visuelle antérieure reste `PHYSICALLY_QUALIFIED` uniquement pour le DVD PAL et la sortie 4K60 enregistrés. Autres sources, autres sorties, acoustique et endurance film complet restent `NOT_PROVEN`.

## Autorisations restantes

Aucun commit, push, tag ni publication n'a été effectué. `.229` n'a subi aucune mutation. Les deux stashes protégés n'ont été ni appliqués, ni modifiés, ni supprimés.
