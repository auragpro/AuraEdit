"""Petits composants réutilisés dans plusieurs onglets."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)


def page_header(title, hint):
    """Titre + phrase d'aide en haut de chaque onglet."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 8)
    t = QLabel(title)
    t.setObjectName("h1")
    h = QLabel(hint)
    h.setObjectName("hint")
    h.setWordWrap(True)
    lay.addWidget(t)
    lay.addWidget(h)
    return box


def file_filter(label, extensions):
    return f"{label} ({' '.join('*' + e for e in sorted(extensions))})"


class FilePicker(QFrame):
    """Choix d'UN fichier : bouton « Choisir... », « Retirer », ou glisser-déposer."""
    changed = pyqtSignal(object)        # chemin (str) ou None

    def __init__(self, label, extensions, kind_label, optional=False, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.extensions = {e.lower() for e in extensions}
        self.kind_label = kind_label
        self.path = None
        self.setAcceptDrops(True)

        title = QLabel(label + ("  (optionnel)" if optional else ""))
        title.setStyleSheet("font-weight: 700;")
        self.name = QLabel()
        self.name.setWordWrap(True)
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_choose = QPushButton("Choisir...")
        self.btn_clear = QPushButton("Retirer")
        self.btn_choose.clicked.connect(self.browse)
        self.btn_clear.clicked.connect(lambda: self.set_path(None, notify=True))

        row = QHBoxLayout()
        row.addWidget(self.name, 1)
        row.addWidget(self.btn_choose)
        row.addWidget(self.btn_clear)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.addWidget(title)
        lay.addLayout(row)
        self.set_path(None)

    def accepts(self, path):
        return Path(path).suffix.lower() in self.extensions

    def set_path(self, path, notify=False):
        self.path = path or None
        self.name.setToolTip(self.path or "")
        if self.path is None:
            self.name.setText("Aucun fichier — clique sur « Choisir... » ou glisse un fichier ici")
            self.name.setObjectName("hint")
        elif not Path(self.path).is_file():
            self.name.setText(f"⚠ Introuvable : {self.path}")
            self.name.setObjectName("ko")
        else:
            self.name.setText(Path(self.path).name)
            self.name.setObjectName("")
        self.name.style().unpolish(self.name)      # applique le nouveau style
        self.name.style().polish(self.name)
        self.btn_clear.setEnabled(self.path is not None)
        if notify:
            self.changed.emit(self.path)

    def browse(self):
        start = str(Path(self.path).parent) if self.path else ""
        path, _ = QFileDialog.getOpenFileName(self, f"Choisir {self.kind_label}", start,
                                              file_filter(self.kind_label.capitalize(), self.extensions))
        if path:
            self.set_path(path, notify=True)

    # glisser-déposer depuis l'explorateur Windows
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() and self.accepts(urls[0].toLocalFile()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if self.accepts(path):
            self.set_path(path, notify=True)
        else:
            QMessageBox.warning(self, "Fichier refusé", f"Ce n'est pas {self.kind_label}.")
