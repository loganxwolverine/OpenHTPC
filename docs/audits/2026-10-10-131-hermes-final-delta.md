Lecture seule terminée. Snapshot : `openhtpc-audit-20261010T170140Z-6cdaef7-131-final-delta`, branche `feature/magnificence-sd-auto`, HEAD `6cdaef7`, VERSION 1.3.0, worktree dirty « 1.3.1 ». Aucun fichier du snapshot modifié (copie de travail faite sous `/opt/data/cache/scratch/proj`). Aucun commit/push/déploiement/contact machine.

Rapport d'audit contradictoire — OPENHTPC 1.3.1 (delta final)

=========================================================
CONTEXTE / PROVENANCE VÉRIFIÉE
=========================================================
FACT
- Snapshot sans `.git` (pas d'autorité Git) ; `AUDIT_PROVENANCE.md` donne HEAD/`VERSION`/stashes. `GIT_STATUS.txt` liste 50 fichiers modifiés + 6 non suivis ; `GIT_STASH.txt` : `stash@{0}` (RTX stale) et `stash@{1}` (RC7 T5 network deferred). Aucune correspondance avec `.git` local ici, donc les assertions « git show » ne sont pas exécutables (voir plus bas).
- `OPENHTPC_CURRENT_STATE.json` décrit toujours le workstream P2 (STALE) : aucune autorité n'en est tirée, conforme au contrat.
- Tests ciblés réexécutés en copie isolée (venv Python 3.14 + pytest 9.1 + Pillow + PySide6, bits +x restaurés). Résultat : tous les tests hermétiques pertinents PASSENT ; seuls échouent les tests qui exigent `.git` (absents ici) ou un hôte Fedora 44 / libGL (voir « Artefacts d'environnement »).

=========================================================
FACT — points vérifiés conformes (pas de régression reproduite)
=========================================================
1) Ordre DVD modeset→settle→audio→mpv, repli PCM, garde-fou teardown [OK]
- `payload/openhtpc-play-dvd:160-166` : délègue via `--decision-json "$policy_json"` ; aucun `prepare-bitstream` avant le matcher (il n'existe plus qu'au `:168-171`, dans la branche de repli « matcher absent », juste avant mpv). Test source `tests/test_rc7_audio_display_lifecycle.py:313-323` PASS, et `tests/test_refresh_match.py:296` (CLI) PASS.
- `payload/openhtpc-refresh-match.py:390-407` (modeset+settle AVANT prep), `:686-704` (audio_prep après settle), `:711-712` (pin sink), `:663-678` (fail-safe PCM si `iec958_prepare_status != SUCCESS`, préférence user intacte). Tests `test_rc7_audio_display_lifecycle.py` test_08/09/10 PASS.
- Garde-fou teardown `refresh-match.py:567-636` : terminaison forcée seulement après le marqueur propre `Exiting... (Quit)` + 1,5 s ; `playback_teardown_forced` posé `:751`. Test `test_refresh_match.py:277-293` PASS (rc forcé=0).
- `openhtpc-protected-optical-backend.py:217-218,246-253` : `argv` diagnostique = commande effective ; commande construite avec `--log-file={attempt}` (`:185`) donc le garde-fou teardown est actif aussi en optique protégé.

2) Publication capacités par GPU PCI + remédiation Mesa AMD sans union trompeuse [OK sur le fond]
- `openhtpc-capabilities.py:631-655` : `per_gpu_va_profiles` indexé par PCI persistant, **uniquement** si `gpu_runtime.validate_render_node(node, pci, …) is True` (identité PCI↔render prouvée). `:683-720` : matrice par PCI. `:829-877` : `synchronize_profile_capabilities(..., per_gpu_observations)` ; miroirs liés au PCI exact, union machine seulement pour `media_stack`. Test `test_amd_codec_phase2a_collector.py` (dual-GPU) PASS ; `test_codec_capability_audit.py` PASS.
- Installateur : `install-openhtpc-fedora.sh:103-131` annote chaque `vainfo` par vendor sysfs ; `:138-147` `media_extension_required` raisonne **par vendor** (AMD_VA_*/INTEL_VA_*), jamais sur l'union ; `:555-563` mode update = différé, pas de prompt DNF caché ; `:245-249` supprime l'écrasement des miroirs par l'union. Test `test_amd_codec_phase2b_enablement.py::test_multi_gpu_union_cannot_hide_missing_amd_codec_driver` PASS (GLOBAL=true,true,true / AMD=false,false,false / INTEL=true,true,true), ainsi que `test_update_mode_reports_per_gpu_remediation_without_prompting`.

