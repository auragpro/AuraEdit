"""Fenêtre : les sound kills trouvés dans le projet FL Studio, avec leur type deviné. Tu corriges, il apprend."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout)

from app.core import markers as mk
from app.core import sk_learn

CHOICES = [("clip", "Clip / flickaway"), ("dash", "Dash"), ("kunai", "Kunai"), (None, "?  (ignorer)")]


class FlpDialog(QDialog):
    def __init__(self, hits, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sound kills du projet FL Studio")
        self.resize(820, 600)
        self.hits = hits
        self.preds = sk_learn.predict(hits)
        self.result = []

        unknown = sum(1 for p in self.preds if p[0] is None)
        head = QLabel(f"<b>{len(hits)} sound kill(s)</b> trouvé(s) — tempo {info['tempo']:g} BPM. "
                      + (f"<span style='color:#ffb84d'>{unknown} inconnu(s) : choisis leur type.</span>"
                         if unknown else "Vérifie les types, corrige si besoin."))
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setWordWrap(True)
        n_s, n_e = sk_learn.stats()
        sub = QLabel(f"Le logiciel a déjà appris {n_s} son(s) ({n_e} exemples). "
                     "Chaque validation et chaque correction l'entraîne.")
        sub.setObjectName("hint")

        self.table = QTableWidget(len(hits), 5)
        self.table.setHorizontalHeaderLabels(["Moment", "Son", "Écart", "Type", "Pourquoi"])
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        feats = sk_learn.features(hits)
        self.combos = []
        for r, (h, (t, conf, why), f) in enumerate(zip(hits, self.preds, feats)):
            m, s = divmod(h["t"], 60)
            self.table.setItem(r, 0, QTableWidgetItem(f"{int(m)}:{s:06.3f}"))
            name = QTableWidgetItem(h["nom"])
            name.setToolTip(h["sample"])
            self.table.setItem(r, 1, name)
            self.table.setItem(r, 2, QTableWidgetItem(f"{min(f[0], f[1]):.2f} s"))
            cb = QComboBox()
            for k, lab in CHOICES:
                cb.addItem(lab, k)
            cb.setCurrentIndex([k for k, _ in CHOICES].index(t))
            cb.currentIndexChanged.connect(lambda _=0, row=r: self._paint(row))
            self.table.setCellWidget(r, 3, cb)
            self.combos.append(cb)
            why_item = QTableWidgetItem(why + (f" ({int(conf * 100)} %)" if t else ""))
            self.table.setItem(r, 4, why_item)
            self._paint(r)

        # changer tous les sound kills du même son d'un coup
        self.same = QPushButton("Appliquer le type choisi à tous les sons identiques")
        self.same.clicked.connect(self._apply_same)

        ok = QPushButton("Valider (place les repères et apprend)")
        ok.setObjectName("primary")
        ok.clicked.connect(self._validate)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.same)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)

        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(sub)
        lay.addWidget(self.table, 1)
        lay.addLayout(row)

    def _paint(self, r):
        k = self.combos[r].currentData()
        col = QColor(mk.COLORS[k]) if k else QColor("#ffb84d")
        col.setAlpha(60)
        for c in (0, 1, 2, 4):
            it = self.table.item(r, c)
            if it:
                it.setBackground(col)

    def _apply_same(self):
        rows = {i.row() for i in self.table.selectedIndexes()} or {self.table.currentRow()}
        for r in rows:
            if r < 0:
                continue
            k = sk_learn.key(self.hits[r]["sample"])
            val = self.combos[r].currentIndex()
            for j, h in enumerate(self.hits):
                if sk_learn.key(h["sample"]) == k:
                    self.combos[j].setCurrentIndex(val)

    def _validate(self):
        types = [cb.currentData() for cb in self.combos]
        sk_learn.learn(self.hits, types)
        feats = sk_learn.features(self.hits)
        self.result = [{"t": h["t"], "type": t, "src": {"sample": h["sample"], "f": f, "type": t}}
                       for h, t, f in zip(self.hits, types, feats) if t]
        self.skipped = sum(1 for t in types if not t)
        self.accept()
