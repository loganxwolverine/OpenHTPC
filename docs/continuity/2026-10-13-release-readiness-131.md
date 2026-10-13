# OPENHTPC — Préparation d'une version (release/RC) et point de reprise — 2026-10-13

Préparé par Hermes (lecture seule) sur demande de Steve : « consolider, finaliser,
solidifier, et m'assurer de pouvoir reprendre le cours du projet ».
Destination suggérée : `docs/continuity/2026-10-13-release-readiness-131.md` (fichier neuf).

Ce document ne crée **aucune** autorisation. Il ne commite rien, ne construit aucun
artifact et ne publie rien. Il dit ce qui est prêt, ce qui manque pour une identité de
version, et comment reprendre.

## 0. Base vérifiée

- Relevé fait **par moi** via le canal SSH en lecture seule (whitelist `status|digest|export`,
  sans `.git`, `--no-optional-locks`) — ce ne sont plus des valeurs reconstruites depuis des
  documents, mais des mesures.
- Branche `feature/magnificence-sd-auto` ; HEAD `975402945376618db56e29945074ea30ddcd2cb8` ;
  VERSION `1.3.1` ; commit de tête : « release: prepare OPENHTPC 1.3.1 Patina » (2026-10-10 20:08).
- Empreinte d'arbre du worktree canonique : `35c03c7d34f4f8d7ff21188ed843a47e5c2b2b39e50788f836ac27293c44e3d9`
  (identique avant capture, après capture, et recalculée sur la copie locale ; 1 038 fichiers).
- Worktree volontairement dirty ; stashes protégés intacts :
  `pre-sync stale RTX experiment 2026-10-02` et `RC7 T5 network deferred`.
- Environnement d'exécution de mes tests : `.venv`, Python 3.14.7, pytest 9.1.1.

## 1. Ce qui est prêt aujourd'hui

| Élément | État | Preuve |
| --- | --- | --- |
| Identité produit | `1.3.1` / `public-release-1.3.1` / Patina | `VERSION`, `payload/version.json`, commit `9754029` |
| Correctif de portée PAL | **dans le worktree**, non commité | `payload/openhtpc-playback-policy.py` ; empreinte `255225a0…` ; ` M` dans `status` |
| Test garde PAL | nouveau, présent | `tests/test_magnificence_source_scope_guard.py` ; empreinte `7546692c…` |
| Binaire Flex distribué / métadonnée | cohérents | contrôle d'empreinte **PASS** (exécuté, 2026-10-13) |
| Outillage de release (`tools/openhtpc-devctl`) | intact | `tests/test_devctl.py` : **77 passed** |
| Gates que j'ai exécutés aujourd'hui | verts | Magnificence + garde PAL + registre P2 + Système générique + devctl : **168 passed, 1 skipped** |

Résultats **consignés** par l'opérateur, non réexécutés par moi, donc à ne pas confondre :
gate canonique 1.3.1 (**2284 PASS / 18 SKIP / 0 FAIL**), gate de résolution des dépendances
(**75 PASS / 3 SKIP**), régressions (**209 PASS / 8 SKIP**).

## 2. Ce qu'il manque pour une identité de version — et la recette

**Le point dur, dit nettement : aucune identité de version n'inclut le correctif PAL.**

1. Le correctif est une modification de worktree, non commitée. Un artifact construit
   « depuis HEAD » ne le contient pas.
2. L'artifact `OpenHTPC-1.3.1.tar.gz` déjà préparé a été construit depuis `9754029` :
   il **ne contient pas** le correctif. Le distribuer tel quel, c'est distribuer un produit
   qui classe encore du SD non-PAL comme PAL.
3. Il faut donc, pour disposer d'une version cohérente : **commiter**, puis **reconstruire
   l'artifact depuis ce commit exact**, puis **vérifier**.

Recette (opérateur/Codex, dans le dépôt canonique) :

    1. Relire l'état et confirmer les deux stashes intacts.
    2. Commiter le correctif + son test garde ensemble (jamais l'un sans l'autre).
    3. Construire l'artifact depuis le commit exact (build officiel, Flex reconstruit
       et provenance schema 2).
    4. Vérifier : devctl verify, métadonnées d'archive, checksum, `install.sh --check`.
    5. Consigner commit/SHA dans le rapport/sidecar ignorés par Git — qui font autorité.

Critère de sortie : un artifact dont le rapport porte **version, build, et commit source
exact** correspondant au commit qui contient le correctif, et `install.sh --check` PASS.

Ce qui est requis de Steve : **l'autorisation de commit** (le contrat AGENTS.md interdit
tout commit sans autorisation explicite). Push, tag et publication restent non autorisés —
et « disponible au public ou non » signifie qu'un artifact local et vérifié suffit.

## 3. Une fragilité de la chaîne de release — identifiée et corrigée en proposition

**FACT** — `tools/openhtpc-devctl:295-302` (`_source_fingerprint`) hache **tous** les
fichiers sous `vendor/flex-launcher`, sans filtre. Mesuré : **100 fichiers, dont 69 sous
`vendor/flex-launcher/build/`** — or `.gitignore` déclare `vendor/**/build/`. La
référence d'intégrité de la release couvre donc des artefacts de compilation volatils et
non suivis.

