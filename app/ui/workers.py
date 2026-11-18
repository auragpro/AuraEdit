"""Tâches lancées en arrière-plan pour que la fenêtre ne se fige jamais.

Règle de Qt : on ne touche JAMAIS à l'interface depuis un thread. Les threads
envoient des signaux ; Qt les livre à la fenêtre dans le thread principal.
"""
from PyQt6.QtCore import QThread, pyqtSignal

from app.core import project, updater


class UpdateCheckThread(QThread):
    """Demande à GitHub s'il existe une nouvelle version."""
    found = pyqtSignal(object)      # UpdateInfo
    nothing = pyqtSignal()          # à jour, ou pas d'internet

    def run(self):
        try:
            info = updater.check_for_update()
        except Exception:           # une MAJ ratée ne doit jamais empêcher de lancer l'app
            info = None
        if info:
            self.found.emit(info)
        else:
            self.nothing.emit()


class DownloadThread(QThread):
    """Télécharge la mise à jour."""
    progress = pyqtSignal(object, object)   # reçu, total (octets)
    done = pyqtSignal(str)                  # chemin du fichier téléchargé
    failed = pyqtSignal(str)                # message d'erreur

    def __init__(self, info, dest, parent=None):
        super().__init__(parent)
        self.info = info
        self.dest = dest
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = updater.download(self.info, self.dest,
                                    progress=lambda r, t: self.progress.emit(r, t),
                                    is_cancelled=lambda: self._cancel)
            self.done.emit(str(path))
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Erreur inattendue : {e}")


class ScanThread(QThread):
    """Cherche les vidéos dans des dossiers du PC."""
    done = pyqtSignal(list)

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = folders
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = project.scan_videos(self.folders, is_cancelled=lambda: self._cancel)
        except Exception:
            result = []
        self.done.emit(result)
