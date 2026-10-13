# OPENHTPC — Décisions déléguées : portée PAL, filtre logiciel, gate de promotion — 2026-10-13

Consolidation : 2026-10-13, Europe/Brussels.

Steve a explicitement délégué la décision (« je te propose de prendre toi-même la
bonne décision »). Ce document rend les décisions **d'ingénierie** qui peuvent l'être,
avec leur raison et leur condition de retournement.

Limites d'autorité, inchangées :

- aucune de ces décisions n'autorise un commit, un push, un tag, une publication, un
  déploiement ou une action physique ;
- l'intégration dans le dépôt canonique reste à l'opérateur/Codex (aucun `.git` ni dépôt
  canonique accessible depuis l'atelier d'audit) ;
- la **qualification physique** et les **décisions produit** restent à Steve : je ne
  décide pas à sa place ce qu'il doit voir de ses yeux ni ce qu'il veut livrer.

## 0. Fait vérifié par moi, indépendamment de la revue

Vérification faite dans ma base **et** dans l'installation réelle `.59`
(`~/.local/lib/openhtpc/assets/`), sur les JSON d'autorité runtime :

| Chaîne | Filtre logiciel `lavfi=[bwdif…]` | `--hwdec=vaapi-copy` | Verdict |
| --- | --- | --- | --- |
| 7 profils exacts : N150 `8086:46d4` | non | non | cohérent (pas de filtre) |
| Vega 3 `1002:15d8` | non | non | cohérent (pas de filtre) |
| A310 `8086:56a6` | oui | oui | cohérent |
| **HD 630 `8086:5912`** | **oui** | **non** | **anomalie** |
| RTX 3050 `10de:2507` | non | non | cohérent (pas de filtre) |
| **RX 580 `1002:67df`** | **oui** | **non** | **anomalie** |
| RX 5700 XT `1002:731f` | oui | oui | cohérent |
| IT13 `8086:7d55` (installation `.59`) | oui | oui | cohérent |
| 4 recettes de famille LIGHT/MEDIUM/STRONG/HIGH | oui | **non** (`vaapi-copy` : 0 occurrence) | **anomalie** |

Conclusion vérifiée : dans le produit, **toute chaîne qui porte un filtre BWDIF logiciel
porte `vaapi-copy` — sauf HD 630, RX 580 et les quatre recettes de famille.**

Ce qui est par ailleurs prouvé (physiquement, sur IT13 le 2026-10-11) : sous
`hwdec=vaapi` direct, MPV refuse le format `vaapi` et **désactive** BWDIF
(`failed to configure the filter graph`) ; sous `vaapi-copy`, le graphe BWDIF est
construit et conservé. Ce qui **n'est pas** prouvé : que HD 630 et RX 580 se comportent
de même (la revue le dit elle-même : non observé sur ces hôtes).

## D1 — C5/F1 : intégrer le correctif `<= 576` → `== 576`

