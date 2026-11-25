"""Onglet « Reproduire » : copier un edit fini (toutes les fonctions de la fenêtre Reproduire, dans un onglet)."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class ReproduceTab(QWidget):
    changed = pyqtSignal()
    finished_ok = pyqtSignal(bool)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.page = None
        self._new()

    def _new(self):
        from ..reproduce_dialog import ReproduceDialog
        if self.page is not None:
            self.lay.removeWidget(self.page)
            self.page.deleteLater()
        self.page = ReproduceDialog(self.project, self)
        self.page.setWindowFlags(Qt.WindowType.Widget)          # la fenêtre devient une page de l'onglet
        self.page.reject = lambda: None                         # Échap ne ferme pas la page
        self.page.finished.connect(self._done)
        self.lay.addWidget(self.page)
        self.page.show()

    def _done(self, result):
        ok = bool(result)
        self.changed.emit()
        self.finished_ok.emit(ok)
        self._new()                                             # prêt pour reprendre / un autre edit

    def stop(self):
        """Fermeture de l'app : arrête les analyses et sauvegarde l'edit en cours."""
        if self.page is not None:
            try:
                self.page.finished.disconnect(self._done)
                self.page.done(0)
            except (RuntimeError, TypeError):
                pass
