"""Onglet Musique : le son de l'edit + la frise des moments clip / dash / kunai."""
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from app.core import markers as mk
from app.core.project import AUDIO_EXT

from ..style import PANEL_2
from ..widgets import FilePicker, file_filter, page_header
from ..workers import FuncThread


class Timeline(QWidget):
    """Forme de la musique + repères. Clic sur un repère : change son type. Clic droit : le retire.
    Double-clic dans le vide : ajoute un clip."""
    edited = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.env = None
        self.duration = 0.0
        self.markers = []
        self.setMinimumHeight(170)
        self.setMouseTracking(True)

    def set_audio(self, env, duration):
        self.env, self.duration = env, duration
        self.update()

    def set_markers(self, markers):
        self.markers = markers
        self.update()

    def _area(self):
        return QRectF(self.rect()).adjusted(8, 8, -8, -26)

    def _x(self, t):
        r = self._area()
        return r.left() + r.width() * (t / self.duration if self.duration else 0)

    def _t(self, x):
        r = self._area()
        return max(0.0, min(self.duration, (x - r.left()) / max(1, r.width()) * self.duration))

    def _near(self, x):
        best, dist = None, 7
        for i, m in enumerate(self.markers):
            d = abs(self._x(m["t"]) - x)
            if d < dist:
                best, dist = i, d
        return best

    def mousePressEvent(self, e):
        if not self.duration:
            return
        i = self._near(e.position().x())
        if i is None:
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.markers.pop(i)
        else:
            m = self.markers[i]
            m["type"] = mk.TYPES[(mk.TYPES.index(m["type"]) + 1) % len(mk.TYPES)]
        self.update()
        self.edited.emit()

    def mouseDoubleClickEvent(self, e):
        if self.duration and self._near(e.position().x()) is None:
            self.markers.append({"t": round(self._t(e.position().x()), 3), "type": "clip"})
            self.markers.sort(key=lambda m: m["t"])
            self.update()
            self.edited.emit()

    def mouseMoveEvent(self, e):
        i = self._near(e.position().x()) if self.duration else None
        if i is None:
            self.setToolTip("")
        else:
            m = self.markers[i]
            self.setToolTip(f"{mk.LABELS[m['type']]} à {m['t']:.2f} s — clic : changer, clic droit : retirer")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b0f14"))
        r = self._area()
        if self.env is None or not self.duration:
            p.setPen(QColor("#6b7785"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choisis une musique au-dessus")
            p.end()
            return
        mid = r.center().y()
        p.setPen(QPen(QColor(PANEL_2), 1))
        n = len(self.env)
        for i in range(0, n, max(1, n // int(r.width()) or 1)):
            x = r.left() + r.width() * i / n
            h = self.env[i] * r.height() / 2
            p.drawLine(QPointF(x, mid - h), QPointF(x, mid + h))
        # graduations toutes les 10 s
        p.setPen(QColor("#6b7785"))
        step = 10 if self.duration < 300 else 30
        t = 0
        while t <= self.duration:
            x = self._x(t)
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 4))
            p.drawText(QRectF(x - 30, r.bottom() + 4, 60, 16), Qt.AlignmentFlag.AlignCenter,
                       f"{int(t) // 60}:{int(t) % 60:02d}")
            t += step
        for m in self.markers:
            c = QColor(mk.COLORS[m["type"]])
            x = self._x(m["t"])
            p.setPen(QPen(c, 2))
            p.drawLine(QPointF(x, r.top() + 10), QPointF(x, r.bottom()))
            p.setBrush(c)
            p.drawPolygon(QPolygonF([QPointF(x - 5, r.top()), QPointF(x + 5, r.top()), QPointF(x, r.top() + 9)]))
        p.end()


class MusicTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.thread = None
        self.music = FilePicker("Musique", AUDIO_EXT, "un fichier audio")
        self.music.set_path(project.music)
        self.music.changed.connect(self._set_music)

        self.timeline = Timeline()
        self.timeline.set_markers(project.markers)
        self.timeline.edited.connect(self._edited)
        self.legend = QLabel()
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        self.btns = []

        def btn(text, fn, tip="", primary=False):
            b = QPushButton(text)
            b.setToolTip(tip)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(fn)
            self.btns.append(b)
            return b

        grid = QGridLayout()
        grid.addWidget(QLabel("Placer les moments clip / dash / kunai :"), 0, 0, 1, 3)
        grid.addWidget(btn("Depuis mes soundkills (Sons IA)", self.from_sounds,
                           "Prend les sound kills placés dans l'onglet Sons IA."), 1, 0)
        grid.addWidget(btn("Depuis un audio avec soundkills...", self.from_soundkill_audio,
                           "Ta musique avec tes sound kills déjà faits : le logiciel les retrouve.", True), 1, 1)
        grid.addWidget(btn("Depuis un audio de claps...", self.from_claps,
                           "Un clap par moment, avec le clap de chaque type (voir « Mes claps » en bas)."), 1, 2)
        grid.addWidget(QLabel("Claps :"), 2, 0, 1, 3)
        grid.addWidget(btn("Créer l'audio de claps...", self.make_claps,
                           "Fabrique automatiquement l'audio de claps à partir des repères."), 3, 0)
        grid.addWidget(btn("Exporter les 3 claps (WAV)...", self.export_claps,
                           "Pour faire ton audio de claps toi-même dans FL Studio."), 3, 1)
        grid.addWidget(btn("Tout effacer", self.clear), 3, 2)

        # --- mes claps : mes propres fichiers audio pour chaque type
        grid.addWidget(QLabel("Mes claps (tes propres sons) :"), 4, 0, 1, 3)
        self.clap_labels = {}
        crow = QHBoxLayout()
        for kind in mk.TYPES:
            box = QFrame()
            box.setStyleSheet(f"QFrame {{ border: 1px solid {mk.COLORS[kind]}; border-radius: 8px; }}"
                              "QLabel, QPushButton { border: none; }")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 6, 10, 6)
            head = QLabel(f'<span style="color:{mk.COLORS[kind]}">■</span> {mk.LABELS[kind]}')
            head.setTextFormat(Qt.TextFormat.RichText)
            name = QLabel()
            name.setObjectName("hint")
            self.clap_labels[kind] = name
            r = QHBoxLayout()
            b_pick = QPushButton("Choisir...")
            b_pick.clicked.connect(lambda _=False, k=kind: self.pick_clap(k))
            b_play = QPushButton("▶")
            b_play.setFixedWidth(36)
            b_play.setToolTip("Écouter")
            b_play.clicked.connect(lambda _=False, k=kind: self.play_clap(k))
            b_reset = QPushButton("↺")
            b_reset.setFixedWidth(36)
            b_reset.setToolTip("Revenir au clap du logiciel")
            b_reset.clicked.connect(lambda _=False, k=kind: self.reset_clap(k))
            r.addWidget(b_pick, 1)
            r.addWidget(b_play)
            r.addWidget(b_reset)
            bl.addWidget(head)
            bl.addWidget(name)
            bl.addLayout(r)
            crow.addWidget(box)
        grid.addLayout(crow, 5, 0, 1, 3)
        self._clap_names()

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        title = QLabel("Moments de l'edit sur la musique")
        title.setStyleSheet("font-weight: 700;")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.legend)
        cl.addLayout(top)
        cl.addWidget(self.timeline)
        hint = QLabel("Clic sur un repère : changer son type. Clic droit : le retirer. Double-clic : ajouter un clip.")
        hint.setObjectName("hint")
        cl.addWidget(hint)
        cl.addLayout(grid)
        cl.addWidget(self.status)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)
        lay.addWidget(page_header("Musique", "Le son sur lequel l'edit sera monté, et à quels moments viennent "
                                             "les clips, les dash et les kunais."))
        lay.addWidget(self.music)
        lay.addWidget(card, 1)
        self._legend()
        if project.music:
            self._load_env()

    # ------------------------------------------------------------ outils
    def _legend(self):
        counts = {k: sum(1 for m in self.project.markers if m["type"] == k) for k in mk.TYPES}
        self.legend.setText("   ".join(f'<span style="color:{mk.COLORS[k]}">■</span> {mk.LABELS[k]} : {counts[k]}'
                                       for k in mk.TYPES))

    def _edited(self):
        self.project.markers = self.timeline.markers
        self._legend()
        self.changed.emit()

    def _set_markers(self, markers, source):
        self.project.markers = mk.clean(markers)
        self.timeline.set_markers(self.project.markers)
        self._edited()
        n = len(self.project.markers)
        self.status.setText(f"{n} moment(s) trouvé(s) {source}. Vérifie-les sur la frise." if n else
                            f"Aucun moment trouvé {source}.")

    def _run(self, fn, done, text):
        if self.thread is not None and self.thread.isRunning():
            return
        for b in self.btns:
            b.setEnabled(False)
        self.status.setText(text)
        self.thread = FuncThread(fn, self)
        self.thread.progress.connect(lambda t, f: self.status.setText(f"{t} ({int(f * 100)} %)"))
        self.thread.done.connect(lambda res: (self._unlock(), done(res)))
        self.thread.failed.connect(lambda msg: (self._unlock(), self.status.setText(f"Impossible : {msg}")))
        self.thread.start()

    def _unlock(self):
        for b in self.btns:
            b.setEnabled(True)

    def _need_music(self):
        if not self.project.music or not Path(self.project.music).is_file():
            QMessageBox.information(self, "Musique", "Choisis d'abord la musique (sans les sons).")
            return False
        return True

    def _load_env(self):
        path = self.project.music
        self._run(lambda prog: mk.envelope(path), lambda res: self.timeline.set_audio(*res),
                  "Lecture de la musique...")

    def _set_music(self, path):
        self.project.music = path
        self.changed.emit()
        if path:
            self._load_env()
        else:
            self.timeline.set_audio(None, 0.0)

    # ----------------------------------------------------------- sources
    def from_sounds(self):
        pl = (self.project.sons or {}).get("placements") or []
        if not pl:
            self.status.setText("Aucun sound kill dans l'onglet Sons IA pour l'instant.")
            return
        self._set_markers(mk.from_placements(pl), "dans tes sound kills")

    def from_soundkill_audio(self):
        if not self._need_music():
            return
        f, _ = QFileDialog.getOpenFileName(self, "Audio avec tes sound kills déjà faits (musique + sons)", "",
                                           file_filter("Audio / vidéo", AUDIO_EXT | {".mp4", ".mov", ".mkv"}))
        if not f:
            return
        music = self.project.music
        folder = (self.project.sons or {}).get("dossier")

        def job(prog):
            library = None
            if folder and Path(folder).is_dir():
                from app.core import sound_ai as sa
                library = sa.scan_library(folder)
            return mk.from_soundkill_audio(f, music, library, prog)

        self._run(job, lambda res: (self._set_markers(res, "dans ton audio"), self._offer_claps()),
                  "Recherche de tes sound kills...")

    def from_claps(self):
        f, _ = QFileDialog.getOpenFileName(self, "Audio de claps (calé sur le début de la musique)", "",
                                           file_filter("Audio", AUDIO_EXT))
        if f:
            self._run(lambda prog: mk.from_claps(f), lambda res: self._set_markers(res, "dans tes claps"),
                      "Lecture des claps...")

    def _offer_claps(self):
        if self.project.markers and QMessageBox.question(
                self, "Audio de claps", "Créer l'audio de claps à partir de ces sound kills ?\n"
                "(clap médium = clip, grave = dash, aigu = kunai) — tu pourras le corriger dans FL Studio "
                "s'il manque des moments, puis le réimporter.") == QMessageBox.StandardButton.Yes:
            self.make_claps()

    # ------------------------------------------------------------- claps
    def make_claps(self):
        if not self.project.markers:
            self.status.setText("Aucun moment : place-les d'abord (sound kills ou claps).")
            return
        base = Path(self.project.music).stem if self.project.music else "edit"
        out, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'audio de claps",
                                             str(Path.home() / f"{base} - claps.wav"), "WAV (*.wav)")
        if not out:
            return
        if not out.lower().endswith(".wav"):
            out += ".wav"
        markers = list(self.project.markers)
        music = self.project.music if self.project.music and Path(self.project.music).is_file() else None
        dur = self.timeline.duration

        def job(prog):
            from app.core import audio
            claps, mixed = mk.clap_track(markers, dur, music)
            audio.save_wav(out, claps, mk.SR)
            files = [out]
            if mixed is not None:
                p2 = out[:-4] + " (avec musique).wav"
                audio.save_wav(p2, mixed, mk.SR)
                files.append(p2)
            return files

        self._run(job, lambda files: self.status.setText("Audio de claps créé : " + " / ".join(
            Path(x).name for x in files)), "Création de l'audio de claps...")

    def _clap_names(self):
        custom = mk.custom_claps()
        for kind, lab in self.clap_labels.items():
            lab.setText(Path(custom[kind]).name if kind in custom else "clap du logiciel")

    def pick_clap(self, kind):
        f, _ = QFileDialog.getOpenFileName(self, f"Ton son pour : {mk.LABELS[kind]}", "",
                                           file_filter("Audio", AUDIO_EXT))
        if f:
            mk.set_custom_clap(kind, f)
            self._clap_names()
            self.status.setText(f"{mk.LABELS[kind]} : ton son « {Path(f).name} » sera utilisé pour créer "
                                "et pour reconnaître les claps.")

    def reset_clap(self, kind):
        mk.set_custom_clap(kind, None)
        self._clap_names()

    def play_clap(self, kind):
        import tempfile
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        from app.core import audio
        out = Path(tempfile.gettempdir()) / f"auraedit_clap_{kind}.wav"
        try:
            audio.save_wav(out, mk.clap(kind), mk.SR)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        except OSError as e:
            self.status.setText(f"Lecture impossible : {e}")

    def export_claps(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier où mettre les 3 claps")
        if folder:
            files = mk.export_claps(folder)
            self.status.setText("Claps exportés : " + ", ".join(Path(f).name for f in files) + ".")

    def clear(self):
        if self.project.markers and QMessageBox.question(self, "Effacer", "Effacer tous les moments ?") \
                == QMessageBox.StandardButton.Yes:
            self._set_markers([], "")

    def stop(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.wait(5000)
