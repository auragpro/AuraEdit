"""Fenêtre « Reproduire un edit » : on donne un edit fini, l'app trouve toutes les transitions,
puis on choisit plan par plan le clip à mettre (un couteau de ma bibliothèque, un dash, un kunai)."""
import json
import random
import time
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                             QListWidgetItem, QMenu, QMessageBox, QPushButton, QSlider, QStackedWidget,
                             QVBoxLayout, QWidget)

from app.core import vclip
from app.core import project as proj
from app.core import timeremap as tr
from app.core import video_cuts

ROLE = Qt.ItemDataRole.UserRole
PREV_W, PREV_H = 560, 315


def _saved_file():
    return proj.config_dir() / "reproduire_edits.json"


def load_saved():
    """Edits déjà découpés : {chemin de l'edit: {"cuts", "length", "fps", "choices", "overlays", "date"}}."""
    try:
        d = json.loads(_saved_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_saved(d):
    try:
        _saved_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def fmt(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


class CutsThread(QThread):
    done = pyqtSignal(list, float, float)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            from app.core.render import duration
            # seuil bas : on préfère trop de transitions (faciles à supprimer) que d'en rater
            cuts = video_cuts.detect_cuts(self.path, threshold=0.18, min_gap=0.08)
            self.done.emit(cuts, float(duration(self.path) or 0), float(tr.source_fps(self.path)))
        except Exception as e:                          # noqa: BLE001
            self.failed.emit(str(e))


class AutoThread(QThread):
    """Analyse de l'edit pour l'edit auto (en arrière-plan)."""
    step = pyqtSignal(float, str)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, edit, bounds, classes, parent=None):
        super().__init__(parent)
        self.edit, self.bounds, self.classes = edit, bounds, classes

    def run(self):
        try:
            from app.core import auto_match
            res = auto_match.analyse(self.edit, self.bounds, self.classes, tr.clip_remaps(),
                                     lambda f, t: self.step.emit(f, t))
            self.done.emit(res)
        except Exception as e:                          # noqa: BLE001
            self.failed.emit(str(e))


class Preview(QLabel):
    """Image de la vidéo à un instant (mise à jour un peu après le dernier changement)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(PREV_W, PREV_H)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #0b0f14; border-radius: 10px;")
        self.path, self.t = None, 0.0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._load)

    def show_at(self, path, t):
        self.path, self.t = path, t
        self.timer.start(60)

    def _load(self):
        if not self.path:
            return
        pix = QPixmap()
        pix.loadFromData(tr.grab_png(self.path, self.t, PREV_W))
        if not pix.isNull():
            self.setPixmap(pix.scaled(PREV_W, PREV_H, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))


class ReproduceDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reproduire un edit")
        self.resize(1080, 720)
        self.project = project
        self.path, self.length, self.fps = None, 0.0, 60.0
        self.cuts = []
        self.choices = []                 # par plan : (catégorie, chemin) ou None
        self.overlays = {}                # par plan : réglages de la vidéo superposée (fond vert)
        self.seg = 0
        self.thread = None
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_cuts())
        self.stack.addWidget(self._page_choose())
        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)

    # ------------------------------------------------------------ page 1
    def _page_cuts(self):
        w = QWidget()
        title = QLabel("1. Les transitions de l'edit")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        info = QLabel("Choisis un edit fini : je trouve toutes les transitions (changements de clip). "
                      "S'il en manque une, mets-toi dessus avec le curseur ou ◀ -1 / +1 ▶ et clique "
                      "« ➕ Transition ici ». Une transition en trop : sélectionne-la et supprime-la.")
        info.setWordWrap(True)
        b_open = QPushButton("Choisir l'edit (vidéo)...")
        b_open.clicked.connect(self.open_edit)
        self.cut_status = QLabel("")
        self.view = Preview()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._moved)
        b_m = QPushButton("◀  -1")
        b_p = QPushButton("+1  ▶")
        b_m.clicked.connect(lambda: self.slider.setValue(self.slider.value() - 1))
        b_p.clicked.connect(lambda: self.slider.setValue(self.slider.value() + 1))
        self.pos = QLabel("0:00.00")
        srow = QHBoxLayout()
        srow.addWidget(b_m)
        srow.addWidget(self.slider, 1)
        srow.addWidget(b_p)
        srow.addWidget(self.pos)
        self.cut_list = QListWidget()
        self.cut_list.itemClicked.connect(lambda it: self._goto(it.data(ROLE)))
        b_add = QPushButton("➕ Transition ici")
        b_add.clicked.connect(self.add_cut)
        b_del = QPushButton("🗑 Supprimer la transition")
        b_del.clicked.connect(self.del_cut)
        self.b_next = QPushButton("Choisir les clips  →")
        self.b_next.setObjectName("primary")
        self.b_next.setEnabled(False)
        self.b_next.clicked.connect(self.start_choose)
        left = QVBoxLayout()
        left.addWidget(self.view)
        left.addLayout(srow)
        self.saved_list = QListWidget()
        self.saved_list.setMaximumHeight(150)
        self.saved_list.itemDoubleClicked.connect(lambda it: self.load_edit(it.data(ROLE)))
        b_load = QPushButton("📂 Reprendre cet edit")
        b_load.clicked.connect(lambda: self.saved_list.currentItem() and
                               self.load_edit(self.saved_list.currentItem().data(ROLE)))
        b_forget = QPushButton("🗑 Retirer de la liste")
        b_forget.clicked.connect(self.forget_edit)
        right = QVBoxLayout()
        right.addWidget(QLabel("Edits déjà découpés (tout est gardé : transitions et clips choisis)"))
        right.addWidget(self.saved_list)
        srow2 = QHBoxLayout()
        srow2.addWidget(b_load)
        srow2.addWidget(b_forget)
        right.addLayout(srow2)
        right.addWidget(QLabel("Transitions trouvées"))
        right.addWidget(self.cut_list, 1)
        right.addWidget(b_add)
        right.addWidget(b_del)
        body = QHBoxLayout()
        body.addLayout(left, 2)
        body.addLayout(right, 1)
        top = QHBoxLayout()
        top.addWidget(b_open)
        top.addWidget(self.cut_status, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.b_next)
        lay = QVBoxLayout(w)
        lay.addWidget(title)
        lay.addWidget(info)
        lay.addLayout(top)
        lay.addLayout(body, 1)
        lay.addLayout(bottom)
        self._fill_saved()
        return w

    # ------------------------------------------------------------ edits enregistrés
    def _fill_saved(self):
        self.saved_list.clear()
        d = load_saved()
        for path, e in sorted(d.items(), key=lambda kv: -float(kv[1].get("date", 0))):
            n = len(e.get("cuts", [])) + 1
            done = sum(1 for c in e.get("choices", []) if c)
            ok = "" if Path(path).is_file() else "  ⚠ fichier introuvable"
            it = QListWidgetItem(f"{Path(path).name}  —  {n} plans, {done} clip(s) choisi(s)  "
                                 f"({time.strftime('%d/%m %H:%M', time.localtime(float(e.get('date', 0))))}){ok}")
            it.setData(ROLE, path)
            self.saved_list.addItem(it)

    def save_state(self):
        """Garde les transitions et les clips choisis de cet edit (on peut le reprendre plus tard)."""
        if not self.path:
            return
        d = load_saved()
        d[self.path] = {"cuts": [round(c, 4) for c in sorted(self.cuts)], "length": self.length, "fps": self.fps,
                        "choices": [list(c) if c else None for c in self.choices],
                        "overlays": {str(k): v for k, v in self.overlays.items()}, "date": time.time()}
        write_saved(d)

    def load_edit(self, path):
        e = load_saved().get(path)
        if not e:
            return
        if not Path(path).is_file():
            self.cut_status.setText("Cet edit n'est plus à son emplacement sur le PC.")
            return
        self.path = path
        self.length, self.fps = float(e.get("length") or 0), float(e.get("fps") or 60)
        self.cuts = [float(c) for c in e.get("cuts", [])]
        self.choices = [tuple(c) if c else None for c in e.get("choices", [])]
        self.overlays = {int(k): v for k, v in (e.get("overlays") or {}).items()}
        self.slider.setRange(0, max(1, int(self.length * self.fps) - 1))
        self.slider.setEnabled(True)
        self._fill_cuts()
        self._goto(0.0)
        self.b_next.setEnabled(True)
        self.cut_status.setText(f"Edit repris : {len(self.cuts)} transition(s), "
                                f"{sum(1 for c in self.choices if c)} clip(s) déjà choisi(s).")

    def forget_edit(self):
        it = self.saved_list.currentItem()
        if it is None:
            return
        d = load_saved()
        d.pop(it.data(ROLE), None)
        write_saved(d)
        self._fill_saved()

    def open_edit(self):
        f, _ = QFileDialog.getOpenFileName(self, "Edit à reproduire", "",
                                           "Vidéos (*.mp4 *.mov *.mkv *.avi *.webm)")
        if not f or (self.thread is not None and self.thread.isRunning()):
            return
        if f in load_saved():
            self.load_edit(f)                     # déjà découpé : on reprend là où on en était
            return
        self.path = f
        self.choices, self.overlays = [], {}
        self.cut_status.setText("Je cherche les transitions...")
        self.thread = CutsThread(f, self)
        self.thread.done.connect(self._cuts_found)
        self.thread.failed.connect(lambda m: self.cut_status.setText(f"Lecture impossible : {m}"))
        self.thread.start()

    def _cuts_found(self, cuts, length, fps):
        self.length, self.fps = length, fps
        self.cuts = [c for c in cuts if 0.05 < c < length - 0.05]
        self.slider.setRange(0, max(1, int(length * fps) - 1))
        self.slider.setEnabled(True)
        self._fill_cuts()
        self._goto(0.0)
        self.b_next.setEnabled(True)
        self.save_state()
        self._fill_saved()

    def _fill_cuts(self):
        self.cuts.sort()
        self.cut_list.clear()
        for i, c in enumerate(self.cuts):
            it = QListWidgetItem(f"{i + 1}.  {fmt(c)}  (frame {int(round(c * self.fps))})")
            it.setData(ROLE, c)
            self.cut_list.addItem(it)
        self.cut_status.setText(f"{len(self.cuts)} transition(s) → {len(self.cuts) + 1} plan(s). "
                                "Vérifie qu'il n'en manque aucune.")

    def _goto(self, t):
        self.slider.setValue(int(round(t * self.fps)))
        self._moved(self.slider.value())

    def _moved(self, v):
        t = v / self.fps
        self.pos.setText(fmt(t))
        if self.path:
            self.view.show_at(self.path, t)

    def add_cut(self):
        if not self.path:
            return
        t = self.slider.value() / self.fps
        if all(abs(t - c) > 0.5 / self.fps for c in self.cuts):
            self.cuts.append(t)
            self._fill_cuts()
            self.save_state()

    def del_cut(self):
        it = self.cut_list.currentItem()
        if it is not None:
            self.cuts = [c for c in self.cuts if c != it.data(ROLE)]
            self._fill_cuts()
            self.save_state()

    # ------------------------------------------------------------ page 2
    def _page_choose(self):
        w = QWidget()
        self.seg_title = QLabel("")
        self.seg_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        info = QLabel("Regarde le plan de l'edit, puis clique un couteau : je prends un de ses clips au hasard "
                      "(ceux avec le time remap déjà fait en premier). Re-clique dessus pour en avoir un autre.")
        info.setWordWrap(True)
        self.seg_view = Preview()
        self.pick_view = Preview()
        self.pick_name = QLabel("Aucun clip choisi pour ce plan.")
        self.pick_name.setWordWrap(True)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(150, 84))
        self.grid.setGridSize(QSize(170, 120))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.itemClicked.connect(self._pick)
        b_prev = QPushButton("←  Plan précédent")
        b_prev.clicked.connect(lambda: self._show_seg(self.seg - 1))
        self.b_over = QPushButton("🟩 Superposer une vidéo (fond vert)")
        self.b_over.clicked.connect(self._overlay)
        self.b_remap = QPushButton("⏱ Time remap de ce clip")
        self.b_remap.setToolTip("Régler ou changer le time remap du clip choisi pour ce plan (double-clic sur le clip aussi).")
        self.b_remap.clicked.connect(self._remap)
        self.pick_view.mouseDoubleClickEvent = lambda e: self._remap()
        b_skip = QPushButton("Pas de clip pour ce plan")
        b_skip.clicked.connect(self._skip)
        self.b_go = QPushButton("Plan suivant  →")
        self.b_go.setObjectName("primary")
        self.b_auto = QPushButton("🤖 Edit auto : remplir tous les plans")
        self.b_auto.setToolTip("J'analyse chaque plan de l'edit (quel couteau, kunai, dash gauche/droite...) "
                               "et je mets un de tes clips qui correspond.")
        self.b_auto.clicked.connect(self.auto_edit)
        self.auto_status = QLabel("")
        self.b_addclips = QPushButton("➕ Ajouter des clips")
        self.b_addclips.setToolTip("Ajoute des clips à un couteau, au Dash, au Kunai... : ils vont aussi dans "
                                   "« Mes clips » et dans la partie Dash / Kunai.")
        self.b_addclips.clicked.connect(self.add_clips)
        self.b_go.clicked.connect(self._next_seg)
        views = QHBoxLayout()
        lv, rv = QVBoxLayout(), QVBoxLayout()
        lv.addWidget(QLabel("Le plan dans l'edit"))
        lv.addWidget(self.seg_view)
        rv.addWidget(QLabel("Ton clip"))
        rv.addWidget(self.pick_view)
        rv.addWidget(self.pick_name)
        brow = QHBoxLayout()
        brow.addWidget(self.b_remap)
        brow.addWidget(self.b_over)
        rv.addLayout(brow)
        views.addLayout(lv)
        views.addLayout(rv)
        row = QHBoxLayout()
        row.addWidget(b_prev)
        row.addStretch(1)
        row.addWidget(b_skip)
        row.addWidget(self.b_go)
        lay = QVBoxLayout(w)
        trow = QHBoxLayout()
        trow.addWidget(self.seg_title, 1)
        trow.addWidget(self.auto_status)
        trow.addWidget(self.b_addclips)
        trow.addWidget(self.b_auto)
        lay.addLayout(trow)
        lay.addWidget(info)
        lay.addLayout(views)
        lay.addWidget(self.grid, 1)
        lay.addLayout(row)
        return w

    def _pools(self):
        folders = proj.sync_special_folders(self.project)
        knives = tr.load()["couteaux"]
        pools = []
        for name, clips in sorted(folders.items(), key=lambda kv: kv[0].lower()):
            clips = [c for c in clips if vclip.exists(c)]
            if clips:
                k = knives.get(name) or {}
                pools.append((name, clips, k.get("carte") or k.get("image")))
        return pools

    def start_choose(self):
        n = len(self.cuts) + 1
        self.bounds = [0.0] + sorted(self.cuts) + [self.length]
        if len(self.choices) != n:
            self.choices = (list(self.choices) + [None] * n)[:n]
        self._fill_grid()
        self.stack.setCurrentIndex(1)
        self._show_seg(0)

    def _fill_grid(self):
        self.grid.clear()
        for name, clips, img in self._pools():
            pix = QPixmap(img) if img and Path(img).is_file() else QPixmap()
            sym = proj.SPECIAL_FOLDERS.get(name, "")
            attr = proj.SPECIAL_ATTR.get(name)
            if attr:
                # Dash / Kunai / Dash back / Dismiss : une case main gauche et une case main droite
                st = getattr(self.project, attr, None)
                rest = list(clips)
                for side, label in (("gauche", "⬅ gauche"), ("droite", "droite ➡")):
                    part = [c for c in clips if st and c in getattr(st, side, [])]
                    rest = [c for c in rest if c not in part]
                    it = QListWidgetItem(f"{sym} {name}\n{label}\n{len(part)} clip(s)")
                    it.setData(ROLE, (name, part))
                    if not part:
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                        it.setToolTip("Aucun clip pour cette main : ajoute-en avec « ➕ Ajouter des clips ».")
                    self.grid.addItem(it)
                if rest:
                    it = QListWidgetItem(f"{sym} {name}\nmain non choisie\n{len(rest)} clip(s)")
                    it.setData(ROLE, (name, rest))
                    self.grid.addItem(it)
                continue
            it = QListWidgetItem(QIcon(pix) if not pix.isNull() else QIcon(),
                                 f"{sym} {name}\n{len(clips)} clip(s)".strip())
            it.setData(ROLE, (name, clips))
            self.grid.addItem(it)

    def add_clips(self):
        """Ajoute des clips à une catégorie, synchronisé avec « Mes clips » et les parties Dash / Kunai..."""
        folders = proj.sync_special_folders(self.project)
        menu = QMenu(self)
        for name in sorted(folders, key=str.lower):
            menu.addAction(f"{proj.SPECIAL_FOLDERS.get(name, '🔪')}  {name}").setData(name)
        menu.addSeparator()
        menu.addAction("➕  Nouveau couteau...").setData("")
        act = menu.exec(self.b_addclips.mapToGlobal(self.b_addclips.rect().bottomLeft()))
        if act is None:
            return
        name = act.data()
        if not name:
            name, ok = QInputDialog.getText(self, "Nouveau couteau", "Nom du couteau :")
            name = name.strip()
            if not ok or not name:
                return
        files, _ = QFileDialog.getOpenFileNames(self, f"Clips à ajouter dans « {name} »", "",
                                                "Vidéos (*.mp4 *.mov *.mkv *.avi *.webm)")
        if not files:
            return
        attr = proj.SPECIAL_ATTR.get(name)
        side = None
        if attr:
            box = QMessageBox(self)
            box.setWindowTitle(name)
            box.setText(f"Ces {len(files)} clip(s) « {name} » sont de quelle main ?")
            bg = box.addButton("⬅  Main gauche", QMessageBox.ButtonRole.AcceptRole)
            bd = box.addButton("Main droite  ➡", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            side = "gauche" if box.clickedButton() is bg else "droite" if box.clickedButton() is bd else None
            if side is None:
                return
        folders = proj.load_clip_folders()
        lst = folders.setdefault(name, [])
        new = [f for f in files if f not in lst]
        lst += new
        proj.save_clip_folders(folders)
        where = "Mes clips"
        if attr:
            st = getattr(self.project, attr)
            cur = getattr(st, side)
            cur += [f for f in files if f not in st.videos]
            st.sync()
            where += f" + partie {name} ({side})"
        self._fill_grid()
        self.auto_status.setText(f"✓ {len(files)} clip(s) dans « {name} » ({where}).")

    def _show_seg(self, i):
        if i < 0:
            self.stack.setCurrentIndex(0)
            return
        self.seg = i
        a, b = self.bounds[i], self.bounds[i + 1]
        n = len(self.bounds) - 1
        self.seg_title.setText(f"2. Plan {i + 1} / {n}  —  {fmt(a)} → {fmt(b)}  ({b - a:.2f} s)")
        self.seg_view.show_at(self.path, (a + b) / 2)
        self.b_go.setText("Terminer  ✓" if i == n - 1 else "Plan suivant  →")
        self._show_pick()

    def _show_pick(self):
        ch = self.choices[self.seg]
        ov = self.overlays.get(self.seg)
        self.b_over.setEnabled(bool(ch))
        self.b_remap.setEnabled(bool(ch))
        self.b_over.setText(f"🟩 Superposition : {Path(ov['fichier']).name}  (modifier)" if ov
                            else "🟩 Superposer une vidéo (fond vert)")
        if not ch:
            self.pick_name.setText("Aucun clip choisi pour ce plan.")
            self.pick_view.clear()
            return
        cat, path = ch
        rm = tr.clip_remaps().get(path)
        attr = proj.SPECIAL_ATTR.get(cat)
        st = getattr(self.project, attr, None) if attr else None
        side = ("  ⬅ main gauche" if st and path in st.gauche else
                "  main droite ➡" if st and path in st.droite else "")
        s0 = None if rm else tr.clip_starts().get(str(path))
        self.pick_name.setText(f"{cat}{side} : {vclip.name(path)}" + (
            "  (time remap ✓)" if rm else f"  (sans time remap, début frame {int(round(s0 * tr.FPS))})"
            if s0 is not None else ""))
        self.pick_view.show_at(path, float(rm["debut"]) if rm else (s0 if s0 is not None else 0.5))

    def _pick(self, item):
        name, clips = item.data(ROLE)
        used = {c[1] for k, c in enumerate(self.choices) if c and k != self.seg}
        cur = self.choices[self.seg][1] if self.choices[self.seg] else None
        free = [c for c in clips if c not in used and c != cur] or [c for c in clips if c != cur] or clips
        saved = tr.clip_remaps()
        remapped = [c for c in free if c in saved]
        pool = remapped or free                   # les clips avec time remap déjà fait d'abord
        self.choices[self.seg] = (name, random.choice(pool))
        self.save_state()
        self._show_pick()

    def _remap(self):
        """Ouvre le time remap du clip choisi pour ce plan (pour le régler ou le changer)."""
        ch = self.choices[self.seg] if 0 <= self.seg < len(self.choices) else None
        if not ch:
            return
        from .timeremap_dialog import TimeRemapDialog
        cat, path = ch
        mode = {"Kunai": "kunai", "Dash back": "dashback", "Dismiss": "dismiss"}.get(cat)
        gap = self.bounds[self.seg + 1] - self.bounds[self.seg]      # du début de ce plan au clip suivant
        if mode:
            dlg = TimeRemapDialog(self.project, path, None, (), self, mode=mode, gap=gap)
        else:
            knives = [n for n in proj.load_clip_folders() if n not in proj.SPECIAL_FOLDERS]
            dlg = TimeRemapDialog(self.project, path, None if cat == "Dash" else cat, knives, self, gap=gap)
        dlg.exec()
        self._show_pick()

    def _overlay(self):
        ch = self.choices[self.seg]
        if not ch:
            return
        from .overlay_dialog import OverlayDialog
        rm = tr.clip_remaps().get(ch[1])
        dlg = OverlayDialog(ch[1], float(rm["debut"]) if rm else 0.5, self.overlays.get(self.seg), self)
        if dlg.exec():
            if dlg.result:
                self.overlays[self.seg] = dlg.result
            else:
                self.overlays.pop(self.seg, None)
            self._show_pick()
            self.save_state()

    # ------------------------------------------------------------ edit auto
    def _classes(self):
        classes = {}
        for name, clips, img in self._pools():
            attr = proj.SPECIAL_ATTR.get(name)
            if not attr:
                classes[name] = {"clips": clips, "image": img, "pool": name, "special": False}
                continue
            st = getattr(self.project, attr, None)
            rest = list(clips)
            for side in ("gauche", "droite"):
                part = [c for c in clips if st and c in getattr(st, side, [])]
                rest = [c for c in rest if c not in part]
                if part:
                    classes[f"{name}|{side}"] = {"clips": part, "image": None, "pool": name, "special": True}
            if rest:
                classes[name] = {"clips": rest, "image": None, "pool": name, "special": True}
        return classes

    def auto_edit(self):
        if self.thread is not None and self.thread.isRunning():
            return
        self.auto_cls = self._classes()
        if not self.auto_cls:
            self.auto_status.setText("Aucun clip dans « Mes clips ».")
            return
        self.b_auto.setEnabled(False)
        self.auto_status.setText("Analyse...")
        self.thread = AutoThread(self.path, list(self.bounds), self.auto_cls, self)
        self.thread.step.connect(lambda f, t: self.auto_status.setText(f"{t} {int(f * 100)} %"))
        self.thread.done.connect(self._auto_done)
        self.thread.failed.connect(lambda m: (self.auto_status.setText(f"Erreur : {m}"),
                                              self.b_auto.setEnabled(True)))
        self.thread.start()

    def _auto_done(self, ranks):
        self.b_auto.setEnabled(True)
        saved = tr.clip_remaps()
        used = set()

        def take(key):
            clips = self.auto_cls[key]["clips"]
            free = [c for c in clips if c not in used]
            if not free:
                return None
            pool = [c for c in free if c in saved] or free     # time remap déjà fait d'abord
            return random.choice(pool)

        changed, other = 0, 0
        for i, ranked in enumerate(ranks):
            if i >= len(self.choices) or not ranked:
                continue
            best = ranked[0]
            info = self.auto_cls[best]
            pick, key = None, best
            if info["special"]:
                pick = take(best) or random.choice(info["clips"])          # même catégorie, même main
            else:
                for k in ranked:                                         # sinon le couteau le plus proche
                    if not self.auto_cls[k]["special"]:
                        pick = take(k)
                        if pick:
                            key = k
                            break
                if not pick:
                    pick = random.choice(info["clips"])
                elif key != best:
                    other += 1
            used.add(pick)
            self.choices[i] = (self.auto_cls[key]["pool"], pick)
            changed += 1
        msg = f"✓ {changed} plan(s) remplis"
        if other:
            msg += f" ({other} avec un autre couteau, plus de clip libre)"
        self.auto_status.setText(msg + " — vérifie et re-clique un couteau pour changer.")
        self.save_state()
        self._show_seg(0)

    def _skip(self):
        self.choices[self.seg] = None
        self.save_state()
        self._next_seg()

    def _next_seg(self):
        if self.seg < len(self.bounds) - 2:
            self._show_seg(self.seg + 1)
        else:
            self.finish()

    def finish(self):
        clips = [c[1] for c in self.choices if c]
        clips = list(dict.fromkeys(clips))
        saved = tr.clip_remaps()
        plans = {}
        for k, ch in enumerate(self.choices):
            if ch and ch[1] not in plans and k + 1 < len(self.bounds):
                plans[ch[1]] = round(self.bounds[k + 1] - self.bounds[k], 4)   # plan -> clip suivant
        for c in clips:
            if c in saved:
                self.project.remaps[c] = dict(saved[c], plan=plans.get(c))
        self.project.clips = clips
        self.project.overlays = {self.choices[k][1]: ov for k, ov in self.overlays.items()
                                 if k < len(self.choices) and self.choices[k]}
        self.save_state()
        self.accept()

    def done(self, r):
        if self.thread is not None and self.thread.isRunning():
            self.thread.wait()
        self.save_state()
        super().done(r)
