"""Onglet Clips : dossiers de clips (un par couteau), kunais et dash à gauche, ordre de l'edit à droite."""
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QFrame, QLineEdit, QListView, QProgressDialog, QStackedWidget
from PyQt6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QHBoxLayout, QInputDialog,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from app.core import project as proj

from ..widgets import file_filter, page_header

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


CARD_W, CARD_H = 150, 84
NEW = "__nouveau__"
GRID_CSS = """
QListWidget#knives { background: transparent; border: none; }
QListWidget#knives::item { background: #1b2733; border: 2px solid #243342; border-radius: 12px;
                           margin: 5px; padding: 6px 4px 8px 4px; color: white; font-weight: 600; }
QListWidget#knives::item:hover { border: 2px solid #4a5a6a; }
QListWidget#knives::item:selected { background: #243342; border: 2px solid #e8ecef; }
"""


def _rounded(pix, w=CARD_W, h=CARD_H, r=10):
    """Image du couteau recadrée en carte arrondie."""
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.setClipPath(path)
    p.fillRect(out.rect(), QColor("#11181f"))
    if pix is not None and not pix.isNull():
        sc = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((w - sc.width()) // 2, (h - sc.height()) // 2, sc)
    p.end()
    return out


def _symbol(text, size=30):
    out = _rounded(None)
    p = QPainter(out)
    f = QFont()
    f.setPointSize(size)
    p.setFont(f)
    p.setPen(QColor("#c8d0d8"))
    p.drawText(out.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return out


class DropList(QListWidget):
    """Liste qui accepte les vidéos (ou dossiers) glissées depuis l'Explorateur Windows."""
    files_dropped = pyqtSignal(list, object)     # chemins des vidéos, élément sous la souris (ou None)

    def __init__(self, hint="", parent=None):
        super().__init__(parent)
        self.hint = hint
        self._over = False
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    @staticmethod
    def _videos(event):
        out = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.is_dir():
                out += proj.scan_videos([p])
            elif p.suffix.lower() in proj.VIDEO_EXT:
                out.append(str(p))
        return out

    def _set_over(self, on):
        self._over = on
        self.setStyleSheet("QListWidget { border: 2px dashed #ff4655; }" if on else "")
        if self.objectName() == "knives":
            self.setStyleSheet(GRID_CSS + ("QListWidget#knives { border: 2px dashed #ff4655; }" if on else ""))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_over(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self._set_over(False)
            item = self.itemAt(event.position().toPoint())
            files = self._videos(event)
            event.acceptProposedAction()
            self.files_dropped.emit(files, item)
        else:
            super().dropEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0 and self.hint:
            p = QPainter(self.viewport())
            p.setPen(QColor("#6b7785"))
            f = p.font()
            f.setPointSize(11)
            p.setFont(f)
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.hint)
            p.end()


class ClipsTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.folders = proj.load_clip_folders()     # {couteau: [clips]}
        self.mode = "Clips"
        self.knife = None                           # couteau ouvert (page de ses clips)

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

        # page 1 : grille des couteaux
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrer les couteaux...")
        self.filter.textChanged.connect(self._filter)
        self.grid = DropList()
        self.grid.setObjectName("knives")
        self.grid.files_dropped.connect(self._dropped_on_grid)
        self.grid.setStyleSheet(GRID_CSS)
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(CARD_W, CARD_H))
        self.grid.setGridSize(QSize(CARD_W + 22, CARD_H + 52))
        self.grid.setWordWrap(False)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.itemClicked.connect(self._card_clicked)
        b_import = QPushButton("Importer un dossier du PC...")
        b_import.setToolTip("Chaque sous-dossier devient un couteau.")
        b_import.clicked.connect(self.import_folder)
        grid_page = QWidget()
        gl = QVBoxLayout(grid_page)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(self.filter)
        gl.addWidget(self.grid, 1)
        gl.addWidget(b_import)

        # page 2 : les clips d'un couteau
        b_back = QPushButton("←  Couteaux")
        b_back.setObjectName("link")
        b_back.clicked.connect(self.close_knife)
        self.knife_img = QLabel()
        self.knife_img.setFixedSize(CARD_W, CARD_H)
        self.knife_title = QLabel()
        self.knife_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        b_img = QPushButton("Image du couteau...")
        b_img.clicked.connect(self.pick_knife_image)
        b_fill = QPushButton("Ajouter des clips...  (ou glisse-les dans la liste)")
        b_fill.setObjectName("primary")
        b_fill.clicked.connect(self.fill_folder)
        b_rm = QPushButton("Retirer")
        b_rm.clicked.connect(self.remove_from_knife)
        b_delk = QPushButton("Supprimer le couteau")
        b_delk.clicked.connect(self.delete_knife)
        self.clips = DropList("Glisse tes clips ici\n(depuis l'Explorateur Windows)")
        self.clips.files_dropped.connect(self._dropped_on_knife)
        self.clips.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.clips.itemDoubleClicked.connect(lambda it: self.add_to_edit([it.data(ROLE)]))
        info = QVBoxLayout()
        info.addWidget(self.knife_title)
        info.addWidget(b_img)
        info.addStretch(1)
        top = QHBoxLayout()
        top.addWidget(self.knife_img)
        top.addLayout(info, 1)
        krow = QVBoxLayout()
        krow.addWidget(b_fill)
        krow2 = QHBoxLayout()
        krow2.addWidget(b_rm)
        krow2.addWidget(b_delk)
        krow.addLayout(krow2)
        knife_page = QWidget()
        kl = QVBoxLayout(knife_page)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(b_back, alignment=Qt.AlignmentFlag.AlignLeft)
        kl.addLayout(top)
        kl.addWidget(self.clips, 1)
        kl.addLayout(krow)

        # page 3 : kunai / dash
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._double)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(grid_page)
        self.left_stack.addWidget(knife_page)
        self.left_stack.addWidget(self.tree)

        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        left = QVBoxLayout()
        left.addLayout(mode_row)
        left.addWidget(self.left_stack, 1)
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
        cols.addLayout(left, 3)
        cols.addLayout(middle)
        cols.addLayout(right, 2)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header("Clips", "Choisis un couteau pour voir ses clips. En haut à gauche, "
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
        used = path in self.project.clips
        child = QTreeWidgetItem(parent, [("✓ déjà dans l'edit — " if used else "") + _name(path)])
        child.setData(0, ROLE, str(path))
        child.setToolTip(0, str(path))
        if used:                                   # un clip ne sert qu'une fois dans l'edit
            child.setForeground(0, QColor("#6b7785"))
        return child

    def _knife_pixmap(self, name):
        from app.core import timeremap
        k = timeremap.load()["couteaux"].get(name) or {}
        img = k.get("carte") or k.get("image")
        pix = QPixmap(img) if img and Path(img).is_file() else None
        return _rounded(pix) if pix is not None and not pix.isNull() else _symbol("🔪")

    def refresh_left(self):
        """Redessine la partie gauche selon le mode choisi."""
        if self.mode == "Clips":
            self._fill_grid()
            if self.knife in self.folders:
                self._fill_knife()
                self.left_stack.setCurrentIndex(1)
            else:
                self.knife = None
                self.left_stack.setCurrentIndex(0)
                self.status.setText("" if self.folders else
                                    "Crée une carte par couteau avec « Nouveau couteau », puis ajoute ses clips.")
        else:
            self.tree.clear()
            st = self.project.kunai if self.mode == "Kunai" else self.project.dash
            for side, icon in (("gauche", "✋"), ("droite", "🤚")):
                lst = getattr(st, side)
                top = QTreeWidgetItem(self.tree, [f"{icon} {self.mode} main {side}  ({len(lst)})"])
                top.setData(0, ROLE_DIR, f"{self.mode} {side}")
                for v in lst:
                    self._clip_child(top, v)
            self.tree.expandAll()
            self.left_stack.setCurrentIndex(2)
            self.status.setText("" if st.videos else f"Aucune vidéo : ajoute-les dans l'onglet {self.mode}.")
        for i in range(self.order.count()):       # met à jour les préfixes
            it = self.order.item(i)
            it.setText(self._order_item(it.data(ROLE)).text())

    def _fill_grid(self):
        self.grid.clear()
        new = QListWidgetItem(QIcon(_symbol("＋", 34)), "Nouveau couteau")
        new.setData(ROLE_DIR, NEW)
        new.setSizeHint(QSize(CARD_W + 16, CARD_H + 46))
        self.grid.addItem(new)
        for name in sorted(self.folders, key=str.lower):
            clips = self.folders[name]
            free = sum(1 for c in clips if c not in self.project.clips)
            it = QListWidgetItem(QIcon(self._knife_pixmap(name)), name)
            it.setData(ROLE_DIR, name)
            it.setToolTip(f"{name} — {len(clips)} clip(s), {free} pas encore dans l'edit")
            it.setSizeHint(QSize(CARD_W + 16, CARD_H + 46))
            self.grid.addItem(it)
        self._filter(self.filter.text())

    def _filter(self, text):
        t = text.strip().lower()
        for i in range(self.grid.count()):
            it = self.grid.item(i)
            it.setHidden(bool(t) and it.data(ROLE_DIR) != NEW and t not in it.text().lower())

    def _card_clicked(self, item):
        if QApplication.keyboardModifiers() & (Qt.KeyboardModifier.ControlModifier |
                                               Qt.KeyboardModifier.ShiftModifier):
            return                                 # Ctrl/Maj : sélection de plusieurs couteaux
        name = item.data(ROLE_DIR)
        if name == NEW:
            self.new_folder()
        else:
            self.open_knife(name)

    def _dropped_on_knife(self, files, _item):
        if not files:
            self.status.setText("Aucune vidéo dans ce que tu as glissé.")
            return
        if self.knife:
            self._add_to_folder(self.knife, files)
            self._fill_knife()

    def _dropped_on_grid(self, files, item):
        if not files:
            self.status.setText("Aucune vidéo dans ce que tu as glissé.")
            return
        name = item.data(ROLE_DIR) if item is not None else None
        if not name or name == NEW:
            self.status.setText("Lâche tes clips sur la carte d'un couteau (ou ouvre un couteau).")
            return
        self._add_to_folder(name, files)
        self.open_knife(name)

    def open_knife(self, name):
        self.knife = name
        self._fill_knife()
        self.left_stack.setCurrentIndex(1)

    def close_knife(self):
        self.knife = None
        self.refresh_left()

    def _fill_knife(self):
        name = self.knife
        clips = self.folders.get(name, [])
        self.knife_title.setText(f"{name}\n{len(clips)} clip(s)")
        self.knife_img.setPixmap(self._knife_pixmap(name))
        self.clips.clear()
        for c in clips:
            used = c in self.project.clips
            it = QListWidgetItem(("✓ déjà dans l'edit — " if used else "") + _name(c))
            it.setData(ROLE, c)
            it.setToolTip(c)
            if used:
                it.setForeground(QColor("#6b7785"))
            self.clips.addItem(it)
        self.status.setText("Double-clique un clip (ou sélectionne-les puis « Ajouter → »)."
                            if clips else "Aucun clip : glisse tes vidéos dans la liste, ou « Ajouter des clips... ».")

    def _selected_paths(self):
        """Clips sélectionnés ; une carte de couteau sélectionnée = tous ses clips."""
        out = []
        if self.mode == "Clips":
            if self.left_stack.currentIndex() == 1:
                out = [it.data(ROLE) for it in self.clips.selectedItems()]
            else:
                for it in self.grid.selectedItems():
                    out += self.folders.get(it.data(ROLE_DIR), [])
        else:
            for it in self.tree.selectedItems():
                if it.data(0, ROLE):
                    out.append(it.data(0, ROLE))
                else:
                    out += [it.child(i).data(0, ROLE) for i in range(it.childCount())]
        seen = set()
        return [p for p in out if p and not (p in seen or seen.add(p))]

    def _double(self, item, _col):
        if item.data(0, ROLE):
            self.add_to_edit([item.data(0, ROLE)])

    # ----------------------------------------------------------- couteaux
    def _save_folders(self):
        proj.save_clip_folders(self.folders)
        self.refresh_left()

    def new_folder(self):
        name, ok = QInputDialog.getText(self, "Nouveau couteau", "Nom du couteau (ex. Oni Claw, Reaver...) :")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.folders:
            self.status.setText(f"Le couteau « {name} » existe déjà.")
            return
        self.folders[name] = []
        proj.save_clip_folders(self.folders)
        self.open_knife(name)
        self._fill_grid()
        self.pick_knife_image()

    def pick_knife_image(self):
        if not self.knife:
            return
        f, _ = QFileDialog.getOpenFileName(self, f"Image du couteau « {self.knife} »", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not f:
            return
        import shutil
        from app.core import timeremap
        cfg = timeremap.load()
        target = timeremap.knife_dir() / (proj_safe(self.knife) + "_carte" + Path(f).suffix.lower())
        try:
            shutil.copyfile(f, target)
            f = str(target)
        except OSError:
            pass
        cfg["couteaux"].setdefault(self.knife, {})["carte"] = f      # image de la carte (≠ image de détection)
        timeremap.save(cfg)
        self.refresh_left()

    def _store(self, name, paths):
        """Copie les clips dans la bibliothèque d'AuraEdit (Documents/AuraEdit/Clips/<couteau>)."""
        out = []
        dlg = QProgressDialog("Sauvegarde des clips dans AuraEdit...", "Arrêter", 0, len(paths), self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(300)
        for i, p in enumerate(paths):
            if dlg.wasCanceled():
                break
            dlg.setValue(i)
            dlg.setLabelText(f"Sauvegarde dans AuraEdit : {Path(p).name}")
            QApplication.processEvents()
            try:
                out.append(proj.store_clip(p, name))
            except OSError:
                out.append(p)                      # copie impossible : on garde l'original
        dlg.setValue(len(paths))
        return out

    def _add_to_folder(self, name, paths):
        clips = self.folders[name]
        stored = self._store(name, [p for p in paths if p not in clips])
        new = [p for p in stored if p not in clips]
        clips += new
        self._save_folders()
        self.status.setText(f"{len(new)} clip(s) sauvegardé(s) dans « {name} ».")

    def fill_folder(self):
        name = self.knife
        if not name:
            return
        files, _ = QFileDialog.getOpenFileNames(self, f"Clips pour « {name} »", "",
                                                file_filter("Vidéos", proj.VIDEO_EXT))
        if files:
            self._add_to_folder(name, files)

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
            new = [v for v in self._store(name, vids) if v not in clips]
            clips += new
            total += len(new)
        self._save_folders()
        self.status.setText(f"{total} clip(s) importé(s) dans {len(groups)} couteau(x).")

    def remove_from_knife(self):
        if not self.knife:
            return
        for it in self.clips.selectedItems():
            p = it.data(ROLE)
            if p in self.folders[self.knife]:
                self.folders[self.knife].remove(p)
        self._save_folders()

    def delete_knife(self):
        if not self.knife:
            return
        if QMessageBox.question(self, "Supprimer", f"Supprimer le couteau « {self.knife} » ?\n"
                                "(les vidéos restent dans Documents/AuraEdit/Clips)") \
                != QMessageBox.StandardButton.Yes:
            return
        self.folders.pop(self.knife, None)
        self.knife = None
        self._save_folders()

    # -------------------------------------------------------------- ordre
    def add_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.status.setText("Ouvre un couteau et sélectionne des clips (ou sélectionne des cartes avec Ctrl).")
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
            self.status.setText(f"{skipped} clip(s) déjà dans l'edit : chaque clip ne sert qu'une fois.")
        # time remap déjà fait pour ce clip (dans un autre projet) : on le reprend directement
        from app.core import timeremap
        saved = timeremap.clip_remaps()
        todo = []
        for p in new:
            if p in saved:
                self.project.remaps[p] = saved[p]
            else:
                todo.append(p)
        self.sync()
        self.refresh_left()
        if self.mode == "Clips" and todo:
            self.open_remap(todo)

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
        self.refresh_left()

    def clear(self):
        self.order.clear()
        self.sync()
        self.refresh_left()

    def sync(self, *args):
        self.project.clips = [self.order.item(i).data(ROLE) for i in range(self.order.count())]
        self._update_count()
        self.changed.emit()

    def _update_count(self):
        n = self.order.count()
        self.count.setText(f"{n} clip(s) dans l'edit" if n else "Aucun clip dans l'edit pour l'instant.")

    def stop(self):
        pass


def proj_safe(name):
    import re
    return re.sub(r'[<>:"/\\|?*]', "_", name)
