"""Onglet Sons IA : l'IA place des sound kills sur la musique et apprend de tes choix."""
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QSlider, QVBoxLayout, QWidget)

from app.core import sound_ai as sa

from ..style import MUTED, PANEL, PANEL_2, RED
from ..widgets import page_header
from ..workers import AnalyzeThread, RenderThread

ROLE = Qt.ItemDataRole.UserRole


def fmt(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:05.2f}"


def open_file(path):
    """Ouvre un fichier avec le programme par défaut (lecteur audio...)."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ================================================================ timeline ====

class Timeline(QWidget):
    """Forme d'onde + beats + drops + sons placés. Clic = sélection, double-clic = ajouter un son."""
    clicked = pyqtSignal(int)          # id du placement sélectionné
    add_at = pyqtSignal(float)         # temps où ajouter un son

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis = None
        self.placements = []
        self.selected = None
        self.setMinimumHeight(150)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_data(self, analysis, placements, selected=None):
        self.analysis, self.placements, self.selected = analysis, placements, selected
        self.update()

    def _x(self, t):
        d = self.analysis.duration if self.analysis else max([p.t for p in self.placements] + [1]) + 1
        return int(8 + (self.width() - 16) * t / max(d, 0.01))

    def _t(self, x):
        d = self.analysis.duration if self.analysis else 1
        return max(0.0, (x - 8) / max(1, self.width() - 16) * d)

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(PANEL))
        mid = h // 2
        if self.analysis and self.analysis.envelope:
            env = self.analysis.envelope
            p.setPen(QPen(QColor(PANEL_2), 1))
            n = len(env)
            for x in range(8, w - 8):
                v = env[min(n - 1, int((x - 8) / max(1, w - 16) * n))]
                y = int(v * (h * 0.38))
                p.drawLine(x, mid - y, x, mid + y)
            for b in self.analysis.beats:
                x = self._x(b.t)
                if b.drop:
                    p.setPen(QPen(QColor(RED), 2))
                    p.drawLine(x, 0, x, h)
                else:
                    p.setPen(QPen(QColor(MUTED), 1))
                    tick = 14 if b.bar_pos == 0 else 6
                    p.drawLine(x, h - tick, x, h)
            p.setPen(QPen(QColor("#3ddc97"), 1))
            for t in self.analysis.vocal_onsets:
                x = self._x(t)
                p.drawLine(x, 0, x, 5)
        elif not self.placements:
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "Clique sur « Analyser et générer » pour voir ta musique ici")
        for pl in self.placements:
            x = self._x(pl.t)
            color = QColor(sa.COLORS.get(pl.category, MUTED))
            sel = pl.id == self.selected
            p.setPen(QPen(color, 3 if sel else 2))
            p.drawLine(x, 18, x, h - 18)
            p.setBrush(color)
            r = 6 if sel else 4
            p.drawEllipse(x - r, 18 - r, 2 * r, 2 * r)
        p.end()

    def _nearest(self, x):
        if not self.placements:
            return None
        best = min(self.placements, key=lambda pl: abs(self._x(pl.t) - x))
        return best if abs(self._x(best.t) - x) <= 8 else None

    def mousePressEvent(self, event):
        hit = self._nearest(event.position().x())
        if hit is not None:
            self.clicked.emit(hit.id)

    def mouseDoubleClickEvent(self, event):
        if self.analysis and self._nearest(event.position().x()) is None:
            self.add_at.emit(self._t(event.position().x()))


# ================================================================ onglet ====