3) Libellés « Compatibilité vidéo » [OK]
- `openhtpc-system-model.py:532-565` : capacités lues **par PCI du GPU de rendu** (`decode["devices"][render_pci]`), jamais l'union ; `UNSUPPORTED` → « Indisponible via <backend> » (`:558-559`), backend lu de la pure.conf effective, sinon « Non déterminé ». `openhtpc-ui.py:426` colore « Indisponible… ». Test `test_rc7_system_model.py:677` PASS.

4) Rafraîchissement Santé globale après PID Flex [OK]
- `openhtpc-home.py:178-199` : publication atomique `authoritative_flex_pid` (`:181-182`) → attente bornée 2 s vérifiant le PID exact dans `managed_processes()["ui"]` (`:184-191`) → `engine.render_system_pages()` (`:192`) → `FLEX_STARTED` (`:203`). Échec du refresh journalisé sans tuer Flex. `session-engine.py:1625-1666` (helper isolé) + `:1727`. Tests `test_1_3_1_stabilization_lifecycle.py:135-172` PASS (écrasement BLOCKED→READY par le helper prod + ordre publish<observe<render<FLEX_STARTED).

5) Télémétrie MEDIA détection Flex [OK]
- `openhtpc-play:230` (regex POSIX `( |$)`, plus de groupe Python non capturant). Test `test_1_3_1_stabilization_lifecycle.py:175-188` PASS (compte=1, pid exact).

6) lifecycle tracked exact [OK]
- Source unique `vendor/flex-launcher/src/lifecycle.c` (état, ECHILD fail-closed `:192-200`, reap exact `:176-187`, focus/timeout gardés `:153-163`). `launcher.c:3372-3376` reape uniquement le PID tracké ; `:2697-2704` rejette la double activation ; garde clavier/contrôleur `:692, :2663, :2902, :2942`. Aucun `wait(NULL)`/`waitpid(-1)`/`killall`/`pkill` dans `src/`. Harness de test = ctypes sur `lifecycle.c` compilé (`test_rc7_tracked_lifecycle.py:67-92`) ; tests comportementaux PASS (dont test_11 réécrit, test_7 T8.5 ordering).

