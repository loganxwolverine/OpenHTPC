# OPENHTPC — Dispositions des findings ouverts — 2026-10-13

Consolidation : 2026-10-13, Europe/Brussels (relevé final 11:29 UTC / 13:29 CEST).
Priorité appliquée à la demande de Steve : **fermer la boucle** — donner à chaque
finding déjà produit une disposition écrite, une raison, une destination et un
responsable, avant d'ajouter une preuve nouvelle.

Ce checkpoint ne crée aucune autorisation. Il ne modifie aucun code, aucun profil,
aucun état machine et aucune installation.

## Autorité et périmètre

- Mandat : « applique ta priorité » (boucler la traçabilité des travaux déjà
  produits). Aucun commit, push, tag, publication, déploiement ni action physique
  n'est autorisé par ce checkpoint.
- Findings traités : revue matrice Magnificence `openhtpc-magnificence-matrix-20261011T162911Z`
  (C1–C7, D1–D6) et audit `hermes-real-01` (F1, H1–H2, Q1–Q3).
- Audits triés : trois snapshots préparés sans rapport (voir §5).

## Base et limites — à lire avant de conclure

Mon atelier repose sur le snapshot `openhtpc-preflight-20261011T105147Z-9754029`
(capture 2026-10-11 10:51 UTC). Cette base est **en retard** sur le worktree
canonique : le snapshot `openhtpc-magnificence-matrix-20261011T162911Z` (capture
16:29 UTC, lisible en read-only) démontre l'existence de fichiers canoniques
absents de ma copie au 2026-10-13 :

    docs/continuity/2026-10-11-plugin-dependency-resolution.md
    docs/continuity/2026-10-11-dvd-menu-plugin-priority.md
    docs/continuity/2026-10-11-extensions-protected-optical-readiness.md
    docs/continuity/2026-10-11-it13-magnificence-assessment.md
    docs/continuity/2026-10-11-it13-strong-dvd-resource-test.md
    docs/continuity/2026-10-11-it13-system-magnificence-deployment.md
    docs/continuity/2026-10-11-development-resume-preflight-79.md
    docs/continuity/2026-10-11-openhtpc-mpv-rendering-skill.md
    docs/audits/2026-10-11-it13-magnificence-hermes.md

Deux de ces checkpoints (essai STRONG IT13, déploiement Système/Magnificence IT13)
ont pu être lus en lecture seule dans le snapshot matrice ; les autres non.

Conséquences opposables :

- Toute correction portant sur un fichier que je ne peux pas lire
  (`docs/OPENHTPC_MAGNIFICENCE_QUALIFICATION_PROTOCOL.md`, `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md`,
  roadmap globale et roadmaps spécialisées) doit être appliquée **sur la source
  fraîche**, pas depuis ma copie.
- Branche, HEAD, status dirty et stashes restent ceux **consignés** (`AUDIT_PROVENANCE.md`,
  `PROVENANCE.md` du snapshot matrice, checkpoint migration `.79`) : `feature/magnificence-sd-auto`,
  HEAD `975402945376618db56e29945074ea30ddcd2cb8`, VERSION `1.3.1`. Aucun relevé Git
  direct n'est possible ici ; je ne le reconstruis pas.
- Fait observé pendant ce travail : le worktree canonique a bougé au moins deux fois
  le 2026-10-11 (10:51 → 16:29) et probablement depuis.

## 1. Dispositions — revue matrice Magnificence

Statuts : `ACCEPTÉ` (fait confirmé, disposition retenue) · `DIFFÉRÉ` · `REJETÉ` ·
`SUPERSEDED` · `DÉCISION REQUISE` (Steve).

