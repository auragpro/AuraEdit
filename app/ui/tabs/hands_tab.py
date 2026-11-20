"""Onglets Kunai et Dash : deux mains (gauche / droite), chacune avec ses propres vidéos."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from app.core.project import VIDEO_EXT

from ..style import MUTED, PANEL_2, RED
from ..widgets import file_filter, page_header

ROLE = Qt.ItemDataRole.UserRole
SIDES = (("gauche", "Main gauche"), ("droite", "Main droite"))


class HandsPreview(QWidget):
    """Schéma de l'écran : les côtés qui ont des vidéos s'allument."""

    def __init__(self, word, parent=None):
        super().__init__(parent)
        self.word = word
        self.sides = {"gauche": 0, "droite": 0}
        self.enabled = True
        self.setMinimumSize(300, 150)
        self.setMaximumHeight(220)

    def set_state(self, sides, enabled):
        self.sides, self.enabled = sides, enabled
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = min(self.width(), self.height() * 16 / 9)
        h = w * 9 / 16
        screen = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.setPen(QPen(QColor(MUTED), 1))
        p.setBrush(QColor(PANEL_2))
        p.drawRoundedRect(screen, 6, 6)
        p.setPen(QColor(MUTED))
        p.drawText(screen, Qt.AlignmentFlag.AlignCenter, "ton clip")
        side_w = screen.width() * 0.26
        zones = {"gauche": QRectF(screen.left() + 8, screen.top() + 8, side_w, screen.height() - 16),
                 "droite": QRectF(screen.right() - 8 - side_w, screen.top() + 8, side_w, screen.height() - 16)}
        for name, rect in zones.items():
            n = self.sides.get(name, 0)
            on = self.enabled and n > 0
            color = QColor(RED if on else MUTED)
            color.setAlpha(200 if on else 60)
            p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine if on else Qt.PenStyle.DashLine))
            fill = QColor(RED)
            fill.setAlpha(55 if on else 0)
            p.setBrush(fill)
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor("white") if on else QColor(MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.word}\n{name}\n({n})")
        p.end()


class HandsTab(QWidget):
    changed = pyqtSignal()
    ATTR = "kunai"           # project.kunai ou project.dash
    TITLE = "Kunai"
    HINT = ""
    ENABLE = "Activer"

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        s = self.settings

        self.enabled = QCheckBox(self.ENABLE)
        self.enabled.setChecked(s.enabled)
        self.enabled.toggled.connect(self._toggle)
        self.preview = HandsPreview(self.TITLE.lower())

        self.lists, self.counts = {}, {}
        cols = QHBoxLayout()
        cols.setSpacing(16)
        for side, label in SIDES:
            lst = QListWidget()
            lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            for v in getattr(s, side):
                lst.addItem(self._item(v))
            b_add = QPushButton("Ajouter des vidéos...")
            b_add.setObjectName("primary")
            b_remove = QPushButton("Retirer")
            b_add.clicked.connect(lambda _=False, sd=side: self.add_videos(sd))
            b_remove.clicked.connect(lambda _=False, sd=side: self.remove_selected(sd))
            if self.ATTR in ("kunai", "dashback", "dismiss"):
                b_remap = QPushButton("⏱ Time remap...")
                b_remap.setToolTip("Régler le time remap des vidéos sélectionnées (double-clic aussi).")
                b_remap.clicked.connect(lambda _=False, sd=side: self.remap_selected(sd))
                lst.itemDoubleClicked.connect(lambda it: self.open_remap([it.data(ROLE)]))
            count = QLabel()
            count.setObjectName("hint")
            title = QLabel(("✋  " if side == "gauche" else "🤚  ") + label)
            title.setStyleSheet("font-size: 16px; font-weight: 700;")
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.addWidget(title)
            cl.addWidget(lst, 1)
            row = QHBoxLayout()
            row.addWidget(b_add)
            row.addWidget(b_remove)
            if self.ATTR in ("kunai", "dashback", "dismiss"):
                row.addWidget(b_remap)
            cl.addLayout(row)
            cl.addWidget(count)
            cols.addWidget(card, 1)
            self.lists[side], self.counts[side] = lst, count

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.addWidget(page_header(self.TITLE, self.HINT))
        top = QHBoxLayout()
        top.addWidget(self.enabled)
        top.addStretch(1)
        if self.ATTR == "dash":
            b_split = QPushButton("✂ Couper une compilation de dash...")
            b_split.setToolTip("Coupe une compilation à la 1re frame de chaque dash après un kill : dash1, dash2...")
            b_split.clicked.connect(self.split_compilation)
            top.addWidget(b_split)
        lay.addLayout(top)
        lay.addWidget(self.preview)
        lay.addLayout(cols, 1)
        self._refresh()

    def split_compilation(self):
        from PyQt6.QtWidgets import QMessageBox
        from ..dash_split_dialog import DashSplitDialog
        dlg = DashSplitDialog(self)
        if not (dlg.exec() and dlg.result):
            return
        box = QMessageBox(self)
        box.setWindowTitle("Compilation coupée")
        box.setText(f"{len(dlg.result)} dash enregistré(s) à part (dash1, dash2...) dans « Mes clips » → Dash.\n\n"
                    "Je les ajoute aussi ici, dans quelle main ?")
        b_g = box.addButton("Main gauche", QMessageBox.ButtonRole.AcceptRole)
        b_d = box.addButton("Main droite", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Ne pas ajouter", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        side = {b_g: "gauche", b_d: "droite"}.get(box.clickedButton())
        if side:
            current = set(getattr(self.settings, side))
            for f in dlg.result:
                if f not in current:
                    self.lists[side].addItem(self._item(f))
                    current.add(f)
            self._sync()

    @property
    def settings(self):
        return getattr(self.project, self.ATTR)

    def _item(self, path):
        p = Path(path)
        mark = "⏱ " if self.ATTR in ("kunai", "dashback", "dismiss") and str(path) in self.project.remaps else ""
        item = QListWidgetItem(mark + (p.name if p.is_file() else f"⚠ {p.name} (introuvable)"))
        item.setData(ROLE, str(path))
        item.setToolTip(str(path))
        return item

    def _toggle(self, on):
        self.settings.enabled = on
        self._refresh()
        self.changed.emit()

    def add_videos(self, side):
        label = dict(SIDES)[side]
        files, _ = QFileDialog.getOpenFileNames(self, f"{self.TITLE} — {label}", "",
                                                file_filter("Vidéos", VIDEO_EXT))
        current = set(getattr(self.settings, side))
        for f in files:
            if f not in current:
                self.lists[side].addItem(self._item(f))
                current.add(f)
        if files:
            self._sync()

    def remove_selected(self, side):
        lst = self.lists[side]
        for it in lst.selectedItems():
            lst.takeItem(lst.row(it))
        self._sync()

    # ------------------------------------------------------- time remap kunai
    def remap_selected(self, side):
        paths = [it.data(ROLE) for it in self.lists[side].selectedItems()]
        if not paths:
            paths = [self.lists[side].item(i).data(ROLE) for i in range(self.lists[side].count())]
        self.open_remap(paths)

    def open_remap(self, paths):
        from ..timeremap_dialog import TimeRemapDialog
        for p in paths:
            dlg = TimeRemapDialog(self.project, p, None, (), self, mode=self.ATTR)
            dlg.exec()
            if dlg.skip_all:
                break
        self._relabel()
        self.changed.emit()

    def _relabel(self):
        for lst in self.lists.values():
            for i in range(lst.count()):
                it = lst.item(i)
                it.setText(self._item(it.data(ROLE)).text())

    def showEvent(self, e):
        super().showEvent(e)
        if self.ATTR in ("kunai", "dashback", "dismiss"):
            try:
                from app.core import timeremap as tr
                saved = tr.clip_remaps()
                for v in self.settings.videos:
                    if v in saved and v not in self.project.remaps:
                        self.project.remaps[v] = saved[v]
            except Exception:
                pass
            self._relabel()

    def _sync(self):
        for side, lst in self.lists.items():
            setattr(self.settings, side, [lst.item(i).data(ROLE) for i in range(lst.count())])
        self.settings.sync()
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        on = self.settings.enabled
        sides = {}
        for side, lst in self.lists.items():
            lst.setEnabled(on)
            n = lst.count()
            sides[side] = n
            self.counts[side].setText(f"{n} vidéo(s)" if n else "Aucune vidéo pour l'instant.")
        self.preview.set_state(sides, on)
