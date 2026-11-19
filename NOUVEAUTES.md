## Nouveautés de la version 0.5.0

- **Time remap automatique sur tes clips de couteau.** Quand tu ajoutes un clip à l'edit, une page s'ouvre :
  - **C'est quel couteau ?** Choisis-le (tes dossiers de couteaux sont proposés) et mets son image si tu veux.
  - Le logiciel trouve tout seul la **keyframe 1** (première frame sans les mains, quand le perso sort le couteau) et la **keyframe 2** (couteau sorti). Tu vois les deux images.
  - Si c'est mauvais : déplace les curseurs image par image, ou « Refaire la détection ».
  - La **keyframe 3** est une copie de la 1 : le reverse.
- **Tes courbes** : courbe 1 (keyframe 1 → 2) et courbe 2 (2 → 3) au format « 0.39, 0.59, 0.26, 1 », avec le graphique. La durée du ralenti et du retour se règlent aussi.
- **Frame blending** : le ralenti est fluide et le reverse a du flou de mouvement.
- Le logiciel **retient chaque couteau** : la prochaine fois, il sait jusqu'où va le time remap.
- Bouton **« ⏱ Time remap... »** (ou double-clic) dans l'ordre de l'edit pour refaire celui d'un clip.
- « Générer l'edit » applique le time remap à chaque clip qui en a un.
