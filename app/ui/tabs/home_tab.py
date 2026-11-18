"""Onglet Accueil : résumé du projet et ce qu'il reste à faire."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ..widgets import page_header


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

        self.btn_render = QPushButton("Générer l'edit")
        self.btn_render.setObjectName("primary")
        self.btn_render.setEnabled(False)
        self.btn_render.setToolTip("Le montage automatique arrive à la prochaine étape.")
        hint = QLabel("La génération de l'edit (montage + kunais + export MP4) arrive à la prochaine étape.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Accueil", "Remplis chaque onglet à gauche. Tout est sauvegardé automatiquement."))
        lay.addWidget(QLabel("Nom de l'edit"))
        lay.addWidget(self.name)
        lay.addWidget(card)
        lay.addWidget(self.missing)
        lay.addStretch(1)
        lay.addWidget(self.btn_render)
        lay.addWidget(hint)
        self.refresh()

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
        missing = self.project.missing_files()
        self.missing.setVisible(bool(missing))
        if missing:
            self.missing.setText(f"⚠ {len(missing)} fichier(s) introuvable(s) (déplacé(s) ou supprimé(s)). "
                                 "Vérifie les onglets marqués.")
