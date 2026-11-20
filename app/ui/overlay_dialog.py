"""Fenêtre « Superposer une vidéo » : on choisit une vidéo (fond vert ou autre), la couleur à enlever
(pipette, auto ou nuancier) et on règle le détourage comme Keylight + Advanced Spill Suppressor."""
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

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
        self.clip, self.t_clip = clip, t_clip
        self.cfg = chroma.cfg_full(cfg)
        self.result = None
        self.bg = None
        self.fg_raw = None
        self.shown = None
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

        self.sl = {}
        form = QFormLayout()
        form.addRow("Couleur du fond à enlever", crow)
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
            row = QHBoxLayout()
            row.addWidget(s)
            row.addWidget(val)
            form.addRow(label, row)
            self.sl[key] = s
        self.s_start = QSlider(Qt.Orientation.Horizontal)
        self.s_start.setRange(0, 0)
        self.s_start.setValue(int(float(self.cfg["debut"]) * 100))
        self.s_start.valueChanged.connect(self._start_moved)
        self.l_start = QLabel("0.00 s")
        rs = QHBoxLayout()
        rs.addWidget(self.s_start)
        rs.addWidget(self.l_start)
        form.addRow("Début dans la vidéo", rs)
        self.c_loop = QCheckBox("Répéter la vidéo si elle est plus courte que le plan")
        self.c_loop.setChecked(bool(self.cfg["boucle"]))
        self.c_loop.toggled.connect(lambda v: self.cfg.__setitem__("boucle", v))
        form.addRow("", self.c_loop)
        form.addRow("Affichage", self.mode)

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
        top = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.view)
        tip = QLabel("Astuce : passe en « Masque » et monte la tolérance jusqu'à ce que le fond soit tout noir, "
                     "puis baisse le débordement si le sujet devient gris.")
        tip.setWordWrap(True)
        tip.setMaximumWidth(PW)
        left.addWidget(tip)
        left.addStretch(1)
        top.addLayout(left)
        top.addWidget(right, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(bot)

        self._swatch()
        img = chroma.read_frame(vclip.source(clip), (vclip.offset(clip) or 0) + t_clip, PW, PH,
                                f"scale={PW}:{PH}:force_original_aspect_ratio=decrease,"
                                f"pad={PW}:{PH}:(ow-iw)/2:(oh-ih)/2,format=rgb24") if clip else None
        self.bg = img if img is not None else np.zeros((PH, PW, 3), np.uint8)
        if self.cfg["fichier"] and Path(self.cfg["fichier"]).is_file():
            self._file_set(self.cfg["fichier"], keep=True)
        else:
            self._redraw()

    # ------------------------------------------------------------ fichier
    def _choose(self):
        f, _ = QFileDialog.getOpenFileName(self, "Vidéo à superposer", "",
                                           "Vidéos (*.mp4 *.mov *.mkv *.webm *.avi);;Tous les fichiers (*)")
        if f:
            self._file_set(f)

    def _file_set(self, f, keep=False):
        from app.core import render
        self.cfg["fichier"] = f
        d = render.duration(f)
        self.l_file.setText(f"{Path(f).name}  ({d:.2f} s)")
        self.s_start.blockSignals(True)
        self.s_start.setRange(0, max(0, int(d * 100) - 1))
        self.s_start.setValue(int(float(self.cfg["debut"]) * 100) if keep else 0)
        self.s_start.blockSignals(False)
        if not keep:
            self.cfg["debut"] = 0.0
        self.l_start.setText(f"{self.s_start.value() / 100:.2f} s")
        self._load_fg()
        if not keep and self.fg_raw is not None:
            self._auto()

    def _start_moved(self, v):
        self.cfg["debut"] = v / 100
        self.l_start.setText(f"{v / 100:.2f} s")
        self.ftimer.start(120)

    def _load_fg(self):
        if not self.cfg["fichier"]:
            return
        w, h, _, _ = chroma.layout(self.cfg, PW, PH)
        self.fg_raw = chroma.read_frame(self.cfg["fichier"], float(self.cfg["debut"]), w, h,
                                        chroma.fit_filter(self.cfg, w, h))
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
            self._load_fg()               # les bandes autour prennent la nouvelle couleur

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
        if k in ("taille", "x", "y"):
            self.ftimer.start(120) if k == "taille" else self.timer.start(30)
        else:
            self.timer.start(30)

    def _redraw(self):
        out = self.bg
        if self.fg_raw is not None:
            _, _, x, y = chroma.layout(self.cfg, PW, PH)
            out = chroma.composite(self.bg, self.fg_raw, self.cfg, x, y, scale=PW / 1920,
                                   view=VIEWS[self.mode.currentIndex()][1])
        out = np.ascontiguousarray(out)
        self.shown = out
        img = QImage(out.data, PW, PH, PW * 3, QImage.Format.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(img.copy()))

    # ------------------------------------------------------------ fin
    def _remove(self):
        self.result = None
        self.accept()

    def _ok(self):
        self.result = dict(self.cfg) if self.cfg["fichier"] else None
        self.accept()
