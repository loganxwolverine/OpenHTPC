# Mandat — capacités d'exécution pour Hermes

**Proposé par Hermes, validé par Steve et mis en œuvre par Codex CLI le 2026-10-13.**
Les §4.1–4.4 sont installés avec les bornes du §5 et revue Codex/Steve ; le §6
reste exclu. Les faits d'installation et de vérification sont consignés dans
`docs/continuity/2026-10-13-hermes-direct-engineering-access.md`. Les constats
« aujourd'hui » ci-dessous décrivent le pré-installation et sont conservés comme
motivation historique.

## 1. Objectif

Supprimer la friction qui, aujourd'hui, transforme chaque acte de Hermes en une commande à faire
taper par Steve. Steve l'a demandé explicitement : « ce que Codex CLI est capable de faire, tu dois
en être capable aussi ».

## 2. Ce qui manque aujourd'hui — mesuré, pas supposé

| Fait constaté | Conséquence |
| --- | --- |
| Hermes tourne dans un conteneur, UID 10000, sans socket Docker, sans dépôt monté, sans clé opérateur | Aucun accès direct au dépôt ni à la chaîne d'outils |
| L'accès à `.79` passe par **une commande forcée** (`/usr/local/bin/openhtpc-readonly.sh`) dont la liste d'opérations est fixe : `status`, `digest`, `export`, `bundle`, `artifacts`, `put` (documents `.md` neufs), `commit-docs` (documentation seule, proposé) | Toute autre action est refusée par construction |
| La voie ingénierie sanctionnée (`openhtpc-hermes-engineer prepare/run/export`) **exige le socket Docker de `.79`** | Elle est inutilisable : c'est le blocage structurel actuel |
| Codex CLI, lui, tourne **nativement sur `.79` sous l'identité `steve`**, avec le dépôt, la chaîne d'outils et le groupe `docker` | Il peut tout faire ; Hermes ne peut que lire et déposer |

Autrement dit : l'écart entre Codex et Hermes n'est **pas** un mandat, c'est une **infrastructure**.
Aucun texte ne le comble : il faut installer quelque chose sur `.79`.

## 3. Ce que « aussi capable que Codex » signifie, capacité par capacité

| Capacité | Ce que cela exige concrètement |
| --- | --- |
| Lire/écrire le dépôt canonique | Un compte ou des ACL en écriture sur `/home/steve/OpenHTPC/github-openhtpc-rc2-integration` |
| Git complet : branche, commit, amend, stash | Le même accès, plus une identité Git propre |
| Lancer les tests et le build du projet | Un shell sur `.79` avec la chaîne Python/pytest et `tools/openhtpc-devctl` |
| `openhtpc-hermes-engineer`, CodeGraph, Autopilot | Le socket Docker (ou une règle `sudo` bornée aux lanceurs sanctionnés) |
| Publier (push, tag, release) | Le réseau et une autorisation explicite — **irréversible, donc jamais implicite** |
| Valider physiquement (DVD, image, son) | Impossible pour une machine : reste à Steve, par nature |

## 4. Mandat proposé — ce qui est accordé

**4.1 Une identité dédiée, pas celle de Steve.** Compte Unix `hermes-eng` sur `.79`, shell réel
(`/bin/bash`), propriétaire de ses processus. Le dépôt lui est ouvert en lecture/écriture par ACL,
sans changer les propriétaires existants :

    sudo useradd -m -s /bin/bash hermes-eng
    sudo setfacl -R  -m u:hermes-eng:rwX /home/steve/OpenHTPC/github-openhtpc-rc2-integration
    sudo setfacl -R -d -m u:hermes-eng:rwX /home/steve/OpenHTPC/github-openhtpc-rc2-integration

**4.2 Une clé SSH dédiée, avec shell.** Clé `hermes_eng_ed25519` (à générer par Hermes, à ne pas
confondre avec la clé de lecture seule ni avec celle de `.59`), déposée dans
`~hermes-eng/.ssh/authorized_keys`. Pas de commande forcée : l'isolation vient des permissions du
compte, pas d'une liste d'opérations. C'est ce qui rend Hermes réellement capable — et c'est aussi
ce qui déplace la garantie : elle passe de « liste blanche » à « droits Unix ».

**4.3 Git complet dans le dépôt.** Branches, commits, amend, stash, rebase **sur ses propres
branches**, `git apply`, `git bundle`, inspection. Identité Git dédiée pour que l'historique dise
qui a écrit quoi :

    [user] name = Hermes Agent / email = hermes@openhtpc.local

**4.4 Tests et build.** Exécution de `python3 -m pytest`, de `tools/openhtpc-devctl` et des
scripts du projet, avec la chaîne d'outils installée pour ce compte.

**4.5 Socket Docker ou règle `sudo` bornée** — voir §6 : c'est le seul point de ce mandat que je
recommande de traiter à part, parce qu'il équivaut à un accès root sur `.79`.

## 5. Bornes que je recommande de garder — avec la raison, en une ligne

1. **Aucun push, aucun tag, aucune publication sans autorisation explicite au cas par cas.**
   Raison : c'est irréversible, et c'est la seule action que le projet ne peut pas défaire.
