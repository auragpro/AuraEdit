"""Time remap manuel (2K / 3K / 4K dismiss ou flick away) : des keyframes et des courbes, comme dans After Effects.

Chaque keyframe dit : « à tel moment du plan, on montre telle frame du clip ». Entre deux keyframes,
la courbe (code Flow / cubic-bezier) règle l'accélération."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.core import render, timeremap as tr

from .style import MUTED, RED
from .timeremap_dialog import FramePicker

PRESETS = [("Douce", "0.33, 0, 0.67, 1"), ("Flow forte", "0.69, 0, 0.31, 1"), ("Linéaire", "0, 0, 1, 1"),
           ("Accélère", "0.6, 0, 1, 1"), ("Ralentit", "0, 0, 0.4, 1")]


class Graph(QWidget):
    """Courbe : temps du clip (vertical) selon le moment du plan (horizontal)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self.keys, self.curves, self.total = [], [], 1.0

    def set(self, keys, curves, total):
        self.keys, self.curves, self.total = keys, curves, total
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#05080f"))
        if len(self.keys) < 2:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Ajoute au moins 2 keyframes")
            return
        try:
            ts = tr.manual_times(self.keys, self.curves, self.total)
        except ValueError:
            return
        lo, hi = min(ts), max(ts)
        hi = hi if hi > lo else lo + 0.01
        m = 14
        w, h = self.width() - 2 * m, self.height() - 2 * m

        def pt(x, y):
            return QPointF(m + w * x, m + h * (1 - (y - lo) / (hi - lo)))
        p.setPen(QPen(QColor("#1f2c45"), 1))
        for k in range(5):
            p.drawLine(pt(k / 4, lo), pt(k / 4, hi))
        p.setPen(QPen(QColor("#ffffff"), 2))
        n = len(ts)
        for i in range(1, n):
            p.drawLine(pt((i - 1) / (n - 1), ts[i - 1]), pt(i / (n - 1), ts[i]))
        p.setBrush(QColor(RED))
        p.setPen(Qt.PenStyle.NoPen)
        end = max(k[0] for k in self.keys) or 1.0
        for a, b in self.keys:
            c = pt(a / end, b)
            p.drawRect(int(c.x()) - 4, int(c.y()) - 4, 8, 8)


