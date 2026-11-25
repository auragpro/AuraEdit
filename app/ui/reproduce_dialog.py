"""Fenêtre « Reproduire un edit » : on donne un edit fini, l'app trouve toutes les transitions,
puis on choisit plan par plan le clip à mettre (un couteau de ma bibliothèque, un dash, un kunai)."""
import json
import random
import time
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                             QListWidgetItem, QMenu, QMessageBox, QPushButton, QSizePolicy, QSlider,
                             QSplitter, QStackedWidget, QVBoxLayout, QWidget, QComboBox, QSpinBox, QCheckBox)

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


class ThumbThread(QThread):
    """Miniatures de la timeline des plans, faites en arrière-plan (jamais dans l'interface)."""
    got = pyqtSignal(int, int, bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        import collections
        import threading
        self.jobs = collections.deque()
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.cache = {}
        self.stop = False

    def add(self, jobs, first=False):
        with self.lock:
            if first:
                self.jobs.extendleft(reversed(jobs))        # changement de clip : tout de suite
            else:
                self.jobs.extend(jobs)
        self.wake.set()

    def clear(self):
        with self.lock:
            self.jobs.clear()

    def run(self):
        while not self.stop:
            with self.lock:
                job = self.jobs.popleft() if self.jobs else None
            if job is None:
                self.wake.wait(0.3)
                self.wake.clear()
                continue
            i, gen, path, t = job
            key = (str(path), round(float(t), 3))
            data = self.cache.get(key)
            if data is None:
                try:
                    data = tr.grab_png(path, t, 160) or b""
                except Exception:
                    data = b""
                self.cache[key] = data
            if data and not self.stop:
                self.got.emit(i, gen, data)


class Preview(QLabel):
    """Image de la vidéo à un instant (mise à jour un peu après le dernier changement). S'agrandit avec la page.
    L'image est lue en arrière-plan : l'interface ne se fige jamais."""
    _got = pyqtSignal(int, bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._got.connect(self._loaded)
        self._lgen = 0
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #05080f; border-radius: 12px;")
        self.path, self.t = None, 0.0
        self._pix = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._load)

    def show_at(self, path, t):
        self.stop()
        self.path, self.t = path, t
        self.timer.start(60)

    def _load(self):
        if not self.path:
            return
        import threading
        self._lgen += 1
        gen, path, t = self._lgen, self.path, self.t

        def run():
            try:
                data = tr.grab_png(path, t, 960) or b""
            except Exception:                    # noqa: BLE001
                data = b""
            try:
                self._got.emit(gen, data)
            except RuntimeError:                 # page fermée entre-temps
                pass
        threading.Thread(target=run, daemon=True).start()

    def _loaded(self, gen, data):
        if gen != self._lgen or self.playing():
            return
        pix = QPixmap()
        if data and pix.loadFromData(data):
            self._pix = pix
            self._fit()

    def _fit(self):
        if self._pix is not None:
            self.setPixmap(self._pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    # ---------------------------------------------------------------- lecture (barre espace)
    PW, PH, PFPS = 384, 216, 30

    def play(self, path, start, dur, t0=None):
        self.play_seq([("stream", path, start, dur)], t0)

    def play_seq(self, items, t0=None):
        """Lit une suite de morceaux sans attendre : ("stream", clip, début, durée) lu tel quel,
        ("times", clip, [temps source à 30 i/s]) pour un time remap, ("black", nb d'images) = écran noir.
        t0 : horloge commune (time.monotonic) pour que 2 vidéos restent synchronisées."""
        import subprocess
        import threading
        import time as _t
        from app.core import audio
        self.stop()
        frames = {}
        self._frames, self._i, self._alive, self._decoding = frames, 0, True, True
        self._gen = gen = getattr(self, "_gen", 0) + 1
        self._t0 = t0 or _t.monotonic()
        self._last = None
        if getattr(self, "_ptimer", None) is None:
            self._ptimer = QTimer(self)
            self._ptimer.timeout.connect(self._tick)
        W, H, F = self.PW, self.PH, self.PFPS
        size = W * H * 3
        black = bytes(size)
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
              f"format=rgb24")

        def alive():
            return self._alive and self._gen == gen

        def wait_room(n):
            while alive() and n - self._i > 90:          # pas plus de 3 s d'avance (mémoire)
                _t.sleep(0.02)

        def proc(args, fps):
            return subprocess.Popen([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args, "-an", "-vf",
                                     f"fps={fps},{vf}", "-f", "rawvideo", "-"], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                    creationflags=audio._NO_WINDOW)

        def run():
            n = 0
            try:
                for it in items:
                    if not alive():
                        break
                    if it[0] == "black":
                        for _ in range(it[1]):
                            wait_room(n)
                            frames[n] = black
                            n += 1
                    elif it[0] == "stream":
                        _, path, start, dur = it
                        p = proc([*vclip.input_args(path, ss=max(0.0, start)), "-t", f"{max(0.04, dur):.3f}"], F)
                        while alive():
                            wait_room(n)
                            buf = p.stdout.read(size)
                            if len(buf) < size:
                                break
                            frames[n] = buf
                            n += 1
                        p.kill()
                    else:                                     # time remap : on pioche les bonnes images
                        _, path, times = it
                        lo, hi = max(0.0, min(times) - 0.05), max(times) + 0.05
                        p = proc([*vclip.input_args(path, ss=lo), "-t", f"{hi - lo:.3f}"], 60)
                        src = []
                        while alive():
                            buf = p.stdout.read(size)
                            if len(buf) < size:
                                break
                            src.append(buf)
                        p.kill()
                        for t in times:
                            wait_room(n)
                            frames[n] = src[min(len(src) - 1, max(0, int(round((t - lo) * 60))))] if src else black
                            n += 1
            except OSError:
                pass
            if self._gen == gen:
                self._decoding = False
                self._total = n
        self._total = None
        threading.Thread(target=run, daemon=True).start()
        self._ptimer.start(int(1000 / F))

    def stop(self):
        self._alive = False
        self._decoding = False
        if getattr(self, "_ptimer", None):
            self._ptimer.stop()

    def playing(self):
        return bool(getattr(self, "_ptimer", None) and self._ptimer.isActive())

    def _tick(self):
        import time as _t
        from PyQt6.QtGui import QImage
        idx = int((_t.monotonic() - self._t0) * self.PFPS)
        if self._total is not None and idx >= self._total:
            self.stop()                                    # fin de la lecture
            return
        fr = self._frames
        while self._i < idx and self._i in fr:            # on libère les images déjà passées
            fr.pop(self._i, None)
            self._i += 1
        buf = fr.get(idx)
        if buf is None:
            return                                         # pas encore décodée : on garde l'image d'avant
        self._i = idx
        img = QImage(buf, self.PW, self.PH, self.PW * 3, QImage.Format.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(img).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))


class TextPreview(Preview):
    """Image du clip + le texte posé dessus (biseautage, incrustation), recalculée à chaque réglage."""
    PREV = (640, 360)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg, self._base = None, None

    def set_cfg(self, cfg):
        self.cfg = cfg
        self._compose()

    def _loaded(self, gen, data):
        if gen != self._lgen:
            return
        from PyQt6.QtGui import QImage
        import numpy as np
        img = QImage.fromData(data)
        if img.isNull():
            return
        w, h = self.PREV
        img = img.scaled(w, h).convertToFormat(QImage.Format.Format_RGB888)
        ptr = img.constBits()
        ptr.setsize(img.bytesPerLine() * h)
        self._base = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())[:, :w * 3].reshape(h, w, 3).copy()
        self._compose()

    def _compose(self):
        if self._base is None:
            return
        import numpy as np
        from PyQt6.QtGui import QImage
        from app.core import textfx
        out = self._base
        w, h = self.PREV
        if self.cfg and self.cfg.get("texte"):
            try:
                c = textfx.full(self.cfg)
                out = textfx.blend(self._base, textfx.layer(c, w, h, scale=w / 1920), c["mode"])
            except Exception:                    # noqa: BLE001
                out = self._base
        out = np.ascontiguousarray(out)
        self._pix = QPixmap.fromImage(QImage(out.data, w, h, w * 3, QImage.Format.Format_RGB888).copy())
        self._fit()


DUR_LABELS = {1: "très court", 3: "court", 5: "normal", 7: "long", 9: "très long"}


