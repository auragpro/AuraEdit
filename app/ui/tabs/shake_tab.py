"""Onglet Shake : le shake « Hit Impulse » posé sur chaque coupe (IN 1x–5x, OUT 1x–5x, durée, seed)."""
import random

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)

from app.core import shake

from ..style import PANEL_2, RED
from ..widgets import page_header

BTN = f"""
QPushButton {{ background: {PANEL_2}; border: 1px solid #3a3f4b; border-radius: 6px; padding: 10px 0;
              font-weight: 600; min-width: 54px; }}
QPushButton:checked {{ background: {RED}; border-color: {RED}; color: white; }}
QPushButton:hover {{ border-color: {RED}; }}
"""
SEG = f"""
QPushButton {{ background: {PANEL_2}; border: none; border-radius: 3px; min-width: 26px; min-height: 22px; }}
QPushButton:checked {{ background: {RED}; }}
"""


class ShakeTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.cfg = shake.clean(project.shakes)

        self.enable = QCheckBox("Ajouter un shake à chaque coupe entre les clips")
        self.enable.setChecked(self.cfg["actif"])
        self.enable.toggled.connect(self._save)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(12)
        title = QLabel("Hit Impulse")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        cl.addWidget(title)
        self.groups = {}
        for side, label, tip in (("in", "IN", "monte jusqu'à la coupe (fin du clip d'avant)"),
                                 ("out", "OUT", "part de la coupe et retombe (début du clip suivant)")):
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setFixedWidth(46)
            lab.setStyleSheet("font-weight: 700; font-size: 15px;")
            lab.setToolTip(tip)
            row.addWidget(lab)
            g = QButtonGroup(self)
            g.setExclusive(True)
            for lvl in range(0, 6):
                b = QPushButton("Off" if lvl == 0 else f"{lvl}x")
                b.setCheckable(True)
                b.setStyleSheet(BTN)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setChecked(self.cfg[side] == lvl)
                g.addButton(b, lvl)
                row.addWidget(b)
            g.idClicked.connect(self._save)
            self.groups[side] = g
            row.addStretch(1)
            cl.addLayout(row)

        drow = QHBoxLayout()
        dl = QLabel("Duration")
        dl.setFixedWidth(70)
        drow.addWidget(dl)
        self.dur = QButtonGroup(self)
        for i in range(1, 10):
            b = QPushButton()
            b.setCheckable(True)
            b.setStyleSheet(SEG)
            b.setToolTip(f"×{shake.DURATIONS[i - 1]:g}" + (" (normal)" if i == 5 else ""))
            b.setChecked(self.cfg["duree"] == i)
            self.dur.addButton(b, i)
            drow.addWidget(b)
        self.dur.idClicked.connect(self._save)
        self.dur_label = QLabel()
        self.dur_label.setObjectName("hint")
        drow.addSpacing(10)
        drow.addWidget(self.dur_label)
        drow.addStretch(1)
        cl.addLayout(drow)

        srow = QHBoxLayout()
        sl = QLabel("Seed")
        sl.setFixedWidth(70)
        srow.addWidget(sl)
        self.seed = QSpinBox()
        self.seed.setRange(0, 99999)
        self.seed.setValue(self.cfg["seed"])
        self.seed.valueChanged.connect(self._save)
        dice = QPushButton("🎲 Aléatoire")
        dice.clicked.connect(lambda: self.seed.setValue(random.randint(0, 99999)))
        srow.addWidget(self.seed)
        srow.addWidget(dice)
        srow.addStretch(1)
        cl.addLayout(srow)

        hint = QLabel("Chaque niveau ajoute un zoom arrière (bords en miroir), un tremblement de position et de "
                      "rotation et un décalage de couleurs, plus forts de 1x à 5x. Le seed change le tremblement ; "
                      "chaque coupe a son propre tremblement. Le shake est posé quand tu cliques « Générer l'edit ».")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Shake", "Le shake entre chaque clip, comme le preset Hit Impulse."))
        lay.addWidget(self.enable)
        lay.addWidget(card)
        lay.addWidget(hint)
        lay.addStretch(1)
        self.card = card
        self._refresh()

    def _refresh(self):
        self.card.setEnabled(self.enable.isChecked())
        d = self.cfg["duree"]
        self.dur_label.setText(f"×{shake.DURATIONS[d - 1]:g}" + (" (normal)" if d == 5 else ""))

    def _save(self, *_):
        self.cfg = shake.clean({"actif": self.enable.isChecked(), "in": self.groups["in"].checkedId(),
                                "out": self.groups["out"].checkedId(), "duree": self.dur.checkedId(),
                                "seed": self.seed.value()})
        self.project.shakes = dict(self.cfg)
        self._refresh()
        self.changed.emit()

    def summary(self):
        c = shake.clean(self.project.shakes)
        if not c["actif"] or not (c["in"] or c["out"]):
            return "désactivé"
        f = lambda v: f"{v}x" if v else "off"
        return f"✓ IN {f(c['in'])} · OUT {f(c['out'])}"
