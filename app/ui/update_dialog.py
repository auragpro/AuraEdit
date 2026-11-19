"""Popup « Nouvelle mise à jour » : [Télécharger et installer] / [Plus tard]."""
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox,
                             QProgressBar, QPushButton, QTextBrowser, QVBoxLayout)

from app.core import updater
from version import __version__

from .workers import DownloadThread


def _mo(n):
    return f"{n / 1_048_576:.1f} Mo"


class UpdateDialog(QDialog):
    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self.thread = None
        self.setWindowTitle("Mise à jour disponible")
        self.setModal(True)
        self.setMinimumWidth(480)

        title = QLabel(f"Nouvelle mise à jour (version {info.version} disponible)")
        title.setObjectName("h1")
        title.setWordWrap(True)
        current = QLabel(f"Ta version : {__version__}")
        current.setObjectName("hint")

        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(info.notes or "_Pas de détails pour cette version._")
        self.notes.setMaximumHeight(180)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("hint")

        self.btn_later = QPushButton("Plus tard")
        self.btn_install = QPushButton("Télécharger et installer")
        self.btn_install.setObjectName("primary")
        self.btn_install.setDefault(True)
        self.btn_later.clicked.connect(self.reject)
        self.btn_install.clicked.connect(self.start)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_later)
        buttons.addWidget(self.btn_install)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addWidget(current)
        lay.addWidget(QLabel("Nouveautés :"))
        lay.addWidget(self.notes)
        lay.addWidget(self.progress)
        lay.addWidget(self.status)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------
    def start(self):
        if not updater.is_frozen():
            # On tourne depuis le code Python : impossible de se remplacer soi-même.
            QDesktopServices.openUrl(QUrl(self.info.page_url))
            self.accept()
            return
        self.btn_install.setEnabled(False)
        self.btn_later.setText("Annuler")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)            # animation « en cours » tant qu'on ne connaît pas la taille
        self.status.setText("Téléchargement...")
        dest = updater.code_download_path() if self.info.kind == "code" else updater.download_path()
        self.thread = DownloadThread(self.info, dest, self)
        self.thread.progress.connect(self.on_progress)
        self.thread.done.connect(self.on_done)
        self.thread.failed.connect(self.on_failed)
        self.thread.start()

    def on_progress(self, received, total):
        if total:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(received * 1000 / total))
            self.status.setText(f"Téléchargement... {_mo(received)} / {_mo(total)}")
        else:
            self.status.setText(f"Téléchargement... {_mo(received)}")

    def on_done(self, path):
        self.status.setText("Installation...")
        try:
            if self.info.kind == "code":
                updater.install_code(path, self.info.version)
            else:
                updater.install(path)
            updater.restart()
        except updater.UpdateError as e:
            self.on_failed(str(e))
            return
        except OSError as e:
            self.on_failed(f"Relance impossible ({e}). Relance AuraEdit à la main.")
            return
        QApplication.quit()                     # la nouvelle version est lancée

    def on_failed(self, message):
        self.progress.setVisible(False)
        self.status.setText("")
        self.btn_install.setEnabled(True)
        self.btn_install.setText("Réessayer")
        self.btn_later.setText("Plus tard")
        if self.isVisible():
            QMessageBox.warning(self, "Mise à jour", message)

    def reject(self):
        """Plus tard / Annuler / croix / Échap : on arrête proprement un téléchargement en cours."""
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(5000)
        super().reject()
