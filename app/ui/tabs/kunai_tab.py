"""Onglet Kunais Jett : tes vidéos de kills avec Jett, placées à gauche et/ou à droite."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                             QRadioButton, QVBoxLayout, QWidget)

from app.core.project import KUNAI_POSITIONS, VIDEO_EXT

from ..style import MUTED, PANEL_2, RED
from ..widgets import file_filter, page_header

ROLE = Qt.ItemDataRole.UserRole


class KunaiPreview(QWidget):
    """Schéma de l'écran : où apparaîtront les vidéos de kunais."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.position = "les deux"
        self.enabled = True
        self.setMinimumSize(320, 180)

    def set_state(self, position, enabled):
        self.position, self.enabled = position, enabled
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
        active = ["gauche", "droite"] if self.position == "les deux" else [self.position]
        for name, rect in zones.items():
            on = self.enabled and name in active
            color = QColor(RED if on else MUTED)
            color.setAlpha(200 if on else 60)
            p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine if on else Qt.PenStyle.DashLine))
            fill = QColor(RED)
            fill.setAlpha(55 if on else 0)
            p.setBrush(fill)
            p.drawRoundedRect(rect, 4, 4)
            if on:
                p.setPen(QColor("white"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "kunai\nJett")
        p.end()


class KunaiTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        k = project.kunai

        self.enabled = QCheckBox("Activer les kunais de Jett")
        self.enabled.setChecked(k.enabled)
        self.enabled.toggled.connect(self._toggle)

        self.group = QButtonGroup(self)
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Position :"))
        self.radios = {}
        for name in KUNAI_POSITIONS:
            rb = QRadioButton(name.capitalize())
            rb.setChecked(name == k.position)
            self.group.addButton(rb)
            self.radios[name] = rb
            rb.toggled.connect(self._position)
            pos_row.addWidget(rb)
        pos_row.addStretch(1)

        self.preview = KunaiPreview()

        self.videos = QListWidget()
        self.videos.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for v in k.videos:
            self.videos.addItem(self._item(v))
        b_add = QPushButton("Ajouter des vidéos...")
        b_remove = QPushButton("Retirer")
        b_add.clicked.connect(self.add_videos)
        b_remove.clicked.connect(self.remove_selected)
        self.count = QLabel()
        self.count.setObjectName("hint")

        options = QFrame()
        options.setObjectName("card")
        ol = QVBoxLayout(options)
        ol.setContentsMargins(16, 14, 16, 14)
        ol.addWidget(self.enabled)
        ol.addLayout(pos_row)
        ol.addWidget(self.preview, 1)

        vids = QVBoxLayout()
        vids.addWidget(QLabel("Tes vidéos de kills avec Jett"))
        vids.addWidget(self.videos, 1)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_remove)
        row.addStretch(1)
        vids.addLayout(row)
        vids.addWidget(self.count)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(options, 1)
        cols.addLayout(vids, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header("Kunai", "Ajoute tes vidéos de kills avec Jett : elles seront "
                                                 "incrustées sur le côté gauche, droit, ou les deux."))
        lay.addLayout(cols, 1)
        self._refresh()

    @staticmethod
    def _item(path):
        p = Path(path)
        item = QListWidgetItem(p.name if p.is_file() else f"⚠ {p.name} (introuvable)")
        item.setData(ROLE, str(path))
        item.setToolTip(str(path))
        return item

    def _toggle(self, on):
        self.project.kunai.enabled = on
        self._refresh()
        self.changed.emit()

    def _position(self, checked):
        if not checked:                 # chaque clic déclenche aussi le « décochage » de l'ancien
            return
        for name, rb in self.radios.items():
            if rb.isChecked():
                self.project.kunai.position = name
        self._refresh()
        self.changed.emit()

    def add_videos(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Vidéos de kills avec Jett", "",
                                                file_filter("Vidéos", VIDEO_EXT))
        current = set(self.project.kunai.videos)
        for f in files:
            if f not in current:
                self.videos.addItem(self._item(f))
                current.add(f)
        if files:
            self._sync()

    def remove_selected(self):
        for it in self.videos.selectedItems():
            self.videos.takeItem(self.videos.row(it))
        self._sync()

    def _sync(self):
        self.project.kunai.videos = [self.videos.item(i).data(ROLE) for i in range(self.videos.count())]
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        on = self.project.kunai.enabled
        for rb in self.radios.values():
            rb.setEnabled(on)
        self.videos.setEnabled(on)
        self.preview.set_state(self.project.kunai.position, on)
        n = self.videos.count()
        self.count.setText(f"{n} vidéo(s)" if n else "Aucune vidéo pour l'instant.")