class SoundsTab(QWidget):
    changed = pyqtSignal()

    def __init__(self, project, parent=None, ai=None):
        super().__init__(parent)
        self.project = project
        self.cfg = project.sons
        self.ai = ai or sa.SoundAI()
        self.library = []
        self.analysis = None
        self.placements = [sa.Placement.from_dict(d) for d in self.cfg.get("placements", [])
                           if isinstance(d, dict)]
        self.threads = []
        self.seed = random.getrandbits(31)
        self.pending_generate = False

        # ---------- réglages (gauche)
        self.lib_label = QLabel()
        self.lib_label.setWordWrap(True)
        self.lib_label.setObjectName("hint")
        b_lib = QPushButton("Choisir le dossier de sons...")
        b_lib.clicked.connect(self.pick_library)

        self.lrc_label = QLabel()
        self.lrc_label.setObjectName("hint")
        self.lrc_label.setWordWrap(True)
        b_lrc = QPushButton("Paroles (.lrc)...")
        b_lrc_clear = QPushButton("Retirer")
        b_lrc.clicked.connect(self.pick_lrc)
        b_lrc_clear.clicked.connect(lambda: self.set_lrc(None))
        self.keywords = QLineEdit(self.cfg.get("mots_cles", ""))
        self.keywords.setPlaceholderText("Mots-clés des paroles (ex. bang, tire, kill)")
        self.keywords.editingFinished.connect(self._save_settings)

        self.density = self._slider(self.cfg.get("densite", 0.5))
        self.creativity = self._slider(self.cfg.get("creativite", 0.3))
        self.c_drops = QCheckBox("Sur les drops")
        self.c_beats = QCheckBox("Sur les temps")
        self.c_voice = QCheckBox("Sur la voix")
        for c, key in ((self.c_drops, "drops"), (self.c_beats, "temps"), (self.c_voice, "voix")):
            c.setChecked(bool(self.cfg.get(key, True)))
            c.toggled.connect(self._save_settings)

        self.btn_generate = QPushButton("Analyser et générer")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.clicked.connect(self.analyze_and_generate)
        self.btn_regen = QPushButton("Autre version")
        self.btn_regen.clicked.connect(self.regenerate)
        self.tempo_label = QLabel("Tempo : —")
        b_half = QPushButton("÷2")
        b_double = QPushButton("×2")
        b_half.setToolTip("Le tempo trouvé est 2 fois trop rapide")
        b_double.setToolTip("Le tempo trouvé est 2 fois trop lent")
        b_half.clicked.connect(lambda: self.fix_tempo(0.5))
        b_double.clicked.connect(lambda: self.fix_tempo(2))

        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(330)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 14, 16, 14)
        ll.setSpacing(8)
        ll.addWidget(self._title("Bibliothèque de sons"))
        ll.addWidget(self.lib_label)
        ll.addWidget(b_lib)
        ll.addSpacing(6)
        ll.addWidget(self._title("Paroles (optionnel)"))
        ll.addWidget(self.lrc_label)
        r = QHBoxLayout()
        r.addWidget(b_lrc)
        r.addWidget(b_lrc_clear)
        ll.addLayout(r)
        ll.addWidget(self.keywords)
        ll.addSpacing(6)
        ll.addWidget(self._title("Réglages"))
        ll.addWidget(QLabel("Quantité de sons"))
        ll.addWidget(self.density)
        ll.addWidget(QLabel("Créativité (surprises)"))
        ll.addWidget(self.creativity)
        for c in (self.c_drops, self.c_beats, self.c_voice):
            ll.addWidget(c)
        ll.addStretch(1)
        tr = QHBoxLayout()
        tr.addWidget(self.tempo_label, 1)
        tr.addWidget(b_half)
        tr.addWidget(b_double)
        ll.addLayout(tr)
        ll.addWidget(self.btn_generate)
        ll.addWidget(self.btn_regen)
        self.btn_learn_edit = QPushButton("Apprendre d'un edit déjà fait...")
        self.btn_learn_edit.setToolTip("L'IA écoute un de tes edits finis et copie ta façon de placer les sons")
        self.btn_learn_edit.clicked.connect(self.learn_from_edit)
        ll.addWidget(self.btn_learn_edit)

        # ---------- timeline + liste (droite)
        self.timeline = Timeline()
        self.timeline.clicked.connect(self.select_id)
        self.timeline.add_at.connect(self.add_at)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._row_changed)
        self.cat_combo = QComboBox()
        b_change = QPushButton("Changer de son")
        b_delete = QPushButton("Supprimer")
        b_listen = QPushButton("Écouter ce son")
        b_change.clicked.connect(self.change_selected)
        b_delete.clicked.connect(self.delete_selected)
        b_listen.clicked.connect(self.listen_selected)
        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel("Catégorie :"))
        edit_row.addWidget(self.cat_combo)
        edit_row.addWidget(b_change)
        edit_row.addWidget(b_listen)
        edit_row.addWidget(b_delete)

        self.level = QLabel()
        self.btn_preview = QPushButton("▶  Écouter l'aperçu")
        self.btn_export = QPushButton("Exporter les WAV...")
        self.btn_photo = QPushButton("Photo des sons...")
        self.btn_photo.setToolTip("Une image avec tous les sons utilisés, à partager")
        self.btn_photo.clicked.connect(self.photo)
        self.btn_validate = QPushButton("Valider : l'IA apprend")
        self.btn_validate.setObjectName("primary")
        b_reset = QPushButton("Réinitialiser l'IA")
        b_reset.setObjectName("link")
        self.btn_preview.clicked.connect(self.preview)
        self.btn_export.clicked.connect(self.export)
        self.btn_validate.clicked.connect(self.validate)
        b_reset.clicked.connect(self.reset_ai)
        bottom = QHBoxLayout()
        bottom.addWidget(self.level, 1)
        bottom.addWidget(b_reset)
        bottom.addWidget(self.btn_preview)
        bottom.addWidget(self.btn_export)
        bottom.addWidget(self.btn_photo)
        bottom.addWidget(self.btn_validate)

        right = QVBoxLayout()
        right.addWidget(self.timeline)
        right.addWidget(self.status)
        right.addWidget(self.list, 1)
        right.addLayout(edit_row)
        right.addLayout(bottom)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(left)
        cols.addLayout(right, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header(
            "Sons IA", "L'IA place des sound kills sur ta musique (beats, drops, voix, paroles). "
                       "Supprime, change ou ajoute des sons (double-clic sur la timeline) puis "
                       "« Valider » : elle apprend tes goûts à chaque edit."))
        lay.addLayout(cols, 1)

        self.load_library(self.cfg.get("dossier"), quiet=True)
        self.set_lrc(self.cfg.get("paroles"), save=False)
        self.refresh()

    # ------------------------------------------------------------ outils
    @staticmethod
    def _title(text):
        lab = QLabel(text)
        lab.setStyleSheet("font-weight: 700;")
        return lab

    def _slider(self, value):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(int(round(float(value) * 100)))
        s.valueChanged.connect(self._save_settings)
        return s

    def _save_settings(self, *args):
        self.cfg.update({
            "mots_cles": self.keywords.text(), "densite": self.density.value() / 100,
            "creativite": self.creativity.value() / 100, "drops": self.c_drops.isChecked(),
            "temps": self.c_beats.isChecked(), "voix": self.c_voice.isChecked()})
        self.changed.emit()

    def _store(self):
        self.cfg["placements"] = [p.to_dict() for p in self.placements]
        self.changed.emit()

    def _busy(self, busy, text=""):
        for b in (self.btn_generate, self.btn_regen, self.btn_preview, self.btn_export, self.btn_validate):
            b.setEnabled(not busy)
        if text:
            self.status.setText(text)

    def _start(self, thread):
        self.threads.append(thread)
        thread.finished.connect(self._cleanup_threads)
        thread.start()

    def _cleanup_threads(self):
        self.threads = [t for t in self.threads if t.isRunning()]

    # ------------------------------------------------------- bibliothèque
    def pick_library(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier de sons (vandal, sheriff, woosh...)",
                                                  self.cfg.get("dossier") or "")
        if folder:
            self.load_library(folder)

    def load_library(self, folder, quiet=False):
        if not folder:
            self.library = []
            self.lib_label.setText("Aucun dossier. Range tes sons dans des sous-dossiers "
                                   "(Vandal, Sheriff, Woosh, Impact...) : l'IA les reconnaît.")
        elif not Path(folder).is_dir():
            self.library = []
            self.lib_label.setText(f"⚠ Dossier introuvable : {folder}")
        else:
            self.library = sa.scan_library(folder)
            summary = sa.library_summary(self.library)
            parts = [f"{sa.LABELS.get(c, c)} {n}" for c, n in sorted(summary.items(), key=lambda x: -x[1])]
            self.lib_label.setText(f"{Path(folder).name} : {len(self.library)} son(s)\n" + " · ".join(parts)
                                   if self.library else f"{Path(folder).name} : aucun son trouvé (wav, mp3, ogg...)")
        if not quiet:
            self.cfg["dossier"] = folder
            self.changed.emit()
        self._fill_categories()

    def _fill_categories(self):
        self.cat_combo.clear()
        for c in sorted(sa.library_summary(self.library)):
            self.cat_combo.addItem(sa.LABELS.get(c, c), c)

    def pick_lrc(self):
        path, _ = QFileDialog.getOpenFileName(self, "Paroles synchronisées", "", "Paroles (*.lrc *.txt)")
        if path:
            self.set_lrc(path)

    def set_lrc(self, path, save=True):
        self.lrc_label.setText(Path(path).name if path else
                               "Aucun fichier. Un .lrc (paroles avec les temps) permet de caler des sons sur des mots.")
        if save:
            self.cfg["paroles"] = path
            self.changed.emit()

    # ----------------------------------------------------------- analyse
    def showEvent(self, event):
        super().showEvent(event)
        if self.analysis is None and self.project.music and Path(self.project.music).is_file() \
                and not self.threads:
            self.run_analysis(generate=False)

    def _keywords(self):
        return [k.strip() for k in self.keywords.text().split(",") if k.strip()]

    def run_analysis(self, generate):
        music = self.project.music
        if not music or not Path(music).is_file():
            QMessageBox.information(self, "Sons IA", "Choisis d'abord une musique dans l'onglet Musique.")
            return
        self.pending_generate = generate
        self._busy(True, "Analyse de la musique...")
        th = AnalyzeThread(music, self.cfg.get("paroles"), self._keywords(), self.cfg.get("tempo_force"), self)
        th.done.connect(self._analysis_done)
        th.failed.connect(self._failed)
        self._start(th)

    def _analysis_done(self, analysis):
        self.analysis = analysis
        self._busy(False)
        txt = f"Tempo : {analysis.tempo:g} BPM"
        self.tempo_label.setText(txt)
        info = (f"{len(analysis.beats)} beats · {len(analysis.drops)} drop(s) · "
                f"{len(analysis.vocal_onsets)} attaques de voix")
        if analysis.lyric_words:
            info += f" · {len(analysis.keyword_hits)} mot(s)-clé(s) trouvé(s) dans les paroles"
        self.status.setText(info)
        if self.pending_generate:
            self.generate()
        self.refresh()

    def _failed(self, message):
        self._busy(False, "")
        QMessageBox.warning(self, "Sons IA", message)

    def analyze_and_generate(self):
        if not self.library:
            QMessageBox.information(self, "Sons IA", "Choisis d'abord ton dossier de sons.")
            return
        if self.analysis is None:
            self.run_analysis(generate=True)
        else:
            self.generate()

    def fix_tempo(self, factor):
        if self.analysis is None:
            return
        self.cfg["tempo_force"] = round(self.analysis.tempo * factor, 2)
        self.changed.emit()
        self.run_analysis(generate=bool(self.placements))

    def regenerate(self):
        self.seed = random.getrandbits(31)
        self.analyze_and_generate()

    def generate(self):
        if self.analysis is None or not self.library:
            return
        self._save_settings()
        try:
            self.placements = self.ai.generate(
                self.analysis, self.library, density=self.density.value() / 100,
                creativity=self.creativity.value() / 100, seed=self.seed,
                use_drops=self.c_drops.isChecked(), use_beats=self.c_beats.isChecked(),
                use_voice=self.c_voice.isChecked(), use_keywords=bool(self._keywords()))
        except ValueError as e:
            QMessageBox.information(self, "Sons IA", str(e))
            return
        self.status.setText(f"{len(self.placements)} son(s) placé(s). Corrige ce qui ne te plaît pas, "
                            "puis « Valider ».")
        self._store()
        self.refresh()

    # ----------------------------------------------------------- liste
    def refresh(self, keep=None):
        keep = keep if keep is not None else self.selected_id()
        self.placements.sort(key=lambda p: p.t)
        self.list.clear()
        row = -1
        for i, p in enumerate(self.placements):
            role = sa.ROLES.get(p.role, p.role)
            tag = " · ajouté" if p.origin == "manuel" else ""
            item = QListWidgetItem(f"{fmt(p.t)}   {sa.LABELS.get(p.category, p.category):<8}  "
                                   f"{Path(p.sound).name}   ({role}{tag})")
            item.setData(ROLE, p.id)
            self.list.addItem(item)
            if p.id == keep:
                row = i
        if row >= 0:
            self.list.setCurrentRow(row)
        self.timeline.set_data(self.analysis, self.placements, keep)
        self.level.setText("IA : " + self.ai.level())

    def selected_id(self):
        row = self.list.currentRow()
        if 0 <= row < self.list.count():
            return self.list.item(row).data(ROLE)
        return None

    def selected(self):
        sid = self.selected_id()
        return next((p for p in self.placements if p.id == sid), None)

    def _row_changed(self, row):
        p = self.selected()
        self.timeline.set_data(self.analysis, self.placements, p.id if p else None)
        if p:
            i = self.cat_combo.findData(p.category)
            if i >= 0:
                self.cat_combo.setCurrentIndex(i)

    def select_id(self, pid):
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE) == pid:
                self.list.setCurrentRow(i)
                return

    # --------------------------------------------------------- corrections
    def _pick_sound(self, category, avoid=None):
        pool = [s for s in self.library if s.category == category]
        if not pool:
            return None
        others = [s for s in pool if s.path != avoid] or pool
        return random.choice(others)

    def change_selected(self):
        p = self.selected()
        cat = self.cat_combo.currentData()
        if p is None or not cat:
            return
        snd = self._pick_sound(cat, avoid=p.sound)
        if snd is None:
            return
        self.ai.learn_change(p, cat, snd.path)
        p.category, p.sound = cat, snd.path
        self._after_learning(p.id)

    def delete_selected(self):
        p = self.selected()
        if p is None:
            return
        row = self.list.currentRow()
        self.ai.learn_delete(p)
        self.placements.remove(p)
        nxt = self.placements[min(row, len(self.placements) - 1)].id if self.placements else None
        self._after_learning(nxt)

    def add_at(self, t):
        cat = self.cat_combo.currentData()
        if not cat or self.analysis is None:
            return
        snd = self._pick_sound(cat)
        if snd is None:
            return
        beats = [b.t for b in self.analysis.beats]
        if beats:                                         # s'aimante sur le beat le plus proche
            nearest = min(beats, key=lambda b: abs(b - t))
            if abs(nearest - t) < 0.12:
                t = nearest
        ctx, role = sa.context_at(self.analysis, t)
        p = sa.Placement(t=round(t, 3), category=cat, sound=snd.path, ctx=ctx, role=role,
                         gain=sa.BASE_GAIN.get(cat, 0.9), origin="manuel", learned=True)
        self.ai.learn_add(ctx, cat, snd.path)
        self.placements.append(p)
        self._after_learning(p.id)

    def _after_learning(self, keep):
        try:
            self.ai.save()
        except OSError:
            pass
        self._store()
        self.refresh(keep)

    def validate(self):
        if not self.placements:
            return
        for p in self.placements:
            self.ai.learn_keep(p)
        self._after_learning(self.selected_id())
        self.status.setText("Merci ! L'IA a retenu tes choix pour les prochains edits.")

    def learn_from_edit(self):
        from ..learn_edit_dialog import LearnFromEditDialog
        if not self.library:
            QMessageBox.information(self, "Sons IA", "Choisis d'abord ton dossier de sons : l'IA s'en sert "
                                                     "pour reconnaître les sons de ton edit.")
            return
        self.edit_dialog = LearnFromEditDialog(self.ai, self.library, self.project.music, open_file, self)
        self.edit_dialog.exec()
        kept, _ = self.edit_dialog.learned
        if kept:
            self.status.setText(f"L'IA a appris de ton edit ({kept} sons). Clique « Autre version » pour voir le résultat.")
        self.refresh(self.selected_id())

    def reset_ai(self):
        answer = QMessageBox.question(self, "Réinitialiser l'IA",
                                      "Oublier tout ce que l'IA a appris de tes edits ?")
        if answer == QMessageBox.StandardButton.Yes:
            self.ai.reset()
            self.refresh()

    # -------------------------------------------------------------- audio
    def listen_selected(self):
        p = self.selected()
        if p and Path(p.sound).is_file():
            open_file(p.sound)

    def preview(self):
        if not self._can_render():
            return
        out = Path(tempfile.gettempdir()) / "auraedit_apercu.wav"
        self._busy(True, "Préparation de l'aperçu...")
        th = RenderThread(self.project.music, list(self.placements), str(out), None, self)
        th.done.connect(self._preview_done)
        th.failed.connect(self._failed)
        self._start(th)

    def _preview_done(self, mix, _sfx):
        self._busy(False, "Aperçu prêt : il s'ouvre dans ton lecteur audio.")
        try:
            open_file(mix)
        except OSError as e:
            QMessageBox.warning(self, "Aperçu", f"Impossible d'ouvrir l'aperçu : {e}")

    def photo(self):
        from ..sounds_photo import make_photo
        if not self.placements:
            QMessageBox.information(self, "Photo des sons", "Aucun son placé pour l'instant.")
            return
        base = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.project.name).strip() or "edit"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la photo des sons",
                                              str(Path.home() / "Pictures" / f"{base} - sons.png"), "Image (*.png)")
        if not path:
            return
        try:
            make_photo(self.placements, self.project.music, self.project.name, path)
        except OSError as e:
            QMessageBox.warning(self, "Photo des sons", str(e))
            return
        open_file(path)

    def export(self):
        if not self._can_render():
            return
        folder = QFileDialog.getExistingDirectory(self, "Où enregistrer les fichiers WAV ?")
        if not folder:
            return
        base = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.project.name).strip() or "edit"
        mix = Path(folder) / f"{base} - musique et sons.wav"
        sfx = Path(folder) / f"{base} - sons seuls.wav"
        self._busy(True, "Export en cours...")
        th = RenderThread(self.project.music, list(self.placements), str(mix), str(sfx), self)
        th.done.connect(lambda m, s: self._busy(False, f"Exporté : {Path(m).name} et {Path(s).name}"))
        th.failed.connect(self._failed)
        self._start(th)

    def _can_render(self):
        if not self.project.music or not Path(self.project.music).is_file():
            QMessageBox.information(self, "Sons IA", "Choisis d'abord une musique dans l'onglet Musique.")
            return False
        if not self.placements:
            QMessageBox.information(self, "Sons IA", "Aucun son placé pour l'instant.")
            return False
        return True

    def stop(self):
        for th in list(self.threads):
            th.wait(10000)
