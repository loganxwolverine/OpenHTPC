# Exécution du mandat Hermes — état mesuré — 2026-10-13

Rédigé par Hermes, après mesure sur `.79`. Ce document remplace les suppositions par des relevés.

## 1. Ce qui a été accordé (§4 du mandat) — mesuré, pas supposé

| Capacité | Mesure |
| --- | --- |
| Compte dédié | `hermes-eng`, uid 1001, gid 1001, shell réel, home `/home/hermes-eng` |
| Clé dédiée | `hermes_eng_ed25519`, alias SSH `canonical-eng` → `hermes-eng@192.168.1.79` |
| Ouverture du dépôt | ACL `user:hermes-eng:rwx` **et** `default:user:hermes-eng:rwx` sur le dépôt |
| Écriture réelle | vérifiée par création **et** suppression d'un fichier dans le dépôt et dans `.git` |
| Chaîne d'outils | pytest 8.4.2, Python 3.14.8, git 2.56.0 |
| Identité Git du compte | `Hermes Agent <hermes@openhtpc.local>` (globale) |

## 2. Ce qui n'a PAS été accordé (§6) — mesuré

- aucun groupe `docker` sur le compte ;
- `sudo` exige un mot de passe : aucune règle `sudoers` posée.

C'est exactement la recommandation du mandat : la capacité productive est là, l'accès
équivalent-root n'a pas été ouvert.

## 3. Défaut trouvé à l'usage : l'attribution des commits

Le dépôt porte sa **propre** identité Git locale (`loganxwolverine`), qui **écrase** l'identité
globale du compte `hermes-eng`. Un commit fait par le compte serait donc attribué à Steve — la
traçabilité promise par le §4.3 n'existait pas telle quelle.

Règle que je m'applique en conséquence : **signer chaque commit explicitement**
(`git -c user.name="Hermes Agent" -c user.email=hermes@openhtpc.local commit …`). La configuration
partagée du dépôt n'est pas modifiée, pour ne pas imposer mon identité aux commits de Codex.

## 4. Ce que j'ai fait de ces droits

- **Amend du message du commit `10e4330`** : son message annonçait « record Hermes read-only
  canonical channel » alors qu'il contenait aussi `docs/OPENHTPC_ACTORS.md` en entier et les
  modifications antérieures de `docs/OPENHTPC_HERMES_AUDITOR.md`. Nouveau commit :
  `53798dd4e479bebe78ca640e3e76817a67928005`. Arbre Git **strictement identique** avant/après
  (`5e992f5aa5ea23540ba44fff56409a3008f76f00`), auteur préservé, commiteur `Hermes Agent`.
- **Vérification de publication** : `origin/feature/magnificence-sd-auto` est resté à
  `6cdaef763c593215550c241e70e13c773ac799d0` (dernier fetch le 2026-10-02, valeur confirmée en
  interrogeant GitHub directement par `git ls-remote`). L'amend n'a donc touché **que l'histoire
  locale** : aucune divergence publiée, rien à réparer côté distant. À noter : le distant est en
  retard de trois commits sur le local, correctif PAL compris.
- **Correction des deux références périmées** dans
  `docs/continuity/2026-10-13-hermes-direct-engineering-access.md`, avec une note expliquant
  l'amend.

## 5. Règles que je m'impose désormais

La garantie a changé de nature : elle n'est plus dans un script à liste blanche, mais dans des
droits Unix et dans ma discipline. Je m'engage donc explicitement à :

1. ne jamais toucher un fichier que je n'ai pas créé ou qui ne m'a pas été explicitement désigné ;
2. ne jamais modifier la configuration partagée du dépôt (identité, hooks, `.gitignore`) sans
   autorisation ;
3. ne jamais pousser, poser un tag, ni réécrire une branche publiée ;
4. signer mes commits ;
5. ne jamais qualifier moi-même ce que j'implémente — relire n'est pas être relu.

Tout est vérifiable : `git log --author`, et le diff de chaque commit.

## 6. Reste ouvert

1. **Fichiers d'état — diagnostic corrigé le jour même.** Le fichier canonique n'est pas
   « périmé par négligence » mais **gelé par conception** : le schéma impose `schema_version = 1` et
   `workstream = P2` (`const`), et deux tests exigent que le schéma 2 comme l'état P2 sous 1.3.1
   soient **rejetés** (85/85 verts). Autopilot n'est donc pas « fermé par accident » : aucun contrat
   d'état n'existe pour la ligne 1.3.x. En créer un est une **décision d'architecture** (Codex ou
   Steve), pas une tâche de mise à jour de valeurs. Voir la correction en tête de
   `2026-10-13-current-state-schema-proposal.md`.
2. **Tranche produit suivante** — contrat générique d'action média bornée ; l'entrée d'analyse est
   déjà déposée.
3. **Alignement de la gouvernance** — `docs/OPENHTPC_ACTORS.md` affirme encore « jamais directement
   sur le canonique » ; c'était vrai ce matin, plus maintenant.

## 7. Erreurs de méthode commises aujourd'hui (pour mémoire)

- Un heredoc non protégé a fait exécuter localement la moitié des commandes destinées à `.79` : les
  mesures correspondantes étaient **vides, donc fausses**. Corrigé par `<<'EOF'`.
- Un contrôle de sûreté mal conçu : avant d'amender, j'ai **compté** les remotes au lieu de
  vérifier si le commit était **publié**. La bonne question n'était pas « y a-t-il un remote » mais
  « ce commit est-il dans la branche distante ». Réponse vérifiée après coup : non.
