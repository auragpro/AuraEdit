"""Onglet Clips : trouver les clips Valorant sur le PC, les choisir et les mettre dans l'ordre."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from app.core import project as proj

from ..widgets import file_filter, page_header
from ..workers import ScanThread

ROLE = Qt.ItemDataRole.UserRole


def _item(path):
    p = Path(path)
    text = p.name if p.is_file() else f"⚠ {p.name} (introuvable)"
    item = QListWidgetItem(text)
    item.setData(ROLE, str(path))
    item.setToolTip(str(path))
    return item


class OrderList(QListWidget):
    """Liste qu'on peut réordonner en glissant ; prévient après chaque déplacement."""
    reordered = pyqtSignal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class ClipsTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.scan_thread = None
        self.scanned_once = False
        self.known = set()          # clips déjà listés à gauche

        # --- gauche : clips trouvés
        self.found = QListWidget()
        self.found.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.found.itemDoubleClicked.connect(lambda it: self.add_to_edit([it.data(ROLE)]))
        self.btn_scan = QPushButton("Chercher sur mon PC")
        self.btn_folder = QPushButton("Ajouter un dossier...")
        self.btn_scan.clicked.connect(lambda: self.scan(proj.default_clip_folders()))
        self.btn_folder.clicked.connect(self.pick_folder)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        left = QVBoxLayout()
        left.addWidget(QLabel("Clips trouvés sur ton PC"))
        left.addWidget(self.found, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_scan)
        row.addWidget(self.btn_folder)
        left.addLayout(row)
        left.addWidget(self.status)

        # --- milieu
        self.btn_add = QPushButton("Ajouter  →")
        self.btn_add.setObjectName("primary")
        self.btn_add.clicked.connect(self.add_selected)
        middle = QVBoxLayout()
        middle.addStretch(1)
        middle.addWidget(self.btn_add)
        middle.addStretch(1)

        # --- droite : ordre de l'edit
        self.order = OrderList()
        self.order.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.order.reordered.connect(self.sync)
        self.count = QLabel()
        self.count.setObjectName("hint")
        b_files = QPushButton("Ajouter des fichiers...")
        b_up = QPushButton("Monter")
        b_down = QPushButton("Descendre")
        b_remove = QPushButton("Retirer")
        b_clear = QPushButton("Tout retirer")
        b_files.clicked.connect(self.pick_files)
        b_up.clicked.connect(lambda: self.move(-1))
        b_down.clicked.connect(lambda: self.move(1))
        b_remove.clicked.connect(self.remove_selected)
        b_clear.clicked.connect(self.clear)

        right = QVBoxLayout()
        right.addWidget(QLabel("Ordre de l'edit  (glisse pour réordonner)"))
        right.addWidget(self.order, 1)
        row2 = QHBoxLayout()
        for b in (b_files, b_up, b_down, b_remove, b_clear):
            row2.addWidget(b)
        right.addLayout(row2)
        right.addWidget(self.count)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addLayout(left, 1)
        cols.addLayout(middle)
        cols.addLayout(right, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header("Clips", "Choisis tes clips Valorant (sélection multiple avec Ctrl ou Maj), "
                                           "puis mets-les dans l'ordre de l'edit."))
        lay.addLayout(cols, 1)

        for c in project.clips:
            self.order.addItem(_item(c))
        self._update_count()

    # ---------------------------------------------------------- recherche
    def showEvent(self, event):
        """La 1re fois qu'on ouvre l'onglet, on cherche les clips tout seul."""
        super().showEvent(event)
        if not self.scanned_once:
            self.scanned_once = True
            folders = proj.default_clip_folders()
            if folders:
                self.scan(folders)
            else:
                self.status.setText("Aucun dossier Vidéos trouvé : utilise « Ajouter un dossier... ».")

    def scan(self, folders):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return
        if not folders:
            self.status.setText("Aucun dossier à analyser.")
            return
        self.btn_scan.setEnabled(False)
        self.btn_folder.setEnabled(False)
        self.status.setText("Recherche dans : " + ", ".join(str(f) for f in folders) + "...")
        self.scan_thread = ScanThread([str(f) for f in folders], self)
        self.scan_thread.done.connect(self._scan_done)
        self.scan_thread.start()

    def _scan_done(self, paths):
        new = [p for p in paths if p not in self.known]
        for p in new:
            self.known.add(p)
            self.found.addItem(_item(p))
        self.btn_scan.setEnabled(True)
        self.btn_folder.setEnabled(True)
        self.status.setText(f"{len(new)} nouveau(x) clip(s) trouvé(s), {self.found.count()} au total."
                            if paths else "Aucune vidéo trouvée ici.")

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier de clips")
        if folder:
            self.scan([folder])

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Ajouter des clips", "",
                                                file_filter("Vidéos", proj.VIDEO_EXT))
        if files:
            self.add_to_edit(files)

    # -------------------------------------------------------------- ordre
    def add_selected(self):
        paths = [it.data(ROLE) for it in self.found.selectedItems()]
        if not paths:
            self.status.setText("Sélectionne d'abord des clips à gauche.")
            return
        # garder l'ordre d'affichage, pas l'ordre de clic
        paths.sort(key=lambda p: next(i for i in range(self.found.count())
                                      if self.found.item(i).data(ROLE) == p))
        self.add_to_edit(paths)

    def add_to_edit(self, paths):
        current = set(self.project.clips)
        added = 0
        for p in paths:
            if p and p not in current:
                self.order.addItem(_item(p))
                current.add(p)
                added += 1
        skipped = len(paths) - added
        if skipped:
            self.status.setText(f"{skipped} clip(s) déjà dans l'edit, ignoré(s).")
        self.sync()

    def move(self, step):
        rows = sorted(self.order.row(it) for it in self.order.selectedItems())
        if not rows:
            return
        if step < 0 and rows[0] == 0 or step > 0 and rows[-1] == self.order.count() - 1:
            return
        for r in (rows if step < 0 else reversed(rows)):
            item = self.order.takeItem(r)
            self.order.insertItem(r + step, item)
            item.setSelected(True)
        self.sync()

    def remove_selected(self):
        for it in self.order.selectedItems():
            self.order.takeItem(self.order.row(it))
        self.sync()

    def clear(self):
        self.order.clear()
        self.sync()

    def sync(self, *args):
        """Recopie l'ordre affiché dans le projet, puis prévient (sauvegarde auto)."""
        self.project.clips = [self.order.item(i).data(ROLE) for i in range(self.order.count())]
        self._update_count()
        self.changed.emit()

    def _update_count(self):
        n = self.order.count()
        self.count.setText(f"{n} clip(s) dans l'edit" if n else "Aucun clip dans l'edit pour l'instant.")

    def stop(self):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait(3000)
