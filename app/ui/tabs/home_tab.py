"""Onglet Accueil : résumé du projet et ce qu'il reste à faire."""
import re
from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QComboBox, QSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
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
        # --- réglages d'export
        from app.core import export_cfg
        self.ecfg = export_cfg.load()
        self.e_res = QComboBox()
        self.e_res.addItems(list(export_cfg.RESOLUTIONS))
        self.e_res.setCurrentText(self.ecfg["resolution"])
        self.e_fps = QComboBox()
        self.e_fps.addItems([f"{f} i/s" for f in export_cfg.FPS_CHOICES])
        self.e_fps.setCurrentText(f"{self.ecfg['fps']} i/s")
        self.e_bit = QSpinBox()
        self.e_bit.setRange(2, 300)
        self.e_bit.setSuffix(" Mb/s")
        self.e_bit.setValue(self.ecfg["debit"])
        self.e_bit.setToolTip("Débit vidéo. 1080p 60 i/s : 40–80 Mb/s = très bonne qualité. 4K : 100 Mb/s et plus.")
        self.e_enc = QComboBox()
        self.e_enc.addItems(list(export_cfg.PRESETS))
        self.e_enc.setCurrentText(self.ecfg["encodage"])
        for w in (self.e_res, self.e_fps, self.e_enc):
            w.currentTextChanged.connect(self._save_export)
        self.e_bit.valueChanged.connect(self._save_export)
        erow = QHBoxLayout()
        for lab, w in (("Résolution", self.e_res), ("Images/s", self.e_fps), ("Débit", self.e_bit),
                       ("Encodage", self.e_enc)):
            l = QLabel(lab)
            l.setObjectName("hint")
            erow.addWidget(l)
            erow.addWidget(w)
            erow.addSpacing(10)
        erow.addStretch(1)

        hint = QLabel("Rendu : intro → clips dans l'ordre → outro, sur ta musique, avec les réglages d'export ci-dessus. "
                      "Les shakes (onglet Montage → Shake) sont posés sur chaque coupe.")
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
        exp = QLabel("Qualité de l'export")
        exp.setStyleSheet("font-weight: 600;")
        lay.addWidget(exp)
        lay.addLayout(erow)
        lay.addLayout(row)
        lay.addWidget(self.bar)
        lay.addWidget(self.render_status)
        lay.addWidget(hint)
        self.refresh()

    # ------------------------------------------------------------ rendu
    def render(self, skip_confirm=False):
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
        try:                                       # shakes posés automatiquement : on confirme coupe par coupe
            if skip_confirm:
                raise StopIteration
            from app.core import shake
            from ..shake_cuts_dialog import ShakeCutsDialog, cut_rows
            rows, over = cut_rows(self.project)
            if any(c is not None for c in shake.cut_cfgs(self.project.shakes, len(rows), over)):
                if not ShakeCutsDialog(self.project, self, confirm=True).exec():
                    return
                self.changed.emit()
        except Exception:                          # noqa: BLE001
            pass
        self.thread = RenderThread(self.project, out, self, export=dict(self.ecfg))
        self.thread.progress.connect(self._progress)
        self.thread.done.connect(self._done)
        self.thread.failed.connect(self._failed)
        self.btn_render.setEnabled(False)
        self.btn_cancel.show()
        self.bar.setValue(0)
        self.bar.show()
        self.render_status.setText("Rendu en cours...")
        self.thread.start()

    def _save_export(self, *_):
        from app.core import export_cfg
        self.ecfg = export_cfg.clean({"resolution": self.e_res.currentText(),
                                      "fps": int(self.e_fps.currentText().split()[0]),
                                      "debit": self.e_bit.value(), "encodage": self.e_enc.currentText()})
        export_cfg.save(self.ecfg)

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
