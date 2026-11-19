"""Onglet Dismiss : vidéos de dismiss, main gauche et main droite."""
from .hands_tab import HandsTab


class DismissTab(HandsTab):
    ATTR = "dismiss"
    TITLE = "Dismiss"
    HINT = "Mets tes vidéos de dismiss dans chaque main : à gauche et/ou à droite, ce que tu as."
    ENABLE = "Activer les dismiss"
