# OPENHTPC — Modèle d'accès Hermes : canal lecture seule + dépôt borné de livrables — 2026-10-13

> État historique : ce checkpoint décrit le canal initial. Il reste valide pour
> `canonical` et pour la voie audit, mais il a été complété le même jour par la
> voie ingénierie directe `canonical-eng`/`hermes-eng`, autorisée par Steve et
> documentée dans `2026-10-13-hermes-direct-engineering-access.md`.

Date : 2026-10-13, Europe/Brussels. Rédigé par Hermes. Steve a autorisé l'ouverture puis
l'extension du canal décrit ici ; ce checkpoint existe pour que le modèle d'accès ne dépende
pas d'un souvenir de conversation.

## Ce qui existe désormais

**Un canal SSH à commande forcée** entre le conteneur Hermes et `openhtpc-control` (`.79`) :

- clé dédiée `hermes-openhtpc-readonly` (côté `.79`, dans `~steve/.ssh/authorized_keys`),
  avec `command="/usr/local/bin/openhtpc-readonly.sh",restrict,no-port-forwarding,`
  `no-agent-forwarding,no-pty,no-user-rc` ;
- script **root-owned 0755** sur `.79` — donc non modifiable par Hermes, c'est la frontière
  d'application ;
- opérations en correspondance littérale ou par expression ancrée, **aucun `eval`**, aucune
  interpolation de l'entrée dans une commande.

| Opération | Effet |
| --- | --- |
| `status` | branche, HEAD, VERSION, `git status --short`, stashes, dernier commit |
| `digest` | empreinte d'arbre du worktree (règle unique, hors `.git`, `artifacts/`, caches) |
| `export` | archive tar du worktree, `.git` et état local d'agent exclus |
| `put <continuity\|audits> <fichier>.md` | dépose **un** livrable documentaire (contenu sur stdin) |

## Le point de conception à retenir : la lecture est vraiment en lecture

`git status` réécrit son cache d'index : un `status` ordinaire **modifie** `.git`. Le canal
utilise `git --no-optional-locks`, et l'absence d'écriture a été **mesurée** (empreinte des
métadonnées de `.git` avant/après, avec et sans le drapeau). Sans ce détail, « lecture seule »
aurait été un abus de langage.

## Ce que `put` accorde — et surtout ce qu'il n'accorde pas

Accordé : déposer un fichier `.md` **daté**, de nom validé, dans `docs/continuity/` ou
`docs/audits/` uniquement.

Jamais accordé :

- aucune écriture ailleurs dans le dépôt (mesuré : `put payload …` refusé) ;
- **aucun écrasement** : un fichier existant fait échouer l'opération (mesuré) ;
- aucun fichier autre que `.md` (un `.py` est refusé — mesuré) ;
- aucun chemin traversant ni sous-répertoire (mesuré) ;
- aucun `git` en écriture, ni `fetch`, ni `push`, ni `commit` (mesuré) ;
- aucune commande arbitraire, aucun port forwarding, aucun TTY, aucun agent.

**La ligne tenue** : Hermes peut déposer ses propres rapports ; il ne peut pas toucher au
produit. Le code, les configurations, les payloads et l'intégration restent hors de sa portée,
et le dépôt de conformité d'audit (snapshots root-owned `0555/0444`) reste préparé par
l'opérateur — un auditeur ne prépare pas sa propre base de preuve.

## Vérifiabilité des écritures

`put` rend `WROTE <chemin> <octets> sha256=<empreinte>`. L'empreinte est comparée à celle du
fichier local : chaque dépôt est donc vérifié **par lecture retour**, par Hermes, sans
intervention de l'opérateur. Les écritures apparaissent en `??` dans `git status`, et restent
donc visibles et révocables.

## Écart assumé vis-à-vis du handoff du 2026-10-11

`docs/continuity/2026-10-11-codex-hermes-operational-handoff.md` affirme : « Hermes n'a
volontairement aucun accès canonique direct ». Ce canal est une **dérogation délibérée**,
motivée par un incident réel du 2026-10-13 : travaillant sur un instantané périmé, Hermes a
présenté comme des faits des affirmations fausses sur ce qui était référencé dans le projet.
Un contrôle de fraîcheur que Hermes peut exercer seul supprime cette cause.

Conséquence : deux documents doivent être alignés par l'opérateur/Codex — `docs/OPENHTPC_ACTORS.md`
et `docs/OPENHTPC_HERMES_AUDITOR.md` — car ils décrivent l'état antérieur. Hermes ne les édite
pas lui-même : `put` n'écrit que des fichiers neufs, jamais des fichiers existants.

## Retour arrière

- retirer la ligne contenant `hermes-openhtpc-readonly` de `~steve/.ssh/authorized_keys` ;
- ou réinstaller la version antérieure du script, conservée par Hermes ;
- aucune autre trace n'est laissée : pas de service, pas de cron, pas de fichier d'état sur `.79`.

## Portée

Aucun commit, push, tag, déploiement, release ou opération physique n'est autorisé par ce
document. Il décrit un accès, il n'autorise aucun acte produit.
