## Nouveautés de la version 0.7.7

- **Nouvelles parties dans Montage : « ↩ Dash back » et « 🌀 Dismiss »**.
  - Elles marchent comme Dash : une main gauche et une main droite.
  - On les retrouve aussi dans **Clips** pour les mettre dans l'ordre de l'edit.
- **« Mes clips » a maintenant 4 catégories en plus des couteaux : Dash, Kunai, Dash back et Dismiss.**
  - Tes vidéos de ces parties y sont rangées automatiquement.
  - Elles sont proposées dans **Reproduire un edit**.

## Nouveautés de la version 0.7.6

- **Nouveau carré « 🎞 Reproduire » dans Montage** : refais un edit fini avec tes propres clips.
  1. Choisis l'edit : l'app trouve **toutes les transitions**.
  2. S'il en manque une, place-toi dessus avec le curseur ou **◀ -1 / +1 ▶** et clique **« ➕ Transition ici »**. Une transition en trop se supprime.
  3. Ensuite, **plan par plan**, tu vois le plan de l'edit et tu choisis : clique un couteau et l'app prend **un de ses clips au hasard**, ceux avec le time remap déjà fait en premier. **Re-clique** pour en avoir un autre. Dash et Kunai sont aussi proposés.
  4. À la fin, les clips sont mis dans l'ordre dans **Clips**.
- **Time remap : courbes enregistrées** comme dans Flow.
  - Elles s'affichent en petites images : un clic applique la courbe.
  - **« 💾 Enregistrer la courbe »** garde ta courbe actuelle sous un nom, et 🗑 la supprime.

## Nouveautés de la version 0.7.5

- **Time remap : la durée du ralenti (1 → 2) et la durée du retour (2 → 3) sont maintenant propres à chaque clip.**
  - Les changer sur un clip ne modifie plus les autres clips.
  - Chaque clip garde ses propres valeurs quand tu le rouvres et quand tu génères l'edit.

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
