"""Onglet Musique : le son de l'edit."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from app.core.project import AUDIO_EXT

from ..widgets import FilePicker, page_header


class MusicTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.music = FilePicker("Musique", AUDIO_EXT, "un fichier audio")
        self.music.set_path(project.music)
        self.music.changed.connect(self._set_music)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Musique", "Le son sur lequel l'edit sera monté (mp3, wav, m4a, flac...)."))
        lay.addWidget(self.music)
        lay.addStretch(1)

    def _set_music(self, path):
        self.project.music = path
        self.changed.emit()
