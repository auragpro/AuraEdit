"""Fenêtre principale : vérification MAJ -> page de démarrage -> mode édition."""
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QLabel, QMainWindow, QMessageBox, QProgressBar, QStackedWidget,
                             QVBoxLayout, QWidget)

from app.core import project as proj

from .edit_view import EditView
from .start_page import StartPage
from .update_dialog import UpdateDialog
from .workers import UpdateCheckThread


class LoadingPage(QWidget):
    """Écran affiché pendant la vérification des mises à jour (quelques secondes max)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        label = QLabel("Recherche de mises à jour...")
        label.setObjectName("subtitle")
        bar = QProgressBar()
        bar.setRange(0, 0)              # barre animée
        bar.setFixedWidth(260)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lay.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AuraEdit")
        self.resize(1200, 760)
        self.setMinimumSize(980, 640)

        self.stack = QStackedWidget()
        self.loading = LoadingPage()
        self.start_page = StartPage()
        self.start_page.new_edit.connect(self.new_edit)
        self.start_page.open_project.connect(self.open_project)
        self.stack.addWidget(self.loading)
        self.stack.addWidget(self.start_page)
        self.setCentralWidget(self.stack)

        self.edit_view = None
        self.check_thread = None

    # ------------------------------------------------- 1. mises à jour
    def start(self):
        """Appelé juste après l'affichage de la fenêtre."""
        self.stack.setCurrentWidget(self.loading)
        self.check_thread = UpdateCheckThread(self)
        self.check_thread.found.connect(self.on_update_found)
        self.check_thread.nothing.connect(self.show_start)
        self.check_thread.start()

    def on_update_found(self, info):
        UpdateDialog(info, self).exec()     # « Plus tard » ferme la popup et on continue
        self.show_start()

    # ------------------------------------------------- 2. démarrage
    def show_start(self):
        self.start_page.refresh()
        self.stack.setCurrentWidget(self.start_page)
        self.setWindowTitle("AuraEdit")

    # ------------------------------------------------- 3. mode édition
    def new_edit(self):
        try:
            project = proj.Project.new()
        except OSError as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le projet :\n{e}")
            return
        self.open_edit(project)

    def open_project(self, path):
        try:
            project = proj.Project.load(path)
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "Projet illisible",
                                f"Ce projet ne peut pas être ouvert :\n{path}\n\n{e}")
            proj.remove_recent(path)
            self.start_page.refresh()
            return
        self.open_edit(project)
        missing = project.missing_files()
        if missing:
            QMessageBox.information(self, "Fichiers introuvables",
                                    f"{len(missing)} fichier(s) de ce projet ont été déplacés ou supprimés. "
                                    "Ils sont marqués ⚠ dans les onglets.")

    def open_edit(self, project):
        self.close_edit()
        self.edit_view = EditView(project)
        self.edit_view.back_home.connect(self.back_home)
        self.edit_view.renamed.connect(lambda name: self.setWindowTitle(f"AuraEdit — {name}"))
        self.stack.addWidget(self.edit_view)
        self.stack.setCurrentWidget(self.edit_view)   # les onglets apparaissent ici
        self.setWindowTitle(f"AuraEdit — {project.name}")

    def close_edit(self):
        if self.edit_view is not None:
            self.edit_view.shutdown()
            self.stack.removeWidget(self.edit_view)
            self.edit_view.deleteLater()
            self.edit_view = None

    def back_home(self):
        self.close_edit()
        self.show_start()

    # ------------------------------------------------- fermeture
    def closeEvent(self, event):
        self.close_edit()
        if self.check_thread is not None and self.check_thread.isRunning():
            self.check_thread.wait(6000)
        event.accept()
