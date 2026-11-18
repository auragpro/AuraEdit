"""Mode édition : barre latérale (onglets) à gauche + contenu de l'onglet à droite."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from .style import PANEL
from .tabs.clips_tab import ClipsTab
from .tabs.home_tab import HomeTab
from .tabs.intro_tab import IntroTab
from .tabs.kunai_tab import KunaiTab
from .tabs.music_tab import MusicTab
from .tabs.sounds_tab import SoundsTab

TABS = [("Accueil", HomeTab), ("Intro", IntroTab), ("Musique", MusicTab),
        ("Clips", ClipsTab), ("Sons IA", SoundsTab), ("Kunais Jett", KunaiTab)]


class EditView(QWidget):
    back_home = pyqtSignal()
    renamed = pyqtSignal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._save_error_shown = False

        # --- barre latérale
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.pages = QStackedWidget()
        self.tabs = {}
        for name, cls in TABS:
            page = cls(project)
            page.changed.connect(self.on_changed)
            self.tabs[name] = page
            self.pages.addWidget(page)
            self.sidebar.addItem(name)
        self.tabs["Accueil"].go_to.connect(self.select)
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)

        self.title = QLabel(project.name)
        self.title.setWordWrap(True)
        self.title.setStyleSheet(f"background: {PANEL}; font-weight: 700; padding: 18px 20px 6px 20px;")
        back = QPushButton("←  Écran de démarrage")
        back.setObjectName("link")
        back.setStyleSheet(f"background: {PANEL}; text-align: left; padding: 16px 20px;")
        back.clicked.connect(self.back_home.emit)

        side = QWidget()
        side.setFixedWidth(230)
        side.setStyleSheet(f"background: {PANEL};")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(self.title)
        sl.addWidget(self.sidebar, 1)
        sl.addWidget(back)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(side)
        lay.addWidget(self.pages, 1)
        self.sidebar.setCurrentRow(0)

    def select(self, name):
        names = [n for n, _ in TABS]
        if name in names:
            self.sidebar.setCurrentRow(names.index(name))

    def on_changed(self):
        """Une modification dans un onglet : sauvegarde auto + mise à jour du résumé."""
        self.title.setText(self.project.name)
        self.renamed.emit(self.project.name)
        self.tabs["Accueil"].refresh()
        self.save()

    def save(self):
        try:
            self.project.save()
            self._save_error_shown = False
        except OSError as e:
            if not self._save_error_shown:     # un seul message, pas une rafale
                self._save_error_shown = True
                QMessageBox.warning(self, "Sauvegarde impossible",
                                    f"Le projet n'a pas pu être sauvegardé :\n{e}")

    def shutdown(self):
        """À appeler avant de fermer : arrête les recherches en cours et sauvegarde."""
        for page in self.tabs.values():
            stop = getattr(page, "stop", None)
            if stop:
                stop()
        self.save()
