"""Onglet Dash : vidéos de dash, main gauche et main droite."""
from .hands_tab import HandsTab


class DashTab(HandsTab):
    ATTR = "dash"
    TITLE = "Dash"
    HINT = "Mets tes vidéos de dash dans chaque main : à gauche et/ou à droite, ce que tu as."
    ENABLE = "Activer les dash"
