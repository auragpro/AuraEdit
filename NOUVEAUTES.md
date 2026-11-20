## Nouveautés de la version 0.8.9

- **Correction : « Edit auto » et la superposition fond vert marchent** (erreur « No module named 'cv2' » réglée).

## Nouveautés de la version 0.8.8

- **🤖 Edit auto dans « Reproduire un edit »** : un bouton remplit tous les plans d'un coup.
  - L'app regarde chaque plan de l'edit fini et reconnaît ce que c'est en le comparant à tes clips : quel couteau (Exo, Kuronami...), un kunai, un dash, un dash back, un dismiss.
  - Les dash, kunai, etc. gardent **le même côté** (main gauche / main droite) que dans l'edit.
  - Si tu n'as plus de clip libre pour ce couteau, l'app prend un clip du **couteau qui ressemble le plus**.
  - Les clips avec le time remap déjà fait passent en premier, sans mettre deux fois le même.
  - Tu peux tout vérifier plan par plan et re-cliquer un couteau pour changer.

## Nouveautés de la version 0.8.7

- **Superposer une vidéo sur un clip, avec fond vert enlevé** (dans « Reproduire un edit », quand tu places tes clips).
  - Bouton **🟩 Superposer une vidéo (fond vert)** sous ton clip, pour chaque plan.
  - **Choisis la couleur à enlever** : 🎯 pipette (clique sur le fond dans l'aperçu), **Auto** (détecte le fond) ou nuancier. Marche avec le vert, le bleu ou n'importe quelle couleur.
  - Détourage propre façon **Keylight** : tolérance, douceur du masque, rétrécir et adoucir les bords, vue **Masque** noir/blanc pour vérifier que le fond part bien.
  - **Suppression du débordement** façon Advanced Spill Suppressor : enlève le reflet vert sur le sujet en gardant sa luminosité.
  - Taille, position, début dans la vidéo et répétition si elle est plus courte que le plan.

## Nouveautés de la version 0.8.6

- **Plus aucune copie de clips sur ton PC.**
  - Quand tu ajoutes un clip, l'app garde seulement son emplacement : le fichier reste où il est, rien n'est dupliqué dans Documents/AuraEdit.
  - **Couper une compilation de dash ne crée plus de fichiers** : chaque dash (dash1, dash2...) est gardé dans l'app comme un morceau de ta compilation, à la frame exacte. Ta compil reste le seul fichier.
  - Les dash déjà coupés sont convertis automatiquement au lancement, avec ta main gauche / droite gardée, puis leurs copies sont supprimées de Documents/AuraEdit/Clips.
- ⚠ Ne déplace pas et ne supprime pas tes compilations : les dash les lisent directement.

## Nouveautés de la version 0.8.5

- **Couper une compilation de dash : chaque dash va directement dans la partie Dash, dans la main que tu choisis.**
  - Sélectionne un dash dans la liste puis clique **⬅ Main gauche** (touche **G**) ou **Main droite ➡** (touche **D**).
  - L'app passe tout de suite au dash suivant : tu peux tout trier au clavier.
  - La main choisie s'affiche à côté de chaque dash. **Pas dans Dash** le laisse seulement dans « Mes clips ».
  - Après « ✂ Couper et enregistrer », chaque dash est ajouté dans sa main.

## Nouveautés de la version 0.8.4

- **Couper une compilation de dash marche sur les grosses compils** (plusieurs Go) :
  - La détection lit la vidéo en flux et n'utilise presque plus de mémoire.
  - L'export de chaque dash va directement au bon endroit de la vidéo au lieu de tout relire depuis le début : c'est beaucoup plus rapide, et toujours à la frame exacte.
- **Après la coupe, les dash peuvent être ajoutés directement dans la partie Dash** : l'app te demande Main gauche, Main droite ou Ne pas ajouter.

## Nouveautés de la version 0.8.3

- **Détection des dash refaite et réglée sur ta vraie compilation** (« compil dash AURA FARM ») :
  - La coupe tombe sur **la frame où l'arme disparaît et où la main du dash commence** : la frame d'avant montre encore l'arme.
  - Sur cette compilation, **48 dash sur 49 tombent exactement à la bonne frame**.
  - Un tir (flash, recul) n'est plus pris pour un dash. Un clip qui commence déjà en plein dash est ignoré.
  - Il ne dépend plus des bannières de kill, qui étaient vues trop tard.
  - Toutes les frames de la vidéo sont lues (120/144 i/s compris).
- Il peut rester quelques coupes en trop : supprime-les avec 🗑 avant d'enregistrer.

## Nouveautés de la version 0.8.2

- **Coupe des dash à la frame près** :
  - L'app affine maintenant chaque coupe **à la vraie cadence de ta vidéo** (toutes les frames, 120/144/240 i/s compris) et plus seulement à 60 i/s.
  - La coupe tombe sur **la 1re frame qui ressemble à la main du dash plutôt qu'à l'arme**, et **jamais avant le kill**.
  - **L'aperçu et l'export tombent exactement sur la même frame** : la frame que tu vois est celle où le dash commence.

## Nouveautés de la version 0.8.1

- **Coupe des dash corrigée** : la coupe se fait maintenant sur **la frame où l'arme disparaît et où la main du dash apparaît** (la frame d'avant montre encore l'arme), juste après chaque bannière de kill.

## Nouveautés de la version 0.8.0

- **Détection des dash refaite** pour « Couper une compilation de dash » : l'app repère maintenant la **1re frame où toute l'image devient floue** (traînées de vent du dash de Jett), au lieu d'un simple gros mouvement.
  - Un flick normal reste net : il n'est plus pris pour un dash.
  - Les dash très nets sont gardés même si la bannière de kill n'a pas été vue.

## Nouveautés de la version 0.7.9

- **Couper une compilation de dash** : bouton **« ✂ Couper une compilation de dash... »** dans **Montage → Dash**.
  - L'app repère chaque **bannière de kill**, puis la **1re frame du dash** qui suit.
  - Tu vérifies chaque coupe à la frame près avant l'export : ◀ -1 / +1 ▶, **↔ Déplacer la coupe ici**, **➕ Coupe ici** ou 🗑 pour supprimer.
  - Chaque dash est enregistré **à part : dash1, dash2...**, en très bonne qualité, dans **Mes clips → Dash**. La numérotation continue après les dash déjà présents.

## Nouveautés de la version 0.7.8

- **Time remap sur les Dash back et les Dismiss**, comme sur les kunais.
  - Dans leur partie de **Montage**, sélectionne des vidéos et clique **« ⏱ Time remap... »**, ou double-clique une vidéo.
  - Tu peux aussi le lancer depuis l'ordre de l'edit dans **Clips**.
  - Chaque type garde **ses propres réglages** : courbes, durées et durée apprise.
  - Les vidéos réglées ont un ⏱, et le time remap est appliqué au rendu.

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
