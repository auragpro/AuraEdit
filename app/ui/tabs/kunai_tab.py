"""Onglet Kunai : vidéos de kunais de Jett, main gauche et main droite."""
from .hands_tab import HandsTab


class KunaiTab(HandsTab):
    ATTR = "kunai"
    TITLE = "Kunai"
    HINT = "Mets tes vidéos de kunais dans chaque main : à gauche et/ou à droite, ce que tu as."
    ENABLE = "Activer les kunais"
