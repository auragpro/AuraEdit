## Nouveautés de la version 0.7.0

- **Shakes « Hit Impulse » refaits** pour être comme dans Motion Bro :
  - le **PEAK** (moment où le shake est le plus fort) tombe **pile sur chaque coupe entre 2 clips**, y compris les clips en time remap ;
  - **durée normale (5ᵉ cran)** : **4 images avant le peak et 20 images après** ;
  - les 9 crans de **Duration** resserrent ou allongent le shake autour du peak ;
  - au peak : gros coup de position, punch de zoom, puis rotation et décalage de couleurs qui retombent.
- Si un shake déborde sur le clip suivant ou sur un autre shake, **il est fait quand même** (les shakes s'additionnent).
- **IN 1x → 5x** (punch en zoom avant) et **OUT 1x → 5x** (punch en zoom arrière) : un seul choix, comme dans Motion Bro.
- Le **seed** a été retiré.
