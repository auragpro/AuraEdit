"""Onglets Kunai et Dash : deux mains (gauche / droite), chacune avec ses propres vidéos."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from app.core.project import VIDEO_EXT

from ..style import MUTED, PANEL_2, RED
from ..widgets import file_filter, page_header

ROLE = Qt.ItemDataRole.UserRole
SIDES = (("gauche", "Main gauche"), ("droite", "Main droite"))


class HandsPreview(QWidget):
    """Schéma de l'écran : les côtés qui ont des vidéos s'allument."""

    def __init__(self, word, parent=None):
        super().__init__(parent)
        self.word = word
        self.sides = {"gauche": 0, "droite": 0}
        self.enabled = True
        self.setMinimumSize(300, 150)
        self.setMaximumHeight(220)

    def set_state(self, sides, enabled):
        self.sides, self.enabled = sides, enabled
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = min(self.width(), self.height() * 16 / 9)
        h = w * 9 / 16
        screen = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.setPen(QPen(QColor(MUTED), 1))
        p.setBrush(QColor(PANEL_2))
        p.drawRoundedRect(screen, 6, 6)
        p.setPen(QColor(MUTED))
        p.drawText(screen, Qt.AlignmentFlag.AlignCenter, "ton clip")
        side_w = screen.width() * 0.26
        zones = {"gauche": QRectF(screen.left() + 8, screen.top() + 8, side_w, screen.height() - 16),
                 "droite": QRectF(screen.right() - 8 - side_w, screen.top() + 8, side_w, screen.height() - 16)}
        for name, rect in zones.items():
            n = self.sides.get(name, 0)
            on = self.enabled and n > 0
            color = QColor(RED if on else MUTED)
            color.setAlpha(200 if on else 60)
            p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine if on else Qt.PenStyle.DashLine))
            fill = QColor(RED)
            fill.setAlpha(55 if on else 0)
            p.setBrush(fill)
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor("white") if on else QColor(MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.word}\n{name}\n({n})")
        p.end()


class HandsTab(QWidget):
    changed = pyqtSignal()
    ATTR = "kunai"           # project.kunai ou project.dash
    TITLE = "Kunai"
    HINT = ""
    ENABLE = "Activer"

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        s = self.settings

        self.enabled = QCheckBox(self.ENABLE)
        self.enabled.setChecked(s.enabled)
        self.enabled.toggled.connect(self._toggle)
        self.preview = HandsPreview(self.TITLE.lower())

        self.lists, self.counts = {}, {}
        cols = QHBoxLayout()
        cols.setSpacing(16)
        for side, label in SIDES:
            lst = QListWidget()
            lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            for v in getattr(s, side):
                lst.addItem(self._item(v))
            b_add = QPushButton("Ajouter des vidéos...")
            b_add.setObjectName("primary")
            b_remove = QPushButton("Retirer")
            b_add.clicked.connect(lambda _=False, sd=side: self.add_videos(sd))
            b_remove.clicked.connect(lambda _=False, sd=side: self.remove_selected(sd))
            count = QLabel()
            count.setObjectName("hint")
            title = QLabel(("✋  " if side == "gauche" else "🤚  ") + label)
            title.setStyleSheet("font-size: 16px; font-weight: 700;")
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.addWidget(title)
            cl.addWidget(lst, 1)
            row = QHBoxLayout()
            row.addWidget(b_add)
            row.addWidget(b_remove)
            cl.addLayout(row)
            cl.addWidget(count)
            cols.addWidget(card, 1)
            self.lists[side], self.counts[side] = lst, count

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header(self.TITLE, self.HINT))
        top = QHBoxLayout()
        top.addWidget(self.enabled)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(self.preview)
        lay.addLayout(cols, 1)
        self._refresh()

    @property
    def settings(self):
        return getattr(self.project, self.ATTR)

    @staticmethod
    def _item(path):
        p = Path(path)
        item = QListWidgetItem(p.name if p.is_file() else f"⚠ {p.name} (introuvable)")
        item.setData(ROLE, str(path))
        item.setToolTip(str(path))
        return item

    def _toggle(self, on):
        self.settings.enabled = on
        self._refresh()
        self.changed.emit()

    def add_videos(self, side):
        label = dict(SIDES)[side]
        files, _ = QFileDialog.getOpenFileNames(self, f"{self.TITLE} — {label}", "",
                                                file_filter("Vidéos", VIDEO_EXT))
        current = set(getattr(self.settings, side))
        for f in files:
            if f not in current:
                self.lists[side].addItem(self._item(f))
                current.add(f)
        if files:
            self._sync()

    def remove_selected(self, side):
        lst = self.lists[side]
        for it in lst.selectedItems():
            lst.takeItem(lst.row(it))
        self._sync()

    def _sync(self):
        for side, lst in self.lists.items():
            setattr(self.settings, side, [lst.item(i).data(ROLE) for i in range(lst.count())])
        self.settings.sync()
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        on = self.settings.enabled
        sides = {}
        for side, lst in self.lists.items():
            lst.setEnabled(on)
            n = lst.count()
            sides[side] = n
            self.counts[side].setText(f"{n} vidéo(s)" if n else "Aucune vidéo pour l'instant.")
        self.preview.set_state(sides, on)
