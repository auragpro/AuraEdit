"""Fenêtre « Apprendre d'un edit déjà fait ».

1. Tu choisis un edit fini (vidéo ou audio) et sa musique d'origine.
2. L'IA écoute l'edit, retire la musique et reconnaît tes sound kills (avec ton dossier de sons).
3. Tu vois la liste : décoche ce qui est faux, puis « Apprendre » → l'IA copie ton style.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                             QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from app.core import edit_learning as el
from app.core import sound_ai as sa
from app.core.project import AUDIO_EXT, VIDEO_EXT

from .widgets import FilePicker
from .workers import ListenThread

ROLE = Qt.ItemDataRole.UserRole
ROLE_NAMES = {"drop": "drop", "avant_drop": "montée vers le drop", "temps_fort": "temps fort",
              "caisse_claire": "caisse claire", "grosse_caisse": "grosse caisse",
              "contre_temps": "entre deux temps", "voix": "voix", "mot_cle": "mot-clé"}


def fmt(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


class LearnFromEditDialog(QDialog):
    def __init__(self, ai, library, music=None, play=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apprendre d'un edit déjà fait")
        self.resize(640, 620)
        self.ai, self.library, self.play = ai, list(library), play
        self.example = None
        self.thread = None
        self.learned = (0, 0)

        intro = QLabel("Donne un edit que tu as déjà fini et sa musique d'origine (sans sons). "
                       "L'IA l'écoute, retrouve chaque sound kill de ton dossier et apprend "
                       "où et quoi tu mets.")
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        self.edit_pick = FilePicker("Edit fini (vidéo ou audio)", VIDEO_EXT | AUDIO_EXT, "un edit")
        self.music_pick = FilePicker("Musique d'origine (sans les sons)", AUDIO_EXT | VIDEO_EXT, "une musique")
        if music and Path(music).is_file():
            self.music_pick.set_path(music)
        self.edit_pick.changed.connect(self._inputs_changed)
        self.music_pick.changed.connect(self._inputs_changed)

        self.btn_listen = QPushButton("Écouter l'edit")
        self.btn_listen.setObjectName("primary")
        self.btn_listen.clicked.connect(self.listen)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._play_item)
        self.btn_play = QPushButton("Écouter ce son")
        self.btn_play.clicked.connect(lambda: self._play_item(self._current()))
        self.btn_fix = QPushButton("Corriger ce son...")
        self.btn_fix.setToolTip("L'IA s'est trompée ? Choisis le bon sound kill à cet endroit")
        self.btn_fix.clicked.connect(self.fix_item)
        self.btn_all = QPushButton("Tout cocher")
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        self.btn_learn = QPushButton("Apprendre")
        self.btn_learn.setObjectName("primary")
        self.btn_learn.clicked.connect(self.learn)
        b_close = QPushButton("Fermer")
        b_close.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_fix)
        row.addWidget(self.btn_all)
        row.addStretch(1)
        row.addWidget(b_close)
        row.addWidget(self.btn_learn)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(self.edit_pick)
        lay.addWidget(self.music_pick)
        lay.addWidget(self.btn_listen)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addWidget(self.list, 1)
        lay.addLayout(row)
        if not self.library:
            self.status.setText("⚠ Choisis d'abord ton dossier de sons dans l'onglet Sons IA : "
                                "l'IA s'en sert pour reconnaître tes sound kills.")
        self._inputs_changed()

    # ----------------------------------------------------------------
    def _inputs_changed(self, *args):
        ok = bool(self.library and self.edit_pick.path and self.music_pick.path
                  and Path(self.edit_pick.path).is_file() and Path(self.music_pick.path).is_file())
        running = self.thread is not None
        self.btn_listen.setEnabled(ok and not running)
        has = self.example is not None and self.list.count() > 0
        for b in (self.btn_learn, self.btn_play, self.btn_fix, self.btn_all):
            b.setEnabled(has and not running)

    def listen(self):
        if self.edit_pick.path == self.music_pick.path:
            QMessageBox.warning(self, "Apprendre d'un edit", "L'edit et la musique sont le même fichier.")
            return
        self.example = None
        self.list.clear()
        self.bar.setValue(0)
        self.bar.setVisible(True)
        th = ListenThread(self.edit_pick.path, self.music_pick.path, self.library, self)
        th.progress.connect(self._progress)
        th.done.connect(self._done)
        th.failed.connect(self._failed)
        th.finished.connect(self._finished)
        self.thread = th
        self._inputs_changed()
        th.start()

    def _progress(self, text, frac):
        self.status.setText(text)
        self.bar.setValue(int(frac * 100))

    def _finished(self):
        self.thread = None
        self.bar.setVisible(False)
        self._inputs_changed()

    def _failed(self, message):
        self.status.setText("")
        QMessageBox.warning(self, "Apprendre d'un edit", message)

    def _done(self, example):
        self.example = example
        dets = example.detections
        cats = {}
        for d in dets:
            cats[d.category] = cats.get(d.category, 0) + 1
        resume = " · ".join(f"{sa.LABELS.get(c, c)} {n}" for c, n in sorted(cats.items(), key=lambda x: -x[1]))
        where = (f"la musique commence à {fmt(example.shift + example.start)} dans l'edit"
                 if example.shift + example.start > 0.3 else "la musique commence au début de l'edit")
        if not dets:
            self.status.setText(f"Musique retrouvée ({where}) mais aucun de tes sons n'a été reconnu. "
                                "Vérifie que ce sont bien les sons de ton dossier.")
        else:
            self.status.setText(f"{len(dets)} sound kill(s) retrouvé(s) — {resume}.\n"
                                f"Musique calée ({where}, morceau utilisé de {fmt(example.start)} à {fmt(example.end)}). "
                                "Double-clic pour écouter. Mauvais son ? « Corriger ce son... ». Pas de son du tout ? Décoche-le. Puis « Apprendre ».")
        for i, d in enumerate(dets):
            it = QListWidgetItem(self._text(d))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if d.keep else Qt.CheckState.Unchecked)
            it.setData(ROLE, i)
            self.list.addItem(it)
        self.btn_learn.setText(f"Apprendre ({len(dets)} sons)" if dets else "Apprendre")

    @staticmethod
    def _text(d):
        if d.score >= 1.0 and getattr(d, "fixed", False):
            sure = "corrigé par toi"
        else:
            sure = ("sûr" if d.score >= el.MATCH_THRESHOLD else "à vérifier") + f" ({int(round(d.score * 100))} %)"
        return (f"{fmt(d.t_edit)}   {sa.LABELS.get(d.category, d.category)} — {Path(d.sound).name}"
                f"   ·  {ROLE_NAMES.get(d.role, d.role)}   ·  {sure}")

    def fix_item(self):
        it = self._current()
        if it is None or self.example is None:
            QMessageBox.information(self, "Corriger", "Sélectionne d'abord un son dans la liste.")
            return
        d = self.example.detections[it.data(ROLE)]
        names = [Path(s.path).name for s in self.library]
        cur = names.index(Path(d.sound).name) if Path(d.sound).name in names else 0
        name, ok = QInputDialog.getItem(self, "Corriger ce son",
                                        f"À {fmt(d.t_edit)}, le vrai sound kill était :", names, cur, False)
        if not ok:
            return
        s = self.library[names.index(name)]
        d.sound, d.category, d.score, d.keep = s.path, s.category, 1.0, True
        d.fixed = True
        it.setText(self._text(d))
        it.setCheckState(Qt.CheckState.Checked)
        if self.play:
            self.play(s.path)

    def _current(self):
        r = self.list.currentRow()
        return self.list.item(r) if 0 <= r < self.list.count() else None

    def _play_item(self, item):
        if item is None or self.example is None or not self.play:
            return
        d = self.example.detections[item.data(ROLE)]
        if Path(d.sound).is_file():
            self.play(d.sound)

    def _check_all(self, on):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def learn(self):
        if self.example is None:
            return
        for i in range(self.list.count()):
            it = self.list.item(i)
            self.example.detections[it.data(ROLE)].keep = it.checkState() == Qt.CheckState.Checked
        try:
            self.learned = el.apply(self.ai, self.example)
        except OSError as e:
            QMessageBox.warning(self, "Apprendre d'un edit", f"Impossible d'enregistrer l'IA : {e}")
            return
        kept, empty = self.learned
        self.total = getattr(self, "total", 0) + kept
        self.learned = (self.total, empty)
        self.edits_done = getattr(self, "edits_done", 0) + 1
        QMessageBox.information(self, "Apprendre d'un edit",
                                f"C'est appris ! {kept} son(s) retenu(s) et {empty} moment(s) où tu n'as rien mis.\n"
                                f"IA : {self.ai.level()}\n\n"
                                "Donne-lui un autre edit pour qu'elle s'améliore encore, ou ferme la fenêtre.")
        self.example = None
        self.list.clear()
        self.edit_pick.set_path(None)
        self.status.setText(f"{self.edits_done} edit(s) appris. Choisis un autre edit (et sa musique).")
        self._inputs_changed()

    def done(self, *a):          # fermeture : on attend la fin de l'écoute
        if self.thread is not None:
            self.thread.wait(15000)
        super().done(*a)