**Décision : oui, intégrer** (recommandation ferme, exécution par l'opérateur).

Raison : le défaut est établi deux fois indépendamment et reproduit par moi le
2026-10-13 (3 échecs sur 4 contre le code canonique ; NTSC 720x480/29.97 résout
`RECIPE_C2_DVD_KRIG_BILATERAL` au lieu de `PURE`). Le correctif est minimal, va dans le
sens du contrat gelé (« prefer safe fallback », « do not fold unknown into a profile »)
et rend vraie l'étiquette `DVD_PAL_FILM` que les profils déclarent.

Cette décision **ne dépend pas** de Q1 : si le NTSC n'est pas supporté, le repli fermé
vers PURE est la bonne réponse ; s'il l'est un jour, il exigera une classe et des
profils propres et ne devra de toute façon pas emprunter des profils déclarés PAL.
Dans les deux branches, le correctif est correct.

Exécution : **faite le 2026-10-13**. Patch code-only posé dans le worktree canonique par
l'opérateur ; `git apply` PASS, ligne 89 en place, **46 passed**, `git diff --check` muet,
stashes protégés intacts. Empreintes du module corrigé et du test garde **relues dans le
dépôt** et conformes à l'octet (`255225a0…`, `7546692c…`) — donc identiques à l'artefact
testé ici, pas seulement déclarées. Aucun commit, push, tag ni publication ; l'artifact
1.3.1 ne contient pas le correctif.

Condition de retournement : elle tomberait si l'on décidait que les profils déclarés PAL
doivent servir du SD non-PAL — décision qui exigerait de changer aussi leur
`source_scope` déclaré, donc une tranche plus large.

## D2 — Q1 : l'invariant est tranché ; la fonctionnalité NTSC ne l'est pas

**Décision :** l'invariant est pris — *un SD non-PAL ne peut pas emprunter une classe ou
un profil déclaré PAL*. Le **support NTSC comme fonctionnalité produit** (nouvelle classe
`DVD_NTSC_FILM` + jeu de profils) n'est **pas** décidé et n'est **pas autorisé** : aucune
preuve, aucune demande, aucune cible matérielle ne le justifie aujourd'hui. Q1 cesse donc
de bloquer le correctif ; elle reste ouverte comme option produit, à la main de Steve.

## D3 — C2/D4 : refus de modifier les recettes sur inférence

**Décision : je ne modifie aucune donnée de recette.** C'est la décision la plus
importante de ce lot, et c'est un refus assumé.

Raisons :

1. L'anomalie est **réelle et vérifiée** (table ci-dessus), mais sa conséquence sur
   HD 630 et RX 580 est **inférée**, pas observée. Le contrat interdit de promouvoir une
   inférence en fait.
2. Ajouter `--hwdec=vaapi-copy` à un profil existant **invalide la qualification physique
   enregistrée de ce profil** : la recette ne serait plus celle qui a été validée
   visuellement. On détruirait la seule preuve attachée à HD 630 et RX 580 pour corriger
   un défaut non observé chez elles. Le remède serait pire que le mal.
3. Modifier les quatre recettes de famille changerait le comportement runtime de tout GPU
   capable non répertorié (le repli de famille), sans aucune mesure.

**Décisions exécutables prises à la place :**

- la **vérité documentaire** est corrigée : pour HD 630, RX 580 et les quatre recettes de
  famille, l'activation du filtre de décodage est `NOT_PROVEN` (le `hwdec` runtime réel
  n'est pas enregistré pour ces chemins). C'est un fait vérifié, pas une hypothèse, et il
  cesse d'être implicite ;
- **aucun test garde n'est ajouté** qui échouerait sur les données actuelles : un test
  rouge forcerait un changement non prouvé. L'invariant est écrit comme **politique**
  (« toute chaîne portant un filtre logiciel doit déclarer un `hwdec` compatible »), à
  encoder en test quand la preuve physique existera ;
- le **test borné qui doit trancher** est défini (D7 ci-dessous).

Condition de retournement : dès qu'un A/B physique montre que le filtre est effectivement
désactivé (ou que son activation change le résultat) sur HD 630 ou RX 580, la correction
des données devient fondée sur une preuve, avec re-validation visuelle du profil modifié.

## D4 — C3 : écrire la gate réellement appliquée, ne pas la fabriquer

**Décision : documenter la réalité, pas l'intention.**

La gate effectivement appliquée est : *profil exact prioritaire sur la famille, toutes les
règles de famille en `REFERENCE_ONLY` (aucune `ACTIVE`), validation physique de l'opérateur
sur le périmètre testé*. L'exigence déclarée « bénéfice visuel aveugle sur la recette plus
légère » n'est **pas** appliquée, et deux défauts livrés ne la satisfont pas (N150 :
confirmation visuelle en attente ; Vega 3 : PURE a gagné le test aveugle alors que Krig est
sélectionné).

Je ne réécris **pas** la politique de sélection pour imposer cette gate : cela
invaliderait des défauts livrés et validés, sans preuve qu'ils sont mauvais. Je consigne
donc la divergence entre la gate annoncée et la gate appliquée, et je la marque comme
décision produit ouverte (`DÉCISION PRODUIT`) — c'est un choix de Steve, pas un défaut de
code.

