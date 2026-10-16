# Catalogue décisionnel des shaders

## Fiche obligatoire pour toute recommandation

Produire une fiche avant même un essai :

1. **Défaut traité** — défaut visible et scène qui permet de le réfuter.
2. **Étage** — hook, plan luma/chroma, dimensions d'entrée/sortie et voisinage des autres passes.
3. **Bénéfice attendu** — formuler comme `HYPOTHESIS` sauf preuve OPENHTPC bornée.
4. **Artefacts possibles** — inclure texture/bruit, halos/ringing, oversharpen, chroma, stabilité temporelle et mismatch de domaine.
5. **Coût GPU qualitatif** — `LOW`, `MEDIUM`, `HIGH` ou `UNKNOWN`, avec raison structurelle ; une étiquette ne remplace jamais la mesure.
6. **Validation/réfutation** — baseline, scènes, métriques, défauts à rechercher et seuil de rejet.

Ajouter provenance/version/hash du fichier, `//!HOOK`/`//!WHEN` effectifs, plateforme, source et sortie. Ne pas réutiliser un verdict hors de ce périmètre.

## FSRCNNX-8 et FSRCNNX-16

- **Défaut** : manque de détail structurel de luma lors d'un agrandissement important.
- **Étage** : passes `LUMA` conditionnelles ; les fichiers OPENHTPC doublent la luma lorsque les ratios satisfont leur `WHEN`.
- **Bénéfice attendu** : reconstruction plus définie que le scaler de référence. OPENHTPC possède des préférences visuelles positives bornées par profils ; ne pas les généraliser.
- **Artefacts** : ringing, faux détail, accentuation du bruit/blocs/moustiques, texture artificielle ou instabilité sur mouvement.
- **Coût qualitatif** : 8 = `MEDIUM`, 16 = `HIGH` comme hypothèse relative fondée sur le nombre de features/passes ; mesurer sur chaque GPU.
- **Valider/réfuter** : PURE puis scaler seul puis FSRCNNX seul, mêmes frames et mouvement ; rejeter si gain non visible à distance normale, artefact récurrent, p95 hors marge ou drops attribuables. Comparer 8 contre 16 directement, sans supposer que 16 gagne.

## KrigBilateral

- **Défaut** : chroma 4:2:0 floue, bavures de couleur et contours chromatiques mal reconstruits.
- **Étage** : `CHROMA`, guidé par `LUMA`, avec reconstruction vers la taille luma dans le fichier distribué.
- **Bénéfice attendu** : contours colorés mieux alignés et chroma plus précise.
- **Artefacts** : bruit chroma accentué, faux contours/couleurs, sur-lissage, sensibilité au chroma location ou à un contenu qui ne correspond pas aux hypothèses.
- **Coût qualitatif** : `MEDIUM` attendu ; plusieurs passes/échantillonnages, à mesurer.
- **Valider/réfuter** : mire chroma compressée plus scènes naturelles saturées/peaux/texte ; comparaison contre `cscale` seul, recherche de déplacement couleur et vérification du hook actif dans `vo-passes`.

## SSimSuperRes

- **Défaut** : finition de l'upscale, netteté perçue insuffisante et ringing du scaler.
- **Étage** : plusieurs passes `POSTKERNEL` dans la version distribuée, donc après le kernel principal ; vérifier ses `WHEN` et buffers intermédiaires.
- **Bénéfice attendu** : correction perceptuelle/antiringing et détail final mieux contrôlé.
- **Artefacts** : halos, oversharpen, bruit et artefacts MPEG plus visibles, rendu artificiel.
- **Coût qualitatif** : `MEDIUM` à `HIGH` attendu selon résolution de sortie ; mesurer l'incrément par rapport à la chaîne sans SSim.
- **Valider/réfuter** : A/B chaîne identique avec/sans pass sur lignes contrastées, visages, grain et moustiques ; rejeter si le gain est invisible à distance normale ou si le coût/artefact domine. OPENHTPC a déjà rejeté son rapport gain/coût pour DETAIL A310 tout en le conservant dans d'autres profils : la plateforme et la recette font partie du verdict.

