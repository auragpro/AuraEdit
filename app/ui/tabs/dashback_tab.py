"""Onglet Dash back : vidéos de dash back, main gauche et main droite."""
from .hands_tab import HandsTab


class DashBackTab(HandsTab):
    ATTR = "dashback"
    TITLE = "Dash back"
    HINT = "Mets tes vidéos de dash back dans chaque main : à gauche et/ou à droite, ce que tu as."
    ENABLE = "Activer les dash back"
