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


SW, SH = 192, 108
SHARP = f"crop=iw*0.8:ih*0.6:iw*0.1:ih*0.15,scale={SW}:{SH}"   # grande zone centrale, sans le HUD


def sharp_curve(path):
    """Netteté de chaque frame (gradient moyen). Le dash de Jett floute toute l'image d'un coup
    (traînées de vent + flou de mouvement) alors qu'un flick normal reste net."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
                        "-vf", f"fps={FPS},{SHARP}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(data) // (SW * SH)
    F = data[:n * SW * SH].reshape(n, SH, SW).astype(np.float32)
    gx = np.abs(np.diff(F, axis=2)).mean(axis=(1, 2))
    gy = np.abs(np.diff(F, axis=1)).mean(axis=(1, 2))
    small = F[:, ::3, ::3].reshape(n, -1)
    mot = np.zeros(n)
    mot[1:] = np.abs(np.diff(small, axis=0)).mean(axis=1)
    return gx + gy, mot


def dash_events(sharp, mot):
    """Débuts des passages flous (dash) : la netteté tombe nettement sous celle des frames d'avant."""
    n = len(sharp)
    ratio = np.ones(n)
    for i in range(n):
        ref = sharp[max(0, i - 45):max(0, i - 4)]
        if len(ref) >= 5:
            ratio[i] = sharp[i] / max(1e-3, float(np.percentile(ref, 70)))
    blur = ratio < 0.62
    ev = []
    i = 0
    while i < n:
        if blur[i]:
            j = i
            while j + 1 < n and (blur[j + 1] or (j + 2 < n and blur[j + 2])):
                j += 1
            if j - i + 1 >= 3:
                s = i
                while s > 0 and ratio[s - 1] < 0.85 and i - s < 4:     # 1re frame où le flou commence
                    s -= 1
                ev.append((s, float(ratio[i:j + 1].min()), j - i + 1))
            i = j + 1
        else:
            i += 1
    return ev, ratio


def dash_starts(path):
    """1re frame de chaque dash (en secondes). Un dash = l'image entière devient floue d'un coup.
    On garde ceux qui suivent une bannière de kill (dans les 3 s) + les dash très nets même sans
    bannière détectée (la détection des bannières n'est pas parfaite)."""
    kills = tr.find_kills(path)
    sharp, mot = sharp_curve(path)
    n = len(sharp)
    if n < 4:
        raise ValueError("Vidéo illisible ou trop courte.")
    ev, _ = dash_events(sharp, mot)
    starts = []
    for s, mn, ln in ev:
        after_kill = any(0 < s - k <= 3 * FPS for k in kills)
        if after_kill or (mn < 0.5 and ln >= 5):
            t = s / FPS
            if not starts or t - starts[-1] > 0.4:
                starts.append(round(t, 4))
    if not starts:                                   # secours : ancien critère (gros mouvement après le kill)
        thr = max(18.0, 2.5 * float(np.median(mot[mot > 0]) if np.any(mot > 0) else 0))
        for k in kills:
            big = [i for i in range(k + 2, min(n, k + int(1.5 * FPS))) if mot[i] >= thr]
            if big and (not starts or big[0] / FPS - starts[-1] > 0.4):
                starts.append(round(big[0] / FPS, 4))
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

    def __init__(self, path, cuts, length, folder, parent=None):
        super().__init__(parent)
        self.path, self.cuts, self.length, self.folder = path, cuts, length, Path(folder)

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
                # -ss après -i : coupe exacte à la frame (ré-encodage en très bonne qualité)
                p = subprocess.run([audio.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                                    "-i", self.path, "-ss", f"{a:.4f}", "-t", f"{max(0.05, b - a):.4f}",
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
            self.view.show_at(self.path, t)

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
        self.thread = ExportThread(self.path, sorted(self.cuts), self.length, folder, self)
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
