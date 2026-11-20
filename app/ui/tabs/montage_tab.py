"""Onglet Montage : de gros carrés (Intro, Musique, Clips, Kunai, Dash, Générer). Un clic ouvre la partie."""
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QGridLayout, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout,
                             QWidget)

from ..style import PANEL, PANEL_2, RED
from ..widgets import page_header
from .clips_tab import ClipsTab
from .dash_tab import DashTab
from .dashback_tab import DashBackTab
from .dismiss_tab import DismissTab
from .intro_tab import IntroTab
from .kunai_tab import KunaiTab
from .music_tab import MusicTab
from .shake_tab import ShakeTab

PARTS = [("Intro", IntroTab), ("Musique", MusicTab), ("Clips", ClipsTab),
         ("Kunai", KunaiTab), ("Dash", DashTab), ("Dash back", DashBackTab), ("Dismiss", DismissTab),
         ("Shake", ShakeTab)]
ICONS = {"Intro": "🎬", "Musique": "🎵", "Clips": "🔪", "Kunai": "🗡", "Dash": "💨", "Dash back": "↩", "Dismiss": "🌀", "Shake": "💥", "Reproduire": "🎞", "Générer": "▶"}

TILE_CSS = f"""
QPushButton {{ background: {PANEL}; border: 2px solid {PANEL_2}; border-radius: 14px;
              font-size: 17px; font-weight: 600; padding: 18px; text-align: center; }}
QPushButton:hover {{ border: 2px solid {RED}; }}
"""
GEN_CSS = TILE_CSS.replace(f"background: {PANEL};", f"background: {RED};")


class MontageTab(QWidget):
    changed = pyqtSignal()
    render_requested = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.stack = QStackedWidget()
        self.parts = {}
        self.tiles = {}

        # --- page des carrés
        grid_page = QWidget()
        grid = QGridLayout()
        grid.setSpacing(18)
        names = [n for n, _ in PARTS] + ["Reproduire", "Générer"]
        for i, name in enumerate(names):
            b = QPushButton()
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            b.setMinimumSize(180, 150)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(GEN_CSS if name == "Générer" else TILE_CSS)
            if name == "Générer":
                b.clicked.connect(self.render_requested.emit)
            elif name == "Reproduire":
                b.clicked.connect(self.reproduce)
            else:
                b.clicked.connect(lambda _=False, n=name: self.open(n))
            self.tiles[name] = b
            grid.addWidget(b, i // 4, i % 4)
        gl = QVBoxLayout(grid_page)
        gl.setContentsMargins(32, 28, 32, 28)
        gl.addWidget(page_header("Montage", "Clique sur un carré pour le remplir. Tout est sauvegardé automatiquement."))
        gl.addLayout(grid, 1)
        self.stack.addWidget(grid_page)

        # --- une page par partie, avec un bouton retour
        for name, cls in PARTS:
            page = cls(project)
            page.changed.connect(self._changed)
            self.parts[name] = page
            back = QPushButton("←  Retour au Montage")
            back.setObjectName("link")
            back.setStyleSheet("text-align: left; padding: 14px 32px 0 32px;")
            back.clicked.connect(self.home)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(0)
            wl.addWidget(back)
            wl.addWidget(page, 1)
            self.stack.addWidget(wrap)
        self.parts["Kunai"].changed.connect(self.parts["Clips"].refresh_left)
        for n in ("Dash", "Dash back", "Dismiss"):
            self.parts[n].changed.connect(self.parts["Clips"].refresh_left)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.refresh()

    def open(self, name):
        if name in self.parts:
            self.stack.setCurrentIndex([n for n, _ in PARTS].index(name) + 1)

    def home(self):
        self.refresh()
        self.stack.setCurrentIndex(0)

    def _changed(self):
        self.refresh()
        self.changed.emit()

    def refresh(self):
        p = self.project
        def name(f):
            return __import__("app.core.vclip", fromlist=["x"]).name(f) if f else None

        def hands(st):
            if not st.enabled:
                return "désactivé"
            if not st.videos:
                return "✗ aucune vidéo"
            return f"✓ gauche {len(st.gauche)} · droite {len(st.droite)}"
        info = {
            "Intro": ("✓ " + name(p.intro)) if p.intro else "✗ à choisir",
            "Musique": (f"✓ {len(p.markers)} moment(s)" if p.markers else "✓ " + name(p.music))
                       if p.music else "✗ à choisir",
            "Clips": f"✓ {len(p.clips)} clip(s)" if p.clips else "✗ aucun clip",
            "Kunai": hands(p.kunai),
            "Dash": hands(p.dash),
            "Dash back": hands(p.dashback),
            "Dismiss": hands(p.dismiss),
            "Shake": self.parts["Shake"].summary() if "Shake" in self.parts else "",
            "Reproduire": "copier un edit fini",
            "Générer": "rendu MP4",
        }
        for n, b in self.tiles.items():
            label = "Générer l'edit" if n == "Générer" else n
            sub = info[n]
            if len(sub) > 34:
                sub = sub[:32] + "…"
            b.setText(f"{ICONS[n]}\n{label}\n{sub}")

    def reproduce(self):
        from ..reproduce_dialog import ReproduceDialog
        if ReproduceDialog(self.project, self).exec():
            clips = self.parts["Clips"]
            clips.order.clear()
            for c in self.project.clips:
                clips.order.addItem(clips._order_item(c))
            clips.sync()
            clips.refresh_left()
            self.open("Clips")
            self._changed()

    def stop(self):
        for page in self.parts.values():
            stop = getattr(page, "stop", None)
            if stop:
                stop()
