"""Page de démarrage : pas d'onglets, juste « Commencer un edit » et les derniers projets."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

from app.core import project
from version import __version__

from .style import asset


class StartPage(QWidget):
    new_edit = pyqtSignal()           # clic sur « Commencer un edit »
    open_project = pyqtSignal(str)    # ouverture d'un projet existant (chemin)

    def __init__(self, parent=None):
        super().__init__(parent)

        logo = QLabel()
        pix = QPixmap(asset("logo.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("AURAEDIT")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Tes edits Valorant, automatiquement.")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_start = QPushButton("COMMENCER UN EDIT")
        self.btn_start.setObjectName("big")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.new_edit.emit)

        self.recent_title = QLabel("Derniers edits")
        self.recent_title.setObjectName("hint")
        self.recent_list = QListWidget()
        self.recent_list.setFixedWidth(460)
        self.recent_list.setMaximumHeight(240)
        self.recent_list.itemClicked.connect(self._open_item)

        btn_open = QPushButton("Ouvrir un autre projet...")
        btn_open.setObjectName("link")
        btn_open.clicked.connect(self._browse)

        version = QLabel(f"version {__version__}")
        version.setObjectName("version")

        center = QVBoxLayout()
        center.setSpacing(14)
        center.addStretch(3)
        center.addWidget(logo)
        center.addWidget(title)
        center.addWidget(subtitle)
        center.addSpacing(36)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_start)
        row.addStretch(1)
        center.addLayout(row)
        center.addSpacing(36)
        for w in (self.recent_title, self.recent_list, btn_open):
            center.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)
        center.addStretch(4)
        center.addWidget(version, alignment=Qt.AlignmentFlag.AlignRight)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.addLayout(center)
        self.refresh()

    def refresh(self):
        """Recharge la liste des derniers projets (cachée s'il n'y en a pas)."""
        self.recent_list.clear()
        recents = project.load_recents()
        for path in recents:
            item = QListWidgetItem(Path(path).stem)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.recent_list.addItem(item)
        self.recent_title.setVisible(bool(recents))
        self.recent_list.setVisible(bool(recents))

    def _open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_project.emit(path)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(project.projects_dir()),
                                              "Projet AuraEdit (*.auraedit)")
        if path:
            self.open_project.emit(path)
