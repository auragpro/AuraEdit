"""Options : choix du thème de l'app (thèmes proposés + thème personnalisé)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QColorDialog, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout)

from . import style

NAMES = {"accent": "Couleur principale", "accent2": "Couleur du dégradé", "bg": "Fond",
         "panel": "Panneaux", "panel2": "Boutons", "border": "Bordures", "text": "Texte", "muted": "Texte discret"}


class ThemeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options — Thème")
        self.setMinimumWidth(640)
        self.theme = dict(style.load_theme())

        kick = QLabel("OPTIONS · APPARENCE")
        kick.setObjectName("kicker")
        title = QLabel("Thème de l'app")
        title.setObjectName("h1")

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (name, t) in enumerate(style.THEMES.items()):
            b = QPushButton(name)
            b.setMinimumHeight(64)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t['bg']}, "
                f"stop:0.55 {t['panel2']}, stop:1 {t['accent']}); color: {t['text']}; "
                f"border: 2px solid {t['border']}; border-radius: 14px; font-weight: 700; }}"
                f"QPushButton:hover {{ border-color: {t['accent2']}; }}")
            b.clicked.connect(lambda _=False, n=name: self._preset(n))
            grid.addWidget(b, i // 3, i % 3)

        card = QFrame()
        card.setObjectName("card")
        cl = QGridLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        head = QLabel("PERSONNALISÉ — clique une couleur pour la changer")
        head.setObjectName("kicker")
        cl.addWidget(head, 0, 0, 1, 4)
        self.swatches = {}
        for i, k in enumerate(style.KEYS):
            lab = QLabel(NAMES[k])
            sw = QPushButton()
            sw.setFixedSize(64, 28)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.clicked.connect(lambda _=False, key=k: self._pick(key))
            self.swatches[k] = sw
            cl.addWidget(lab, 1 + i // 2, (i % 2) * 2)
            cl.addWidget(sw, 1 + i // 2, (i % 2) * 2 + 1)

        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        close = QPushButton("Fermer")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(close)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(kick)
        lay.addWidget(title)
        lay.addLayout(grid)
        lay.addWidget(card)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self):
        for k, sw in self.swatches.items():
            sw.setStyleSheet(f"background: {self.theme[k]}; border: 2px solid #ffffff33; border-radius: 8px;")
        self.status.setText(f"Thème : {self.theme.get('nom', 'Personnalisé')}. Appliqué tout de suite ; "
                            "quelques détails se mettent à jour au prochain lancement.")

    def _apply(self):
        style.apply_theme(self.theme)
        self._refresh()

    def _preset(self, name):
        self.theme = dict(style.THEMES[name], nom=name)
        self._apply()

    def _pick(self, key):
        c = QColorDialog.getColor(QColor(self.theme[key]), self, NAMES[key])
        if c.isValid():
            self.theme[key] = c.name()
            self.theme["nom"] = "Personnalisé"
            self._apply()