=========================================================
FACT — findings (anomalies / incohérences)
=========================================================
F-A) [À CLASSER — impact dépôt↔installateur↔binaire] Le binaire Flex distribué n'est pas reconstruit depuis la source modifiée, et sa métadonnée ne correspond pas au binaire.
- `GIT_STATUS.txt` : ` M vendor/flex-launcher/src/platform/unix.c` mais **ni** `payload/flex/bin/flex-launcher` **ni** `payload/flex/BUILD-METADATA.json` ne sont modifiés → le delta source n'est pas dans l'artefact livré.
- `unix.c:341-352` ajoute `log_error("Could not probe launched application process: %s", …)` ; cette chaîne est **absente** du binaire (`strings payload/flex/bin/flex-launcher` → 0 occurrence ; « Application failed to launch » présent 1×). Le binaire (mtime 2026-09-16) est antérieur au delta.
- `sha256(payload/flex/bin/flex-launcher)` = `6427cfce…` ≠ `BUILD-METADATA.json.binary_sha256` = `351fbe72…`. Validateur projet reproduit : `tools/validate_public_candidate.py:101` → `FAIL flex_binary` (TOTAL 59/65).
- L'installateur installe le binaire précompilé : `install-openhtpc-fedora.sh:629` (aucun rebuild).
- Portée réelle : le chemin « classic launch probe » est atteignable en production via commandes **nues** générées par `session-engine.py:2036` (`systemctl poweroff`), `:2040` (navigateur média), `:2041` (dvd-ui) → `start_process(cmd, application=true)` → bloc `unix.c:335-352`. Le correctif (init `status=0`, contrôle seulement si `launch_probe==child_pid`, boucle EINTR) n'est donc **pas déployé**.
- Classement proposé : NON BLOQUANT pour les qualifications physiques `.67` déjà consignées (celles-ci passent par `:tracked`, non par ce chemin) ; BLOQUANT pour un packaging/déploiement 1.3.1 « propre » (source ≠ artefact). Action minimale : soit reconstruire `payload/flex/bin/flex-launcher` depuis `vendor/flex-launcher/src` + régénérer `BUILD-METADATA.json`, soit documenter/retirer le delta `unix.c`. Note : la divergence binaire↔métadonnée existe aussi au HEAD capturé (aucun des deux fichiers n'est modifié dans le worktree).

F-B) [NON BLOQUANT — incohérence interne] VC-1 absent de la projection publiée `vaapi_decode`.
- `openhtpc-capabilities.py:264-273` : `CODECS` inclut `vc1` (VAProfileVC1*) → la matrice `video_decode.devices[<PCI>]` (lue par la page Système) contient VC-1.
- `:789-796` `PROFILE_CODEC_MAP` ne contient **pas** `vc1` → `_profile_codec_observation_from_matrix` (`:799-809`) produit un `vaapi_decode` **sans** VC-1, utilisé pour `media_stack.observed_capabilities.vaapi_decode` et tous les miroirs PCI (`:847, :863`).
- Conséquence : la page « Compatibilité vidéo » (via la matrice brute) affiche correctement VC-1 « Pris en charge », mais la publication agrégée/miroirs du profil sous-déclare VC-1. Aucun test ne compare VC-1 entre `devices` et `vaapi_decode` → silencieux. Faible sévérité (sous-déclaration, pas d'« union trompeuse »), mais incohérence de la « publication par GPU PCI ».

F-C) [DETTE FUTURE — hygiène release] Le validateur public échoue sur l'arbre de travail à cause des documents non publiables.
- `tools/validate_public_candidate.py:74-76` scanne **tout** l'arbre (`ROOT.rglob`) pour `/home/steve` et les IP `192.168.1.(10|132|229)` ; les fichiers non suivis `docs/continuity/*`, `docs/audits/*`, `OPENHTPC-ROADMAP.md`, et l'artefact `WORKTREE.patch` les contiennent → `FAIL no_private_home`/`FAIL no_private_ips` (reproduit). Non bloquant tant que ces fichiers ne sont pas livrés, mais à exclure explicitement au packaging.
- `FAIL folder_asset_reference` : `:90` exige la chaîne `assets/ui/folder.png` dans `session-engine.py`, alors que la production utilise `media_ui/"folder.png"` (`session-engine.py:803,806`). Check obsolète (validateur étiqueté 1.1.0-dev38), indépendant de ce tranche.

F-D) [NON BLOQUANT — testabilité] Un test hérite du host à la place d'un mock.
- `tests/test_update_runtime_regeneration_dev14.py::test_11` exécute le **vrai** installateur, lequel lit `/etc/os-release` et exige Fedora 44 (`install-openhtpc-fedora.sh:347-350`) → échec hors Fedora. Les nouveaux tests `test_1_3_1_stabilization_lifecycle.py:73-132` utilisent au contraire un `install.sh` factice (hermétiques, PASS). Le nouveau lot respecte AGENTS ; l'ancien test reste dépendant de l'hôte.

F-E) [NON BLOQUANT — héritage, pré-existant] Chemins d'algorithme Flex non-trackés.
- `launcher.c:2790-2795,3342-3345,3378-3382` conservent un cycle de vie par focus pour les applications externes **non** `:tracked` (ex. navigateur média, `systemctl poweroff`). OPENHTPC route toute la lecture via `:tracked` (session-engine `:663, :1433, :1446, :1467`, disc-sheet `:49, :56`) ; l'invariant « focus ≠ fin de processus » est respecté pour la lecture. Aucune régression introduite par ce tranche ; à surveiller si une future entrée lançait un lecteur en commande nue.

