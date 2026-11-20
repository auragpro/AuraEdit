"""Couper une compilation de dash : un clip par dash (dash1, dash2...), coupé à la 1re frame du dash
après chaque bannière de kill. Les coupes sont vérifiables et corrigeables à la frame près avant l'export."""
import re
import subprocess
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QProgressBar, QPushButton, QSlider, QVBoxLayout)

from app.core import audio
from app.core import project as proj
from app.core import timeremap as tr

from .reproduce_dialog import Preview, fmt

ROLE = Qt.ItemDataRole.UserRole
FPS = tr.FPS


def _native_region(path, t0, count, sfps):
    """Zone des mains à la cadence réelle de la vidéo (toutes les frames), à partir de la frame t0*sfps."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                        "-ss", f"{max(0.0, t0 - 0.3 / sfps):.6f}", "-i", str(path), "-an",
                        "-frames:v", str(count), "-vf", tr.REGION, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    size = tr.RW * tr.RH * 3
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(data) // size
    return tr._norm(data[:n * size].reshape(n, size))


def _refine(path, tc, kill_t, sfps):
    """Frame exacte (cadence réelle) où la main du dash apparaît, autour de tc (estimation à 60 i/s).
    Chaque frame est comparée à « l'arme » (frames juste avant) et à « la main » (frames juste après) :
    la coupe = 1re frame plus proche de la main que de l'arme, et qui le reste. Jamais avant le kill."""
    f0 = max(0, int(round((tc - 0.30) * sfps)))
    F = _native_region(path, f0 / sfps, int(0.6 * sfps) + 2, sfps)
    n = len(F)
    if n < 10:
        return tc
    c = int(round(tc * sfps)) - f0                      # position estimée dans la fenêtre
    w0, w1 = max(0, c - int(0.25 * sfps)), max(1, c - int(0.06 * sfps))
    h0, h1 = min(n - 1, c + int(0.05 * sfps)), min(n, c + int(0.16 * sfps))
    if w1 <= w0 or h1 <= h0:
        return tc
    W = F[w0:w1].mean(axis=0)
    W /= np.linalg.norm(W) + 1e-6
    H = F[h0:h1].mean(axis=0)
    H /= np.linalg.norm(H) + 1e-6
    closer = (F @ H) - (F @ W) > 0                     # vrai = ressemble plus à la main qu'à l'arme
    lo = max(w1, int(np.floor(kill_t * sfps)) - f0 + 1 if kill_t is not None else 0)
    for j in range(lo, n - 2):
        if closer[j] and closer[j + 1] and closer[j + 2]:
            return (f0 + j) / sfps
    return tc


def dash_starts(path):
    """1re frame de chaque dash (en secondes, sur une frame exacte de la vidéo) = la frame où l'arme
    disparaît et où la main du dash apparaît, juste après la bannière de kill."""
    a = tr.Analysis(path)
    n, kills = a.n, a.kills
    sfps = float(tr.source_fps(path))
    sw = [i for i in range(10, n - 9) if a._switch(i)]
    picks = []                                       # (frame 60 i/s, kill 60 i/s ou None)
    if kills:
        for k in kills:
            c = [i for i in sw if k < i <= k + 3 * FPS]
            if c:
                picks.append((c[0], k))
    else:
        last = -10 ** 9
        for i in sw:
            if i - last > 1.2 * FPS:
                picks.append((i, None))
                last = i
    starts = []
    for i, k in picks:
        lo = max(1, i - 4)                           # 1re frame (60 i/s) qui ne ressemble plus à l'arme
        before = a.F[max(0, lo - 10):lo].mean(axis=0)
        before /= np.linalg.norm(before) + 1e-6
        j = next((x for x in range(lo, min(n, i + 4)) if float(a.F[x] @ before) < 0.6), i)
        t = _refine(path, j / FPS, None if k is None else k / FPS, sfps)
        t = round(t * sfps) / sfps
        if not starts or t - starts[-1] > 0.4:
            starts.append(t)
    return starts, n / FPS, kills


