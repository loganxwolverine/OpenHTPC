# OPENHTPC — Mode opératoire : construire la version corrigée (1.3.1 + correctif PAL)

Préparé par Hermes, 2026-10-13. Commandes vérifiées contre l'outillage réel
(`tools/openhtpc-devctl`, `DEVCTL.md`), pas reconstruites de mémoire.
Destination : `docs/continuity/2026-10-13-release-build-runbook.md`.

## Pourquoi le commit est obligatoire — et ce n'est pas une formalité

`DEVCTL.md:102-103` : « **Only committed source is used; working-tree changes are
excluded.** » Le build exporte le commit HEAD, reconstruit Flex depuis cette source, génère
les métadonnées, puis vérifie. **Une correction non commitée ne peut donc pas entrer dans
un artifact** — ce n'est pas un risque, c'est le comportement documenté de l'outil.

Corollaire utile : le build calcule l'empreinte source sur un export **sans les fichiers
ignorés**. Autrement dit, il juge déjà la release sur l'ensemble *stable*. La métadonnée
suivie dans le dépôt (`payload/flex/BUILD-METADATA.json`), elle, a été calculée dans un arbre
qui contenait `vendor/flex-launcher/build/` — d'où la fragilité signalée dans
`2026-10-13-release-readiness-131.md` §3. Restreindre la métadonnée suivie aux sources
stables n'est donc pas une invention : c'est **aligner la métadonnée sur ce que le build
fait déjà**.

## Étape 1 — Enregistrer la correction (Steve, 30 secondes)

    cd /home/steve/OpenHTPC/github-openhtpc-rc2-integration
    git add payload/openhtpc-playback-policy.py tests/test_magnificence_source_scope_guard.py
    git commit -m "fix(magnificence): restrict DVD_PAL_FILM to 625-line PAL geometry"

Les deux fichiers **ensemble** : jamais le correctif sans son test garde.

## Étape 2 — Contrôler l'état

    tools/openhtpc-devctl status

Attendu : les deux fichiers ne sont plus dans les modifications ; les deux stashes
(`pre-sync stale RTX experiment 2026-10-02`, `RC7 T5 network deferred`) toujours présents ;
branche `feature/magnificence-sd-auto`, VERSION `1.3.1`.

## Étape 3 — Construire l'artifact depuis ce commit

Les cinq arguments sont **obligatoires** (`tools/openhtpc-devctl:1345-1349`).

    tools/openhtpc-devctl build \
        --name OpenHTPC-1.3.1-Patina-PalScope \
        --build-id patina-pal-scope-fix \
        --dev-tranche DEV1 \
        --workstream MAGNIFICENCE_SD_SCOPE \
        --tests "<résultat RÉEL du gate que tu viens de lancer>"

Deux remarques :

- `--tests` doit porter ton gate réel, pas une estimation. Ce que j'ai exécuté de mon côté
  (sous-ensemble, environnement d'audit) : **168 passed, 1 skipped**. Le gate canonique
  complet est à relancer ici ; les valeurs consignées jusqu'ici étaient 2284 PASS / 18 SKIP / 0 FAIL.
- **Choix d'identité, à assumer explicitement** : garder la version produit `1.3.1` et donner
  à l'archive corrigée un **nom distinct** (proposé ci-dessus). Recommandé : l'ancienne archive
  `OpenHTPC-1.3.1.tar.gz` n'a jamais été publiée, elle reste donc comme historique, et la
  nouvelle archive la remplace sans ambiguïté. Si tu préfères un numéro qui *dise* « corrigé »
  (1.3.2), c'est une tranche d'identité séparée : VERSION, changelog, métadonnées.

## Étape 4 — Vérifier

    tools/openhtpc-devctl verify artifacts/OpenHTPC-1.3.1-Patina-PalScope.tar.gz

Le vérificateur rehache le binaire archivé, contrôle son identité ELF et l'empreinte source,
compare les champs d'identité embarqués au rapport, valide le manifeste et compare la source
archivée au commit annoncé.

## Étape 5 — Consigner

Noter **commit exact + SHA-256 de l'archive** dans le rapport/sidecar ignorés par Git : ce
sont eux qui font autorité pour l'identité d'une release, pas la roadmap.

## Ce qu'il ne faut PAS faire dans ce lot

- pas de `push`, `tag`, ni publication — non autorisés ;
- pas de `ship` ni d'installation sur un hôte : c'est une autorisation et une validation
  physique séparées ;
- ne pas réécrire `OPENHTPC_CURRENT_STATE.json` : voir la proposition de schéma 2, qui crée
  un **nouveau** fichier au lieu de modifier l'ancien.

## Critère de sortie

Une archive dont le rapport porte version `1.3.1`, un build id, et le **commit source exact**
contenant le correctif, avec `verify` PASS. À ce moment, et seulement à ce moment, une version
release/RC existe et le projet peut reprendre sur une base enregistrée.
