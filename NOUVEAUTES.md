## Nouveautés de la version 1.1.0

- **Nouveau design complet** façon tableau de bord : fond bleu nuit, panneaux arrondis, dégradés, halos lumineux, menu de gauche avec icônes, petits titres en majuscules.
- **Options → 🎨 Thème** (en haut à droite) : 6 thèmes proposés (Aura violet, Valorant rouge, Cyan, Émeraude, Sunset, Or) ou **Personnalisé** (tu choisis chaque couleur). Le nom **AuraEdit** est affiché en haut à droite.
- **Reproduire a son propre onglet** (🎞 dans le menu de gauche), avec toutes ses fonctions. Étape 2 : les 2 vidéos (plan de l'edit + ton clip) à gauche, la liste des couteaux / dash / kunai à droite qu'on fait défiler, bouton **⛶ Plein écran**.
- **Correction : les clips ne sont plus enlevés.** Un même clip utilisé sur plusieurs plans est gardé à chaque fois, dans l'ordre. Un plan laissé vide rallonge le clip d'avant pour que tout reste calé sur la musique.
- **Plus de barres noires** : si un clip n'est pas au format 16:9, les bords sont remplis par la vidéo en miroir (effet mosaïque).

## Nouveautés de la version 1.0.3

- **Nouveau look moderne avec effets de lumière, dans toute l'app** : dégradés et reflets sur les boutons, panneaux et listes, halo rouge lumineux autour des boutons principaux (plus fort au survol) et sur chaque bouton survolé, menu de gauche avec lueur rouge sur la page active, titre en dégradé, curseurs et barres de progression lumineux.

## Nouveautés de la version 1.0.2

- **Interface plus propre** : barres de défilement fines, cases à cocher et boutons radio rouges, champs qui s'allument en rouge quand tu écris dedans, menus et listes déroulantes arrondis, info-bulles, onglets, cases numériques (frames, durées) et boutons qui réagissent au clic.

## Nouveautés de la version 1.0.1

- **Correction : plus de plantage dans Reproduire** quand on clique une case sans clip (ex. « Dash back gauche — 0 clip(s) ») : un message dit d'ajouter des clips à la place.
- **Timeline plus fluide** : les miniatures se font en arrière-plan (même quand tu changes de clip) et sont gardées en mémoire, l'interface ne se fige plus.

## Nouveautés de la version 1.0.0

- **Reproduire : la musique de l'edit est gardée.** Quand tu termines, le son de l'edit que tu as mis devient la musique de ton montage.
- **Reproduire : timeline de tes clips.** Sous les aperçus, une miniature par plan montre le clip choisi (« vide » s'il n'y en a pas). Clique une image pour aller directement à ce plan, même quand tu reprends un edit.

## Nouveautés de la version 0.9.9

- **Export plus rapide, même qualité.** Les clips du montage sont préparés en parallèle au lieu d'un par un (plusieurs à la fois selon ton processeur ; les time remaps 2 à la fois sur un PC de 8 cœurs ou plus). Les réglages d'encodage et d'export ne changent pas.

## Nouveautés de la version 0.9.8

- **Chaque clip dure son plan.** Avec ou sans time remap, un clip va de sa coupe à la coupe suivante (ex. frame 25 → 37, puis 37 → 44, etc.), quitte à être coupé. Un clip trop court garde sa dernière image jusqu'à la coupe.

## Nouveautés de la version 0.9.7

- **Time remap : case « 🚫 Sans time remap ».** Elle enlève le time remap du clip sans fermer la fenêtre : tu choisis alors seulement la frame où le clip commence (curseur, ◀ -1 / +1 ▶ ou numéro tapé), puis « Valider le début du clip ». Le clip commence à cette frame dans le rendu.

## Nouveautés de la version 0.9.6

- **Time remap : le reverse passe à 7 frames sur tous les clips** (couteaux, kunais, dash back, dismiss), y compris ceux déjà réglés. Tu peux toujours changer la valeur dans « Durée du retour ».
- **Time remap : choisis la frame exacte.** À côté de chaque curseur de keyframe, une case « frame » où tu tapes le numéro précis (par ex. la frame où le clip commence).

## Nouveautés de la version 0.9.5

- **Time remap : plus de champ « Durée du ralenti ».** Le ralenti dure jusqu'au clip suivant : un clip qui commence à la frame 25 s'arrête à la frame 37 (début du 2e clip), le 2e va de 37 à 44, etc. Le retour est compris dedans.

## Nouveautés de la version 0.9.4

- **Reproduire : main gauche ou main droite pour Dash, Kunai, Dash back et Dismiss.** Chaque catégorie a maintenant deux cases : « ⬅ gauche » et « droite ➡ ». Tu cliques celle que tu veux et le clip vient de cette main. Le clip choisi affiche aussi sa main.
- **Reproduire : bouton « ⏱ Time remap de ce clip »** sous ton clip (ou double-clic sur l'image du clip) pour régler ou changer son time remap sans quitter la page.

## Nouveautés de la version 0.9.3

- **Time remap : code de courbe comme dans Flow (After Effects).** Nouveau champ « Code Flow » : colle le code copié dans Flow (bouton 📋 Coller), puis applique-le à la courbe 1, à la courbe 2 ou aux deux.
  - Formats acceptés : `.69,0,.31,1`, `cubic-bezier(0.69, 0, 0.31, 1)`, `[0.69,0,0.31,1]`, `0,69 ; 0 ; 0,31 ; 1`.
  - Les champs Courbe 1 / Courbe 2 acceptent aussi ces codes directement (avant, `.69` était mal lu).

## Nouveautés de la version 0.9.2

- **Reproduire : tes edits découpés sont gardés.** Une liste « Edits déjà découpés » garde les transitions ET les clips choisis de chaque edit. Double-clic (ou « Reprendre cet edit ») pour continuer là où tu t'étais arrêté, sans refaire l'analyse. Rouvrir le même edit le reprend tout seul.
- **Reproduire : bouton « ➕ Ajouter des clips »** pour ajouter des clips à un couteau (ou un nouveau couteau), au Dash, au Kunai, au Dash back ou au Dismiss sans quitter la fenêtre. Tout est synchronisé : ils arrivent dans « Mes clips » et, pour Dash / Kunai..., dans la partie du Montage avec la main choisie (gauche / droite).
- **Montage : le carré « Dash back » est retiré** (la catégorie Dash back reste dans « Mes clips »).
- Les parties Dash / Kunai / Dismiss se mettent à jour toutes seules quand des clips sont ajoutés ailleurs.

## Nouveautés de la version 0.9.1

- **La durée du ralenti se cale sur les marqueurs de la musique.**
  - Dans le time remap, la case « Caler sur les marqueurs de la musique » (cochée par défaut) règle le ralenti pour que le clip dure exactement jusqu'au marqueur suivant (ralenti + retour = durée du plan).
  - Le 1er clip de l'edit va sur le 1er marqueur « clip », le 2e sur le 2e, etc. (pareil pour les kunais).
  - Au rendu, la durée est recalculée avec les marqueurs actuels : si tu déplaces un marqueur, le ralenti suit.
  - Décoche la case pour remettre une durée à la main.

## Nouveautés de la version 0.9.0

- **Edit auto : reconnaissance des plans bien meilleure.**
  - L'app trouve d'abord le TYPE de plan (flick au couteau, kunai, dash, dash back, dismiss) d'après la forme de ce que le joueur a en main, puis seulement ensuite quel couteau d'après les couleurs du skin.
  - Un flick reçoit un flick (jamais un kunai ni un dash), un kunai reste un kunai, un dash garde son côté.
  - Les couteaux sont appris sur les images où le couteau est sorti, plus sur l'arme d'avant le kill.
- **Fond vert bien plus propre et plus complet.**
  - Bords nettoyés : plus de liseré vert ou sombre autour du sujet.
  - **Choisis le passage** de la vidéo : Début, Fin et un curseur « Aperçu à » pour voir n'importe quel moment.
  - **Fluide en 60 i/s** : une vidéo en 30 i/s est interpolée en 60 i/s.
  - **Continuité** : la vidéo commence sur le clip choisi et continue sur les clips suivants jusqu'à la fin du passage.
  - **Entrée / sortie** : Fondu ou **Dissolve Luma** (désintégration selon la luminosité, façon S_DissolveLuma), avec la durée au choix.

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