| Id | Nature | Disposition | Raison / destination |
| --- | --- | --- | --- |
| C1 | FACT — la session longue A310 (1 h 09) a résolu `RECIPE_MAG_SD_FSRCNNX8_KRIG` alors que le profil sélectionne `RECIPE_MAG_SD_FSRCNNX16_KRIG_VIBRANCE_MILD` ; la passe couleur n'a pas d'endurance requalifiée | `ACCEPTÉ` — correction documentaire | Deux sources indépendantes concordent (revue matrice et « Points à examiner » n° 2 de la roadmap). Risque réel : lire la session longue comme validation de la chaîne sélectionnée. Destination : annotation du profil + chantier endurance A310, par le propriétaire du fichier |
| C2 | FACT — filtre `lavfi` logiciel BWDIF sans `--hwdec=vaapi-copy` sur HD 630, RX 580 et les **quatre recettes de famille** ; sous VAAPI direct MPV désactive le filtre | `ACCEPTÉ`, et **durci** : défaut *reproduit physiquement*, pas seulement déduit | La revue l'a déduit statiquement ; l'essai IT13 du 2026-10-11 a observé le mode d'échec exact (`failed to configure the filter graph`, BWDIF désactivé) puis BWDIF actif et stable avec `vaapi-copy`. Gravité la plus haute du lot : touche plusieurs chemins installés **et** les chemins de famille généralisés, c'est-à-dire ce que l'Étape 1/2 va réutiliser. Destination : `DÉCISION REQUISE` (D4) + test hermétique (D5) |
| C3 | FACT — la gate déclarée « bénéfice visuel aveugle sur la recette plus légère » n'est pas satisfaite par N150 (confirmation visuelle en attente) ni Vega 3 (PURE a gagné) | `ACCEPTÉ` comme incohérence documentaire ; `REJETÉ` comme défaut de code | Ce sont des décisions produit assumées, permises par la règle exact-prévaut-sur-famille. Le remède est d'écrire la décision et la gate réellement appliquée, pas de changer le code. Destination : roadmap Magnificence + Steve |
| C4 | FACT — l'étiquette de classe ne borne plus la charge réalisée (A310 MEDIUM ≈ jeu STRONG ; RX 580 STRONG ≈ jeu HIGH) | `ACCEPTÉ` — clarification documentaire | Conséquence assumée de la règle gelée. À écrire explicitement : LIGHT/MEDIUM/STRONG/HIGH décrivent une intention, pas un budget, et ne peuvent pas fonder une décision de marge |
| C5 | FACT — `_magnificence_source_scope` n'est pas réellement PAL-scopé (tout `kind == "dvd"` et tout SD ≤ 720×576 → `DVD_PAL_FILM`) | `ACCEPTÉ` — défaut réel, correctif **INTÉGRÉ au worktree canonique le 2026-10-13** (non commité) | Identique à F1 de `hermes-real-01`, trouvé indépendamment par deux audits sur deux snapshots. Correctif `<= 576` → `== 576` + test garde ; 3 échecs sur 4 contre le code canonique. Empreintes relues dans le dépôt et conformes à l'octet : `255225a0…` (module), `7546692c…` (test). 46 PASS ciblés. Voir §9. Couvre partiellement D5 |
| C6 | FACT — prose périmée sur IT13 (`QUALIFICATION_PROTOCOL:139`, `GPU-EVIDENCE:25`) | `ACCEPTÉ` — correction documentaire, **partiellement SUPERSEDED** | Au 2026-10-11 16:29 la section IT13 de `OPENHTPC-MAGNIFICENCE-GPU-EVIDENCE.md` avait déjà été réécrite canoniquement (prouvé par le diff du snapshot matrice). Reste la ligne du protocole, non lisible ici → à vérifier et corriger **sur la source fraîche** |
| C7 | FACT — `is_intel_dg2` matche la sous-chaîne « arc » et étiquette Meteor Lake avec une limite de diagnostic propre à Alchemist/DG2 | `ACCEPTÉ` — priorité basse | Diagnostic seulement, n'affecte aucune sélection ni aucun décodage. Correctif borné possible, ou limitation documentée. Destination : tranche cosmétique |

### Corrections et tests recommandés par la revue

