"""Shakes coupe par coupe : chaque coupe a son shake (IN/OUT 1x–5x + durée), qu'on peut retirer.
Sert aussi de confirmation avant le rendu (« voici les shakes posés automatiquement »)."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app.core import render, shake, vclip

LEVELS = [(s, n) for s in ("in", "out") for n in range(1, 6)]


def _fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def cut_rows(project):
    """[(libellé, instant ou None)] pour chaque coupe du montage, + les réglages venant de Reproduire."""
    segs = render.segments(project)
    tl = render.timeline_of(project)
    tl_items = iter(tl or [])
    seg_tl = [next(tl_items, None) if (tl and k == "clip") else None for k, _ in segs]
    times, t = [], 0.0
    for (k, p), e in zip(segs, seg_tl):
        times.append(t)
        if t is None:
            continue
        if e is not None:
            t += float(e.get("duree") or 0)
        elif k in ("intro", "outro"):
            t += render.duration(p)
        else:
            t = None
    rows, over = [], []
    for i in range(1, len(segs)):
        a, b = vclip.name(segs[i - 1][1]), vclip.name(segs[i][1])
        tt = times[i] if i < len(times) else None
        rows.append((f"Coupe {i}  ·  {_fmt(tt) if tt is not None else '—'}  ·  {a}  →  {b}", tt))
        over.append((seg_tl[i] or {}).get("shake"))
    return rows, over


class ShakeCutsDialog(QDialog):
    def __init__(self, project, parent=None, confirm=False):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Shakes coupe par coupe")
        self.resize(820, 600)
        rows, over = cut_rows(project)
        cfgs = shake.cut_cfgs(project.shakes, len(rows), over)
        base = shake.clean(project.shakes)

        kick = QLabel("SHAKES MOTION BRO · HIT IMPULSE")
        kick.setObjectName("kicker")
        title = QLabel("Confirme les shakes" if confirm else "Shakes coupe par coupe")
        title.setObjectName("h1")
        hint = QLabel(("Les shakes ont été posés automatiquement sur chaque coupe. Décoche ceux que tu veux "
                       "retirer, ou change le réglage d'une coupe (ex. OUT 3x durée 5 ici, IN 1x durée 4 là). "
                       if confirm else
                       "Choisis le shake de chaque coupe, ou décoche-le pour ne pas en mettre. ")
                      + "La durée va de 1 (court) à 9 (long), 5 = normal.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.widgets = []
        for i, (label, _) in enumerate(rows):
            c = cfgs[i]
            chk = QCheckBox(label)
            chk.setChecked(c is not None)
            lvl = QComboBox()
            for s, n in LEVELS:
                lvl.addItem(f"{s.upper()} {n}x", (s, n))
            cur = c or base
            lvl.setCurrentIndex(LEVELS.index((cur["sens"], cur["niveau"])))
            dur = QSpinBox()
            dur.setRange(1, 9)
            dur.setPrefix("durée ")
            dur.setValue(cur["duree"])
            chk.toggled.connect(lambda on, a=lvl, b=dur: (a.setEnabled(on), b.setEnabled(on)))
            lvl.setEnabled(c is not None)
            dur.setEnabled(c is not None)
            grid.addWidget(chk, i, 0)
            grid.addWidget(lvl, i, 1)
            grid.addWidget(dur, i, 2)
            self.widgets.append((chk, lvl, dur))
        grid.setColumnStretch(0, 1)
        inner = QWidget()
        inner.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        b_all = QPushButton("Tout cocher")
        b_all.clicked.connect(lambda: [w[0].setChecked(True) for w in self.widgets])
        b_none = QPushButton("Tout décocher")
        b_none.clicked.connect(lambda: [w[0].setChecked(False) for w in self.widgets])
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Valider et lancer le rendu" if confirm else "Valider")
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        row = QHBoxLayout()
        row.addWidget(b_all)
        row.addWidget(b_none)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.addWidget(kick)
        lay.addWidget(title)
        lay.addWidget(hint)
        if not rows:
            none = QLabel("Aucune coupe pour l'instant : ajoute des clips.")
            none.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(none, 1)
        else:
            lay.addWidget(scroll, 1)
        lay.addLayout(row)

    def _ok(self):
        coupes = {}
        for k, (chk, lvl, dur) in enumerate(self.widgets):
            if chk.isChecked():
                s, n = lvl.currentData()
                coupes[str(k)] = {"sens": s, "niveau": n, "duree": dur.value()}
            else:
                coupes[str(k)] = {"off": True}
        sh = dict(self.project.shakes or {})
        sh["coupes"] = coupes
        self.project.shakes = sh
        self.accept()