**Conséquence** : toute compilation faite dans l'arbre change l'empreinte et fait échouer
`tests/test_plugin_framework_generic_system.py:347`. C'est exactement le « douzième échec »
consigné dans `2026-10-11-plugin-dependency-resolution.md` — et cela se produit
systématiquement dans un clone d'ingénierie, puisque celui-ci compile Flex.

**Mesure contradictoire, à retenir** : sur le worktree canonique **d'aujourd'hui**,
l'empreinte **est reproduite à l'identique** et le contrôle **passe** (`1 passed`).
La formulation consignée (« ne peut plus être reproduit depuis l'ensemble actuel ») est donc
vraie pour un arbre qui a été compilé, et **fausse sur le canonique actuel**. Il ne faut pas
révoquer une release sur cette base : il faut corriger la fragilité.

**Correction minimale proposée** (hors de mon couloir, à autoriser) : restreindre
l'empreinte à l'ensemble **stable** en réutilisant les motifs de `.gitignore`
(`vendor/**/build/`, `CMakeFiles/`, `CMakeCache.txt`, `*.o`, `*.a`). Conséquences assumées :
la valeur d'empreinte change, donc la métadonnée devra être régénérée au prochain build
autorisé ; et l'assertion existante doit être modifiée en **déclarant le changement
d'architecture** qui invalide l'ancienne attente (AGENTS.md, « Testing »).

## 4. Ce qui reste ouvert pour reprendre le projet

- **Autorisations** : commit du correctif PAL ; reconstruction d'artifact. Push/tag/publication : non autorisés.
- **Tranche produit suivante** : contrat générique d'action média bornée. La résolution générique
  des dépendances / Doctor / `Système → Extensions` est **faite** (jalon logiciel complet).
  Pré-revue contradictoire livrée séparément : `2026-10-13-media-action-contract-hermes.md`.
- **États machine périmés** : `OPENHTPC_CURRENT_STATE.json` (P2/RC5/RC7) et
  `.openhtpc-autopilot/state.json` (run du 2026-09-01) restent STALE ; modernisation = tranche dédiée.
- **Magnificence** : endurance de la chaîne finale A310 ; A/B `vaapi-copy` sur `.59` (conçu, non exécuté :
  prérequis = DVD PAL inséré + Steve devant l'écran + lanceur de mesure à reconstruire) ; lecture
  physique post-installation IT13 ; corrections documentaires D1-D3/D6.
- **Produit non tranché** : `openhtpc-plugin-catalog-decision-20261011` — question de Steve
  (catalogue de confiance avec activation, ou affichage après ajout local). C'est le seul audit
  préparé réellement sans réponse ni référence.
- **Externe** : réauthentification `gh` privée, Desktop Commander `.79`, connexion CodeGraph MCP persistante.

## 5. Comment reprendre — mode d'emploi

Pour **vérifier l'état soi-même** (aucune dépendance à moi) :

    ssh canonical status          # branche, HEAD, VERSION, status, stashes, log
    bash /opt/data/workspace/hermes-real-01/openhtpc-pull.sh   # base à jour + provenance

Pour une **tranche d'ingénierie** (couloir sanctionné, clone isolé, export revu avant intégration) :

    openhtpc-hermes-engineer prepare <tache> '<objectif borné>'
    openhtpc-hermes-engineer run     <tache> 'lire le handoff, agir, tester, rapporter'
    openhtpc-hermes-engineer export  <tache>      # changes.patch — appliqué seulement après décision

Pour une **version** : la recette du §2.

Pour un **audit contradictoire formel** : snapshot root-owned `0555/0444` sur `.79`, puis
`openhtpc-hermes-audit <snapshot> '<prompt borné>'`.

Pour **me reprendre** dans une nouvelle session, ce brief suffit :

    hermes : reprends OPENHTPC depuis /home/steve/OpenHTPC/github-openhtpc-rc2-integration.
    Lis AGENTS.md, docs/OPENHTPC_CONTINUITY.md, OPENHTPC-ROADMAP.md, le dernier checkpoint,
    et docs/continuity/2026-10-13-release-readiness-131.md. Vérifie l'état réel par le canal
    lecture seule (`ssh canonical status`), signale tout écart, puis applique la mission suivante.

## 6. Limites de ce document

- Je n'ai pas exécuté le gate canonique complet : mon environnement a des échecs
  environnementaux connus (dépendances d'hôte). Les chiffres 2284/18 restent **consignés**.
- Je n'ai pas construit d'artifact et ne peux pas : pas de dépôt canonique en écriture.
- Le diagnostic du §3 est établi par lecture du code de production, calcul avec la fonction
  réelle, et exécution du test — mais sur ma copie filtrée (`.git`, `artifacts/`,
  `__pycache__`, `.hermes`, `.venv` exclus). Aucun de ces exclusions n'est sous
  `vendor/flex-launcher` d'après mes mesures ; le risque résiduel est déclaré, pas masqué.
- Aucune qualification physique, aucun déploiement, aucune publication.