| Id | Objet | Disposition |
| --- | --- | --- |
| D1 | Corriger la prose IT13 périmée | `ACCEPTÉ` — à appliquer sur la source fraîche (voir C6) |
| D2 | Annoter la session FSRCNNX-8 du profil A310 | `ACCEPTÉ` (voir C1) |
| D3 | Réconcilier la recette de famille LIGHT (JSON : BWDIF inclus) avec la table prose (« KrigBilateral » seul) | `ACCEPTÉ` — ambiguïté réelle entre deux autorités documentaires ; à trancher explicitement, pas à laisser diverger |
| D4 | Ajouter `--hwdec=vaapi-copy` là où un filtre `lavfi` logiciel est présent, **ou** documenter explicitement le chemin dégradé | `DÉCISION REQUISE` (Steve) — décision d'architecture, pas d'auditeur. Contrainte : `tests/test_magnificence_policy.py:487` affirme aujourd'hui l'**absence** de `vaapi-copy` pour HD 630 ; le modifier exige de déclarer le changement d'architecture qui invalide l'ancienne attente (AGENTS.md, « Testing ») |
| D5 | Trois assertions hermétiques : filtre `lavfi` ⇒ `--hwdec` compatible ; classifieur DVD PAL/NTSC ; statut `TECHNICALLY_QUALIFIED` avec `visual_basis` en attente remonté comme tel | `ACCEPTÉ` — la deuxième est **déjà écrite et vérifiée** (test garde de `hermes-real-01`) ; les deux autres restent à écrire |
| D6 | Prédicat `is_intel_dg2` spécifique à l'architecture | `ACCEPTÉ` — priorité basse (voir C7) |

## 2. Dispositions — audit `hermes-real-01`

| Id | Nature | Disposition | Raison |
| --- | --- | --- | --- |
| F1 | FACT — `DVD_PAL_FILM` sur-déclaré (branche SD et branche DVD sans sonde) | `ACCEPTÉ` — voir C5 ; **correctif INTÉGRÉ au worktree le 2026-10-13** | Correctif + test garde vérifiés, puis posés dans le dépôt par l'opérateur : empreintes relues conformes à l'octet, 46 PASS, `git diff --check` muet, stashes protégés intacts, aucun commit |
| H1 | HYPOTHÈSE — les hôtes `.67`/`.229` ne reçoivent que de la géométrie PAL, d'où l'absence d'observation | Reste `HYPOTHÈSE` — non prouvée, non réfutée | Non testable depuis un conteneur sans accès aux hôtes ni à leur médiathèque. Reste consignée comme telle |
| H2 | HYPOTHÈSE — la classe PAL inconditionnelle est une hypothèse de foyer PAL délibérée | Cohérente avec l'absence de sonde disponible au point d'appel ; reste `OPEN` | Argument technique vérifié (le chemin DVD passe `optical_state`, pas une sonde). L'intention reste déclarative |
| Q1 | NTSC SD est-il supporté ? | `DÉCISION REQUISE` (Steve) | Si non : le repli fermé vers PURE est la bonne réponse et devient la référence. Si oui : une classe et un jeu de profils NTSC distincts sont la réponse cohérente. La décision détermine si le correctif de C5 est complet |
| Q2 | 352×288 PAL demi-hauteur traité comme film PAL ? | `ACCEPTÉ` — le correctif choisit explicitement le repli fermé | Conservateur par construction et documenté dans le correctif |
| Q3 | Sécuriser la branche `kind == "dvd"` faute de sonde | `DIFFÉRÉ` | Hors périmètre d'un correctif minimal ; nécessiterait une sonde ou une nouvelle source de faits à ce point d'appel. À rouvrir si Q1 répond « oui » |

## 3. Corroborations croisées (à retenir)

- **C5 = F1** : deux audits Hermes, deux snapshots différents, deux jours de préparation
  distincts, même défaut. La probabilité qu'il s'agisse d'un faux positif est nulle ;
  l'hésitation restante porte sur le périmètre produit (Q1), pas sur le fait.
