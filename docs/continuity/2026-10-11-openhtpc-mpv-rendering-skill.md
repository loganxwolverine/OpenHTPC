# Skill projet OPENHTPC MPV Rendering — 2026-10-11

## Périmètre et autorité

Steve a demandé la création de la skill projet `openhtpc-mpv-rendering` comme référence procédurale pour MPV, libplacebo, Vulkan, gpu-next, VAAPI, upscaling, shaders custom et qualification du rendu. Le lot est documentaire : il n'autorise ni modification de preset Magnificence, ni déploiement, ni lecture physique, ni commit/push/publication.

Pré-vol observé : branche `feature/magnificence-sd-auto`, HEAD `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`, worktree déjà dirty. `OPENHTPC_CURRENT_STATE.json` décrit toujours l'ancien workstream 1.2.0/P2 et reste `STALE`. Les deux stashes ont été laissés intacts, dont `stash@{1}: RC7 T5 network deferred` protégé.

## Réalisation

La skill a été créée sous `.agents/skills/openhtpc-mpv-rendering/` avec :

- un `SKILL.md` concis et orienté procédure ;
- une référence d'autorité/provenance et des sources officielles MPV/libplacebo/Vulkan/Mesa/libva ;
- une référence pipeline gpu-next/Vulkan/VAAPI, scaling luma/chroma, hooks et ordre effectif ;
- un catalogue décisionnel FSRCNNX, KrigBilateral, SSimSuperRes, CAS/RCAS, RAVU et ArtCNN ;
- une checklist de qualification avec budgets 24/25/50/60 fps, marge cible 25 %, drops, A/B, plateformes et lien avec Magnificence Auto ;
- les métadonnées UI `agents/openai.yaml`.

Le `.gitignore` conserve les autres contenus locaux de `.agents/` ignorés mais exempte explicitement cette skill afin qu'elle soit visible comme artefact projet et puisse être revue avant un éventuel commit autorisé.

Chaque recommandation shader doit documenter : défaut traité, étage, bénéfice attendu, artefacts, coût GPU qualitatif et méthode de validation/réfutation. ArtCNN est explicitement `STUDY_PENDING`; sa présence dans les assets ne vaut ni sélection ni qualification.

Les skills `shader-programming` et `ffmpeg-skill` sont appelées seulement dans leur périmètre : analyse GLSL théorique pour la première, préparation/probe de corpus pour la seconde. Elles ne remplacent ni les contrats mpv/libplacebo ni la qualification runtime OPENHTPC.

## Vérification

Commande exécutée :

```text
python3 .agents/skills/skill-creator/scripts/quick_validate.py .agents/skills/openhtpc-mpv-rendering
```

Résultat : `Skill is valid!` (exit 0). Six fichiers sont présents, `SKILL.md` contient 40 lignes, les quatre références 296 lignes au total, et aucun marqueur `TODO`/placeholder n'a été trouvé.

Aucun fichier sous `payload/assets/magnificence_profiles.json`, `payload/assets/magnificence_gpu_knowledge.json`, `payload/assets/shaders/` ou dans le runtime installé n'a été modifié par ce lot. Seul `.gitignore` est ajusté hors skill/continuité pour rendre la nouvelle skill traçable. Aucune qualification logicielle ou physique nouvelle n'est revendiquée.

## Prochaine action

Utiliser la skill lors d'une prochaine analyse ou campagne explicitement autorisée. Toute proposition de promotion Auto reste soumise au protocole canonique, aux tests, à la décision visuelle de Steve et à une autorisation distincte de modification des presets.