2. **Aucune réécriture d'historique sur une branche partagée** (pas de `push --force`, pas de
   `filter-branch`). Raison : le dépôt est aujourd'hui la seule copie de son histoire.
3. **La validation physique reste à Steve.** Raison : impossible pour une machine.
4. **Les décisions produit restent à Steve.** Raison : autorité définie par le projet.
5. **Ce que Hermes implémente, Hermes ne le qualifie pas.** Raison : c'est la seule borne dont la
   levée détruit la valeur de l'auditeur contradictoire. Si Hermes écrit du code, ce code doit être
   relu par Codex ou par Steve **avant** d'être traité comme validé.

## 6. Le point que je ne recommande pas — et pourquoi, franchement

**Le socket Docker, et à plus forte raison un accès `root` ou l'identité `steve`, ne devraient pas
être accordés.** Le socket Docker donne un pouvoir équivalent à root sur `.79` : celui qui l'a peut
lire tous les secrets du serveur, modifier n'importe quel conteneur, et sortir du périmètre du
projet. Accorder cela à une machine qui n'en a pas besoin pour travailler est une dépense de risque
sans contrepartie.

Alternative qui donne la même capacité productive sans le risque : une règle `sudoers` limitée aux
deux lanceurs sanctionnés, du type

    hermes-eng ALL=(root) NOPASSWD: /usr/local/bin/openhtpc-hermes-engineer, /usr/local/bin/openhtpc-hermes-audit

Ce qui permet d'utiliser la voie ingénierie isolée — celle que le projet a déjà conçue et écrite —
sans donner les clés du serveur.

## 7. Ce que ce mandat coûte au projet — dit sans détour

Aujourd'hui, le projet a deux agents avec deux rôles distincts : Codex implémente, Hermes contredit.
Cette séparation est ce qui donne sa valeur à l'audit : quelqu'un qui n'a pas écrit le code le relit.

Si Hermes reçoit la capacité d'écrire et de committer, **cette séparation disparaît** — sauf si
Steve désigne explicitement qui relit Hermes. Deux issues possibles, à choisir consciemment :

- **Recommandée** : Hermes devient un second ingénieur aux mains libres, et **Codex devient le
  relecteur de Hermes** (symétrie : chacun relit l'autre). Le projet garde deux paires d'yeux.
- **À éviter** : Hermes écrit, Hermes relit, Hermes valide. Le projet n'a plus qu'un avis, donné
  par la partie prenante. C'est moins cher aujourd'hui et beaucoup plus cher au premier défaut
  sérieux.

Le §5.5 est précisément la borne qui rend la première issue possible.

## 8. Traçabilité et révocation

- **Traçabilité** : identité Git dédiée (tout `git log --author` est vérifiable), un point de
  situation daté après chaque chantier, aucune action silencieuse. La discipline actuelle ne change
  pas ; seule la capacité change.
- **Révocation** : trois commandes, réversibles séparément —

      sudo userdel -r hermes-eng
      sudo setfacl -R -x u:hermes-eng /home/steve/OpenHTPC/github-openhtpc-rc2-integration
      sudo rm -f /etc/sudoers.d/openhtpc-hermes-eng

## 9. Si Steve veut la variante sans aucune borne

Elle est techniquement possible et se décrit en cinq lignes : compte avec l'identité de `steve`
(ou `root`), socket Docker, push autorisé, aucune borne de §5. Conséquences : plus aucune
attribution fiable dans l'historique, aucun moyen d'auditer ce que Hermes a fait, l'auditeur
contradictoire disparaît, et une erreur de Hermes devient une erreur du projet sans filet. Je
l'écris parce que tu l'as demandée ; je ne la recommande pas, et je ne la crois pas nécessaire :
tout ce qui te coûte du temps aujourd'hui est couvert par les §4 et §6.

## 10. Le pas immédiat, si tu ne veux pas attendre Codex

Le script de canal **déjà écrit et éprouvé** (`openhtpc-canonical-channel.sh`, empreinte
`b2268e77b1a61b79…`) ajoute `commit-docs` : Hermes committe lui-même toute la documentation, y
compris les corrections de message. C'est une commande d'installation, sans compte ni ACL, et cela
supprime la majorité de la friction constatée aujourd'hui :

    sudo install -o root -g root -m 0755 \
      /home/steve/.local/share/hermes-agent/workspace/hermes-real-01/openhtpc-canonical-channel.sh \
      /usr/local/bin/openhtpc-readonly.sh

## 11. Ce que ces droits serviraient, tout de suite

1. Réécrire les deux fichiers d'état périmés en schéma 2 — Autopilot est fermé depuis le 11/10.
2. Ouvrir la tranche produit suivante : le contrat générique d'action média bornée.
3. Tenir à jour la documentation de gouvernance sans passer par Steve à chaque phrase.

Aucune de ces trois choses n'exige le §6. Toutes exigent le §4.1–4.4.

---

**Décision de Steve** : §4.1 à §4.4 validés et installés ; §5 maintenu ; Codex
ou Steve relit Hermes ; §6 exclu.
