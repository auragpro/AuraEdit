"""Fenêtre « Superposer une vidéo » : on choisit une vidéo (fond vert ou autre), le passage à garder,
la couleur à enlever (pipette, auto ou nuancier), le détourage façon Keylight + Advanced Spill Suppressor,
et l'apparition / disparition (fondu ou Dissolve Luma)."""
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QVBoxLayout,
                             QWidget)

from app.core import chroma, vclip

PW, PH = 640, 360
VIEWS = [("Résultat", "resultat"), ("Masque (noir = enlevé)", "masque"), ("Vidéo brute (pour la pipette)", "brut")]


class Canvas(QLabel):
    def __init__(self, on_click):
        super().__init__()
        self.setFixedSize(PW, PH)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #0b0f14; border-radius: 10px;")
        self.on_click = on_click

    def mousePressEvent(self, e):
        self.on_click(int(e.position().x()), int(e.position().y()))


class OverlayDialog(QDialog):
    def __init__(self, clip, t_clip, cfg=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Superposer une vidéo (fond vert)")
        self.resize(1250, 760)
        self.clip, self.t_clip = clip, t_clip
        self.cfg = chroma.cfg_full(cfg)
        self.result = None
        self.length = 0.0
        self.fg_raw = None
        self.noise = None
        self.picking = False

        self.view = Canvas(self._clicked)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._redraw)
        self.ftimer = QTimer(self)
        self.ftimer.setSingleShot(True)
        self.ftimer.timeout.connect(self._load_fg)

        self.b_file = QPushButton("Choisir la vidéo à superposer...")
        self.b_file.clicked.connect(self._choose)
        self.l_file = QLabel("")
        self.l_file.setWordWrap(True)

        self.swatch = QPushButton()
        self.swatch.setFixedWidth(70)
        self.swatch.clicked.connect(self._color_dialog)
        self.b_pip = QPushButton("🎯 Pipette")
        self.b_pip.setCheckable(True)
        self.b_pip.toggled.connect(self._pip)
        b_auto = QPushButton("Auto")
        b_auto.clicked.connect(self._auto)
        crow = QHBoxLayout()
        crow.addWidget(self.swatch)
        crow.addWidget(self.b_pip)
        crow.addWidget(b_auto)
        crow.addStretch(1)

        self.mode = QComboBox()
        for label, _ in VIEWS:
            self.mode.addItem(label)
        self.mode.currentIndexChanged.connect(lambda _: self._redraw())

        form = QFormLayout()
        # --- passage de la vidéo
        self.s_a, self.l_a = self._time_slider("debut")
        self.s_b, self.l_b = self._time_slider("fin")
        self.s_p = QSlider(Qt.Orientation.Horizontal)
        self.s_p.valueChanged.connect(lambda _: self.ftimer.start(90))
        self.l_p = QLabel("")
        form.addRow(self._title("Passage de la vidéo"))
        form.addRow("Début", self._row(self.s_a, self.l_a))
        form.addRow("Fin", self._row(self.s_b, self.l_b))
        form.addRow("Aperçu à", self._row(self.s_p, self.l_p))
        self.c_cont = QCheckBox("Continuer sur les clips suivants (sans s'arrêter à la fin du clip)")
        self.c_cont.setChecked(bool(self.cfg["continuer"]))
        self.c_cont.toggled.connect(self._cont)
        self.c_loop = QCheckBox("Répéter si elle est plus courte que le clip")
        self.c_loop.setChecked(bool(self.cfg["boucle"]))
        self.c_loop.toggled.connect(lambda v: self.cfg.__setitem__("boucle", v))
        self.c_fluid = QCheckBox("Fluidifier en 60 i/s si la vidéo est en 30 i/s (interpolation)")
        self.c_fluid.setChecked(bool(self.cfg["fluide"]))
        self.c_fluid.toggled.connect(lambda v: self.cfg.__setitem__("fluide", v))
        form.addRow("", self.c_cont)
        form.addRow("", self.c_loop)
        form.addRow("", self.c_fluid)
        # --- détourage
        form.addRow(self._title("Détourage"))
        form.addRow("Couleur du fond à enlever", crow)
        self.sl = {}
        for key, label, lo, hi in [("tolerance", "Tolérance", 0, 100), ("douceur", "Douceur du masque", 0, 100),
                                   ("retrecir", "Rétrécir les bords (px)", 0, 10),
                                   ("adoucir", "Adoucir les bords", 0, 10),
                                   ("spill", "Suppression du débordement", 0, 100),
                                   ("taille", "Taille (%)", 10, 200), ("x", "Position X", -100, 100),
                                   ("y", "Position Y", -100, 100)]:
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(int(round(float(self.cfg[key]))))
            val = QLabel(str(s.value()))
            val.setFixedWidth(34)
            s.valueChanged.connect(lambda v, k=key, lab=val: self._set(k, v, lab))
            form.addRow(label, self._row(s, val))
            self.sl[key] = s
        form.addRow("Affichage", self.mode)
        # --- apparition / disparition
        form.addRow(self._title("Apparition / disparition"))
        for k in ("entree", "sortie"):
            cb = QComboBox()
            for code, label in chroma.TRANSITIONS:
                cb.addItem(label, code)
            cb.setCurrentIndex(max(0, [c for c, _ in chroma.TRANSITIONS].index(self.cfg[k])
                                   if self.cfg[k] in [c for c, _ in chroma.TRANSITIONS] else 0))
            cb.currentIndexChanged.connect(lambda _, k=k, cb=cb: self._trans(k, cb.currentData()))
            sp = QDoubleSpinBox()
            sp.setRange(0.05, 5.0)
            sp.setSingleStep(0.05)
            sp.setSuffix(" s")
            sp.setValue(float(self.cfg[k + "_duree"]))
            sp.valueChanged.connect(lambda v, k=k: self._trans_d(k, v))
            form.addRow("Entrée" if k == "entree" else "Sortie", self._row(cb, sp))

        b_del = QPushButton("Retirer la superposition")
        b_del.clicked.connect(self._remove)
        b_cancel = QPushButton("Annuler")
        b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton("Valider  ✓")
        b_ok.setObjectName("primary")
        b_ok.clicked.connect(self._ok)
        bot = QHBoxLayout()
        bot.addWidget(b_del)
        bot.addStretch(1)
        bot.addWidget(b_cancel)
        bot.addWidget(b_ok)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(self.b_file)
        rl.addWidget(self.l_file)
        rl.addLayout(form)
        rl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        left = QVBoxLayout()
        left.addWidget(self.view)
        tip = QLabel("Astuce : passe en « Masque » et monte la tolérance jusqu'à ce que le fond soit tout noir. "
                     "Si un liseré reste autour du sujet, monte « Rétrécir les bords » de 1 ou 2. "
                     "Bouge « Aperçu à » au début / à la fin pour voir l'entrée et la sortie.")
        tip.setWordWrap(True)
        tip.setMaximumWidth(PW)
        left.addWidget(tip)
        left.addStretch(1)
        top = QHBoxLayout()
        top.addLayout(left)
        top.addWidget(scroll, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(bot)

        self._swatch()
        self._cont(self.c_cont.isChecked())
        img = chroma.read_frame(vclip.source(clip), (vclip.offset(clip) or 0) + t_clip, PW, PH,
                                f"scale={PW}:{PH}:force_original_aspect_ratio=decrease,"
                                f"pad={PW}:{PH}:(ow-iw)/2:(oh-ih)/2,format=rgb24") if clip else None
        self.bg = img if img is not None else np.zeros((PH, PW, 3), np.uint8)
        if self.cfg["fichier"] and Path(self.cfg["fichier"]).is_file():
            self._file_set(self.cfg["fichier"], keep=True)
        else:
            self._redraw()

    # ------------------------------------------------------------ petits widgets
    @staticmethod
    def _title(t):
        lab = QLabel(t)
        lab.setStyleSheet("font-weight: 700; margin-top: 8px;")
        return lab

    @staticmethod
    def _row(*ws):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in ws:
            h.addWidget(x)
        return w

    def _time_slider(self, key):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 0)
        lab = QLabel("0.00 s")
        lab.setFixedWidth(60)
        s.valueChanged.connect(lambda v, k=key: self._time_moved(k, v))
        return s, lab

    # ------------------------------------------------------------ fichier / passage
    def _choose(self):
        f, _ = QFileDialog.getOpenFileName(self, "Vidéo à superposer", "",
                                           "Vidéos (*.mp4 *.mov *.mkv *.webm *.avi);;Tous les fichiers (*)")
        if f:
            self._file_set(f)

    def _file_set(self, f, keep=False):
        from app.core import render, timeremap
        self.cfg["fichier"] = f
        self.length = d = render.duration(f)
        fps = timeremap.source_fps(f) or 0
        self.l_file.setText(f"{Path(f).name}  ({d:.2f} s, {fps:.0f} i/s)")
        n = max(1, int(d * 100))
        a = int(float(self.cfg["debut"]) * 100) if keep else 0
        b = int(float(self.cfg["fin"]) * 100) if keep and self.cfg["fin"] else n
        for s, v in ((self.s_a, a), (self.s_b, b), (self.s_p, a)):
            s.blockSignals(True)
            s.setRange(0, n)
            s.setValue(min(n, v))
            s.blockSignals(False)
        if not keep:
            self.cfg["debut"], self.cfg["fin"] = 0.0, None
        self._labels()
        self._load_fg()
        if not keep and self.fg_raw is not None:
            self._auto()

    def _time_moved(self, k, v):
        if k == "debut":
            if v >= self.s_b.value():
                self.s_b.setValue(min(self.s_b.maximum(), v + 1))
            self.cfg["debut"] = v / 100
            self.s_p.setValue(v)
        else:
            if v <= self.s_a.value():
                self.s_a.setValue(max(0, v - 1))
            self.cfg["fin"] = None if v >= self.s_b.maximum() else v / 100
            self.s_p.setValue(max(self.s_a.value(), v - 1))
        self._labels()
        self.ftimer.start(90)

    def _labels(self):
        self.l_a.setText(f"{self.s_a.value() / 100:.2f} s")
        self.l_b.setText(f"{self.s_b.value() / 100:.2f} s")
        self.l_p.setText(f"{self.s_p.value() / 100:.2f} s")

    def _cont(self, v):
        self.cfg["continuer"] = v
        self.c_loop.setEnabled(not v)

    def _span(self):
        return max(0.05, self.s_b.value() / 100 - self.s_a.value() / 100)

    def _load_fg(self):
        self._labels()
        if not self.cfg["fichier"]:
            return
        w, h, _, _ = chroma.layout(self.cfg, PW, PH)
        self.fg_raw = chroma.read_frame(self.cfg["fichier"], self.s_p.value() / 100, w, h,
                                        chroma.fit_filter(self.cfg, w, h))
        self.noise = chroma._noise(h, w) if self.fg_raw is not None else None
        self._redraw()

    # ------------------------------------------------------------ couleur
    def _swatch(self):
        self.swatch.setStyleSheet(f"background: {self.cfg['couleur']}; border-radius: 6px; min-height: 22px;")
        self.swatch.setToolTip(self.cfg["couleur"])

    def _color_dialog(self):
        c = QColorDialog.getColor(QColor(self.cfg["couleur"]), self, "Couleur du fond à enlever")
        if c.isValid():
            self._color(c.name())

    def _color(self, hexa):
        self.cfg["couleur"] = hexa
        self._swatch()
        if self.cfg["fichier"]:
            self._load_fg()

    def _auto(self):
        if self.fg_raw is not None:
            self._color(chroma.border_color(self.fg_raw))

    def _pip(self, on):
        self.picking = on
        self.view.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        if on:
            self.mode.setCurrentIndex(2)

    def _clicked(self, px, py):
        if not self.picking or self.fg_raw is None:
            return
        _, _, x, y = chroma.layout(self.cfg, PW, PH)
        h, w = self.fg_raw.shape[:2]
        fx, fy = px - x, py - y
        if not (0 <= fx < w and 0 <= fy < h):
            return
        zone = self.fg_raw[max(0, fy - 2):fy + 3, max(0, fx - 2):fx + 3].reshape(-1, 3)
        self.b_pip.setChecked(False)
        self.mode.setCurrentIndex(0)
        self._color(chroma.rgb_hex(np.median(zone, axis=0)))

    # ------------------------------------------------------------ réglages / aperçu
    def _set(self, k, v, lab):
        self.cfg[k] = v
        lab.setText(str(v))
        (self.ftimer if k == "taille" else self.timer).start(60 if k == "taille" else 30)

    def _trans(self, k, code):
        self.cfg[k] = code
        self.timer.start(30)

    def _trans_d(self, k, v):
        self.cfg[k + "_duree"] = v
        self.timer.start(30)

    def _redraw(self):
        out = self.bg
        if self.fg_raw is not None:
            _, _, x, y = chroma.layout(self.cfg, PW, PH)
            t = self.s_p.value() / 100 - self.s_a.value() / 100
            mult, glow = chroma.visibility(self.cfg, t, self._span(), self.fg_raw, self.noise)
            out = chroma.composite(self.bg, self.fg_raw, self.cfg, x, y, scale=PW / 1920,
                                   view=VIEWS[self.mode.currentIndex()][1], mult=mult, glow=glow)
        out = np.ascontiguousarray(out)
        img = QImage(out.data, PW, PH, PW * 3, QImage.Format.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(img.copy()))

    # ------------------------------------------------------------ fin
    def _remove(self):
        self.result = None
        self.accept()

    def _ok(self):
        self.result = dict(self.cfg) if self.cfg["fichier"] else None
        self.accept()
