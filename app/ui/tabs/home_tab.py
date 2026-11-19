"""Onglet Accueil : résumé du projet et ce qu'il reste à faire."""
import re
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..widgets import page_header
from ..workers import RenderThread


class HomeTab(QWidget):
    changed = pyqtSignal()
    go_to = pyqtSignal(str)          # demande d'ouvrir un onglet (ex. "Musique")

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project

        self.name = QLineEdit(project.name)
        self.name.setPlaceholderText("Nom de l'edit")
        self.name.editingFinished.connect(self._rename)

        card = QFrame()
        card.setObjectName("card")
        self.card_lay = QVBoxLayout(card)
        self.card_lay.setContentsMargins(18, 16, 18, 16)
        self.card_lay.setSpacing(10)
        self.missing = QLabel()
        self.missing.setObjectName("ko")
        self.missing.setWordWrap(True)

        self.thread = None
        self.btn_render = QPushButton("Générer l'edit (rendu MP4)")
        self.btn_render.setObjectName("primary")
        self.btn_render.clicked.connect(self.render)
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_cancel.hide()
        self.btn_open = QPushButton("Ouvrir le rendu")
        self.btn_open.clicked.connect(self.open_render)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.hide()
        hint = QLabel("Rendu : intro → clips dans l'ordre → outro, sur ta musique, en 1080p 60 i/s. "
                      "Les coupes sont gardées pour ajouter les shakes entre chaque clip ensuite.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.render_status = QLabel()
        self.render_status.setObjectName("hint")
        self.render_status.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.btn_render, 1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_open)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Accueil", "Remplis chaque onglet à gauche. Tout est sauvegardé automatiquement."))
        lay.addWidget(QLabel("Nom de l'edit"))
        lay.addWidget(self.name)
        lay.addWidget(card)
        lay.addWidget(self.missing)
        lay.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(self.bar)
        lay.addWidget(self.render_status)
        lay.addWidget(hint)
        self.refresh()

    # ------------------------------------------------------------ rendu
    def render(self):
        if self.thread is not None and self.thread.isRunning():
            return
        if not self.project.clips:
            QMessageBox.information(self, "Rendu", "Ajoute d'abord des clips dans l'onglet Clips.")
            self.go_to.emit("Clips")
            return
        videos = Path.home() / "Videos"
        base = videos if videos.is_dir() else Path.home()
        name = re.sub(r'[<>:"/\\|?*]', "_", self.project.name)
        out, _ = QFileDialog.getSaveFileName(self, "Enregistrer le rendu", str(base / f"{name}.mp4"),
                                             "Vidéo MP4 (*.mp4)")
        if not out:
            return
        if not out.lower().endswith(".mp4"):
            out += ".mp4"
        self.thread = RenderThread(self.project, out, self)
        self.thread.progress.connect(self._progress)
        self.thread.done.connect(self._done)
        self.thread.failed.connect(self._failed)
        self.btn_render.setEnabled(False)
        self.btn_cancel.show()
        self.bar.setValue(0)
        self.bar.show()
        self.render_status.setText("Rendu en cours...")
        self.thread.start()

    def cancel(self):
        if self.thread is not None:
            self.thread.cancel()

    def _progress(self, frac, text):
        self.bar.setValue(int(frac * 1000))
        self.render_status.setText(text)

    def _end(self):
        self.btn_render.setEnabled(True)
        self.btn_cancel.hide()
        self.bar.hide()

    def _done(self, res):
        self._end()
        self.project.render = res
        n = len(res.get("coupes", []))
        self.render_status.setText(f"✓ Rendu terminé ({res.get('duree', 0):.0f} s, {n} transition(s)) : "
                                   f"{res.get('fichier')}")
        self.changed.emit()
        self.refresh()

    def _failed(self, msg):
        self._end()
        self.render_status.setText("Rendu interrompu.")
        if msg != "Rendu annulé.":
            QMessageBox.warning(self, "Rendu impossible", msg[-1500:])

    def open_render(self):
        f = (self.project.render or {}).get("fichier")
        if f and Path(f).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(f))

    def stop(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(5000)

    def _rename(self):
        name = self.name.text().strip()
        if not name:
            self.name.setText(self.project.name)
            return
        if name != self.project.name:
            self.project.name = name
            self.changed.emit()

    def refresh(self):
        """Met à jour la liste ✓ / ✗ (appelé à chaque modification du projet)."""
        while self.card_lay.count():
            w = self.card_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for label, ok in self.project.checklist():
            btn = QPushButton(("✓  " if ok else "✗  ") + label)
            btn.setObjectName("link")
            btn.setStyleSheet(f"text-align: left; font-size: 15px; color: {'#3ddc97' if ok else '#ff4655'};")
            tab = label.split(" (")[0]
            btn.clicked.connect(lambda _=False, t=tab: self.go_to.emit(t))
            self.card_lay.addWidget(btn)
        f = (self.project.render or {}).get("fichier")
        self.btn_open.setVisible(bool(f and Path(f).is_file()))
        missing = self.project.missing_files()
        self.missing.setVisible(bool(missing))
        if missing:
            self.missing.setText(f"⚠ {len(missing)} fichier(s) introuvable(s) (déplacé(s) ou supprimé(s)). "
                                 "Vérifie les onglets marqués.")
