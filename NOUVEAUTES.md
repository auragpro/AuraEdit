## Nouveautés de la version 0.5.6

- **Pixel Motion réparé et presque 3 fois plus rapide.** Avant, il calculait beaucoup trop d'images intermédiaires : le rendu semblait bloqué. Maintenant il en calcule juste assez (×2 pour un clip en 60 i/s, ×4 pour un clip en 30 i/s).
- **On voit l'avancement** pendant le rendu, image par image (« Pixel Motion : calcul des images 40/120 »), au lieu d'une barre figée.
- **Nouveau bouton « ▶ Aperçu »** dans la page Time remap : il rend ce clip avec ton time remap et le frame blending choisi, puis l'ouvre dans ton lecteur vidéo. Tu vois tout de suite si Pixel Motion te plaît.
- Si le Pixel Motion n'arrive pas à traiter un clip, le logiciel passe automatiquement en Frame Mix au lieu de bloquer le rendu.
