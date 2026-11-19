"""Onglet Dash : tes vidéos de dash (Jett) à utiliser dans l'edit."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from app.core.project import VIDEO_EXT

from ..widgets import file_filter, page_header

ROLE = Qt.ItemDataRole.UserRole


class DashTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        d = project.dash

        self.enabled = QCheckBox("Activer les dash")
        self.enabled.setChecked(d.enabled)
        self.enabled.toggled.connect(self._toggle)

        self.videos = QListWidget()
        self.videos.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for v in d.videos:
            self.videos.addItem(self._item(v))
        b_add = QPushButton("Ajouter des vidéos...")
        b_remove = QPushButton("Retirer")
        b_add.clicked.connect(self.add_videos)
        b_remove.clicked.connect(self.remove_selected)
        self.count = QLabel()
        self.count.setObjectName("hint")

        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_remove)
        row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header("Dash", "Ajoute tes vidéos de dash. Tu pourras aussi les placer "
                                          "dans l'ordre de l'edit depuis l'onglet Clips."))
        lay.addWidget(self.enabled)
        lay.addWidget(QLabel("Tes vidéos de dash"))
        lay.addWidget(self.videos, 1)
        lay.addLayout(row)
        lay.addWidget(self.count)
        self._refresh()

    @staticmethod
    def _item(path):
        p = Path(path)
        item = QListWidgetItem(p.name if p.is_file() else f"⚠ {p.name} (introuvable)")
        item.setData(ROLE, str(path))
        item.setToolTip(str(path))
        return item

    def _toggle(self, on):
        self.project.dash.enabled = on
        self._refresh()
        self.changed.emit()

    def add_videos(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Vidéos de dash", "", file_filter("Vidéos", VIDEO_EXT))
        current = set(self.project.dash.videos)
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
        self.project.dash.videos = [self.videos.item(i).data(ROLE) for i in range(self.videos.count())]
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        self.videos.setEnabled(self.project.dash.enabled)
        n = self.videos.count()
        self.count.setText(f"{n} vidéo(s)" if n else "Aucune vidéo pour l'instant.")