class DurCombo(QComboBox):
    """Durée du shake (1 à 9) en liste déroulante ; mêmes fonctions qu'une case numérique."""
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        for i in range(1, 10):
            self.addItem(f"Durée {i}" + (f" · {DUR_LABELS[i]}" if i in DUR_LABELS else ""), i)
        self.setCurrentIndex(4)
        self.currentIndexChanged.connect(lambda _: self.valueChanged.emit(self.value()))

    def value(self):
        return int(self.currentData() or 5)

    def setValue(self, v):
        self.setCurrentIndex(max(0, min(8, int(v) - 1)))


GROUP_COLORS = ["#ff4655", "#3d9bff", "#ffb020", "#2ed47a", "#b06bff", "#ff6bd5", "#20d5d5", "#f5f5f5",
                "#ff8a3d", "#9be22d"]


def group_key(cfg):
    return (cfg["sens"], cfg["niveau"], cfg["duree"]) if cfg else None


class MarkerBar(QWidget):
    """Barre de temps du montage : un losange par coupe (shake). Une couleur par groupe de réglages,
    plus gros = plus fort, gris = pas de shake. Clic = choisir ; Ctrl/Maj + clic ou glisser = plusieurs."""
    picked = pyqtSignal(int)
    selection = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(78)
        self.total, self.cuts, self.cfgs, self.sel = 1.0, [], [], 0
        self.chosen = set()
        self.groups = {}
        self._press = None

    def set(self, total, cuts, cfgs):
        self.total, self.cuts, self.cfgs = max(0.01, total), list(cuts), list(cfgs)
        keys = []
        for c in self.cfgs:
            k = group_key(c)
            if k and k not in keys:
                keys.append(k)
        self.groups = {k: GROUP_COLORS[i % len(GROUP_COLORS)] for i, k in enumerate(sorted(keys))}
        self.update()

    def select(self, i):
        self.sel = i
        if i not in self.chosen:
            self.chosen = {i}
        self.update()

    def _x(self, t):
        return 12 + (self.width() - 24) * t / self.total

    def _nearest(self, x):
        return min(range(len(self.cuts)), key=lambda i: abs(self._x(self.cuts[i]) - x))

    def mousePressEvent(self, e):
        if not self.cuts:
            return
        x = e.position().x()
        i = self._nearest(x)
        mods = e.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                a, b = sorted((self.sel, i))
                self.chosen |= set(range(a, b + 1))
            elif i in self.chosen and len(self.chosen) > 1:
                self.chosen.discard(i)
            else:
                self.chosen.add(i)
            self.sel = i
            self.update()
            self.selection.emit(sorted(self.chosen))
            return
        self._press = x
        self.chosen = {i}
        self.sel = i
        self.update()
        self.picked.emit(i)
        self.selection.emit([i])

    def mouseMoveEvent(self, e):
        if self._press is None or not self.cuts:
            return
        a, b = sorted((self._press, e.position().x()))
        if b - a < 6:
            return
        self.chosen = {i for i, c in enumerate(self.cuts) if a - 6 <= self._x(c) <= b + 6} or self.chosen
        self.update()
        self.selection.emit(sorted(self.chosen))

    def mouseReleaseEvent(self, e):
        self._press = None

    def paintEvent(self, e):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QColor, QPainter, QPolygonF
        from .style import BORDER, PANEL_2
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        mid = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PANEL_2))
        p.drawRoundedRect(8, int(mid - 8), self.width() - 16, 16, 8, 8)
        p.setBrush(QColor(BORDER))
        for c in self.cuts:
            p.drawRect(int(self._x(c)) - 1, int(mid - 8), 2, 16)
        for i, c in enumerate(self.cuts):
            cfg = self.cfgs[i] if i < len(self.cfgs) else None
            r = 5 + (cfg["niveau"] * 2 if cfg else 0)
            x = self._x(c)
            col = QColor(self.groups.get(group_key(cfg), "#ff4655")) if cfg else QColor("#555a66")
            if i in self.chosen:
                p.setBrush(QColor("#ffffff"))
                g = 4 if i == self.sel else 3
                p.drawPolygon(QPolygonF([QPointF(x, mid - r - g), QPointF(x + r + g, mid), QPointF(x, mid + r + g),
                                         QPointF(x - r - g, mid)]))
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(x, mid - r), QPointF(x + r, mid), QPointF(x, mid + r),
                                     QPointF(x - r, mid)]))


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
        self.fx = {}                      # par plan : {"fondu": ms, "shake": None / {"off"} / réglage}
        self.texts = []                   # textes de l'edit (étape 3)
        self.seg = 0
        self.thread = None
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_cuts())
        self.stack.addWidget(self._page_choose())
        self.stack.addWidget(self._page_shakes())
        self.stack.addWidget(self._page_texts())          # index 3 : textes (avant les shakes)
        from PyQt6.QtGui import QKeySequence, QShortcut
        sc = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self._space)
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
        left.addWidget(self.view, 1)
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
                        "overlays": {str(k): v for k, v in self.overlays.items()},
                        "fx": {str(k): v for k, v in self.fx.items()}, "textes": self.texts, "date": time.time()}
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
        self.fx = {int(k): v for k, v in (e.get("fx") or {}).items() if isinstance(v, dict)}
        self.texts = [t for t in (e.get("textes") or []) if isinstance(t, dict)]
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
        self.choices, self.overlays, self.fx, self.texts = [], {}, {}, []
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
        # timeline : une miniature par plan (le clip choisi), clic = aller au plan
        self.tl = QListWidget()
        self.tl.setViewMode(QListWidget.ViewMode.IconMode)
        self.tl.setFlow(QListWidget.Flow.LeftToRight)
        self.tl.setWrapping(False)
        self.tl.setIconSize(QSize(96, 54))
        self.tl.setGridSize(QSize(106, 80))
        self.tl.setFixedHeight(100)
        self.tl.setMovement(QListWidget.Movement.Static)
        self.tl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tl.itemClicked.connect(lambda it: self._show_seg(self.tl.row(it)))
        self.tl_gen = []
        self.tl_thread = ThumbThread(self)
        self.tl_thread.got.connect(self._tl_icon)
        self.tl_thread.start()
        from .style import BORDER, PANEL, PANEL_2, RED as ACC
        from .tabs.clips_tab import CARD_H, CARD_W
        self.grid = QListWidget()                       # grosses cartes des couteaux / dash / kunai... (défilant)
        self.grid.setObjectName("skins")
        self.grid.setStyleSheet(
            f"QListWidget#skins {{ background: transparent; border: none; }}"
            f"QListWidget#skins::item {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px;"
            f" margin: 4px; padding: 6px 4px 8px 4px; color: white; font-weight: 600; }}"
            f"QListWidget#skins::item:hover {{ border: 1px solid #ffffff55; background: {PANEL_2}; }}"
            f"QListWidget#skins::item:selected {{ border: 2px solid {ACC}; background: {PANEL_2}; }}"
            f"QListWidget#skins::item:disabled {{ color: #666; }}")
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setIconSize(QSize(CARD_W, CARD_H))
        self.grid.setGridSize(QSize(CARD_W + 20, CARD_H + 62))
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.grid.itemClicked.connect(self._pick)
        b_prev = QPushButton("←  Plan précédent")
        b_prev.clicked.connect(lambda: self._show_seg(self.seg - 1))
        self.b_over = QPushButton("🟩 Superposer une vidéo (fond vert ou normale)")
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
        # effets à l'entrée de ce plan (sur la coupe juste avant) : fondu d'opacité + shake de cette coupe
        self.fx_fade = QSpinBox()
        self.fx_fade.setRange(0, 1500)
        self.fx_fade.setSingleStep(20)
        self.fx_fade.setPrefix("Fondu : ")
        self.fx_fade.setSuffix(" ms")
        self.fx_fade.setSpecialValueText("Fondu : aucun")
        self.fx_fade.setToolTip("Le clip de ce plan commence quelques millisecondes plus tôt et apparaît "
                                "de 0 à 100 % d'opacité par-dessus le clip d'avant.")
        self.fx_shake = QComboBox()
        self.fx_shake.addItem("Shake : réglage global", None)
        self.fx_shake.addItem("Shake : aucun", "off")
        for sens in ("in", "out"):
            for n in range(1, 6):
                self.fx_shake.addItem(f"Shake {sens.upper()} {n}x", (sens, n))
        self.fx_dur = DurCombo()
        for w_ in (self.fx_fade, self.fx_dur):
            w_.valueChanged.connect(self._fx_changed)
        self.fx_shake.currentIndexChanged.connect(self._fx_changed)
        # multi-kill : ce plan devient un seul clip 2K / 3K / 4K (on enlève les transitions qui suivent)
        self.b_multi = []
        for n in (2, 3, 4):
            b = QPushButton(f"{n}K")
            b.setToolTip(f"{n}K dismiss / flick away : j'enlève les {n} transitions qui suivent ce plan "
                         "(un seul clip pour tout le passage), puis tu fais son time remap manuel.")
            b.clicked.connect(lambda _=False, n=n: self._multikill(n))
            self.b_multi.append(b)
        self.b_man = QPushButton("🎛  Time remap manuel")
        self.b_man.setToolTip("Keyframes et courbes comme dans After Effects, pour ce plan.")
        self.b_man.clicked.connect(self._manual)
        self.b_align = QPushButton("🎯  Caler sur l'edit")
        self.b_align.setToolTip("Le clip commence sur la même frame que le plan de l'edit (même cut). "
                                "Sinon : sur la 1re frame du flick away.")
        self.b_align.clicked.connect(lambda: self.align(False))
        self.b_align_all = QPushButton("🎯  Tout caler")
        self.b_align_all.setToolTip("Cale le début de tous les clips choisis sur l'edit.")
        self.b_align_all.clicked.connect(lambda: self.align(True))
        self.b_cmp = QPushButton("🆚  Comparer avec l'edit")
        self.b_cmp.setToolTip("Aperçu rapide : l'edit d'exemple à gauche, tes clips choisis à droite (sans ralentis), "
                              "avec le son de l'edit.")
        self.b_cmp.clicked.connect(self.compare)
        self.b_full = QPushButton("⛶  Plein écran")
        self.b_full.setObjectName("pill")
        self.b_full.clicked.connect(self._fullscreen)

        def kick(txt):
            k = QLabel(txt)
            k.setObjectName("kicker")
            return k

        # à gauche : les 2 vidéos (plan de l'edit / ton clip) + timeline
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        lv.setSpacing(6)
        lv.addWidget(kick("LE PLAN DANS L'EDIT"))
        lv.addWidget(self.seg_view, 1)
        lv.addWidget(kick("TON CLIP"))
        lv.addWidget(self.pick_view, 1)
        lv.addWidget(self.pick_name)
        brow = QHBoxLayout()
        brow.addWidget(self.b_remap)
        brow.addWidget(self.b_over)
        lv.addLayout(brow)
        lv.addWidget(kick("ENTRÉE DE CE PLAN (LA COUPE JUSTE AVANT)"))
        frow = QHBoxLayout()
        self.fx_fade.hide()
        self.b_fade = QPushButton("🌗  Fondu")
        self.b_fade.setToolTip("Fondu d'opacité vers ce plan : choisis juste où il commence, le reste se fait seul.")
        self.b_fade.clicked.connect(self._fade_button)
        frow.addWidget(self.b_fade)
        frow.addWidget(self.fx_shake)
        frow.addWidget(self.fx_dur)
        frow.addStretch(1)
        lv.addLayout(frow)
        lv.addWidget(kick("MULTI-KILL · TIME REMAP MANUEL · DÉBUT DU CLIP"))
        mrow = QHBoxLayout()
        for b in self.b_multi:
            mrow.addWidget(b)
        mrow.addWidget(self.b_man)
        mrow.addWidget(self.b_align)
        mrow.addStretch(1)
        lv.addLayout(mrow)
        lv.addWidget(kick("TIMELINE DE TES CLIPS — CLIQUE UNE IMAGE POUR ALLER AU PLAN"))
        lv.addWidget(self.tl)
        # à droite : la liste des couteaux, dash, kunai... qu'on fait défiler
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        rv.setSpacing(6)
        rv.addWidget(kick("TES CLIPS — CLIQUE POUR CHOISIR"))
        rv.addWidget(self.grid, 1)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)

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
        trow.addWidget(self.b_align_all)
        trow.addWidget(self.b_cmp)
        trow.addWidget(self.b_full)
        lay.addLayout(trow)
        lay.addWidget(info)
        lay.addWidget(split, 1)
        lay.addLayout(row)
        return w

    def _fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showNormal()
            self.b_full.setText("⛶  Plein écran")
        else:
            win.showFullScreen()
            self.b_full.setText("🗗  Quitter le plein écran")

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
        self._fill_timeline()
        self._show_seg(0)

    # ------------------------------------------------------------ timeline
    def _tl_src(self, i):
        """Image à montrer pour le plan i : le clip choisi (au début de son time remap), sinon l'edit."""
        ch = self.choices[i] if i < len(self.choices) else None
        if ch:
            rm = tr.clip_remaps().get(ch[1])
            s0 = tr.clip_starts().get(str(ch[1]))
            return ch[1], float(rm["debut"]) if rm else (s0 if s0 is not None else 0.5)
        return self.path, (self.bounds[i] + self.bounds[i + 1]) / 2

    def _tl_text(self, i):
        return f"{i + 1}" + ("" if self.choices[i] else " · vide")

    def _stop_thumbs(self):
        if self.tl_thread is not None:
            self.tl_thread.stop = True
            self.tl_thread.wake.set()
            self.tl_thread.wait(3000)
            self.tl_thread = None

    def _fill_timeline(self):
        if self.tl_thread is None:
            return
        self.tl_thread.clear()
        self.tl.clear()
        n = len(self.bounds) - 1
        self.tl_gen = [g + 1 for g in (self.tl_gen + [0] * n)[:n]]
        jobs = []
        for i in range(n):
            it = QListWidgetItem(self._tl_text(i))
            it.setToolTip(f"Plan {i + 1} : {fmt(self.bounds[i])} → {fmt(self.bounds[i + 1])}")
            self.tl.addItem(it)
            path, t = self._tl_src(i)
            jobs.append((i, self.tl_gen[i], path, t))
        self.tl_thread.add(jobs)

    def _tl_icon(self, i, gen, data):
        if i >= len(self.tl_gen) or gen != self.tl_gen[i]:
            return                                   # image d'un ancien clip : ignorée
        it = self.tl.item(i)
        pix = QPixmap()
        if it is not None and pix.loadFromData(data):
            it.setIcon(QIcon(pix))

    def _tl_update(self, i):
        it = self.tl.item(i)
        if it is None or self.tl_thread is None or i >= len(self.tl_gen):
            return
        it.setText(self._tl_text(i))
        self.tl_gen[i] += 1
        path, t = self._tl_src(i)
        self.tl_thread.add([(i, self.tl_gen[i], path, t)], first=True)

    def _fill_grid(self):
        from .tabs.clips_tab import _rounded, _symbol
        self.grid.clear()
        for name, clips, img in self._pools():
            pix = QPixmap(img) if img and Path(img).is_file() else QPixmap()
            card = QIcon(_rounded(pix)) if not pix.isNull() else None
            sym = proj.SPECIAL_FOLDERS.get(name, "")
            attr = proj.SPECIAL_ATTR.get(name)
            if attr:
                # Dash / Kunai / Dash back / Dismiss : une case main gauche et une case main droite
                st = getattr(self.project, attr, None)
                rest = list(clips)
                for side, label in (("gauche", "⬅ gauche"), ("droite", "droite ➡")):
                    part = [c for c in clips if st and c in getattr(st, side, [])]
                    rest = [c for c in rest if c not in part]
                    it = QListWidgetItem(QIcon(_symbol(sym or "🎬")), f"{name}  {label}\n{len(part)} clip(s)")
                    it.setData(ROLE, (name, part))
                    if not part:
                        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                        it.setToolTip("Aucun clip pour cette main : ajoute-en avec « ➕ Ajouter des clips ».")
                    self.grid.addItem(it)
                if rest:
                    it = QListWidgetItem(QIcon(_symbol(sym or "🎬")), f"{name}  (main ?)\n{len(rest)} clip(s)")
                    it.setData(ROLE, (name, rest))
                    self.grid.addItem(it)
                continue
            it = QListWidgetItem(card or QIcon(_symbol(sym or "🔪")), f"{name}\n{len(clips)} clip(s)")
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
        self.b_go.setText("Étape 3 : textes  →" if i == n - 1 else "Plan suivant  →")
        if self.tl.count() == n:
            self.tl.setCurrentRow(i)
            self.tl.scrollToItem(self.tl.item(i))
        self._show_fx()
        self._show_pick()

    def _show_fx(self):
        fx = self.fx.get(self.seg) or {}
        sh = fx.get("shake")
        for w_ in (self.fx_fade, self.fx_shake, self.fx_dur):
            w_.blockSignals(True)
        self.fx_fade.setValue(int(fx.get("fondu") or 0))
        if sh is None:
            self.fx_shake.setCurrentIndex(0)
        elif sh.get("off"):
            self.fx_shake.setCurrentIndex(1)
        else:
            idx = self.fx_shake.findData((sh.get("sens", "out"), int(sh.get("niveau", 3))))
            self.fx_shake.setCurrentIndex(max(0, idx))
            self.fx_dur.setValue(int(sh.get("duree", 5)))
        self.fx_dur.setEnabled(self.fx_shake.currentIndex() > 1)
        for w_ in (self.fx_fade, self.fx_shake, self.fx_dur):
            w_.blockSignals(False)
            w_.setEnabled(self.seg > 0 and (w_ is not self.fx_dur or self.fx_shake.currentIndex() > 1))
        f = int(fx.get("fondu") or 0)
        self.b_fade.setText(f"🌗  Fondu ✓  ({f} ms)" if f else "🌗  Fondu")
        self.b_fade.setEnabled(self.seg > 0)
        n = fx.get("multi")
        self.b_man.setText(("🎛  Time remap manuel ✓" if fx.get("manuel") else "🎛  Time remap manuel")
                           + (f"  ({n}K)" if n else ""))
        last = len(self.bounds) - 2
        for b in self.b_multi:
            b.setEnabled(self.seg < last)

    def _fx_changed(self, *_):
        data = self.fx_shake.currentData()
        if data is None:
            sh = None
        elif data == "off":
            sh = {"off": True}
        else:
            sh = {"sens": data[0], "niveau": data[1], "duree": self.fx_dur.value()}
        self.fx_dur.setEnabled(self.fx_shake.currentIndex() > 1)
        fx = dict(self.fx.get(self.seg) or {})
        fx.update(fondu=self.fx_fade.value(), shake=sh)
        if not fx["fondu"] and sh is None and not fx.get("manuel") and not fx.get("multi"):
            self.fx.pop(self.seg, None)
        else:
            self.fx[self.seg] = fx
        self.save_state()

    # ------------------------------------------------------------ lecture (espace)
    def _clip_start(self, path):
        rm = tr.clip_remaps().get(path)
        s0 = tr.clip_starts().get(str(path))
        return float(rm["debut"]) if rm else float(s0 or 0.0)

    def _plan_item(self, k):
        """Morceau à lire pour le plan k : ton clip avec SON time remap (ou écran noir si pas de clip)."""
        F = Preview.PFPS
        d = self.bounds[k + 1] - self.bounds[k]
        n = max(1, int(round(d * F)))
        ch = self.choices[k] if k < len(self.choices) else None
        if not ch:
            return ("black", n)
        path = ch[1]
        fx = self.fx.get(k) or {}
        try:
            man = fx.get("manuel")
            if man and man.get("keys"):
                ts = tr.manual_times(man["keys"], man.get("courbes") or [], d)
                return ("times", path, [ts[min(len(ts) - 1, int(i * tr.FPS / F))] for i in range(n)])
            rm = tr.clip_remaps().get(path) or self.project.remaps.get(path)
            if rm:
                rcfg = tr.cfg_for(rm)
                rcfg["duree_ralenti"] = max(0.1, d - int(rcfg.get("frames_retour", 7)) / tr.FPS)
                total = sum(tr.timing(rcfg))
                return ("times", path, [tr.source_time(min(i / F, total), float(rm["debut"]), float(rm["fin"]), rcfg)
                                        for i in range(n)])
        except Exception:                          # noqa: BLE001
            pass
        return ("stream", path, self._clip_start(path), d)

    def _space(self):
        import time as _t
        page = self.stack.currentIndex()
        if page == 1:
            views = (self.seg_view, self.pick_view)
            if any(v.playing() for v in views):
                for v in views:
                    v.stop()
                self._show_seg(self.seg)
                return
            # lecture continue à partir de ce plan : l'edit à gauche, tes clips (time remap compris) en dessous
            a = self.bounds[self.seg]
            t0 = _t.monotonic() + 0.15
            self.seg_view.play(self.path, a, self.length - a, t0)
            self.pick_view.play_seq([self._plan_item(k) for k in range(self.seg, len(self.bounds) - 1)], t0)
        elif page == 2:
            if self.sh_view.playing():
                self.sh_view.stop()
                self._sh_select(self.sh_sel)
                return
            e = self.sh_tl[self.sh_sel + 1] if self.sh_sel + 1 < len(self.sh_tl) else None
            if e:
                self.sh_view.play(e["clip"], self._clip_start(e["clip"]), e["duree"])

    # ------------------------------------------------------------ fondu (bouton)
    def _fade_button(self):
        fx = self.fx.get(self.seg) or {}
        if fx.get("fondu"):
            menu = QMenu(self)
            a1 = menu.addAction("Changer où le fondu commence...")
            a2 = menu.addAction("Enlever le fondu")
            act = menu.exec(self.b_fade.mapToGlobal(self.b_fade.rect().bottomLeft()))
            if act is a2:
                self.fx_fade.setValue(0)
                self._show_fx()
                return
            if act is not a1:
                return
        ms = self._pick_fade_start(int(fx.get("fondu") or 200))
        if ms:
            self.fx_fade.setValue(ms)
            self._show_fx()

    def _pick_fade_start(self, cur_ms):
        """Petite fenêtre : sur TON clip, on choisit la frame où le fondu commence (avant le début du clip)."""
        ch = self.choices[self.seg] if self.seg < len(self.choices) else None
        if not ch:
            QMessageBox.information(self, "Fondu", "Choisis d'abord le clip de ce plan : le fondu se fait sur lui.")
            return 0
        path = ch[1]
        cut = self._clip_start(path)                     # là où ton clip commence dans le montage
        lo = max(0.0, cut - 1.5)
        if cut - lo < 2 / 60:
            QMessageBox.information(self, "Fondu", "Ton clip commence tout au début de la vidéo : il n'y a pas "
                                                   "d'images avant pour faire le fondu. Recule son début "
                                                   "(time remap ou « Sans time remap ») pour en avoir.")
            return 0
        fps = 60.0
        n = max(1, int(round((cut - lo) * fps)))
        dlg = QDialog(self)
        dlg.setWindowTitle("Fondu : où il commence")
        dlg.resize(720, 520)
        view = Preview()
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(0, n - 1)
        sl.setValue(max(0, n - max(1, int(round(cur_ms / 1000 * fps)))))
        lab = QLabel()
        lab.setWordWrap(True)

        def upd(v):
            t = lo + v / fps
            lab.setText(f"Le fondu commence sur cette image de ton clip : {(cut - t) * 1000:.0f} ms avant son début. "
                        f"Ton clip apparaît de 0 à 100 % d'opacité par-dessus le clip d'avant jusqu'à la coupe.")
            view.show_at(path, t)
        sl.valueChanged.connect(upd)
        upd(sl.value())
        ok = QPushButton("Valider le fondu")
        ok.setObjectName("primary")
        ok.clicked.connect(dlg.accept)
        k = QLabel(f"FONDU D'OPACITÉ · {vclip.name(path).upper()} · CHOISIS LE DÉBUT")
        k.setObjectName("kicker")
        lay = QVBoxLayout(dlg)
        lay.addWidget(k)
        lay.addWidget(view, 1)
        lay.addWidget(sl)
        lay.addWidget(lab)
        lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignRight)
        if not dlg.exec():
            return 0
        return max(20, int(round((cut - (lo + sl.value() / fps)) * 1000)))

    # ------------------------------------------------------------ étape 3 : textes
    def _page_texts(self):
        from PyQt6.QtWidgets import QFontComboBox, QFormLayout, QLineEdit
        from app.core import textfx
        w = QWidget()
        title = QLabel("3. Les textes")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        info = QLabel("Ajoute des textes sur ton edit : police de ton PC, effet « Biseautage et estampage » et mode "
                      "« Incrustation » (le texte devient transparent, on ne voit que son relief). Choisis sur quels "
                      "plans il apparaît. Pas de texte ? Passe directement aux shakes.")
        info.setWordWrap(True)
        info.setObjectName("hint")
        self.tx_view = TextPreview()
        self.tx_list = QListWidget()
        self.tx_list.setMaximumHeight(130)
        self.tx_list.currentRowChanged.connect(self._tx_pick)
        b_new = QPushButton("➕ Nouveau texte")
        b_new.setObjectName("primary")
        b_new.clicked.connect(self._tx_new)
        b_del = QPushButton("🗑 Supprimer")
        b_del.clicked.connect(self._tx_del)
        self.tx_text = QLineEdit()
        self.tx_text.setPlaceholderText("Ton texte (ex. AT)")
        self.tx_font = QFontComboBox()
        self.tx_size = QSpinBox()
        self.tx_size.setRange(20, 900)
        self.tx_size.setSuffix(" px")
        self.tx_bold = QCheckBox("Gras")
        self.tx_x = QSlider(Qt.Orientation.Horizontal)
        self.tx_y = QSlider(Qt.Orientation.Horizontal)
        for sl in (self.tx_x, self.tx_y):
            sl.setRange(-50, 50)
        self.tx_bev = QCheckBox("Biseautage et estampage")
        self.tx_bsize = QSlider(Qt.Orientation.Horizontal)
        self.tx_bsize.setRange(1, 40)
        self.tx_bforce = QSlider(Qt.Orientation.Horizontal)
        self.tx_bforce.setRange(5, 100)
        self.tx_fill = QSlider(Qt.Orientation.Horizontal)
        self.tx_fill.setRange(-40, 60)
        self.tx_mode = QComboBox()
        for code, label in textfx.MODES:
            self.tx_mode.addItem(label, code)
        self.tx_color = QPushButton("Couleur")
        self.tx_color.clicked.connect(self._tx_color)
        self.tx_from = QSpinBox()
        self.tx_to = QSpinBox()
        self.tx_from.setPrefix("du plan ")
        self.tx_to.setPrefix("au plan ")
        b_here = QPushButton("Plan affiché")
        b_here.setToolTip("Le texte commence au plan affiché à l'étape 2.")
        b_here.clicked.connect(lambda: (self.tx_from.setValue(self.seg + 1), self.tx_to.setValue(self.seg + 1)))
        for wd in (self.tx_text,):
            wd.textChanged.connect(self._tx_edit)
        self.tx_font.currentFontChanged.connect(self._tx_edit)
        for wd in (self.tx_size, self.tx_from, self.tx_to):
            wd.valueChanged.connect(self._tx_edit)
        for wd in (self.tx_x, self.tx_y, self.tx_bsize, self.tx_bforce, self.tx_fill):
            wd.valueChanged.connect(self._tx_edit)
        for wd in (self.tx_bold, self.tx_bev):
            wd.toggled.connect(self._tx_edit)
        self.tx_mode.currentIndexChanged.connect(self._tx_edit)
        form = QFormLayout()
        form.addRow("Texte", self.tx_text)
        form.addRow("Police (de ton PC)", self.tx_font)
        r1 = QHBoxLayout()
        r1.addWidget(self.tx_size)
        r1.addWidget(self.tx_bold)
        form.addRow("Taille", r1)
        form.addRow("Position X", self.tx_x)
        form.addRow("Position Y", self.tx_y)
        form.addRow("Effet", self.tx_bev)
        form.addRow("Taille du biseau", self.tx_bsize)
        form.addRow("Profondeur", self.tx_bforce)
        r2 = QHBoxLayout()
        r2.addWidget(self.tx_mode, 1)
        r2.addWidget(self.tx_color)
        form.addRow("Mode de fusion", r2)
        form.addRow("Remplissage", self.tx_fill)
        r3 = QHBoxLayout()
        r3.addWidget(self.tx_from)
        r3.addWidget(self.tx_to)
        r3.addWidget(b_here)
        form.addRow("Apparaît", r3)
        self.tx_editor = QWidget()
        self.tx_editor.setLayout(form)
        right = QVBoxLayout()
        lrow = QHBoxLayout()
        lrow.addWidget(b_new)
        lrow.addWidget(b_del)
        right.addLayout(lrow)
        right.addWidget(self.tx_list)
        right.addWidget(self.tx_editor, 1)
        body = QHBoxLayout()
        body.addWidget(self.tx_view, 3)
        body.addLayout(right, 2)
        b_back = QPushButton("←  Retour aux clips")
        b_back.clicked.connect(lambda: (self.stack.setCurrentIndex(1), self._show_seg(self.seg)))
        b_next = QPushButton("Étape 4 : shakes  →")
        b_next.setObjectName("primary")
        b_next.clicked.connect(lambda: (self.save_state(), self.start_shakes()))
        row = QHBoxLayout()
        row.addWidget(b_back)
        row.addStretch(1)
        row.addWidget(b_next)
        lay = QVBoxLayout(w)
        lay.addWidget(title)
        lay.addWidget(info)
        lay.addLayout(body, 1)
        lay.addLayout(row)
        self.tx_sel = -1
        return w

    def start_texts(self):
        n = len(self.bounds) - 1
        for sb in (self.tx_from, self.tx_to):
            sb.blockSignals(True)
            sb.setRange(1, max(1, n))
            sb.blockSignals(False)
        self.tx_list.blockSignals(True)
        self.tx_list.clear()
        for t in self.texts:
            self.tx_list.addItem(t.get("texte") or "(vide)")
        self.tx_list.blockSignals(False)
        self.stack.setCurrentIndex(3)
        if self.texts:
            self.tx_list.setCurrentRow(0)
            self._tx_pick(0)
        else:
            self.tx_sel = -1
            self.tx_editor.setEnabled(False)
            self._tx_base(self.seg)
            self.tx_view.set_cfg(None)

    def _tx_base(self, k):
        k = max(0, min(len(self.bounds) - 2, k))
        ch = self.choices[k] if k < len(self.choices) else None
        if ch:
            self.tx_view.show_at(ch[1], self._clip_start(ch[1]))
        else:
            self.tx_view.show_at(self.path, (self.bounds[k] + self.bounds[k + 1]) / 2)

    def _tx_new(self):
        from app.core import textfx
        t = dict(textfx.DEFAULT, police=self.tx_font.currentFont().family(), debut=self.seg, fin=self.seg)
        self.texts.append(t)
        self.tx_list.addItem(t["texte"])
        self.tx_list.setCurrentRow(len(self.texts) - 1)
        self.save_state()

    def _tx_del(self):
        r = self.tx_list.currentRow()
        if 0 <= r < len(self.texts):
            del self.texts[r]
            self.start_texts()
            self.save_state()

    def _tx_pick(self, r):
        from PyQt6.QtGui import QFont
        from app.core import textfx
        if not 0 <= r < len(self.texts):
            return
        self.tx_sel = r
        t = textfx.full(self.texts[r])
        ws = (self.tx_text, self.tx_font, self.tx_size, self.tx_bold, self.tx_x, self.tx_y, self.tx_bev,
              self.tx_bsize, self.tx_bforce, self.tx_fill, self.tx_mode, self.tx_from, self.tx_to)
        for wd in ws:
            wd.blockSignals(True)
        self.tx_text.setText(t["texte"])
        self.tx_font.setCurrentFont(QFont(t["police"]))
        self.tx_size.setValue(int(t["taille"]))
        self.tx_bold.setChecked(bool(t["gras"]))
        self.tx_x.setValue(int(t["x"]))
        self.tx_y.setValue(int(t["y"]))
        self.tx_bev.setChecked(bool(t["biseau"]))
        self.tx_bsize.setValue(int(t["biseau_taille"]))
        self.tx_bforce.setValue(int(t["biseau_force"]))
        self.tx_fill.setValue(int(t["remplissage"]))
        self.tx_mode.setCurrentIndex(max(0, self.tx_mode.findData(t["mode"])))
        self.tx_from.setValue(int(t["debut"]) + 1)
        self.tx_to.setValue(int(t["fin"]) + 1)
        for wd in ws:
            wd.blockSignals(False)
        self.tx_editor.setEnabled(True)
        self.tx_color.setEnabled(t["mode"] == "normal")
        self._tx_base(int(t["debut"]))
        self.tx_view.set_cfg(t)

    def _tx_edit(self, *_):
        r = self.tx_sel
        if not 0 <= r < len(self.texts):
            return
        a, b = self.tx_from.value() - 1, self.tx_to.value() - 1
        old_start = int(self.texts[r].get("debut", 0))
        t = dict(self.texts[r], texte=self.tx_text.text(), police=self.tx_font.currentFont().family(),
                 taille=self.tx_size.value(), gras=self.tx_bold.isChecked(), x=self.tx_x.value(), y=self.tx_y.value(),
                 biseau=self.tx_bev.isChecked(), biseau_taille=self.tx_bsize.value(),
                 biseau_force=self.tx_bforce.value(), remplissage=self.tx_fill.value(),
                 mode=self.tx_mode.currentData(), debut=min(a, b), fin=max(a, b))
        self.texts[r] = t
        it = self.tx_list.item(r)
        if it is not None:
            it.setText(t["texte"] or "(vide)")
        self.tx_color.setEnabled(t["mode"] == "normal")
        if t["debut"] != old_start:
            self._tx_base(t["debut"])
        self.tx_view.set_cfg(t)
        self.save_state()

    def _tx_color(self):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        r = self.tx_sel
        if not 0 <= r < len(self.texts):
            return
        c = QColorDialog.getColor(QColor(self.texts[r].get("couleur", "#ffffff")), self, "Couleur du texte")
        if c.isValid():
            self.texts[r]["couleur"] = c.name()
            self.tx_view.set_cfg(self.texts[r])
            self.save_state()

    # ------------------------------------------------------------ étape 4 : shakes
    def _page_shakes(self):
        w = QWidget()
        self.sh_title = QLabel("4. Les shakes")
        self.sh_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        info = QLabel("Un shake a été posé automatiquement sur chaque coupe (les losanges, une couleur par réglage). "
                      "Clique un losange pour le voir et changer sa puissance. Plusieurs d'un coup : glisse sur la "
                      "barre, ou Ctrl + clic / Maj + clic. Espace : lire le clip.")
        info.setWordWrap(True)
        info.setObjectName("hint")
        self.sh_view = Preview()
        self.sh_bar = MarkerBar()
        self.sh_bar.picked.connect(self._sh_select)
        self.sh_bar.selection.connect(self._sh_multi)
        self.sh_legend = QLabel("")
        self.sh_legend.setTextFormat(Qt.TextFormat.RichText)
        self.sh_on = QCheckBox("Shake sur cette coupe")
        self.sh_lvl = QComboBox()
        for sens in ("in", "out"):
            for n in range(1, 6):
                self.sh_lvl.addItem(f"{sens.upper()} {n}x", (sens, n))
        self.sh_dur = DurCombo()
        for w_ in (self.sh_on,):
            w_.toggled.connect(self._sh_edit)
        self.sh_lvl.currentIndexChanged.connect(self._sh_edit)
        self.sh_dur.valueChanged.connect(self._sh_edit)
        self.sh_info = QLabel("")
        b_prev = QPushButton("◀")
        b_prev.clicked.connect(lambda: self._sh_select(max(0, self.sh_sel - 1)))
        b_next = QPushButton("▶")
        b_next.clicked.connect(lambda: self._sh_select(min(len(self.sh_cfg) - 1, self.sh_sel + 1)))
        b_all = QPushButton("Appliquer à toutes les coupes")
        b_all.clicked.connect(self._sh_all)
        ctl = QHBoxLayout()
        ctl.addWidget(b_prev)
        ctl.addWidget(b_next)
        ctl.addWidget(self.sh_info, 1)
        ctl.addWidget(self.sh_on)
        ctl.addWidget(self.sh_lvl)
        ctl.addWidget(self.sh_dur)
        ctl.addWidget(b_all)
        b_back = QPushButton("←  Retour aux textes")
        b_back.clicked.connect(lambda: (self._save_shakes(force=True), self.start_texts()))
        b_view = QPushButton("👁  Voir le résultat à côté de l'edit")
        b_view.clicked.connect(lambda: (self._save_shakes(), self.apply_project(), self.show_final()))
        b_end = QPushButton("Terminer sans exporter")
        b_end.clicked.connect(lambda: self.finish(False))
        b_exp = QPushButton("Exporter l'edit  →")
        b_exp.setObjectName("primary")
        b_exp.clicked.connect(lambda: self.finish(True))
        row = QHBoxLayout()
        row.addWidget(b_back)
        row.addStretch(1)
        row.addWidget(b_view)
        row.addWidget(b_end)
        row.addWidget(b_exp)
        lay = QVBoxLayout(w)
        lay.addWidget(self.sh_title)
        lay.addWidget(info)
        lay.addWidget(self.sh_view, 1)
        lay.addWidget(self.sh_bar)
        lay.addWidget(self.sh_legend)
        lay.addLayout(ctl)
        lay.addLayout(row)
        self.sh_cfg, self.sh_tl, self.sh_sel, self.sh_many = [], [], 0, [0]
        return w

    def start_shakes(self):
        from app.core import shake
        self.sh_tl = self.build_timeline()
        if len(self.sh_tl) < 2:
            self.finish(False)
            return
        base = dict(shake.clean(self.project.shakes), actif=True)
        self.sh_cfg = []
        for e in self.sh_tl[1:]:
            o = (self.fx.get(e["plan"]) or {}).get("shake")
            if isinstance(o, dict) and o.get("off"):
                self.sh_cfg.append(None)
            elif isinstance(o, dict):
                self.sh_cfg.append(shake.clean(dict(base, **o, actif=True)))
            else:
                self.sh_cfg.append(dict(base))               # posé automatiquement
        t, cuts = 0.0, []
        for e in self.sh_tl[:-1]:
            t += e["duree"]
            cuts.append(t)
        self.sh_bar.set(t + self.sh_tl[-1]["duree"], cuts, self.sh_cfg)
        self.stack.setCurrentIndex(2)
        self.sh_title.setText(f"4. Les shakes — {len(cuts)} coupe(s)")
        self._sh_legend()
        self._sh_select(0)

    def _sh_select(self, i):
        if not self.sh_cfg:
            return
        self.sh_sel = i = max(0, min(len(self.sh_cfg) - 1, i))
        self.sh_bar.select(i)
        self.sh_many = sorted(self.sh_bar.chosen)
        c = self.sh_cfg[i]
        e = self.sh_tl[i + 1]
        for w_ in (self.sh_on, self.sh_lvl, self.sh_dur):
            w_.blockSignals(True)
        self.sh_on.setChecked(c is not None)
        if c:
            self.sh_lvl.setCurrentIndex(max(0, self.sh_lvl.findData((c["sens"], c["niveau"]))))
            self.sh_dur.setValue(c["duree"])
        self.sh_lvl.setEnabled(c is not None)
        self.sh_dur.setEnabled(c is not None)
        for w_ in (self.sh_on, self.sh_lvl, self.sh_dur):
            w_.blockSignals(False)
        self.sh_info.setText(f"Coupe {i + 1}/{len(self.sh_cfg)}  ·  {fmt(self.sh_bar.cuts[i])}  ·  "
                             f"vers {vclip.name(e['clip'])}")
        self.sh_view.show_at(e["clip"], self._clip_start(e["clip"]))

    def _sh_multi(self, idx):
        self.sh_many = list(idx) or [self.sh_sel]
        if len(self.sh_many) > 1:
            self.sh_info.setText(f"{len(self.sh_many)} coupes choisies : les réglages s'appliquent à toutes")

    def _sh_legend(self):
        parts = []
        for (sens, niv, dur), col in self.sh_bar.groups.items():
            n = sum(1 for c in self.sh_cfg if group_key(c) == (sens, niv, dur))
            parts.append(f"<span style='color:{col}; font-size:16px'>◆</span> {sens.upper()} {niv}x · durée {dur} "
                         f"<span style='color:#888'>({n})</span>")
        off = sum(1 for c in self.sh_cfg if c is None)
        if off:
            parts.append(f"<span style='color:#555a66; font-size:16px'>◆</span> sans shake ({off})")
        self.sh_legend.setText("&nbsp;&nbsp;&nbsp;".join(parts))

    def _sh_edit(self, *_):
        if not self.sh_cfg:
            return
        for i in (self.sh_many if self.sh_sel in self.sh_many else [self.sh_sel]):
            if self.sh_on.isChecked():
                s, n = self.sh_lvl.currentData()
                self.sh_cfg[i] = {"actif": True, "sens": s, "niveau": n, "duree": self.sh_dur.value()}
            else:
                self.sh_cfg[i] = None
        self.sh_lvl.setEnabled(self.sh_on.isChecked())
        self.sh_dur.setEnabled(self.sh_on.isChecked())
        self.sh_bar.set(self.sh_bar.total, self.sh_bar.cuts, self.sh_cfg)
        self.sh_bar.update()
        self._sh_legend()

    def _sh_all(self):
        c = self.sh_cfg[self.sh_sel] if self.sh_cfg else None
        self.sh_cfg = [dict(c) if c else None for _ in self.sh_cfg]
        self.sh_bar.set(self.sh_bar.total, self.sh_bar.cuts, self.sh_cfg)
        self.sh_bar.select(self.sh_sel)
        self._sh_legend()

    def _save_shakes(self, force=False):
        """Les réglages de l'étape 4 vont dans chaque plan (ils servent au rendu)."""
        if not self.sh_cfg or (self.stack.currentIndex() != 2 and not force):
            return
        for e, c in zip(self.sh_tl[1:], self.sh_cfg):
            fx = dict(self.fx.get(e["plan"]) or {})
            fx["shake"] = ({"sens": c["sens"], "niveau": c["niveau"], "duree": c["duree"]} if c
                           else {"off": True})
            self.fx[e["plan"]] = fx
        self.save_state()

    # ------------------------------------------------------------ 2K / 3K / 4K + time remap manuel
    def _multikill(self, n):
        k = self.seg
        avail = len(self.bounds) - 2 - k                  # transitions après ce plan
        if avail <= 0:
            return
        m = min(n, avail)
        if QMessageBox.question(
                self, f"{n}K", f"J'enlève les {m} transition(s) qui suivent ce plan : il devient un seul clip "
                f"{n}K ({fmt(self.bounds[k])} → {fmt(self.bounds[k + m + 1])}).\n\nEnsuite tu règles son time "
                "remap manuel (keyframes + courbes). Continuer ?") != QMessageBox.StandardButton.Yes:
            return
        cuts = sorted(self.cuts)
        self.cuts = cuts[:k] + cuts[k + m:]

        def shift(d):
            return {(i if i <= k else i - m): v for i, v in d.items() if i <= k or i > k + m}
        self.choices = self.choices[:k + 1] + self.choices[k + 1 + m:]
        self.overlays = shift(self.overlays)
        self.fx = shift(self.fx)
        fx = dict(self.fx.get(k) or {})
        fx["multi"] = n
        fx.pop("manuel", None)
        self.fx[k] = fx
        self.bounds = [0.0] + sorted(self.cuts) + [self.length]
        self._fill_cuts()
        self.save_state()
        self._fill_timeline()
        self._show_seg(k)
        if self.choices[k]:
            self._manual()
        else:
            self.auto_status.setText(f"Choisis le clip {n}K à droite, puis « 🎛 Time remap manuel ».")

    def _manual(self):
        ch = self.choices[self.seg] if self.seg < len(self.choices) else None
        if not ch:
            self.auto_status.setText("Choisis d'abord un clip pour ce plan.")
            return
        from .manual_remap_dialog import ManualRemapDialog
        d = self.bounds[self.seg + 1] - self.bounds[self.seg]
        fx = dict(self.fx.get(self.seg) or {})
        rm = tr.clip_remaps().get(ch[1])
        s0 = tr.clip_starts().get(str(ch[1]))
        start = float(rm["debut"]) if rm else float(s0 or 0.0)
        n = fx.get("multi")
        title = f"{n}K dismiss / flick away — time remap manuel" if n else "Time remap manuel"
        data = fx.get("manuel")
        if not data and n:                     # multi-kill : une keyframe par kill trouvé (bannières de kill)
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                kills = [k / tr.FPS for k in tr.find_kills(ch[1]) if k / tr.FPS > start - 0.05][:n]
            except Exception:                  # noqa: BLE001
                kills = []
            finally:
                QApplication.restoreOverrideCursor()
            if kills:
                keys = [[0.0, start]] + [[round(d * (i + 1) / (len(kills) + 1), 3), kt] for i, kt in enumerate(kills)]
                keys.append([d, kills[-1] + 0.35])
                data = {"keys": keys, "courbes": ["0.33, 0, 0.67, 1"] * (len(keys) - 1)}
        dlg = ManualRemapDialog(ch[1], d, data, start, title, self)
        if dlg.exec() and dlg.result:
            fx["manuel"] = dlg.result
            self.fx[self.seg] = fx
            self.save_state()
            self._show_fx()

    # ------------------------------------------------------------ caler le début sur l'edit
    def align(self, all_plans=False):
        if not self.path or not getattr(self, "bounds", None):
            return
        from app.core import auto_match
        idx = range(len(self.bounds) - 1) if all_plans else [self.seg]
        todo = [(k, self.choices[k][1]) for k in idx if k < len(self.choices) and self.choices[k]]
        if not todo:
            self.auto_status.setText("Aucun clip choisi à caler.")
            return
        edit, bounds = self.path, list(self.bounds)

        def fn(p):
            res = {}
            for j, (k, clip) in enumerate(todo):
                if self._cancel_job:
                    break
                p(f"Je cale le début : plan {k + 1} ({j + 1}/{len(todo)})", j / len(todo))
                if clip not in res:                      # un même clip n'a qu'un seul début
                    res[clip] = (k,) + tuple(auto_match.align_start(edit, bounds[k], clip))
            return res
        r = self._job("Caler les débuts sur l'edit", fn)
        if "err" in r:
            QMessageBox.warning(self, "Caler sur l'edit", r["err"][-800:])
        if "ok" not in r:
            return
        same = flick = 0
        for clip, (k, t, is_same) in r["ok"].items():
            if t is None:
                continue
            same += bool(is_same)
            flick += not is_same
            rm = tr.clip_remaps().get(clip)
            if rm:                                       # time remap : on décale ses 2 keyframes
                delta = t - float(rm["debut"])
                rm = dict(rm, debut=round(max(0.0, float(rm["debut"]) + delta), 4),
                          fin=round(max(0.02, float(rm["fin"]) + delta), 4))
                tr.save_clip_remap(clip, rm)
                if clip in self.project.remaps:
                    self.project.remaps[clip] = dict(self.project.remaps[clip], debut=rm["debut"], fin=rm["fin"])
            else:
                tr.save_clip_start(clip, t)
        self.auto_status.setText(f"✓ Débuts calés : {same} même(s) cut(s) retrouvé(s), "
                                 f"{flick} sur la 1re frame du flick away.")
        self._show_pick()
        self._fill_timeline()

    # ------------------------------------------------------------ comparaison
    def _job(self, title, fn):
        """Lance fn(progress) en arrière-plan avec une fenêtre de progression. Renvoie {"ok": ...} ou {"err": ...}."""
        from PyQt6.QtCore import QEventLoop
        from PyQt6.QtWidgets import QProgressDialog
        from .workers import FuncThread
        dlg = QProgressDialog(title, "Annuler", 0, 1000, self)
        dlg.setWindowTitle(title)
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        self._cancel_job = False
        dlg.canceled.connect(lambda: setattr(self, "_cancel_job", True))
        th = FuncThread(fn, self)
        res = {}
        loop = QEventLoop()
        th.progress.connect(lambda txt, f: (dlg.setLabelText(txt), dlg.setValue(int(max(0, min(1, f)) * 1000))))
        th.done.connect(lambda r: (res.setdefault("ok", r), loop.quit()))
        th.failed.connect(lambda m: (res.setdefault("err", m), loop.quit()))
        th.start()
        dlg.show()
        loop.exec()
        th.wait()
        dlg.close()
        if self._cancel_job:
            res = {"annule": True}
        return res

    def _show_result(self, res, what):
        from app.core import compare
        if "ok" in res:
            try:
                compare.open_file(res["ok"])
            except OSError:
                QMessageBox.information(self, what, f"Vidéo prête :\n{res['ok']}")
        elif "err" in res:
            QMessageBox.warning(self, what, f"Impossible de faire la vidéo :\n{res['err'][-800:]}")

    def compare(self):
        """Aperçu rapide de ce que j'ai mis pour l'instant, à côté de l'edit de base."""
        if not self.path or not getattr(self, "bounds", None):
            return
        from app.core import compare
        plans = []
        for k in range(len(self.bounds) - 1):
            d = self.bounds[k + 1] - self.bounds[k]
            ch = self.choices[k] if k < len(self.choices) else None
            if ch:
                rm = tr.clip_remaps().get(ch[1])
                s0 = tr.clip_starts().get(str(ch[1]))
                plans.append((ch[1], float(rm["debut"]) if rm else float(s0 or 0.0), d))
            else:
                plans.append((None, 0.0, d))
        d = proj.config_dir() / "apercus"
        d.mkdir(parents=True, exist_ok=True)
        out = d / "comparaison_rapide.mp4"
        res = self._job("Comparer avec l'edit", lambda p: compare.quick_preview(
            self.path, plans, out, p, lambda: self._cancel_job))
        self._show_result(res, "Comparer avec l'edit")

    def show_final(self):
        """Vrai rendu du montage (ralentis, shakes, fondus...) puis vidéo côte à côte avec l'edit d'exemple."""
        from app.core import compare
        from app.core import render as rnd
        d = proj.config_dir() / "apercus"
        d.mkdir(parents=True, exist_ok=True)
        result, out = d / "resultat.mp4", d / "resultat_vs_edit.mp4"

        def fn(p):
            rnd.render(self.project, str(result), progress=lambda f, txt: p(txt, f * 0.92),
                       is_cancelled=lambda: self._cancel_job)
            p("Comparaison avec l'edit d'exemple...", 0.95)
            return compare.side_by_side(self.path, result, out, lambda: self._cancel_job)
        self._show_result(self._job("Résultat à côté de l'edit", fn), "Résultat")

    def _show_pick(self):
        ch = self.choices[self.seg]
        ov = self.overlays.get(self.seg)
        self.b_over.setEnabled(bool(ch))
        self.b_remap.setEnabled(bool(ch))
        self.b_over.setText(f"🟩 Superposition : {Path(ov['fichier']).name}  (modifier)" if ov
                            else "🟩 Superposer une vidéo (fond vert ou normale)")
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
        data = item.data(ROLE) if item is not None else None
        if not data or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        name, clips = data
        clips = [c for c in clips if vclip.exists(c)]
        if not clips:
            self.auto_status.setText(f"Aucun clip dans « {name} » ici : ajoute-en avec « ➕ Ajouter des clips ».")
            return
        if not (0 <= self.seg < len(self.choices)):
            return
        used = {c[1] for k, c in enumerate(self.choices) if c and k != self.seg}
        cur = self.choices[self.seg][1] if self.choices[self.seg] else None
        free = [c for c in clips if c not in used and c != cur] or [c for c in clips if c != cur] or clips
        saved = tr.clip_remaps()
        remapped = [c for c in free if c in saved]
        pool = remapped or free                   # les clips avec time remap déjà fait d'abord
        self.choices[self.seg] = (name, random.choice(pool))
        self.save_state()
        self._show_pick()
        self._tl_update(self.seg)

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
        self._tl_update(self.seg)

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
        self._fill_timeline()
        self._show_seg(0)
        if changed and QMessageBox.question(
                self, "Edit auto", "Je cale aussi le début de chaque clip sur l'edit ?\n\n"
                "Je regarde la 1re frame de chaque plan de l'edit et je la retrouve dans ton clip (même cut). "
                "Si ce n'est pas le même cut, je prends la 1re frame du flick away.") == QMessageBox.StandardButton.Yes:
            self.align(True)

    def _skip(self):
        self.choices[self.seg] = None
        self.save_state()
        self._tl_update(self.seg)
        self._next_seg()

    def _next_seg(self):
        if self.seg < len(self.bounds) - 2:
            self._show_seg(self.seg + 1)
        else:
            self.start_texts()                          # étape 3 : les textes, puis étape 4 : les shakes

    def build_timeline(self):
        """Un élément par plan, dans l'ordre (un même clip peut revenir plusieurs fois).
        Un plan sans clip rallonge le clip d'avant (ou celui d'après au début) : tout reste calé sur la musique."""
        timeline = []
        lead = 0.0
        for k, ch in enumerate(self.choices):
            if k + 1 >= len(self.bounds):
                break
            d = self.bounds[k + 1] - self.bounds[k]
            if ch and vclip.exists(ch[1]):
                e = {"clip": ch[1], "duree": round(d + lead, 4), "plan": k}
                if k in self.overlays:
                    e["overlay"] = self.overlays[k]
                fx = self.fx.get(k) or {}
                if fx.get("fondu"):
                    e["fondu"] = int(fx["fondu"])
                if fx.get("shake") is not None:
                    e["shake"] = fx["shake"]
                if fx.get("manuel"):
                    e["manuel"] = fx["manuel"]
                timeline.append(e)
                lead = 0.0
            elif timeline:
                timeline[-1]["duree"] = round(timeline[-1]["duree"] + d, 4)
            else:
                lead += d
        return timeline

    def apply_project(self):
        """Met le montage dans le projet (clips dans l'ordre, durées, time remaps, effets, musique)."""
        timeline = self.build_timeline()
        clips = list(dict.fromkeys(e["clip"] for e in timeline))
        saved = tr.clip_remaps()
        plans = {}
        for k, ch in enumerate(self.choices):
            if ch and ch[1] not in plans and k + 1 < len(self.bounds):
                plans[ch[1]] = round(self.bounds[k + 1] - self.bounds[k], 4)   # plan -> clip suivant
        for c in clips:
            if c in saved:
                self.project.remaps[c] = dict(saved[c], plan=plans.get(c))
        self.project.clips = [e["clip"] for e in timeline]         # dans l'ordre, doublons gardés
        self.project.timeline = timeline
        self.project.plans = {c: plans[c] for c in clips if plans.get(c)}   # chaque clip dure son plan
        self.project.overlays = {self.choices[k][1]: ov for k, ov in self.overlays.items()
                                 if k < len(self.choices) and self.choices[k]}
        n = len(self.bounds) - 1
        self.project.texts = [dict(t, debut_s=round(self.bounds[min(n - 1, int(t.get("debut", 0)))], 4),
                                   fin_s=round(self.bounds[min(n, int(t.get("fin", 0)) + 1)], 4))
                              for t in self.texts if t.get("texte")]
        sh = dict(self.project.shakes or {})
        sh.pop("coupes", None)                     # les réglages de shake de ce plan-ci reprennent la main
        self.project.shakes = sh
        self._keep_music()
        self.save_state()
        try:
            self.project.save()
        except (OSError, ValueError):
            pass

    def finish(self, export=False):
        self._save_shakes()
        self.apply_project()
        self.done(2 if export else 1)                 # 2 = on enchaîne sur l'export de l'edit

    def _keep_music(self):
        """Garde la musique de l'edit : elle devient la musique du projet."""
        if not self.path or not Path(self.path).is_file():
            return
        import subprocess
        from app.core import audio
        d = proj.config_dir() / "musiques_edits"
        out = d / (Path(self.path).stem + ".wav")
        try:
            d.mkdir(parents=True, exist_ok=True)
            r = subprocess.run([audio.ffmpeg_exe(), "-y", "-hide_banner", "-i", str(self.path), "-vn",
                                "-c:a", "pcm_s16le", "-ar", "48000", str(out)], capture_output=True,
                               stdin=subprocess.DEVNULL, creationflags=audio._NO_WINDOW)
            if r.returncode == 0 and out.is_file() and out.stat().st_size > 1000:
                self.project.music = str(out)
        except OSError:
            pass

    def done(self, r):
        if self.thread is not None and self.thread.isRunning():
            self.thread.wait()
        self._stop_thumbs()
        self.save_state()
        super().done(r)
