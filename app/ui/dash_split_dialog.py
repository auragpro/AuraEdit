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


SW, SH = 320, 180



def _feats(path):
    """Une seule lecture de la vidéo (toutes les frames, 320x180), en flux : peu de mémoire même pour
    une compilation de plusieurs Go. Renvoie par frame : netteté, changement de plan, changement de la
    zone de l'arme / du bas de l'image, et ressemblance de la frame d'avant avec les 7 précédentes."""
    p = subprocess.Popen([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
                          "-vf", f"scale={SW}:{SH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=audio._NO_WINDOW)
    size = SW * SH * 3
    sharp, hd, cb, ca, st = [], [], [], [], []
    prev_h = prev_a = None
    hist_b = []                                       # 9 dernières zones de l'arme (vecteurs normés)

    def norm(x):
        x = x.astype(np.float32)
        x -= x.mean(1, keepdims=True)
        return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-6)

    while True:
        buf = p.stdout.read(size * 120)
        if not buf:
            break
        m = len(buf) // size
        if m == 0:
            break
        f = np.frombuffer(buf[:m * size], np.uint8).reshape(m, SH, SW, 3)
        g = f.astype(np.float32).mean(axis=3)
        c = g[:, int(SH * .15):int(SH * .75), int(SW * .1):int(SW * .9)]
        sharp.extend(np.abs(np.diff(c, axis=2)).mean((1, 2)) + np.abs(np.diff(c, axis=1)).mean((1, 2)))
        q = (f[:, ::4, ::4] // 32).astype(np.int32)
        idx = (q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]).reshape(m, -1)
        H = np.stack([np.bincount(r, minlength=512) for r in idx]).astype(np.float32)
        H /= H.sum(1, keepdims=True)
        B = norm(f[:, int(SH * .5)::3, int(SW * .55)::3].reshape(m, -1))
        A = norm(f[:, int(SH * .58)::3, ::3].reshape(m, -1))
        for i in range(m):
            hd.append(1.0 if prev_h is None else float(0.5 * np.abs(H[i] - prev_h).sum()))
            ca.append(1.0 if prev_a is None else float(A[i] @ prev_a))
            cb.append(1.0 if not hist_b else float(B[i] @ hist_b[-1]))
            # pour la frame i : ressemblance de la frame i-1 avec les frames i-8..i-2
            st.append([float(hist_b[-1] @ v) for v in hist_b[:-1]] if len(hist_b) >= 2 else [])
            prev_h, prev_a = H[i], A[i]
            hist_b.append(B[i])
            if len(hist_b) > 8:
                hist_b.pop(0)
    p.wait()
    if not sharp:
        return None
    return np.array(sharp, np.float32), np.array(hd), np.array(cb), np.array(ca), st


def _detect(path, sfps):
    """Numéros de frame (cadence réelle) de la 1re frame de chaque dash :
    l'arme disparaît d'un coup (gros changement en bas de l'image) ET l'image perd de la netteté
    (le dash floute), alors qu'un tir change l'arme sans flouter. Une frame avant = l'arme."""
    r = _feats(path)
    if r is None:
        return [], 0
    s, d, cb, ca, st = r
    n = len(s)
    cuts = [0]
    for i in range(1, n):
        if d[i] > 0.3 and i - cuts[-1] > 20:
            cuts.append(i)
    seg_start = np.zeros(n, int)
    nxt_cut = np.full(n, n)
    k = 0
    for i in range(n):
        while k + 1 < len(cuts) and cuts[k + 1] <= i:
            k += 1
        seg_start[i] = cuts[k]
        nxt_cut[i] = cuts[k + 1] if k + 1 < len(cuts) else n
    refr = int(0.9 * sfps)
    out, last = [], -10 ** 9
    for j in range(8, n - 2):
        a0 = seg_start[j]
        if cb[j] > 0.995 or j - a0 < 4 or nxt_cut[j] - j < 6:   # doublon / trop près d'un changement de plan
            continue
        sr = s[j] / (np.median(s[max(a0, j - 6):j]) + 1e-6)
        if sr >= 0.93 or not (cb[j] < 0.65 or ca[j] < 0.8):
            continue
        # frames j-8..j-2 qui sont dans le même plan
        vals = [v for t, v in zip(range(j - 1 - len(st[j]), j - 1), st[j]) if t >= a0]
        stab = float(np.median(vals)) if vals else 1.0
        if stab < 0.25:                    # juste avant, l'image bougeait déjà (dash déjà commencé)
            continue
        if a0 > last or j - last > refr:
            out.append(j)
            last = j
    return out, n


def dash_starts(path):
    """1re frame de chaque dash (en secondes, sur une frame exacte de la vidéo).
    Réglé sur une vraie compilation (49 dash vérifiés à l'œil) : la frame où l'arme disparaît
    et où la main du dash commence, la frame d'avant montre encore l'arme."""
    sfps = float(tr.source_fps(path))
    frames, n = _detect(path, sfps)
    if n < 4:
        raise ValueError("Vidéo illisible ou trop courte.")
    return [f / sfps for f in frames], n / sfps, []


class DetectThread(QThread):
    done = pyqtSignal(list, float, list)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            s, length, kills = dash_starts(self.path)
            self.done.emit(s, length, kills)
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
                # coupe à la frame exacte : -ss juste avant la frame fa (même méthode que l'aperçu, donc
                # même frame), puis exactement fb-fa frames. Rapide même au milieu d'une longue vidéo.
                fa = int(round(a * self.fps))
                fb = int(round(b * self.fps)) if i + 1 < len(self.cuts) else None
                cmd = [audio.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                       "-ss", f"{max(0.0, (fa - 0.3) / self.fps):.6f}", "-i", self.path]
                if fb is not None:
                    cmd += ["-frames:v", str(max(1, fb - fa)), "-t", f"{(fb - fa) / self.fps:.6f}"]
                cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "12",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", str(target)]
                p = subprocess.run(cmd, capture_output=True, creationflags=audio._NO_WINDOW)
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
        self.sides = {}                    # coupe -> "gauche" / "droite" (main où le dash va dans la partie Dash)
        self.result_sides = {}
        self.thread = None
        info = QLabel("Choisis ta compilation : je repère la 1re frame de chaque dash (la frame où l'arme "
                      "disparaît et où la main du dash apparaît). Vérifie CHAQUE coupe (clique-la dans la liste) : corrige avec ◀ -1 / +1 ▶ puis "
                      "« ↔ Déplacer ici », ajoute une coupe oubliée avec « ➕ Coupe ici », ou supprime une coupe "
                      "en trop. Pour chaque dash, choisis où il va dans la partie Dash : ⬅ Main gauche (touche G) "
                      "ou Main droite ➡ (touche D), l'app passe ensuite au dash suivant. Chaque dash est ensuite ajouté à part (dash1, dash2...) dans l'app, sans créer de fichier sur ton PC : il lit directement ta compilation.")
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
        b_g, b_d, b_n = QPushButton("⬅ Main gauche (G)"), QPushButton("Main droite (D) ➡"), QPushButton("Pas dans Dash")
        b_g.clicked.connect(lambda: self.set_side("gauche"))
        b_d.clicked.connect(lambda: self.set_side("droite"))
        b_n.clicked.connect(lambda: self.set_side(None))
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("G"), self, activated=lambda: self.set_side("gauche"))
        QShortcut(QKeySequence("D"), self, activated=lambda: self.set_side("droite"))
        side_row = QHBoxLayout()
        for w in (b_g, b_d, b_n):
            side_row.addWidget(w)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.b_go = QPushButton("✂ Couper et ajouter les dash")
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
        right.addWidget(QLabel("Envoyer le dash sélectionné dans la partie Dash :"))
        right.addLayout(side_row)
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
        self.status.setText("Je cherche les dash (lecture de toutes les frames, ça peut prendre une minute)...")
        self.thread = DetectThread(f, self)
        self.thread.done.connect(self._found)
        self.thread.failed.connect(lambda m: self.status.setText(f"Détection impossible : {m}"))
        self.thread.start()

    def _found(self, starts, length, kills):
        self.length, self.fps = length, float(tr.source_fps(self.path))
        self.cuts = list(starts)
        self.sides = {}
        self.slider.setRange(0, max(1, int(length * self.fps) - 1))
        self.slider.setEnabled(True)
        self._fill()
        self._goto(self.cuts[0] if self.cuts else 0.0)
        self.status.setText(f"{len(starts)} dash trouvé(s). Vérifie chaque coupe (clique-la dans la liste).")

    def _fill(self):
        self.cuts.sort()
        self.list.clear()
        for i, c in enumerate(self.cuts):
            side = {"gauche": "⬅ gauche", "droite": "droite ➡"}.get(self.sides.get(c), "—")
            it = QListWidgetItem(f"dash {i + 1}  —  {fmt(c)}  (frame {int(round(c * self.fps))})   [{side}]")
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
            old, new = it.data(ROLE), self._here()
            self.cuts = [c for c in self.cuts if c != old] + [new]
            if old in self.sides:
                self.sides[new] = self.sides.pop(old)
            self._fill()
            self._select(new)

    def del_cut(self):
        it = self.list.currentItem()
        if it is not None:
            self.cuts = [c for c in self.cuts if c != it.data(ROLE)]
            self._fill()

    def _select(self, c):
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE) == c:
                self.list.setCurrentRow(i)
                return

    def set_side(self, side):
        it = self.list.currentItem()
        if it is None:
            return
        c = it.data(ROLE)
        if side:
            self.sides[c] = side
        else:
            self.sides.pop(c, None)
        row = self.list.currentRow()
        self._fill()
        if row + 1 < self.list.count():                 # passe direct au dash suivant
            self.list.setCurrentRow(row + 1)
            self._goto(self.list.item(row + 1).data(ROLE))
        else:
            self.list.setCurrentRow(row)

    def export(self):
        """Aucun fichier créé : chaque dash est un morceau de la compilation, gardé dans l'app
        (début et fin à la frame exacte)."""
        if not self.cuts or self._busy():
            return
        from app.core import vclip
        folders = proj.load_clip_folders()
        lst = folders.setdefault("Dash", [])
        used = [int(m.group(1)) for c in lst if (m := re.fullmatch(r"dash(\d+)", vclip.stem(c)))]
        num = max(used, default=0)
        cuts = sorted(self.cuts)
        bounds = cuts + [self.length]
        files, self.result_sides = [], {}
        for i, c in enumerate(cuts):
            num += 1
            fa = int(round(c * self.fps))
            fb = int(round(bounds[i + 1] * self.fps)) if i + 1 < len(cuts) else None
            end = fb / self.fps if fb is not None else self.length
            v = vclip.make(self.path, f"dash{num}", fa / self.fps, end)
            files.append(v)
            self.result_sides[v] = self.sides.get(c)
        lst += [f for f in files if f not in lst]
        proj.save_clip_folders(folders)
        self.result = files
        self.accept()

    def done(self, r):
        if self._busy():
            self.thread.wait()
        super().done(r)