## CAS / RCAS

- **Défaut** : douceur résiduelle après upscale.
- **Étage** : dépend du port réellement testé. Le `FSR.glsl` distribué combine EASU puis RCAS et opère sur `LUMA`; ne pas appeler cette chaîne « CAS seul ». Pour un essai RCAS isolé, identifier un artefact séparé, sa licence, son hook et son hash.
- **Bénéfice attendu** : accentuation adaptative à coût potentiellement inférieur à une reconstruction neuronale.
- **Artefacts** : halos, bruit/grain accentué, contours durs, oversharpen et double-accentuation après un autre reconstructeur.
- **Coût qualitatif** : RCAS isolé `LOW` à `MEDIUM` attendu ; FSR EASU+RCAS `MEDIUM` ou `UNKNOWN` selon ratio/résolution. Mesurer.
- **Valider/réfuter** : tester isolé puis en fin de chaîne, balayer une plage bornée, comparer au shader absent et à SSimSuperRes. Les essais A310 consignés n'ont pas retenu RCAS isolé ; ne pas extrapoler aux autres plateformes.

## RAVU Lite / RAVU Zoom

- **Défaut** : reconstruction luma lors d'un upscale 2x (Lite) ou arbitraire (Zoom).
- **Étage** : fichiers `.hook` LUMA ; Lite produit un 2x, Zoom vise la sortie. Lire leurs textures LUT, tailles et conditions effectives.
- **Bénéfice attendu** : reconstruction orientée contours ; les variantes AR ajoutent un contrôle du ringing.
- **Artefacts** : ringing résiduel, contours artificiels, texture lissée ou structurée, comportement défavorable hors ratio prévu.
- **Coût qualitatif** : Lite `MEDIUM`, Zoom `HIGH` attendu à grande sortie car il travaille à la résolution cible ; hypothèses issues de la structure/amont, à mesurer.
- **Valider/réfuter** : comparer au scaler intégré et à FSRCNNX au même ratio ; inclure diagonales, texte, grain, mouvement et p95. RAVU existe dans le catalogue/outil de review OPENHTPC mais n'est pas dans le classifieur Auto gelé.

## ArtCNN

- **Statut OPENHTPC** : `STUDY_PENDING`. Les fichiers existent dans le dépôt, mais la roadmap courante exclut ArtCNN du classifieur Magnificence automatique. Ne pas le recommander pour un preset avant une tranche autorisée.
- **Défaut** : luma à reconstruire ; certains modèles amont ciblent spécifiquement anime, débruitage/adoucissement ou débruitage/accentuation.
- **Étage** : modèles GLSL distribués au hook `LUMA`, compute multi-passes, sortie 2x conditionnelle.
- **Bénéfice attendu** : reconstruction CNN récente ; l'adéquation au film/DVD réel est `HYPOTHESIS`, pas un fait.
- **Artefacts** : biais de domaine anime, texture inventée, lissage plastique, ringing/accentuation selon variante, prérequis compute/FP16 non satisfaits.
- **Coût qualitatif** : C4F16 `HIGH` attendu, C4F32 plus élevé ; confirmer compilation, précision réellement utilisée et mesure.
- **Valider/réfuter** : commencer par compatibilité Vulkan/libplacebo, puis modèle neutre sur corpus film et, séparément, anime ; comparer FSRCNNX/RAVU/PURE, inspecter temporalité et visages. Un meilleur score ou une préférence sur anime ne promeut pas le DVD/cinéma.

## Ordre et combinaison

Ne jamais recommander une chaîne par simple concaténation des fiches. Justifier les dépendances : nettoyage natif éventuel → reconstruction luma/chroma à leurs hooks → scaler résiduel → finition post-kernel → couleur/output. Confirmer le graphe réel par directives, conditions et `vo-passes`. Ajouter un shader un par un et retirer le dernier composant si son bénéfice isolé n'est pas démontré.
