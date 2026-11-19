"""Page « Time remap » ouverte à chaque clip ajouté : quel couteau, keyframes détectées, courbes."""
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout,
                             QWidget)

from app.core import timeremap as tr

from .style import MUTED, PANEL_2


class DetectThread(QThread):
    done = pyqtSignal(object)            # tr.Analysis
    failed = pyqtSignal(str)

    def __init__(self, path, knife, parent=None):
        super().__init__(parent)
        self.path, self.knife = path, knife

    def run(self):
        try:
            self.done.emit(tr.Analysis(self.path, self.knife))
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)


class PreviewThread(QThread):
    progress = pyqtSignal(float, str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, path, start, end, cfg, parent=None):
        super().__init__(parent)
        self.args = (path, start, end, cfg)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import tempfile
        out = str(Path(tempfile.gettempdir()) / "auraedit_apercu_time_remap.mp4")
        try:
            tr.render(*self.args, out, lambda: self._cancel, self.progress.emit)
        except InterruptedError:
            self.failed.emit("Aperçu annulé.")
            return
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.done.emit(out)


class CurvePreview(QWidget):
    """Graphique des valeurs du time remap : monte (courbe 1) puis redescend (courbe 2)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.c1, self.c2 = tr.DEFAULTS["courbe1"], tr.DEFAULTS["courbe2"]
        self.setMinimumSize(320, 150)

    def set_curves(self, c1, c2):
        self.c1, self.c2 = c1 or self.c1, c2 or self.c2
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        p.fillRect(self.rect(), QColor("#0b0f14"))
        p.setPen(QPen(QColor(PANEL_2), 1))
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        mid = r.left() + r.width() / 2
        a, b, c = QPointF(r.left(), r.bottom()), QPointF(mid, r.top()), QPointF(r.right(), r.bottom())

        def seg(p0, p1, curve):
            x1, y1, x2, y2 = curve
            w, h = p1.x() - p0.x(), p1.y() - p0.y()
            return (QPointF(p0.x() + w * x1, p0.y() + h * y1), QPointF(p0.x() + w * x2, p0.y() + h * y2))

        h1 = seg(a, b, self.c1)
        h2 = seg(b, c, self.c2)
        path = QPainterPath(a)
        path.cubicTo(h1[0], h1[1], b)
        path.cubicTo(h2[0], h2[1], c)
        p.setPen(QPen(QColor(MUTED), 1))
        for p0, hh, p1 in ((a, h1, b), (b, h2, c)):
            p.drawLine(p0, hh[0])
            p.drawLine(p1, hh[1])
            for q in hh:
                p.fillRect(QRectF(q.x() - 3, q.y() - 3, 6, 6), QColor("#aaa"))
        p.setPen(QPen(QColor("white"), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        for q in (a, b, c):
            p.fillRect(QRectF(q.x() - 5, q.y() - 5, 10, 10), QColor("white"))
        p.end()


class FramePicker(QFrame):
    """Une keyframe : image de la vidéo + curseur image par image."""
    moved = pyqtSignal()

    def __init__(self, title, path, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.path = path
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 700;")
        self.image = QLabel("Analyse...")
        self.image.setFixedSize(400, 225)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background: #000;")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._label)
        self.slider.sliderReleased.connect(self.show_frame)
        self.info = QLabel()
        self.info.setObjectName("hint")
        prev, nxt = QPushButton("◀ -1"), QPushButton("+1 ▶")
        prev.clicked.connect(lambda: self.step(-1))
        nxt.clicked.connect(lambda: self.step(1))
        row = QHBoxLayout()
        row.addWidget(prev)
        row.addWidget(self.slider, 1)
        row.addWidget(nxt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(self.title)
        lay.addWidget(self.image)
        lay.addLayout(row)
        lay.addWidget(self.info)

    def setup(self, frames, value):
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, frames - 1))
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.slider.setEnabled(True)
        self._label()
        self.show_frame()

    def step(self, d):
        self.slider.setValue(self.slider.value() + d)
        self.show_frame()

    def seconds(self):
        return self.slider.value() / tr.FPS

    def _label(self, *_):
        self.info.setText(f"frame {self.slider.value()}  ({self.seconds():.3f} s)")
        self.moved.emit()

    def show_frame(self):
        pix = QPixmap()
        if pix.loadFromData(tr.grab_png(self.path, self.seconds(), 400)):
            self.image.setPixmap(pix.scaled(400, 225, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))


class TimeRemapDialog(QDialog):
    """Renvoie Accepted (time remap enregistré) ou Rejected (pas de time remap pour ce clip)."""

    def __init__(self, project, path, knife=None, knives=(), parent=None, mode="clip"):
        super().__init__(parent)
        self.kunai = mode == "kunai"
        self.setWindowTitle("Time remap — kunai" if self.kunai else "Time remap")
        self.setMinimumWidth(900)
        self.project, self.path = project, path
        self.cfg = tr.cfg_for({"type": "kunai"}) if self.kunai else tr.load()
        self.skip_all = False
        self.thread = None
        old = tr.clip_remaps().get(path) or project.remaps.get(path) or {}
        # durées propres à ce clip : elles ne changent pas les réglages des autres clips
        self._glob = (self.cfg["duree_ralenti"], self.cfg["frames_retour"])
        if old.get("ralenti"):
            self.cfg["duree_ralenti"] = float(old["ralenti"])
        if old.get("retour"):
            self.cfg["frames_retour"] = int(old["retour"])

        title = QLabel(f"Time remap {'kunai ' if self.kunai else ''}— {Path(path).name}")
        title.setObjectName("h1")

        # --- couteau
        names = sorted(set(knives) | set(self.cfg["couteaux"]), key=str.lower)
        self.knife = QComboBox()
        self.knife.setEditable(True)
        self.knife.addItems(names)
        self.knife.setCurrentText(old.get("couteau") or knife or (names[0] if names else ""))
        self.knife.currentTextChanged.connect(self._knife_changed)
        self.knife_img = QLabel()
        self.knife_img.setFixedSize(160, 90)
        self.knife_img.setStyleSheet("background: #000;")
        self.knife_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_img = QPushButton("Image du couteau...")
        b_img.clicked.connect(self.pick_image)
        self.knife_info = QLabel()
        self.knife_info.setObjectName("hint")
        self.knife_info.setWordWrap(True)
        krow = QHBoxLayout()
        kcol = QVBoxLayout()
        kcol.addWidget(QLabel("C'est quel couteau ?"))
        kcol.addWidget(self.knife)
        kcol.addWidget(b_img)
        kcol.addWidget(self.knife_info)
        krow.addLayout(kcol, 1)
        krow.addWidget(self.knife_img)

        # --- keyframes
        if self.kunai:
            self.k1 = FramePicker("Keyframe 1 — début : le kunai part (moment du kill)", path)
            self.k2 = FramePicker("Keyframe 2 — fin : jusqu'où va le time remap", path)
        else:
            self.k1 = FramePicker("Keyframe 1 — début : plus de mains à l'écran", path)
            self.k2 = FramePicker("Keyframe 2 — fin : couteau sorti (jusqu'où va le time remap)", path)
        frames = QHBoxLayout()
        frames.addWidget(self.k1)
        frames.addWidget(self.k2)
        self.status = QLabel("Je cherche le kill et les keyframes dans la vidéo...")
        self.status.setWordWrap(True)
        self.analysis = None
        self.kill = QComboBox()
        self.kill.setVisible(False)
        self.kill.currentIndexChanged.connect(self._kill_changed)
        killrow = QHBoxLayout()
        killrow.addWidget(self.status, 1)
        killrow.addWidget(self.kill)

        # --- courbes et réglages
        self.c1 = QLineEdit(tr.curve_text(self.cfg["courbe1"]))
        self.c2 = QLineEdit(tr.curve_text(self.cfg["courbe2"]))
        for e in (self.c1, self.c2):
            e.textChanged.connect(self._curves)
        self.slow = QDoubleSpinBox()
        self.slow.setRange(0.1, 10)
        self.slow.setSingleStep(0.1)
        self.slow.setSuffix(" s")
        self.slow.setValue(float(self.cfg["duree_ralenti"]))
        self.back = QSpinBox()
        self.back.setRange(1, 120)
        self.back.setSuffix(" frames")
        self.back.setValue(int(self.cfg["frames_retour"]))
        self.blend = QComboBox()
        for key, label in tr.BLEND_MODES.items():
            self.blend.addItem(label, key)
        self.blend.setCurrentIndex(list(tr.BLEND_MODES).index(tr.blend_mode(self.cfg)))
        self.preview = CurvePreview()
        self._curves()
        grid = QGridLayout()
        grid.addWidget(QLabel("Courbe 1 (keyframe 1 → 2)"), 0, 0)
        grid.addWidget(self.c1, 0, 1)
        grid.addWidget(QLabel("Courbe 2 (keyframe 2 → 3, reverse)"), 1, 0)
        grid.addWidget(self.c2, 1, 1)
        grid.addWidget(QLabel("Durée du ralenti (1 → 2)"), 2, 0)
        grid.addWidget(self.slow, 2, 1)
        grid.addWidget(QLabel("Durée du retour (2 → 3)"), 3, 0)
        grid.addWidget(self.back, 3, 1)
        grid.addWidget(QLabel("Frame blending"), 4, 0)
        grid.addWidget(self.blend, 4, 1)
        settings = QHBoxLayout()
        settings.addLayout(grid, 1)
        settings.addWidget(self.preview, 1)

        # --- boutons
        self.b_ok = QPushButton("Valider ce time remap")
        self.b_ok.setObjectName("primary")
        self.b_ok.setEnabled(False)
        self.b_ok.clicked.connect(self.validate)
        self.b_preview = QPushButton("▶ Aperçu")
        self.b_preview.setToolTip("Rend ce clip avec le time remap et le frame blending choisis, puis l'ouvre.")
        self.b_preview.clicked.connect(self.preview_render)
        self.preview_thread = None
        b_redo = QPushButton("Refaire la détection")
        b_redo.clicked.connect(self.run_detect)
        b_none = QPushButton("Pas de time remap")
        b_none.clicked.connect(self.reject)
        b_later = QPushButton("Plus tard (tous)")
        b_later.clicked.connect(self._later)
        brow = QHBoxLayout()
        brow.addWidget(b_redo)
        brow.addWidget(self.b_preview)
        brow.addStretch(1)
        brow.addWidget(b_later)
        brow.addWidget(b_none)
        brow.addWidget(self.b_ok)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        if self.kunai:
            for w in (self.knife, b_img, self.knife_info, self.knife_img):
                w.setVisible(False)
            info = QLabel("Réglages propres aux kunais : les courbes et durées ci-dessous sont gardées à part "
                          "de celles des clips au couteau. Je retiens la durée que tu valides pour les prochains kunais.")
            info.setObjectName("hint")
            info.setWordWrap(True)
            lay.addWidget(info)
        lay.addLayout(krow)
        lay.addLayout(frames)
        lay.addLayout(killrow)
        lay.addLayout(settings)
        lay.addLayout(brow)

        self._knife_changed()
        if old:
            self.status.setText("Time remap déjà fait pour ce clip : corrige-le ou clique « Refaire la détection ».")
            self._ready(float(old["debut"]), float(old["fin"]), None)
        else:
            self.run_detect()

    # ---------------------------------------------------------- couteau
    def _knife_data(self):
        if self.kunai:
            d = (self.cfg.get("kunai_reglages") or {}).get("duree")
            return {"duree": d} if d else {}
        return self.cfg["couteaux"].get(self.knife.currentText().strip(), {})

    def _knife_changed(self, *_):
        if self.kunai:
            return
        k = self._knife_data()
        img = k.get("image")
        pix = QPixmap(img) if img and Path(img).is_file() else QPixmap()
        if pix.isNull():
            self.knife_img.setText("pas d'image")
        else:
            self.knife_img.setPixmap(pix.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        if k.get("duree"):
            self.knife_info.setText("Keyframe 1 = 1re frame du couteau, keyframe 2 = flick away + 20 frames. "
                                    f"Si le flick n'est pas trouvé : {k['duree'] * tr.FPS:.0f} frames après la 1.")
        else:
            self.knife_info.setText("Keyframe 1 = 1re frame du couteau, keyframe 2 = flick away + 20 frames. "
                                    "Vérifie les 2 keyframes : la frame « couteau sorti » devient l'image du couteau.")

    def pick_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "Image du couteau (capture du couteau sorti)", "",
                                           "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        name = self.knife.currentText().strip()
        if f and name:
            self.cfg["couteaux"].setdefault(name, {})["image"] = f
            tr.save(self._global_cfg())
            self._knife_changed()

    # --------------------------------------------------------- détection
    def run_detect(self):
        if self.thread is not None and self.thread.isRunning():
            return
        self.b_ok.setEnabled(False)
        self.status.setText("Je cherche le kill et les keyframes dans la vidéo...")
        self.thread = DetectThread(self.path, self._knife_data(), self)
        self.thread.done.connect(self._analysed)
        self.thread.failed.connect(lambda m: self.status.setText(f"Détection impossible : {m}"))
        self.thread.start()

    def _analysed(self, a):
        self.analysis = a
        self.kill.blockSignals(True)
        self.kill.clear()
        for i, k in enumerate(a.kills):
            self.kill.addItem(f"Kill {i + 1} ({k / tr.FPS:.2f} s)")
        start, end = a.keyframes()
        if self.kunai:                      # kunai : le kunai part au kill, puis la durée retenue
            kill = a.kills[-1] / tr.FPS if a.kills else start
            d = (self.cfg.get("kunai_reglages") or {}).get("duree") or 0.5
            start, end = kill, min(a.length - 1 / tr.FPS, kill + d)
        before = [i for i, k in enumerate(a.kills) if k <= start * tr.FPS + tr.FPS // 2]
        self.kill.setCurrentIndex(before[-1] if before else max(0, len(a.kills) - 1))
        self.kill.blockSignals(False)
        self.kill.setVisible(len(a.kills) > 1)
        self._ready(start, end, a.length)
        flick = "flick away trouvé" if a.flick is not None else "flick away pas trouvé (fin estimée)"
        self.status.setText(f"Keyframe 1 = 1re frame du couteau ({start:.2f} s). Keyframe 2 = flick away + 20 frames "
                            f"({end:.2f} s, {flick}). Si c'est mauvais, déplace les curseurs ou choisis un autre kill.")

    def _kill_changed(self, i):
        if self.analysis is None or i < 0:
            return
        start, end = self.analysis.keyframes(i)
        if self.kunai:
            kill = self.analysis.kills[i] / tr.FPS
            d = (self.cfg.get("kunai_reglages") or {}).get("duree") or 0.5
            start, end = kill, min(self.analysis.length - 1 / tr.FPS, kill + d)
        self._ready(start, end, self.analysis.length)
        self.status.setText(f"Kill à {self.analysis.kills[i] / tr.FPS:.2f} s : keyframe 1 = 1re frame du couteau, "
                            "keyframe 2 = flick away + 20 frames.")

    def _ready(self, start, end, length):
        if length is None:
            from app.core.render import duration
            length = duration(self.path) or end + 1
        n = int(length * tr.FPS)
        self.k1.setup(n, int(round(start * tr.FPS)))
        self.k2.setup(n, int(round(end * tr.FPS)))
        self.b_ok.setEnabled(True)

    # ---------------------------------------------------------- réglages
    def _curves(self, *_):
        self.preview.set_curves(tr.parse_curve(self.c1.text()), tr.parse_curve(self.c2.text()))

    def _save_settings(self):
        c1, c2 = tr.parse_curve(self.c1.text()), tr.parse_curve(self.c2.text())
        if c1:
            self.cfg["courbe1"] = c1
        if c2:
            self.cfg["courbe2"] = c2
        self.cfg["duree_ralenti"] = self.slow.value()
        self.cfg["frames_retour"] = self.back.value()
        self.cfg["blending_mode"] = self.blend.currentData()
        self.cfg["blending"] = self.cfg["blending_mode"] != "off"

    def preview_render(self):
        if self.preview_thread is not None and self.preview_thread.isRunning():
            self.preview_thread.cancel()
            return
        start, end = self.k1.seconds(), self.k2.seconds()
        if end <= start:
            self.status.setText("La keyframe 2 doit être après la keyframe 1.")
            return
        self._save_settings()
        self.preview_thread = PreviewThread(self.path, start, end, dict(self.cfg), self)
        self.preview_thread.progress.connect(lambda f, t: self.status.setText(f"Aperçu {int(f * 100)} % — {t}"))
        self.preview_thread.done.connect(self._preview_done)
        self.preview_thread.failed.connect(self._preview_failed)
        self.b_preview.setText("■ Annuler l'aperçu")
        self.status.setText("Aperçu en cours...")
        self.preview_thread.start()

    def _preview_done(self, out):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        self.b_preview.setText("▶ Aperçu")
        self.status.setText("Aperçu prêt : il s'ouvre dans ton lecteur vidéo.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    def _preview_failed(self, msg):
        self.b_preview.setText("▶ Aperçu")
        self.status.setText(f"Aperçu impossible : {msg[-300:]}")

    def validate(self):
        start, end = self.k1.seconds(), self.k2.seconds()
        if end <= start:
            self.status.setText("La keyframe 2 (couteau sorti) doit être après la keyframe 1.")
            return
        self._save_settings()
        if self.kunai:
            self.cfg["duree_kunai"] = round(end - start, 4)
            tr.save_kunai(self._global_cfg())
            data = {"type": "kunai", "debut": round(start, 4), "fin": round(end, 4),
                    "ralenti": self.slow.value(), "retour": self.back.value()}
            self.project.remaps[self.path] = data
            tr.save_clip_remap(self.path, data)
            self.accept()
            return
        name = self.knife.currentText().strip() or "Couteau"
        k = self.cfg["couteaux"].setdefault(name, {})
        k["duree"] = round(end - start, 4)
        if not (k.get("image") and Path(k["image"]).is_file()):
            img = tr.save_knife_image(name, self.path, end)
            if img:
                k["image"] = img
        tr.save(self._global_cfg())
        data = {"couteau": name, "debut": round(start, 4), "fin": round(end, 4),
                "ralenti": self.slow.value(), "retour": self.back.value()}
        self.project.remaps[self.path] = data
        tr.save_clip_remap(self.path, data)
        self.accept()

    def _later(self):
        self.skip_all = True
        self.reject()

    def _global_cfg(self):
        """Réglages à garder pour tous les clips : sans les durées propres à ce clip."""
        g = dict(self.cfg)
        g["duree_ralenti"], g["frames_retour"] = self._glob
        return g

    def done(self, r):
        self._save_settings()
        if self.kunai:
            tr.save_kunai(self._global_cfg())
        else:
            tr.save(self._global_cfg())
        if self.thread is not None and self.thread.isRunning():
            self.thread.wait(10000)
        if self.preview_thread is not None and self.preview_thread.isRunning():
            self.preview_thread.cancel()
            self.preview_thread.wait(10000)
        super().done(r)
