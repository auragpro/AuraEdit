## Nouveautés de la version 0.7.4

- **Détection du time remap des clips refaite** :
  - **Keyframe 1** = la **1re frame où ton perso sort le couteau**, juste après avoir rangé son arme au kill. L'app saute les frames où les mains sont vides.
  - **Keyframe 2** = le **flick away** (le gros mouvement de caméra) **+ 20 frames**.
  - L'app part du flick, recule jusqu'au moment où l'arme disparaît, puis avance jusqu'au couteau. Ça marche même quand la bannière de kill n'est pas trouvée.
  - Si un clip a plusieurs kills, choisis le bon kill dans la liste : la détection repart de cette bannière.
- Le texte sous les keyframes dit si le flick away a été trouvé.

## Nouveautés de la version 0.7.3

- **Nouveau : le time remap marche sur les kunais.**
  - Dans **Montage → Kunai**, sélectionne une ou plusieurs vidéos et clique **« ⏱ Time remap... »** (ou double-clique une vidéo).
  - Sans sélection, le bouton enchaîne toutes les vidéos de la main.
  - Tu peux aussi le lancer depuis l'ordre de l'edit dans **Clips** : les kunais ne sont plus ignorés.
- Même page que pour les clips :
  - détection du kill ;
  - **Keyframe 1** = le kunai part, **Keyframe 2** = fin du time remap ;
  - courbes, durée du ralenti, retour, frame blending (Pixel Motion) et **▶ Aperçu**.
- Les **réglages des kunais sont séparés** de ceux des couteaux : tu peux avoir des courbes et des durées différentes. L'app retient la durée validée et la propose pour les kunais suivants.
- Les kunais réglés ont un **⏱** devant leur nom, et le time remap est appliqué quand tu génères l'edit.