=========================================================
HYPOTHÈSE
=========================================================
H-1) Le delta `unix.c` (F-A) visait une lecture de `status` non initialisée qui pouvait faire échouer aléatoirement les entrées `systemctl poweroff` / navigateur / dvd-ui (WPEXITED(garbage)). Non prouvé empiriquement ici (pas d'exécution de Flex), déduit du seul code + des commandes nues générées. Les qualifications `.67` consignées n'exercent pas ce chemin → aucun effet observé.

H-2) L'omission VC-1 (F-B) pourrait masquer un codec dans d'éventuels consommateurs du profil (miroirs/`media_stack`). Aucun consommateur actuel identifié ne l'utilise pour VC-1 ; la page Système n'est pas affectée. À confirmer si un futur gate de cohérence étend la comparaison aux 8 codecs (`tools/openhtpc-codec-capability-audit.py` ne compare que les clés de `CODECS` via `union`, côté matrice brute ; les miroirs dérivés en sont une projection).

H-3) `no_private_home`/`no_private_ips` (F-C) échouent ici aussi à cause des documents de continuité non suivis. S'ils ne sont jamais empaquetés, c'est un faux positif local ; sinon bloquant pour une validation « public candidate ».

=========================================================
QUESTION OUVERTE
=========================================================
Q-1) F-A : le delta `unix.c` doit-il être considéré comme partie du candidat 1.3.1 ? Si oui, le binaire distribué doit être reconstruit (et `BUILD-METADATA.json` régénéré) avant tout packaging ; sinon, quelle raison justifie un delta source non compilé dans le worktree ?

Q-2) F8/F-B : politique des miroirs PCI (`capabilities.py:857-867`) — un rôle GPU sans entrée per-PCI laisse sa valeur **inchangée** (possiblement périmée) au lieu d'un fail-closed. Disposition antérieure = « risque séparé, pas de divergence sur `.67` ». Confirmez-vous que ce fail-open reste accepté pour 1.3.1 ?

Q-3) F-A : `tools/validate_public_candidate.py` est-il encore un gate actif ? S'il l'est, le `FAIL flex_binary` pré-existe au HEAD et devrait être classé dette/incident plutôt que 1.3.1.

=========================================================
ARTEFACTS D'ENVIRONNEMENT (ne pas confondre avec des findings)
=========================================================
- Snapshot sans `.git` : échec attendu de `test_protected_optical_backend_dev3.py` (boundary, `git show 8553e…`), `test_dev37_final_ui_optical.py`, `test_update_runtime_regeneration_dev14.py::test_11` (aussi hôte), et de quelques assertions historiques — PASS sur le dépôt canonique avec `.git` en lecture seule (cf. checkpoint 1847 PASS).
- Fichiers 0444 sans bit +x : rétabli en copie (`chmod +x`) sinon `install.sh`/`openhtpc-*`/`update.sh` non exécutables → faux échecs. Pillow/PySide6 absents initialement (rôle `libGL`/Pillow), installés pour l'audit.
- 13 skips `OBSOLETE_FROZEN_SOURCE_IDENTITY` confirmés (dette de couverture, non promus en PASS), identiques à l'audit précédent.

=========================================================
SYNTHÈSE
=========================================================
- Aucun blocage sur les six deltas demandés : ordre DVD/repli PCM/teardown, libellés Compatibilité vidéo, refresh Santé, télémétrie MEDIA, publication par PCI sans union trompeuse, lifecycle tracked exact = FACT conformes et couverts par des tests qui passent (hors artefacts d'environnement).
- Le seul point à trancher avant packaging/déploiement 1.3.1 est F-A (binaire Flex non reconstruit depuis `unix.c` + `BUILD-METADATA` incohérent). F-B/F-C/F-D/F-E = non bloquants / dette.
- Aucune action Git, aucun déploiement, aucune modification du snapshot.