class DetectThread(QThread):
    done = pyqtSignal(list, float, list)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            s, length, kills = dash_starts(self.path)
            self.done.emit(s, length, [k / FPS for k in kills])
        except Exception as e:                              # noqa: BLE001
            self.failed.emit(str(e))


class ExportThread(QThread):
    progress = pyqtSignal(int, str)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, path, cuts, length, folder, parent=None, fps=60.0):
        super().__init__(parent)
        self.path, self.cuts, self.length, self.folder = path, cuts, length, Path(folder)
        self.fps = fps

    def run(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            used = [int(m.group(1)) for f in self.folder.glob("dash*.mp4")
                    if (m := re.fullmatch(r"dash(\d+)", f.stem))]
            num = max(used, default=0)
            out = []
            bounds = list(self.cuts) + [self.length]
            for i in range(len(self.cuts)):
                a, b = bounds[i], bounds[i + 1]
                num += 1
                target = self.folder / f"dash{num}.mp4"
                self.progress.emit(int(100 * i / len(self.cuts)), f"Export de {target.name}...")
                # coupe au numéro de frame exact (trim), même frame que celle vue dans l'aperçu
                fa = int(round(a * self.fps))
                fb = int(round(b * self.fps)) if i + 1 < len(self.cuts) else 10 ** 9
                ta, tb = fa / self.fps, (fb / self.fps if fb < 10 ** 9 else self.length + 1)
                p = subprocess.run([audio.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                                    "-i", self.path,
                                    "-vf", f"trim=start_frame={fa}:end_frame={fb},setpts=PTS-STARTPTS",
                                    "-af", f"atrim=start={ta:.6f}:end={tb:.6f},asetpts=PTS-STARTPTS",
                                    "-c:v", "libx264", "-preset", "medium", "-crf", "12",
                                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", str(target)],
                                   capture_output=True, creationflags=audio._NO_WINDOW)
                if p.returncode != 0:
                    raise ValueError(p.stderr.decode("utf-8", "replace")[-400:])
                out.append(str(target))
            self.done.emit(out)
        except Exception as e:                              # noqa: BLE001
            self.failed.emit(str(e))


class DashSplitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Couper une compilation de dash")
        self.resize(1000, 680)
        self.path, self.length, self.fps = None, 0.0, 60.0
        self.cuts, self.result = [], []
        self.thread = None
        info = QLabel("Choisis ta compilation : je repère chaque bannière de kill puis la 1re frame du dash "
                      "qui suit. Vérifie CHAQUE coupe (clique-la dans la liste) : corrige avec ◀ -1 / +1 ▶ puis "
                      "« ↔ Déplacer ici », ajoute une coupe oubliée avec « ➕ Coupe ici », ou supprime une coupe "
                      "en trop. Chaque dash est ensuite enregistré à part : dash1, dash2...")
        info.setWordWrap(True)
        b_open = QPushButton("Choisir la compilation...")
        b_open.clicked.connect(self.open_video)
        self.status = QLabel("")
        self.view = Preview()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._moved)
        b_m, b_p = QPushButton("◀  -1"), QPushButton("+1  ▶")
        b_m.clicked.connect(lambda: self.slider.setValue(self.slider.value() - 1))
        b_p.clicked.connect(lambda: self.slider.setValue(self.slider.value() + 1))
        self.pos = QLabel("0:00.00")
        srow = QHBoxLayout()
        for w in (b_m, self.slider, b_p, self.pos):
            srow.addWidget(w, 1 if w is self.slider else 0)
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda it: self._goto(it.data(ROLE)))
        b_add = QPushButton("➕ Coupe ici")
        b_add.clicked.connect(self.add_cut)
        b_move = QPushButton("↔ Déplacer la coupe ici")
        b_move.clicked.connect(self.move_cut)
        b_del = QPushButton("🗑 Supprimer la coupe")
        b_del.clicked.connect(self.del_cut)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.b_go = QPushButton("✂ Couper et enregistrer les dash")
        self.b_go.setObjectName("primary")
        self.b_go.setEnabled(False)
        self.b_go.clicked.connect(self.export)
        left = QVBoxLayout()
        left.addWidget(self.view)
        left.addLayout(srow)
        right = QVBoxLayout()
        right.addWidget(QLabel("Débuts de dash (1 dash = jusqu'au début du suivant)"))
        right.addWidget(self.list, 1)
        for b in (b_add, b_move, b_del):
            right.addWidget(b)
        body = QHBoxLayout()
        body.addLayout(left, 2)
        body.addLayout(right, 1)
        top = QHBoxLayout()
        top.addWidget(b_open)
        top.addWidget(self.status, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.bar, 1)
        bottom.addWidget(self.b_go)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(top)
        lay.addLayout(body, 1)
        lay.addLayout(bottom)

    def _busy(self):
        return self.thread is not None and self.thread.isRunning()

    def open_video(self):
        f, _ = QFileDialog.getOpenFileName(self, "Compilation de dash", "", "Vidéos (*.mp4 *.mov *.mkv *.avi *.webm)")
        if not f or self._busy():
            return
        self.path = f
        self.status.setText("Je cherche les kills et les dash...")
        self.thread = DetectThread(f, self)
        self.thread.done.connect(self._found)
        self.thread.failed.connect(lambda m: self.status.setText(f"Détection impossible : {m}"))
        self.thread.start()

    def _found(self, starts, length, kills):
        self.length, self.fps = length, float(tr.source_fps(self.path))
        self.cuts = list(starts)
        self.slider.setRange(0, max(1, int(length * self.fps) - 1))
        self.slider.setEnabled(True)
        self._fill()
        self._goto(self.cuts[0] if self.cuts else 0.0)
        extra = "" if len(kills) == len(starts) else \
            f" Attention : {len(kills)} kill(s) vu(s) pour {len(starts)} dash, vérifie bien."
        self.status.setText(f"{len(starts)} dash trouvé(s).{extra}")

    def _fill(self):
        self.cuts.sort()
        self.list.clear()
        for i, c in enumerate(self.cuts):
            it = QListWidgetItem(f"dash {i + 1}  —  {fmt(c)}  (frame {int(round(c * self.fps))})")
            it.setData(ROLE, c)
            self.list.addItem(it)
        self.b_go.setEnabled(bool(self.cuts))

    def _goto(self, t):
        self.slider.setValue(int(round(t * self.fps)))
        self._moved(self.slider.value())

    def _moved(self, v):
        t = v / self.fps
        self.pos.setText(fmt(t))
        if self.path:
            self.view.show_at(self.path, max(0.0, t - 0.3 / self.fps))   # tombe pile sur la frame v

    def _here(self):
        return self.slider.value() / self.fps

    def add_cut(self):
        t = self._here()
        if self.path and all(abs(t - c) > 0.5 / self.fps for c in self.cuts):
            self.cuts.append(t)
            self._fill()

    def move_cut(self):
        it = self.list.currentItem()
        if it is not None:
            self.cuts = [c for c in self.cuts if c != it.data(ROLE)] + [self._here()]
            self._fill()

    def del_cut(self):
        it = self.list.currentItem()
        if it is not None:
            self.cuts = [c for c in self.cuts if c != it.data(ROLE)]
            self._fill()

    def export(self):
        if not self.cuts or self._busy():
            return
        folder = proj.clips_dir() / "Dash"
        self.bar.setVisible(True)
        self.b_go.setEnabled(False)
        self.thread = ExportThread(self.path, sorted(self.cuts), self.length, folder, self, self.fps)
        self.thread.progress.connect(lambda v, t: (self.bar.setValue(v), self.status.setText(t)))
        self.thread.done.connect(self._exported)
        self.thread.failed.connect(lambda m: (self.status.setText(f"Export impossible : {m}"),
                                              self.b_go.setEnabled(True)))
        self.thread.start()

    def _exported(self, files):
        folders = proj.load_clip_folders()
        lst = folders.setdefault("Dash", [])
        lst += [f for f in files if f not in lst]
        proj.save_clip_folders(folders)
        self.result = files
        self.bar.setValue(100)
        self.status.setText(f"{len(files)} dash enregistré(s) dans {Path(files[0]).parent} "
                            f"(catégorie Dash de « Mes clips »).")
        self.accept()

    def done(self, r):
        if self._busy():
            self.thread.wait()
        super().done(r)
