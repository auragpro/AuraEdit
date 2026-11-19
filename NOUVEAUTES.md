## Nouveautés de la version 0.5.1

- **Le time remap part maintenant du kill.** Dès que tu donnes ton clip, le logiciel cherche le kill (la bannière de kill qui apparaît en bas au centre de l'écran), puis la **première frame après le kill où on ne voit plus le couteau** : c'est la keyframe 1.
- La keyframe 2 (couteau qui revient) se place ensuite toute seule, grâce à ce que le logiciel a retenu de ce couteau.
- S'il y a plusieurs kills dans le clip, il prend le dernier ; tu peux choisir un autre kill dans la liste à droite du message.
- Si la bannière n'est pas trouvée, il te prévient : vérifie alors les 2 keyframes.
