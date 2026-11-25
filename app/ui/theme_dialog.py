"""Options : choix du thème de l'app (thèmes proposés + thème personnalisé)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QVBoxLayout)

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

        # personnalisation : animations, fond, lueur, arrondi
        opt = QFrame()
        opt.setObjectName("card")
        ol = QGridLayout(opt)
        ol.setContentsMargins(16, 14, 16, 14)
        oh = QLabel("PERSONNALISATION")
        oh.setObjectName("kicker")
        ol.addWidget(oh, 0, 0, 1, 4)
        self.c_anim = QCheckBox("Animations (apparitions en fondu, transitions)")
        self.c_anim.setChecked(bool(self.theme.get("animations", True)))
        self.c_anim.toggled.connect(lambda v: self._opt("animations", v))
        self.c_bg = QCheckBox("Fond animé sur l'accueil (lueurs qui bougent)")
        self.c_bg.setChecked(bool(self.theme.get("fond_anime", True)))
        self.c_bg.toggled.connect(lambda v: self._opt("fond_anime", v))
        ol.addWidget(self.c_anim, 1, 0, 1, 4)
        ol.addWidget(self.c_bg, 2, 0, 1, 4)
        self.s_glow = QSlider(Qt.Orientation.Horizontal)
        self.s_glow.setRange(0, 100)
        self.s_glow.setValue(int(self.theme.get("lueur", 60)))
        self.s_glow.valueChanged.connect(lambda v: self._opt("lueur", v))
        self.s_round = QSlider(Qt.Orientation.Horizontal)
        self.s_round.setRange(0, 200)
        self.s_round.setValue(int(self.theme.get("arrondi", 100)))
        self.s_round.sliderReleased.connect(lambda: self._opt("arrondi", self.s_round.value()))
        ol.addWidget(QLabel("Lueur des boutons"), 3, 0)
        ol.addWidget(self.s_glow, 3, 1, 1, 3)
        ol.addWidget(QLabel("Arrondi des coins"), 4, 0)
        ol.addWidget(self.s_round, 4, 1, 1, 3)
        b_img = QPushButton("🖼  Image de fond de l'accueil...")
        b_img.clicked.connect(self._bg_image)
        b_noimg = QPushButton("Retirer l'image")
        b_noimg.clicked.connect(lambda: self._opt("fond_image", ""))
        ol.addWidget(b_img, 5, 0, 1, 2)
        ol.addWidget(b_noimg, 5, 2, 1, 2)

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
        lay.addWidget(opt)
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
        keep = {k: self.theme[k] for k in style.OPTIONS if k in self.theme}
        self.theme = dict(style.THEMES[name], nom=name, **keep)
        self._apply()

    def _opt(self, key, value):
        self.theme[key] = value
        self._apply()

    def _bg_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "Image de fond de l'accueil", "",
                                           "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if f:
            self._opt("fond_image", f)

    def _pick(self, key):
        c = QColorDialog.getColor(QColor(self.theme[key]), self, NAMES[key])
        if c.isValid():
            self.theme[key] = c.name()
            self.theme["nom"] = "Personnalisé"
            self._apply()
