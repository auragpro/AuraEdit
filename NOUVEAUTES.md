## Nouveautés de la version 0.5.4

- **Frame blending corrigé, comme After Effects.** Avant, le logiciel mélangeait trop d'images à la fois : ça faisait plein de « fantômes » du couteau et de la main. Maintenant, chaque image ne mélange que les **2 images voisines** (Frame Mix d'After Effects) : c'est net et fluide.
- **Fini l'effet 30 fps** : le logiciel utilise les vraies images de ton clip au lieu de le convertir en 60 i/s avant le time remap (ce qui doublait les images d'un clip en 30 i/s).
- **Nouveau mode « Pixel Motion »** (comme dans After Effects) : il calcule les images intermédiaires pour un ralenti encore plus fluide. Plus lent au rendu.
- Choix dans la page Time remap → **Frame blending** : Frame Mix (par défaut), Pixel Motion ou Aucun.
- Meilleure qualité d'image et beaucoup moins de mémoire utilisée pendant le rendu.
