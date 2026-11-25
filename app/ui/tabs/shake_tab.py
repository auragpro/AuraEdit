"""Onglet Shake : le shake « Hit Impulse » (IN 1x–5x / OUT 1x–5x + durée), peak sur chaque coupe."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from app.core import shake

from ..style import PANEL_2, RED
from ..widgets import page_header

BTN = f"""
QPushButton {{ background: {PANEL_2}; border: 1px solid #3a3f4b; border-radius: 6px; padding: 12px 0;
              font-weight: 600; min-width: 64px; }}
QPushButton:checked {{ background: {RED}; border-color: {RED}; color: white; }}
QPushButton:hover {{ border-color: {RED}; }}
"""
SEG = f"""
QPushButton {{ background: {PANEL_2}; border: none; border-radius: 3px; min-width: 30px; min-height: 22px; }}
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

        grid = QGridLayout()
        grid.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for r, side in enumerate(("in", "out")):
            lab = QLabel(side.upper())
            lab.setStyleSheet("font-weight: 700; font-size: 15px;")
            lab.setToolTip("IN : punch en zoom avant" if side == "in" else "OUT : punch en zoom arrière")
            grid.addWidget(lab, r, 0)
            for lvl in range(1, 6):
                b = QPushButton(f"{lvl}x")
                b.setCheckable(True)
                b.setStyleSheet(BTN)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setChecked(self.cfg["sens"] == side and self.cfg["niveau"] == lvl)
                self.group.addButton(b, (10 if side == "out" else 0) + lvl)
                grid.addWidget(b, r, lvl)
        grid.setColumnStretch(6, 1)
        self.group.idClicked.connect(self._save)
        cl.addLayout(grid)

        drow = QHBoxLayout()
        dl = QLabel("Duration")
        dl.setFixedWidth(70)
        drow.addWidget(dl)
        self.dur = QButtonGroup(self)
        for i in range(1, 10):
            b = QPushButton()
            b.setCheckable(True)
            b.setStyleSheet(SEG)
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

        hint = QLabel("Le PEAK (moment le plus fort du shake) tombe pile sur chaque coupe entre 2 clips, "
                      "clips en time remap compris. Si deux shakes se chevauchent, ils s'additionnent. "
                      "Le shake est posé quand tu cliques « Générer l'edit ».")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Shake", "Le shake Hit Impulse entre chaque clip."))
        lay.addWidget(self.enable)
        lay.addWidget(card)
        b_cuts = QPushButton("🎯  Choisir les shakes coupe par coupe...")
        b_cuts.setToolTip("Un réglage différent à chaque coupe (ex. OUT 3x durée 5 ici, IN 1x durée 4 là), "
                          "ou pas de shake du tout sur certaines coupes.")
        b_cuts.clicked.connect(self._per_cut)
        lay.addWidget(b_cuts, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(hint)
        lay.addStretch(1)
        self.card = card
        self._refresh()

    def _refresh(self):
        self.card.setEnabled(self.enable.isChecked())
        k = shake.DURATIONS[self.cfg["duree"] - 1]
        avant, apres = shake.BEFORE * k, shake.AFTER * k
        self.dur_label.setText(f"{avant:g} images avant le peak · {apres:g} après"
                               + (" (normal)" if self.cfg["duree"] == 5 else ""))

    def _save(self, *_):
        gid = self.group.checkedId()
        self.cfg = shake.clean({"actif": self.enable.isChecked(), "sens": "out" if gid > 10 else "in",
                                "niveau": gid % 10, "duree": self.dur.checkedId()})
        old = self.project.shakes if isinstance(self.project.shakes, dict) else {}
        self.project.shakes = dict(self.cfg, **({"coupes": old["coupes"]} if old.get("coupes") else {}))
        self._refresh()
        self.changed.emit()

    def _per_cut(self):
        from ..shake_cuts_dialog import ShakeCutsDialog
        if ShakeCutsDialog(self.project, self).exec():
            self.changed.emit()

    def summary(self):
        c = shake.clean(self.project.shakes)
        if not c["actif"]:
            return "désactivé"
        return f"✓ {c['sens'].upper()} {c['niveau']}x"
