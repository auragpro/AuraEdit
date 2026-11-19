"""Mode édition : barre latérale (onglets) à gauche + contenu de l'onglet à droite."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .style import PANEL
from .tabs.clips_tab import LibraryTab
from .tabs.home_tab import HomeTab
from .tabs.montage_tab import PARTS, MontageTab
from .tabs.sounds_tab import SoundsTab

# (nom, classe, catégorie) — les onglets d'une même catégorie sont regroupés sous un titre
TABS = [("Accueil", HomeTab, None), ("Montage", MontageTab, None), ("Sons IA", SoundsTab, None),
        ("Mes clips", LibraryTab, "BIBLIOTHÈQUE")]
ROLE = Qt.ItemDataRole.UserRole


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
        self.rows = {}
        group = None
        for name, cls, cat in TABS:
            if cat and cat != group:
                head = QListWidgetItem(cat)
                head.setFlags(Qt.ItemFlag.NoItemFlags)       # titre : pas cliquable
                f = head.font()
                f.setPointSize(8)
                f.setBold(True)
                head.setFont(f)
                self.sidebar.addItem(head)
            group = cat
            page = cls(project)
            page.changed.connect(self.on_changed)
            self.tabs[name] = page
            index = self.pages.addWidget(page)
            item = QListWidgetItem(("    " if cat else "") + name)
            item.setData(ROLE, index)
            self.sidebar.addItem(item)
            self.rows[name] = self.sidebar.count() - 1
        self.tabs["Accueil"].go_to.connect(self.select)
        self.tabs["Montage"].render_requested.connect(self._render)
        self.tabs["Montage"].parts["Clips"].go_library.connect(lambda: self.select("Mes clips"))
        self.sidebar.currentRowChanged.connect(self._row)

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

    def _row(self, row):
        item = self.sidebar.item(row)
        if item is not None and item.data(ROLE) is not None:
            self.pages.setCurrentIndex(item.data(ROLE))
            if self.pages.currentWidget() is self.tabs.get("Montage"):
                self.tabs["Montage"].home()            # revient aux gros carrés

    def _render(self):
        self.select("Accueil")
        self.tabs["Accueil"].render()

    def select(self, name):
        if name in [n for n, _ in PARTS]:          # une partie du Montage
            self.sidebar.setCurrentRow(self.rows["Montage"])
            self.tabs["Montage"].open(name)
            return
        if name in self.rows:
            self.sidebar.setCurrentRow(self.rows[name])

    def on_changed(self):
        """Une modification dans un onglet : sauvegarde auto + mise à jour du résumé."""
        self.title.setText(self.project.name)
        self.renamed.emit(self.project.name)
        self.tabs["Accueil"].refresh()
        self.tabs["Montage"].refresh()
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