- **C2 est corroboré physiquement** par l'essai IT13 du même jour, sur une autre
  machine que celles de la revue. La revue parlait de `HYPOTHESIS` (H1) ; l'essai IT13
  l'a observé. Aucune promotion n'est faite ici pour autant : le défaut est prouvé
  sur le chemin IT13, il reste à établir sur HD 630 et RX 580.
- **D5 ⊃ test garde de F1** : une partie de la correction recommandée par la revue
  est déjà écrite, exécutée et vérifiée dans l'atelier `hermes-real-01`.
- Signal de méthode : deux audits indépendants ont trouvé le même défaut. En revanche,
  **les deux rapports étaient bien visibles côté canonique** — voir §11, qui corrige ce
  que j'avais écrit ici sur la base périmée de mon atelier. Ce qui manquait réellement
  était la disposition finding par finding, que le checkpoint canonique du 2026-10-11
  commissionnait lui-même comme prochaine action.

## 4. États machine STALE — traitement

| Fichier | Contenu | Traitement |
| --- | --- | --- |
| `OPENHTPC_CURRENT_STATE.json` | `schema_version` 1, workstream `PROTECTED_OPTICAL_PLUGIN_FRAMEWORK_P2`, phase `P2_RC5_CANDIDATE_PREPARED_AWAITING_PHYSICAL_VALIDATION`, candidat `public-release-1.2.0-rc7`, `software_implementation_allowed=false` | **STALE confirmé.** Non modifié : réécrire ses gates est interdit par AGENTS.md. Divergence signalée dans la roadmap. Réconciliation = décision du propriétaire de workstream + schéma strict |
| `.openhtpc-autopilot/state.json` | branche `feature/plugin-framework-p2-protected-optical`, HEAD `96a5711…`, `last_run` `2026-09-01`, gate `AFTER_IMPLEMENTATION`, `status=PLANNED` | **STALE**, désormais signalé (roadmap du 2026-10-13). Non modifié. À réconcilier ou à marquer explicitement historique |

Bonne pratique déjà en place, à conserver : le snapshot matrice **exclut**
`OPENHTPC_CURRENT_STATE.json` au motif qu'il est classé STALE pour le workstream
courant. Ce qui manque n'est pas la détection, c'est la décision.

## 5. Audits préparés sans réponse — tri effectué

| Snapshot | Question posée | État | Disposition |
| --- | --- | --- | --- |
| `openhtpc-plugin-catalog-decision-20261011` | Steve a demandé de trancher entre (1) catalogue d'extensions de confiance avec activation et flux de dépendances contrôlé, (2) n'afficher une extension qu'après ajout local — et de challenger les deux, y compris une hybridation bornée | Snapshot prêt (9 fichiers, `AUDIT_CONTEXT.md` présent) ; **aucun rapport** sous `/opt/data/reports/` ; aucun document de suivi ne le mentionne | **À REJOUER en priorité** : c'est une décision produit qui conditionne l'Étape 1 (`Système → Extensions` : provenance, activation, vocabulaire d'état). Alternative : rapatrier le rapport s'il existe côté `.79` |
| `openhtpc-extensions-truth-20261011` | La page Extensions doit distinguer provenance first-party, activation et préparation observée ; pour `plugin.bluray`, `Prérequis externe absent` vs `Prérequis externe détecté — Prêt à tenter la lecture` ; frontière KEYDB | **Corrigé le 2026-10-13 (voir §11)** : ce snapshot **est** référencé canoniquement par `docs/continuity/2026-10-11-extensions-protected-optical-readiness.md` ; mon « non mentionné » était un artefact de base périmée | `SUPERSEDED` probable — le checkpoint canonique de préparation Extensions couvre la question. À confirmer en le lisant, pas à rejouer à l'aveugle |
| `openhtpc-it13-magnificence-20261011T114028Z-9754029` | Faits IT13 (6 fichiers de faits/excerpts) préparés à 13:40 pour un audit Magnificence IT13 | **Corrigé le 2026-10-13 (voir §11)** : l'audit **a eu lieu** et son rapport existe dans le dépôt — `docs/audits/2026-10-11-it13-magnificence-hermes.md` (6 720 o), référencé par `docs/continuity/2026-10-11-it13-magnificence-assessment.md` et `docs/OPENHTPC_HERMES_AUDITOR.md` | `SUPERSEDED` confirmé : les faits ont servi, le rapport est là. Rien à rejouer |

