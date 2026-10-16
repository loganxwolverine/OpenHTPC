# Hermes Unraid → contrôle .79 — migration validée
Date : 2026-10-11, Europe/Brussels. Fin technique : 2026-10-11T10:37:21Z.
Mandat : Steve demande la migration de Hermes dockerisé sur Unraid vers .79, puis confirme l'installation Docker par « fait ».

## État final
- Actif : openhtpc-control / 192.168.1.79, Fedora 44, Docker 29.7.2.
- Conteneur hermes-agent : restart unless-stopped ; service Docker enabled.
- Données : /home/steve/.local/share/hermes-agent → /opt/data.
- Port conservé : 192.168.1.79:8642 → 8642/tcp ; non qualifié comme interface opérateur, utiliser le CLI.
- Source Unraid .10 arrêtée, restart no, aucune entrée hermes-agent dans unraid-autostart ; image et données conservées.
- Hermes Agent 0.21.6 (2026.9.24), upstream 818c13be ; Python 3.14.7 ; OpenAI SDK 2.24.0.
- DeepSeek deepseek/deepseek-v4.1-flash via OpenRouter, reasoning high : appel réel PASS. Le modèle reste distant.
- Launchers : ~/.local/bin/hermes et ~/.local/bin/openhtpc-hermes-audit.

## Conservation et validation
Image exportée et chargée sans upgrade : les 37 couches RootFS, configuration, OS/architecture et date de création sont identiques. IDs différents car le moteur cible utilise le digest du manifeste OCI :
- source config/image : sha256:373ddd5e6649f525b17993e1c885cdf1352127f8e98fd329140a73237125e52f ;
- cible OCI manifest : sha256:f74f7ba5d505ee51305a4e9a619f7c32601d6408a6f645c15210664d9681bf3b.

Archive image : 1 220 236 192 octets, SHA-256 c313451e8d6874c12b19f9128edf022aa9650ba720a1d32cfad0477468a5cbc2.
Archive données initiale : 2 470 533 113 octets, SHA-256 1308a4af21f5a638d4b88151d08feed2116ca09aedc9302aa50fed5f6b5820f7.

Arrêt propre avant capture et transfert avec UID/GID/modes conservés. Premier contrôle SQLite read-only interrompu : la base WAL ne pouvait pas créer sa mémoire partagée. Aucun conteneur cible démarré ; rollback automatique, source relancée. Le validateur a été corrigé pour tester des copies temporaires incluant les WAL sans modifier les originaux.

Nouvel arrêt propre après vérification de zéro session_turn_leases. Inventaire complet des fichiers source/cible ; delta de 24 entrées modifiées et retrait de 7 entrées disparues. Avant démarrage cible :
- parité de 33 119 entrées : type, UID/GID, mode, SHA-256 du contenu et cibles des liens ;
- six bases SQLite : integrity_check ok ;
- state.db : 13 sessions et 1 107 messages ;
- audits : 5 533 fichiers ; reports : 21 fichiers ; empreintes des arbres identiques ;
- cron : zéro exécution ; kanban : zéro tâche ; response_store : zéro réponse.
Historiques, mémoires, profils, auth fournisseur, rapports et identité HD DVD existante préservés. Aucun secret consigné ici. Les nombres décrivent le snapshot de bascule ; les tests/usage créent ensuite de nouvelles sessions.

## Tests effectués
1. CLI --version et gateway status sur .79 ; conteneur RUNNING.
2. gateway_state.json courant : gateway_state running, PID vivant, commande gateway run.
3. Audit one-shot UID10000 : snapshot root-owned 0555/0444 sans .git ; écriture refusée ; aucun dépôt canonique ni socket Docker monté ; capabilities supprimées et no-new-privileges.
4. /opt/data/audits read-only, /opt/data/.ssh vide/read-only, /opt/data/home remplacé par un HOME dédié sans clé ; identité opérateur Unraid jamais montée.
5. Appel réel terminal-only, DeepSeek/OpenRouter/high : lecture MIGRATION.txt et réponse HERMES_MIGRATION_79_OK ; exit 0.
6. Redémarrage du conteneur puis gateway et données persistantes vérifiés.
7. Source .10 arrêtée, restart no et absence d'autostart contrôlés ; launcher hermes --version PASS.

Recent gateway health conserve un avertissement historique Stale gateway_state.json. Les logs ont été préservés ; le PID et l'état courants sont vivants et running après redémarrage. Les logs indiquent aussi qu'aucune plateforme de messagerie n'est activée : configuration préexistante conservée, CLI/LLM vérifié, aucune messagerie externe qualifiée.

## Commandes sur .79
~~~sh
hermes --version
hermes gateway status
hermes
~~~
Audit d'un snapshot déjà préparé :
~~~sh
openhtpc-hermes-audit NOM_SNAPSHOT 'Audit borne en lecture seule, preuves fichier:ligne.'
~~~
Le snapshot doit conserver branche/HEAD/dirty/stashes/diff, exclure .git et être root-owned 0555/0444. Capturer le rapport hors snapshot et vérifier les empreintes avant/après. Le canary ne qualifie aucun finding produit et ne promeut pas Hermes en écriture.

## Retour arrière
Source de secours : root@192.168.1.10, /mnt/user/appdata/hermes-agent. Ne jamais lancer deux gateways simultanément.
Pour un retour immédiat sans nouvelles données à conserver : docker stop --time 30 hermes-agent sur .79, vérifier arrêté, puis docker start hermes-agent sur Unraid via l'opérateur.
Après usage de .79, sauvegarder/réconcilier d'abord les nouvelles données à gateway arrêté ; relancer brutalement la source perdrait les sessions postérieures à la bascule.

## Preuves et périmètre
Preuves privées hors dépôt : /home/steve/.local/state/openhtpc-hermes-migration/20261011 (0700), archives, env/métadonnées sensibles, inventaires, SQLite, isolation, canary, redémarrage et état final. Ne pas publier ce dossier.

Dépôt : feature/magnificence-sd-auto, HEAD 975402945376618db56e29945074ea30ddcd2cb8, VERSION 1.3.1. Dirty antérieur conservé ; seuls les documents de suivi sont modifiés par cette migration. Stashes inchangés :
- c7e45ab9802980de417922754950a2c71fdb73aa — pre-sync stale RTX experiment ;
- d900682dd6b734b7b11c35c064596a6e1948bae2 — RC7 T5 network deferred.
Aucun commit, push, tag, publication ni changement du runtime .229.

L'identité HD DVD .67 existante est conservée dans le gateway normal et masquée dans les audits ; nouvel accès .79 → .67 non requalifié ici.
ChatGPT passe encore par Desktop Commander .229 puis SSH .79 ; aucun device direct Desktop Commander .79 établi.
Hermes → CodeGraph MCP persistant reste NOT_ESTABLISHED. Aucun test produit, lecture média, GPU ou validation physique n'est déduit de la migration.
