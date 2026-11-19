"""Onglet Kunai : vidéos de kunais de Jett, main gauche et main droite."""
from .hands_tab import HandsTab


class KunaiTab(HandsTab):
    ATTR = "kunai"
    TITLE = "Kunai"
    HINT = "Mets tes vidéos de kunais dans chaque main, puis règle leur time remap avec « ⏱ Time remap... » (ou double-clic)."
    ENABLE = "Activer les kunais"
