"""Onglet Intro : clip d'intro (et outro optionnelle)."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from app.core.project import VIDEO_EXT

from ..widgets import FilePicker, page_header


class IntroTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.intro = FilePicker("Clip d'intro", VIDEO_EXT, "une vidéo")
        self.outro = FilePicker("Outro", VIDEO_EXT, "une vidéo", optional=True)
        self.intro.set_path(project.intro)
        self.outro.set_path(project.outro)
        self.intro.changed.connect(self._set_intro)
        self.outro.changed.connect(self._set_outro)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Intro", "Le clip qui ouvre ton edit. L'outro (optionnelle) le termine."))
        lay.addWidget(self.intro)
        lay.addWidget(self.outro)
        lay.addStretch(1)

    def _set_intro(self, path):
        self.project.intro = path
        self.changed.emit()

    def _set_outro(self, path):
        self.project.outro = path
        self.changed.emit()