## 6. Décisions attendues de Steve (rien ne peut les remplacer)

1. **B1 — FAIT (2026-10-13)** : le correctif C5/F1 est intégré au worktree canonique avec son test garde, empreintes relues conformes. Reste la reconstruction d'artifact le jour d'une publication.
2. **B2 / D4** — architecture `vaapi-copy` là où un filtre logiciel est présent, ou chemin dégradé documenté.
3. **Q1** — NTSC SD : supporté (classe/profils distincts) ou non (le repli fermé devient la référence).
4. **C3** — écrire la gate de promotion réellement appliquée (bénéfice visuel aveugle) ou l'amender.
5. **États STALE** — réconciliation officielle ou marquage historique formel.
6. **1.3.1** — push/tag/publication restent non autorisés, en attente d'une décision séparée.

## 7. Prochaine action recommandée

Dans l'ordre :

1. B1 est **fait**. Restent B2/D4 et Q1 — deux réponses courtes — et C3.
2. Opérateur : préparer un snapshot frais + les fichiers de suivi manquants (§Base), pour que
   les corrections documentaires restantes (C6, D1, D3) soient appliquées sur la source à jour.
3. Rejouer l'audit `plugin-catalog-decision` (§5), seule question produit ouverte qui
   bloque l'Étape 1.
4. Ensuite seulement : Étape 1 plugins, en lisant d'abord `2026-10-11-plugin-dependency-resolution.md`
   (existence canonique prouvée, contenu non lu) — une partie de la « prochaine action » peut être déjà faite.

## 8. Vérification directe de `.59` et préservation des preuves — 2026-10-13

Accès obtenu après autorisation de Steve (clé dédiée `hermes_it13_ed25519`, alias `it13`).
Relevés **read-only**, aucun sudo, aucune écriture sur `.59`.

Facts vérifiés sur l'hôte :

- hôte `IT13Max`, `steve`, appliance active (inhibiteur systemd-idle, `openhtpc-home.py`, moniteur optique) ; aucun `mpv` résiduel ;
- build installé : `it13-system-magnificence-validator-20261011` / `OPENHTPC 1.3.1` / build date `2026-10-11` — conforme au checkpoint de déploiement ;
- profil exact présent dans l'installation : `intel_meteor_lake_8086_7d55_sd_2160p` → `RECIPE_MAG_SD_IT13_FSRCNNX16_KRIG_VIBRANCE_MILD` ;
- préférence : `presentation_mode=CINEMA_AUTO`, audio `PCM`/`SYSTEM` ; `tmdb.configured=false` ; `local_media_sources=[]` (aucune source locale configurée — explique l'absence d'`Alerte.mkv`) ;
- runtime effectif `~/.config/openhtpc/runtime/mpv/pure.conf` : `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=vaapi` (direct, pas `vaapi-copy`) ;
- **les six empreintes** déclarées par le checkpoint IT13 (`20261011T120441Z` et `20261011T122213Z`) sont reproduites à l'octet sur l'hôte ;
- la sauvegarde récupérable `pre-it13-system-magnificence-20261011T-current.tar.gz` est présente et son empreinte correspond (`50b4de82…fbf3160`) ; une sauvegarde `pre-extensions-readiness-20261011.tar.gz` existe également.

**Perte constatée** : le banc temporaire `/tmp/openhtpc_it13_strong_probe.py`, cité avec son empreinte (`3458fca8…`) par le checkpoint IT13, est absent après redémarrage. `/tmp` n'est pas durable : la mesure survit, le code qui l'a produite n'existe plus à l'emplacement cité.

