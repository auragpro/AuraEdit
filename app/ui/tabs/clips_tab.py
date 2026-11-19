"""Onglet Clips : dossiers de clips (un par couteau), kunais et dash à gauche, ordre de l'edit à droite."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QHBoxLayout, QInputDialog,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from app.core import project as proj

from ..widgets import file_filter, page_header
from ..workers import ScanThread

ROLE = Qt.ItemDataRole.UserRole
FOUND = "Trouvés sur le PC"
ROLE_DIR = Qt.ItemDataRole.UserRole.value + 1   # nom du dossier sur les lignes « dossier »
MODES = ("Clips", "Kunai", "Dash")


def _name(path):
    p = Path(path)
    return p.name if p.is_file() else f"⚠ {p.name} (introuvable)"


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
        self.found_paths = []                       # clips trouvés par la recherche (non sauvegardés)
        self.folders = proj.load_clip_folders()     # {couteau: [clips]}
        self.mode = "Clips"

        # --- gauche : sélecteur Clips / Kunai / Dash
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self.mode_btns = {}
        for m in MODES:
            b = QPushButton(m)
            b.setCheckable(True)
            b.setChecked(m == self.mode)
            b.clicked.connect(lambda _=False, mm=m: self.set_mode(mm))
            self.mode_group.addButton(b)
            self.mode_btns[m] = b
            mode_row.addWidget(b)
        self._style_modes()

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._double)

        self.btn_new = QPushButton("Nouveau dossier (couteau)...")
        self.btn_fill = QPushButton("Ajouter des clips au dossier...")
        self.btn_put = QPushButton("Mettre dans un dossier...")
        self.btn_import = QPushButton("Importer un dossier du PC...")
        self.btn_scan = QPushButton("Chercher sur mon PC")
        self.btn_del = QPushButton("Supprimer")
        self.btn_new.clicked.connect(self.new_folder)
        self.btn_fill.clicked.connect(self.fill_folder)
        self.btn_put.clicked.connect(self.put_in_folder)
        self.btn_import.clicked.connect(self.import_folder)
        self.btn_scan.clicked.connect(lambda: self.scan(proj.default_clip_folders()))
        self.btn_del.clicked.connect(self.delete_selected)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        left = QVBoxLayout()
        left.addLayout(mode_row)
        left.addWidget(self.tree, 1)
        r1 = QHBoxLayout()
        r1.addWidget(self.btn_new)
        r1.addWidget(self.btn_fill)
        r2 = QHBoxLayout()
        r2.addWidget(self.btn_put)
        r2.addWidget(self.btn_import)
        r3 = QHBoxLayout()
        r3.addWidget(self.btn_scan)
        r3.addWidget(self.btn_del)
        for r in (r1, r2, r3):
            left.addLayout(r)
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
        b_remap = QPushButton("⏱ Time remap...")
        b_remap.clicked.connect(self.remap_selected)
        self.order.itemDoubleClicked.connect(lambda it: self.open_remap([it.data(ROLE)]))
        b_up = QPushButton("Monter")
        b_down = QPushButton("Descendre")
        b_remove = QPushButton("Retirer")
        b_clear = QPushButton("Tout retirer")
        b_up.clicked.connect(lambda: self.move(-1))
        b_down.clicked.connect(lambda: self.move(1))
        b_remove.clicked.connect(self.remove_selected)
        b_clear.clicked.connect(self.clear)

        right = QVBoxLayout()
        right.addWidget(QLabel("Ordre de l'edit  (glisse pour réordonner)"))
        right.addWidget(self.order, 1)
        row2 = QHBoxLayout()
        for b in (b_remap, b_up, b_down, b_remove, b_clear):
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
        lay.addWidget(page_header("Clips", "Range tes clips dans des dossiers (un par couteau). En haut à gauche, "
                                           "choisis ce que tu ajoutes : Clips, Kunai ou Dash."))
        lay.addLayout(cols, 1)

        for c in project.clips:
            self.order.addItem(self._order_item(c))
        self.refresh_left()
        self._update_count()

    # ---------------------------------------------------------- affichage
    def _style_modes(self):
        for m, b in self.mode_btns.items():
            b.setObjectName("primary" if m == self.mode else "")
            b.style().unpolish(b)
            b.style().polish(b)

    def set_mode(self, mode):
        self.mode = mode
        self._style_modes()
        clips = mode == "Clips"
        for b in (self.btn_new, self.btn_fill, self.btn_put, self.btn_import, self.btn_scan):
            b.setVisible(clips)
        self.btn_del.setVisible(clips)
        self.refresh_left()

    def _label_of(self, path):
        """Petit préfixe dans l'ordre de l'edit : [couteau], Kunai, Dash."""
        for name, st in (("Kunai", self.project.kunai), ("Dash", self.project.dash)):
            if path in st.gauche:
                return f"{name} gauche"
            if path in st.droite:
                return f"{name} droite"
        for name, clips in self.folders.items():
            if path in clips:
                return name
        return None

    def _order_item(self, path):
        tag = self._label_of(path)
        mark = "⏱ " if path in self.project.remaps else ""
        item = QListWidgetItem(mark + (f"[{tag}]  " if tag else "") + _name(path))
        item.setData(ROLE, str(path))
        item.setToolTip(str(path))
        return item

    def _clip_child(self, parent, path):
        child = QTreeWidgetItem(parent, [_name(path)])
        child.setData(0, ROLE, str(path))
        child.setToolTip(0, str(path))
        return child

    def refresh_left(self):
        """Redessine la liste de gauche selon le mode choisi."""
        self.tree.clear()
        if self.mode == "Clips":
            for name in sorted(self.folders, key=str.lower):
                top = QTreeWidgetItem(self.tree, [f"🔪 {name}  ({len(self.folders[name])})"])
                top.setData(0, ROLE_DIR, name)
                for c in self.folders[name]:
                    self._clip_child(top, c)
            if self.found_paths:
                top = QTreeWidgetItem(self.tree, [f"🔎 {FOUND}  ({len(self.found_paths)})"])
                top.setData(0, ROLE_DIR, FOUND)
                for c in self.found_paths:
                    self._clip_child(top, c)
            if not self.folders and not self.found_paths:
                self.status.setText("Crée un dossier par couteau avec « Nouveau dossier », puis ajoute ses clips.")
        else:
            st = self.project.kunai if self.mode == "Kunai" else self.project.dash
            videos = st.videos
            for side, icon in (("gauche", "✋"), ("droite", "🤚")):
                lst = getattr(st, side)
                top = QTreeWidgetItem(self.tree, [f"{icon} {self.mode} main {side}  ({len(lst)})"])
                top.setData(0, ROLE_DIR, f"{self.mode} {side}")
                for v in lst:
                    self._clip_child(top, v)
            self.status.setText("" if videos else f"Aucune vidéo : ajoute-les dans l'onglet {self.mode}.")
        self.tree.expandAll()
        for i in range(self.order.count()):       # met à jour les préfixes
            it = self.order.item(i)
            it.setText(self._order_item(it.data(ROLE)).text())

    def _selected_paths(self):
        """Clips sélectionnés ; un dossier sélectionné = tous ses clips."""
        out = []
        for it in self.tree.selectedItems():
            if it.data(0, ROLE):
                out.append(it.data(0, ROLE))
            else:
                out += [it.child(i).data(0, ROLE) for i in range(it.childCount())]
        seen = set()
        return [p for p in out if not (p in seen or seen.add(p))]

    def _selected_folder(self):
        for it in self.tree.selectedItems():
            top = it if it.data(0, ROLE_DIR) else it.parent()
            if top is not None and top.data(0, ROLE_DIR) in self.folders:
                return top.data(0, ROLE_DIR)
        return None

    def _double(self, item, _col):
        if item.data(0, ROLE):
            self.add_to_edit([item.data(0, ROLE)])

    # ----------------------------------------------------------- dossiers
    def _save_folders(self):
        proj.save_clip_folders(self.folders)
        self.refresh_left()

    def new_folder(self):
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du couteau (ex. Kuronami, Reaver...) :")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.folders or name == FOUND:
            self.status.setText(f"Le dossier « {name} » existe déjà.")
            return
        self.folders[name] = []
        self._save_folders()
        self.status.setText(f"Dossier « {name} » créé. Ajoute-lui des clips.")

    def _ask_folder(self, title):
        names = sorted(self.folders, key=str.lower)
        if not names:
            self.status.setText("Crée d'abord un dossier (couteau).")
            return None
        current = self._selected_folder()
        name, ok = QInputDialog.getItem(self, title, "Dossier :", names,
                                        names.index(current) if current in names else 0, False)
        return name if ok else None

    def _add_to_folder(self, name, paths):
        clips = self.folders[name]
        new = [p for p in paths if p not in clips]
        clips += new
        self._save_folders()
        self.status.setText(f"{len(new)} clip(s) ajouté(s) au dossier « {name} ».")

    def fill_folder(self):
        name = self._selected_folder() or self._ask_folder("Ajouter des clips")
        if not name:
            return
        files, _ = QFileDialog.getOpenFileNames(self, f"Clips pour « {name} »", "",
                                                file_filter("Vidéos", proj.VIDEO_EXT))
        if files:
            self._add_to_folder(name, files)

    def put_in_folder(self):
        paths = self._selected_paths()
        if not paths:
            self.status.setText("Sélectionne d'abord des clips.")
            return
        name = self._ask_folder("Mettre dans un dossier")
        if name:
            self._add_to_folder(name, paths)

    def import_folder(self):
        """Un dossier du PC : chaque sous-dossier devient un couteau (ou le dossier lui-même)."""
        folder = QFileDialog.getExistingDirectory(self, "Dossier de clips (un sous-dossier par couteau)")
        if not folder:
            return
        root = Path(folder)
        subs = [d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        groups = {d.name: d for d in subs} or {root.name: root}
        total = 0
        for name, d in groups.items():
            vids = proj.scan_videos([d])
            if not vids:
                continue
            clips = self.folders.setdefault(name, [])
            new = [v for v in vids if v not in clips]
            clips += new
            total += len(new)
        self._save_folders()
        self.status.setText(f"{total} clip(s) importé(s) dans {len(groups)} dossier(s).")

    def delete_selected(self):
        """Supprime les dossiers sélectionnés, ou retire des clips d'un dossier (les fichiers restent sur le PC)."""
        items = self.tree.selectedItems()
        if not items:
            return
        folders = [it.data(0, ROLE_DIR) for it in items if it.data(0, ROLE_DIR) in self.folders]
        if folders and QMessageBox.question(
                self, "Supprimer", f"Supprimer {len(folders)} dossier(s) ? (tes vidéos restent sur le PC)"
        ) != QMessageBox.StandardButton.Yes:
            return
        for f in folders:
            self.folders.pop(f, None)
        for it in items:
            p, parent = it.data(0, ROLE), it.parent()
            if p and parent is not None:
                name = parent.data(0, ROLE_DIR)
                if name in self.folders and p in self.folders[name]:
                    self.folders[name].remove(p)
                elif name == FOUND and p in self.found_paths:
                    self.found_paths.remove(p)
        self._save_folders()

    # ---------------------------------------------------------- recherche
    def showEvent(self, event):
        super().showEvent(event)
        if not self.scanned_once and not self.folders:
            self.scanned_once = True
            folders = proj.default_clip_folders()
            if folders:
                self.scan(folders)

    def scan(self, folders):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return
        if not folders:
            self.status.setText("Aucun dossier Vidéos trouvé : utilise « Importer un dossier du PC ».")
            return
        self.btn_scan.setEnabled(False)
        self.status.setText("Recherche des clips sur ton PC...")
        self.scan_thread = ScanThread([str(f) for f in folders], self)
        self.scan_thread.done.connect(self._scan_done)
        self.scan_thread.start()

    def _scan_done(self, paths):
        known = set(self.found_paths)
        new = [p for p in paths if p not in known]
        self.found_paths += new
        self.btn_scan.setEnabled(True)
        self.refresh_left()
        self.status.setText(f"{len(new)} clip(s) trouvé(s). Range-les avec « Mettre dans un dossier »."
                            if paths else "Aucune vidéo trouvée.")

    # -------------------------------------------------------------- ordre
    def add_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.status.setText("Sélectionne d'abord des clips (ou un dossier entier) à gauche.")
            return
        self.add_to_edit(paths)

    def add_to_edit(self, paths):
        current = set(self.project.clips)
        added = 0
        new = []
        for p in paths:
            if p and p not in current:
                self.order.addItem(self._order_item(p))
                current.add(p)
                added += 1
                new.append(p)
        skipped = len(paths) - added
        if skipped:
            self.status.setText(f"{skipped} clip(s) déjà dans l'edit, ignoré(s).")
        self.sync()
        if self.mode == "Clips" and new:
            self.open_remap(new)

    # ------------------------------------------------------- time remap
    def _knife_of(self, path):
        for name, clips in self.folders.items():
            if path in clips:
                return name
        return None

    def open_remap(self, paths):
        """Ouvre la page Time remap pour chaque clip (couteau, keyframes, courbes)."""
        from ..timeremap_dialog import TimeRemapDialog
        for p in paths:
            if p in self.project.kunai.videos or p in self.project.dash.videos:
                continue
            dlg = TimeRemapDialog(self.project, p, self._knife_of(p), list(self.folders), self)
            dlg.exec()
            self.refresh_left()
            self.changed.emit()
            if dlg.skip_all:
                break

    def remap_selected(self):
        paths = [it.data(ROLE) for it in self.order.selectedItems()]
        if not paths:
            self.status.setText("Sélectionne un clip dans l'ordre de l'edit (à droite).")
            return
        self.open_remap(paths)

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
