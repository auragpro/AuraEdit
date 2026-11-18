"""Point d'entrée d'AuraEdit.  Lancer :  python main.py"""
import sys
import traceback
from datetime import datetime

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.core import project, updater
from app.ui.main_window import MainWindow
from app.ui.style import STYLESHEET, asset
from version import APP_NAME, __version__


def install_error_handler():
    """Au lieu de fermer brutalement, une erreur imprévue est affichée et notée dans un fichier."""
    def handler(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log = None
        try:
            log = project.config_dir() / "erreurs.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} — v{__version__} ===\n{text}")
        except OSError:
            pass
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "Erreur inattendue",
                                 f"Une erreur est survenue :\n{exc}\n\n"
                                 f"Détails enregistrés dans :\n{log}")
        else:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = handler


def set_windows_app_id():
    """Pour que Windows affiche le logo d'AuraEdit dans la barre des tâches."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("auragpro.AuraEdit")
        except Exception:
            pass


def main():
    updater.cleanup_leftovers()          # supprime l'ancienne version après une MAJ
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(asset("logo.ico")))
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)
    install_error_handler()

    window = MainWindow()
    window.show()
    window.start()                       # vérifie les MAJ puis affiche la page de démarrage
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