Préservation effectuée : copie des cinq séries de mesures (15 fichiers, ~25 Mio) vers
`/opt/data/workspace/hermes-real-01/it13-evidence-20261011/`, avec `MANIFEST.sha256`
(empreinte du manifeste `3f5af95d…b6edd6f6`) et `EVIDENCE-MANIFEST.md`. Les six
empreintes du checkpoint y sont reproduites à l'octet. C'est une copie de
préservation : elle ne constitue ni preuve physique nouvelle, ni qualification.

Non traité : la sauvegarde récupérable de 114 Mio (point de retour arrière) reste sur
`.59` ; sa préservation hors hôte est une décision séparée.

## 9. Intégration effective du correctif C5/F1 — 2026-10-13

Le correctif de portée PAL est **dans le worktree canonique**, non commité.

Pose par l'opérateur sur autorisation de Steve, à partir du patch code-only de l'atelier :

| Étape | Preuve |
| --- | --- |
| Intégrité du patch avant application | `sha256sum` conforme : `10b60baddfb21b67e987f707adf9ed977619db52e24bdc0ea52e940c67dc2be1` |
| Application | `git apply --check` puis `git apply` : PASS |
| Correctif en place | `grep -n 'height == 576' payload/openhtpc-playback-policy.py` → ligne 89 |
| Empreinte du module corrigé, **relue dans le dépôt** | `255225a0adb4e172f73c2b1c05098910a178ab509828c0b6bc82ea8d15564fbf` — conforme à l'octet à l'atelier |
| Empreinte du test garde, **relue dans le dépôt** | `7546692c3162e31f087b905eadad2624bb9408fe7e29d49bf79710009e095858` — conforme |
| Tests ciblés | **46 passed** |
| Hygiène Git | `git diff --check` muet ; ` M payload/openhtpc-playback-policy.py` et `?? tests/test_magnificence_source_scope_guard.py` ; les deux stashes protégés intacts |