## D5 — D3 (revue) : le JSON est l'autorité runtime, la prose est fausse

**Décision :** la recette de famille `LIGHT` **contient** BWDIF (le code lit le JSON) ; la
table prose qui décrit « LIGHT | KrigBilateral » seul est **inexacte** et doit être
corrigée. Je ne retire pas BWDIF de la recette JSON : ce serait modifier un comportement
runtime sur la base d'une description, et sans mesure. Même raisonnement que D3.

## D6 — États machine STALE : écrire la règle, pas réécrire les fichiers

**Décision :** ne pas réécrire `OPENHTPC_CURRENT_STATE.json` ni
`.openhtpc-autopilot/state.json` (interdit par AGENTS.md : on ne change pas leurs gates par
déduction). En revanche, la pratique qui a fonctionné est promue en règle : **un snapshot
d'audit exclut les états machine classés STALE et le motif d'exclusion est écrit dans sa
provenance** — c'est ce qu'a fait le snapshot matrice, et cela a évité que je travaille
sur des faits périmés sans le savoir. La modernisation du schéma reste un travail du
propriétaire de workstream.

## D7 — Campagne `.59` : conçue, pas exécutée

**Décision :** ne pas lancer de campagne maintenant, et écrire celle qui doit l'être.

Raisons : ses prérequis ne sont pas les miens (`local_media_sources=[]` — aucune source
locale configurée sur `.59` ; un DVD PAL doit être inséré ; l'A/B exige le jugement visuel
de Steve). Et sa valeur est désormais précise : elle doit répondre à la question laissée
ouverte par la revue — *BWDIF sert-il à quelque chose sur ce matériel, et la copie vaut-elle
son coût ?* — c'est-à-dire fournir la preuve qui manque à D3.

Campagne définie (même DVD PAL, même sortie 3840×2160@60, `.59` seul hôte où le mode
d'échec est reproduit) :

1. référence : profil exact IT13 installé (`vaapi-copy` + BWDIF actif) — la chaîne
   validée physiquement par Steve le 2026-10-11 ;
2. variante : même chaîne en `hwdec=vaapi` direct, filtre logiciel présent, dans un
   lanceur temporaire **hors installation** (le mode d'échec doit être reconfirmé par le
   journal, pas supposé) ;
3. mesures identiques entre les deux : temps VO p95 contre budget 40 ms, pertes
   frame/decoder/delayed, render/CPU/températures ;
4. décision humaine de Steve : à l'image, le filtre apporte-t-il quelque chose sur ce
   matériau ?
5. conséquence : si BWDIF n'apporte rien sur matériau progressif, la question n'est plus
   « faut-il ajouter `vaapi-copy` partout » mais « faut-il retirer BWDIF des recettes où il
   ne sert pas » — question différente, plus économe, et c'est un résultat utile.

Aucun preset, aucun profil, aucune installation ne doit être modifié pendant cette
campagne.

## Ce que je ne décide pas

- L'intégration dans le dépôt canonique (opérateur/Codex) et toute autorisation Git.
- Toute qualification physique et toute décision produit : promotion de profile, contenu
  du catalogue d'extensions, enforcement de la gate de promotion (D4).
- La réécriture du schéma d'état machine.

## Conditions de retournement (résumé)

| Décision | Ce qui la renverserait |
| --- | --- |
| D1 intégrer le correctif PAL | décider que des profils déclarés PAL servent du SD non-PAL, avec changement de `source_scope` |
| D2 NTSC non autorisé | demande produit explicite + cible matérielle |
| D3 pas de modification des recettes | A/B physique montrant filtre désactivé ou utile sur HD 630 / RX 580 |
| D4 gate documentée, non imposée | décision produit d'imposer la gate, avec requalification |
| D5 prose corrigée | preuve que le JSON n'est pas l'autorité runtime (faux par construction) |
| D6 états STALE intacts | modernisation de schéma par le propriétaire de workstream |
