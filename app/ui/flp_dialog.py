"""Fenêtre « Apprendre d'un projet FL Studio » : l'IA lit tes sound kills dans le .flp."""
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from app.core import edit_learning as el
from app.core import flp
from app.core.project import AUDIO_EXT, VIDEO_EXT

from .widgets import FilePicker
from .workers import FlpLearnThread


def _fmt(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


class FlpDialog(QDialog):
    def __init__(self, ai, library, music=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apprendre d'un projet FL Studio")
        self.resize(640, 640)
        self.ai, self.library = ai, list(library)
        self.proj = None
        self.thread = None
        self.learned = (0, 0)
        self._default_music = music

        hint = QLabel("Choisis le projet FL Studio (.flp) où tu as fait tes sound kills. L'IA lit "
                      "chaque son posé dans la playlist et à quel moment, puis apprend ton style.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        self.flp_pick = FilePicker("Projet FL Studio", {".flp"}, "un projet .flp")
        self.flp_pick.changed.connect(self._load)
        self.info = QLabel("")
        self.info.setWordWrap(True)

        self.music_chan = QComboBox()
        self.music_chan.currentIndexChanged.connect(self._music_chan_changed)
        self.music_pick = FilePicker("Musique de l'edit", AUDIO_EXT | VIDEO_EXT, "la musique")
        if music and Path(music).is_file():
            self.music_pick.set_path(music)
        self.start = QDoubleSpinBox()
        self.start.setRange(-600, 600)
        self.start.setDecimals(2)
        self.start.setSuffix(" s")
        row = QHBoxLayout()
        row.addWidget(QLabel("Musique dans le projet :"))
        row.addWidget(self.music_chan, 1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("La musique commence à"))
        row2.addWidget(self.start)
        row2.addStretch(1)

        self.list = QListWidget()
        self.btn_learn = QPushButton("Apprendre")
        self.btn_learn.setObjectName("primary")
        self.btn_learn.clicked.connect(self.learn)
        b_close = QPushButton("Fermer")
        b_close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(b_close)
        bottom.addWidget(self.btn_learn)

        lay = QVBoxLayout(self)
        for w in (hint, self.flp_pick, self.info):
            lay.addWidget(w)
        lay.addLayout(row)
        lay.addWidget(self.music_pick)
        lay.addLayout(row2)
        lay.addWidget(self.list, 1)
        lay.addLayout(bottom)
        self.btn_learn.setEnabled(False)

    # -----------------------------------------------------------------
    def _load(self, path):
        self.proj = None
        self.list.clear()
        self.music_chan.clear()
        if not path:
            return
        try:
            self.proj = flp.read(path)
        except (OSError, ValueError, IndexError, Exception) as e:
            QMessageBox.warning(self, "Projet FL Studio", f"Impossible de lire ce projet : {e}")
            return
        names = {el._norm(s.path) for s in self.library}
        counts = Counter(c.channel for c in self.proj.clips)
        # la musique : un son qui n'est pas dans ton dossier, le plus gros fichier
        guess, best = None, -1
        self.music_chan.addItem("Pas de musique dans le projet", None)
        for ch, n in counts.items():
            name, sample = self.proj.channels.get(ch, ("", ""))
            label = name or Path(sample.replace("\\", "/")).stem or f"Canal {ch}"
            self.music_chan.addItem(label, ch)
            if el._norm(sample) in names or el._norm(label) in names:
                continue
            size = Path(sample).stat().st_size if sample and Path(sample).is_file() else 0
            if size > best:
                guess, best = ch, size
        if guess is not None:
            self.music_chan.setCurrentIndex(self.music_chan.findData(guess))
        self.info.setText(f"FL Studio {self.proj.version or '?'} · {self.proj.tempo:g} BPM · "
                          f"{len(self.proj.clips)} sons posés dans la playlist.")
        self._refresh_list()

    def _music_chan_changed(self, *a):
        if not self.proj:
            return
        ch = self.music_chan.currentData()
        clips = [c for c in self.proj.clips if c.channel == ch] if ch is not None else []
        if clips:
            c = clips[0]
            self.start.setValue(round(c.time - c.offset, 2))
            sample = self.proj.channels.get(ch, ("", ""))[1]
            if sample and Path(sample).is_file():
                self.music_pick.set_path(sample)
        else:
            self.start.setValue(0.0)
        self._refresh_list()

    def _refresh_list(self):
        self.list.clear()
        if not self.proj:
            return
        names = {el._norm(s.path) for s in self.library}
        ch_music = self.music_chan.currentData()
        n = 0
        for c in self.proj.clips:
            if c.channel == ch_music:
                continue
            known = el._norm(c.sample) in names or el._norm(c.name) in names
            it = QListWidgetItem(f"{_fmt(c.time)}   {c.name}" + ("" if known else "   (pas dans ton dossier)"))
            self.list.addItem(it)
            n += 1
        self.btn_learn.setText(f"Apprendre ({n} sons)")
        self.btn_learn.setEnabled(n > 0)

    def learn(self):
        music = self.music_pick.path
        if not music or not Path(music).is_file():
            QMessageBox.information(self, "Projet FL Studio", "Choisis la musique de l'edit.")
            return
        self.btn_learn.setEnabled(False)
        self.info.setText("Analyse de la musique...")
        th = FlpLearnThread(self.proj, self.library, music, self.start.value(),
                            self.music_chan.currentData(), self)
        th.done.connect(self._done)
        th.failed.connect(lambda m: (QMessageBox.warning(self, "Projet FL Studio", m),
                                     self.btn_learn.setEnabled(True)))
        th.finished.connect(lambda: setattr(self, "thread", None))
        self.thread = th
        th.start()

    def _done(self, example):
        if not example.detections:
            QMessageBox.information(self, "Projet FL Studio",
                                    "Aucun son ne tombe pendant la musique. Vérifie « La musique commence à ».")
            self.btn_learn.setEnabled(True)
            return
        try:
            self.learned = el.apply(self.ai, example)
        except OSError as e:
            QMessageBox.warning(self, "Projet FL Studio", f"Impossible d'enregistrer l'IA : {e}")
            return
        kept, empty = self.learned
        QMessageBox.information(self, "Projet FL Studio",
                                f"C'est appris ! {kept} sound kills et {empty} moments sans son.\n"
                                f"IA : {self.ai.level()}")
        self.accept()

    def done(self, *a):
        if self.thread is not None:
            self.thread.wait(15000)
        super().done(*a)