Écart attendu et expliqué : j'annonçais 44 tests, l'opérateur en obtient **46**. Son
`tests/test_magnificence_policy.py` a été modifié canoniquement après ma capture — deux
tests de plus, correspondant au verrouillage du profil exact IT13. **Aucun n'échoue** :
le risque signalé (un test figé sur l'ancienne classification NTSC) est donc écarté sans
avoir eu à affaiblir la moindre assertion.

Le checkpoint correspondant a été posé dans le dépôt comme **fichier neuf** —
`docs/continuity/2026-10-13-magnificence-pal-source-scope-fix.md` — précisément pour
éviter les conflits qu'auraient provoqués les hunks sur la roadmap et le point de reprise.

Nature de la vérification, dite sans embellissement : les empreintes ont été relues dans
le dépôt par l'opérateur, pas par moi — je n'ai aucun accès au dépôt canonique. Ce qui
est établi au-delà du relevé : l'identité **byte à byte** entre le fichier du dépôt et
l'artefact que j'ai construit et testé, puis l'identité de comportement démontrée par les
46 tests exécutés. C'est plus fort qu'une simple déclaration, et je le présente comme tel.

Reste ouvert, sans blocage : l'artifact 1.3.1 construit depuis `9754029` ne contient pas
ce correctif ; toute publication devra le reconstruire depuis le commit exact. Aucun
commit, push, tag ni publication n'a été effectué.

## 10. Atelier transmis (isolé, non intégré)

Non suivis / nouveaux :

- `docs/continuity/2026-10-13-openhtpc-findings-dispositions.md` (ce fichier)
- `docs/continuity/2026-10-13-hermes-real-01-audit-delta.md` (checkpoint du même jour)

Actualisés dans le même lot : `OPENHTPC-ROADMAP.md`, `docs/OPENHTPC_CONTINUITY.md`.

Aucun commit (aucun `.git` accessible), aucun push, tag, publication, déploiement,
action physique, ni modification d'état machine.

## 11. Correction — vérification contre la source canonique (2026-10-13)

En fin de journée, Steve a autorisé un **canal SSH en lecture seule** vers le dépôt
canonique (commande forcée, whitelist `status|digest|export`, clé dédiée, `--no-optional-locks`,
sans `.git`). J'ai donc pu tirer une base à jour et **vérifier mes propres affirmations**
au lieu de raisonner sur un instantané périmé. Deux étaient fausses ; je les corrige ici
plutôt que de les laisser telles quelles.

**Faux, corrigé :**

1. « La revue matrice Magnificence n'est référencée par aucun document » — **faux**.
   Le rapport est dans le dépôt : `docs/audits/2026-10-11-magnificence-gpu-matrix-hermes.md`
   (19 401 o), cité par `docs/continuity/2026-10-11-hermes-magnificence-matrix-and-operator-access.md`
   (l. 40-55, avec son SHA-256 `10c53e52…`), `docs/OPENHTPC_HERMES_AUDITOR.md` (l. 214) et le
   journal de `OPENHTPC-ROADMAP.md` (l. 92). Mieux : ce checkpoint **commissionnait
   explicitement** la suite — « Disposer séparément les findings C1 à C7 contre les sources
   complètes et les preuves installées, puis proposer une tranche bornée. Ne pas modifier les
   presets Magnificence. » C'est exactement le travail de ce document, **y compris** le refus
   de toucher aux presets, pris ici indépendamment.
2. « Trois audits préparés sans rapport » — **partiellement faux**, vérifié :
   `openhtpc-extensions-truth-20261011` **est** référencé par
   `docs/continuity/2026-10-11-extensions-protected-optical-readiness.md` ; et
   `openhtpc-it13-magnificence-20261011T114028Z-9754029` a bien produit un rapport, présent
   dans le dépôt (`docs/audits/2026-10-11-it13-magnificence-hermes.md`, 6 720 o), référencé par
   `docs/continuity/2026-10-11-it13-magnificence-assessment.md` et
   `docs/OPENHTPC_HERMES_AUDITOR.md`. **Un seul** des trois reste réellement sans référence :
   `openhtpc-plugin-catalog-decision-20261011`.

**Cause, dite sans excuse** : ma base était un instantané de 10:51 UTC le 11/10, donc
antérieur à ces checkpoints et au rapport importé. J'ai pris l'absence de référence *dans ma
copie* pour une absence de référence *dans le projet* — une inférence présentée comme un fait,
exactement ce que le vocabulaire du projet interdit.

**Ce qui reste vrai** : ni la revue matrice ni `hermes-real-01` n'avaient été **disposés
finding par finding** avant ce document ; c'est ce que §1 à §3 accomplissent. Et le canal
lecture seule supprime la cause racine : mes relevés Git sont désormais mesurés par moi
(`status` / `digest`), plus reconstruits depuis des documents.

**Découverte de la même vérification** : le jalon canonique
`docs/continuity/2026-10-11-plugin-dependency-resolution.md` déclare la **résolution générique
des dépendances plugins et la vérité commune registre / Doctor / Système → Extensions**
« JALON LOGICIEL COMPLET », et désigne comme prochaine tranche autorisable le **contrat
générique d'action média bornée**. La « prochaine action » que je listais en §7 était donc
déjà faite. Voir la réponse de mission pour la liste corrigée.

**Conséquence sur les livrables** : les hunks documentaires de mon patch d'atelier
(`OPENHTPC-ROADMAP.md`, `docs/OPENHTPC_CONTINUITY.md`) sont **retirés du service**. Ils
dérivaient d'une base périmée alors que le dépôt canonique porte désormais ses propres
versions à jour, plus mon checkpoint. Seuls les hunks `payload/` + `tests/` ont été intégrés
(le 2026-10-13) et les checkpoints sont livrés comme **fichiers neufs**, jamais comme
hunks sur des fichiers partagés.