class ManualRemapDialog(QDialog):
    def __init__(self, path, total, data=None, start=0.0, title="Time remap manuel", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 720)
        self.path, self.total = path, max(0.05, float(total))
        self.result = None
        data = data or {}
        keys = data.get("keys") or [[0.0, start], [self.total, start + self.total]]
        curves = list(data.get("courbes") or [])

        kick = QLabel("TIME REMAP MANUEL · KEYFRAMES + COURBES")
        kick.setObjectName("kicker")
        head = QLabel(title)
        head.setObjectName("h1")
        hint = QLabel(f"Le plan dure {self.total:.2f} s. Place-toi sur un moment du plan, choisis la frame du clip "
                      "à montrer à ce moment, puis « ➕ Keyframe ici ». Entre 2 keyframes, la courbe règle "
                      "l'accélération (colle un code Flow ou choisis un préréglage). Pour un reverse, mets une "
                      "frame plus tôt dans le clip sur la keyframe suivante.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        self.picker = FramePicker("Frame du clip", path)
        n = max(2, int(render.duration(path) * tr.FPS))
        self.picker.setup(n, min(n - 1, int(round(start * tr.FPS))))
        self.picker.show_frame()
        self.moment = QDoubleSpinBox()
        self.moment.setRange(0.0, self.total)
        self.moment.setDecimals(3)
        self.moment.setSingleStep(1 / tr.FPS)
        self.moment.setPrefix("Moment dans le plan : ")
        self.moment.setSuffix(" s")
        b_add = QPushButton("➕ Keyframe ici")
        b_add.setObjectName("primary")
        b_add.clicked.connect(self._add)
        b_del = QPushButton("🗑 Supprimer la keyframe")
        b_del.clicked.connect(self._del)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Moment du plan (s)", "Frame du clip", "Courbe vers la suivante"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._select)
        self.table.itemChanged.connect(lambda *_: self._sync())
        self.preset = QComboBox()
        self.preset.addItem("Courbe de la keyframe choisie…")
        for name, code in PRESETS:
            self.preset.addItem(f"{name}  ({code})", code)
        self.preset.activated.connect(self._preset)
        self.blend = QComboBox()
        for k, v in tr.BLEND_MODES.items():
            self.blend.addItem(v, k)
        self.blend.setCurrentIndex(max(0, self.blend.findData(data.get("blending_mode", "motion"))))
        self.graph = Graph()

        ok = QPushButton("Valider ce time remap")
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(self.picker)
        mrow = QHBoxLayout()
        mrow.addWidget(self.moment, 1)
        mrow.addWidget(b_add)
        left.addLayout(mrow)
        left.addWidget(self.graph, 1)
        right = QVBoxLayout()
        right.addWidget(self.table, 1)
        crow = QHBoxLayout()
        crow.addWidget(self.preset, 1)
        crow.addWidget(b_del)
        right.addLayout(crow)
        right.addWidget(QLabel("Frame blending :"))
        right.addWidget(self.blend)
        body = QHBoxLayout()
        body.addLayout(left, 3)
        body.addLayout(right, 2)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.addWidget(kick)
        lay.addWidget(head)
        lay.addWidget(hint)
        lay.addLayout(body, 1)
        lay.addLayout(bottom)
        self._fill(sorted([float(a), float(b)] for a, b in keys), curves)

    # ---------------------------------------------------------------- table
    def _fill(self, keys, curves):
        self.table.blockSignals(True)
        self.table.setRowCount(len(keys))
        for r, (a, b) in enumerate(keys):
            it = QTableWidgetItem(f"{a:.3f}")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, it)
            it = QTableWidgetItem(f"{int(round(b * tr.FPS))}")
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 1, it)
            code = curves[r] if r < len(curves) else PRESETS[0][1]
            it = QTableWidgetItem("" if r == len(keys) - 1 else code)
            if r == len(keys) - 1:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 2, it)
        self.table.blockSignals(False)
        self._sync()

    def _keys(self):
        keys, curves = [], []
        for r in range(self.table.rowCount()):
            keys.append([float(self.table.item(r, 0).text()), int(self.table.item(r, 1).text()) / tr.FPS])
            curves.append(self.table.item(r, 2).text())
        return keys, curves[:-1]

    def _sync(self):
        keys, curves = self._keys()
        self.graph.set(keys, curves, self.total)

    def _add(self):
        keys, curves = self._keys()
        a, b = round(self.moment.value(), 3), self.picker.seconds()
        for k in keys:
            if abs(k[0] - a) < 0.5 / tr.FPS:
                k[1] = b
                break
        else:
            keys.append([a, b])
            curves.append(PRESETS[0][1])
        order = sorted(range(len(keys)), key=lambda i: keys[i][0])
        allc = curves + [PRESETS[0][1]] * (len(keys) - len(curves))
        self._fill([keys[i] for i in order], [allc[i] for i in order])

    def _del(self):
        r = self.table.currentRow()
        if r < 0:
            return
        keys, curves = self._keys()
        curves = curves + [""]
        del keys[r]
        del curves[r]
        self._fill(keys, curves)

    def _select(self):
        r = self.table.currentRow()
        if r < 0:
            return
        keys, _ = self._keys()
        self.moment.setValue(keys[r][0])
        self.picker.setup(self.picker.slider.maximum() + 1, int(round(keys[r][1] * tr.FPS)))
        self.picker.show_frame()

    def _preset(self, i):
        code = self.preset.itemData(i)
        r = self.table.currentRow()
        if code and 0 <= r < self.table.rowCount() - 1:
            self.table.item(r, 2).setText(code)
        self.preset.setCurrentIndex(0)

    def _ok(self):
        keys, curves = self._keys()
        if len(keys) < 2:
            QMessageBox.information(self, "Time remap manuel", "Il faut au moins 2 keyframes.")
            return
        bad = [c for c in curves if tr.parse_curve(c) is None]
        if bad:
            QMessageBox.information(self, "Time remap manuel", f"Courbe illisible : « {bad[0]} »")
            return
        keys[0][0] = 0.0
        keys[-1][0] = self.total
        self.result = {"keys": keys, "courbes": curves, "blending_mode": self.blend.currentData()}
        self.accept()
