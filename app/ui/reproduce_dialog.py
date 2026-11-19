"""Fenêtre « Reproduire un edit » : on donne un edit fini, l'app trouve toutes les transitions,
puis on choisit plan par plan le clip à mettre (un couteau de ma bibliothèque, un dash, un kunai)."""
import random
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from app.core import project as proj
from app.core import timeremap as tr
from app.core import video_cuts

ROLE = Qt.ItemDataRole.UserRole
PREV_W, PREV_H = 560, 315


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
        right = QVBoxLayout()
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
        return w

    def open_edit(self):
        f, _ = QFileDialog.getOpenFileName(self, "Edit à reproduire", "",
                                           "Vidéos (*.mp4 *.mov *.mkv *.avi *.webm)")
        if not f or (self.thread is not None and self.thread.isRunning()):
            return
        self.path = f
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

    def del_cut(self):
        it = self.cut_list.currentItem()
        if it is not None:
            self.cuts = [c for c in self.cuts if c != it.data(ROLE)]
            self._fill_cuts()

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
        b_skip = QPushButton("Pas de clip pour ce plan")
        b_skip.clicked.connect(self._skip)
        self.b_go = QPushButton("Plan suivant  →")
        self.b_go.setObjectName("primary")
        self.b_go.clicked.connect(self._next_seg)
        views = QHBoxLayout()
        lv, rv = QVBoxLayout(), QVBoxLayout()
        lv.addWidget(QLabel("Le plan dans l'edit"))
        lv.addWidget(self.seg_view)
        rv.addWidget(QLabel("Ton clip"))
        rv.addWidget(self.pick_view)
        rv.addWidget(self.pick_name)
        views.addLayout(lv)
        views.addLayout(rv)
        row = QHBoxLayout()
        row.addWidget(b_prev)
        row.addStretch(1)
        row.addWidget(b_skip)
        row.addWidget(self.b_go)
        lay = QVBoxLayout(w)
        lay.addWidget(self.seg_title)
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
            clips = [c for c in clips if Path(c).is_file()]
            if clips:
                k = knives.get(name) or {}
                pools.append((name, clips, k.get("carte") or k.get("image")))
        return pools

    def start_choose(self):
        n = len(self.cuts) + 1
        self.bounds = [0.0] + sorted(self.cuts) + [self.length]
        if len(self.choices) != n:
            self.choices = [None] * n
        self.grid.clear()
        for name, clips, img in self._pools():
            pix = QPixmap(img) if img and Path(img).is_file() else QPixmap()
            sym = proj.SPECIAL_FOLDERS.get(name, "")
            it = QListWidgetItem(QIcon(pix) if not pix.isNull() else QIcon(),
                                 f"{sym} {name}\n{len(clips)} clip(s)".strip())
            it.setData(ROLE, (name, clips))
            self.grid.addItem(it)
        self.stack.setCurrentIndex(1)
        self._show_seg(0)

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
        if not ch:
            self.pick_name.setText("Aucun clip choisi pour ce plan.")
            self.pick_view.clear()
            return
        cat, path = ch
        rm = tr.clip_remaps().get(path)
        self.pick_name.setText(f"{cat} : {Path(path).name}" + ("  (time remap ✓)" if rm else ""))
        self.pick_view.show_at(path, float(rm["debut"]) if rm else 0.5)

    def _pick(self, item):
        name, clips = item.data(ROLE)
        used = {c[1] for k, c in enumerate(self.choices) if c and k != self.seg}
        cur = self.choices[self.seg][1] if self.choices[self.seg] else None
        free = [c for c in clips if c not in used and c != cur] or [c for c in clips if c != cur] or clips
        saved = tr.clip_remaps()
        remapped = [c for c in free if c in saved]
        pool = remapped or free                   # les clips avec time remap déjà fait d'abord
        self.choices[self.seg] = (name, random.choice(pool))
        self._show_pick()

    def _skip(self):
        self.choices[self.seg] = None
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
        for c in clips:
            if c in saved:
                self.project.remaps[c] = saved[c]
        self.project.clips = clips
        self.accept()

    def done(self, r):
        if self.thread is not None and self.thread.isRunning():
            self.thread.wait()
        super().done(r)
