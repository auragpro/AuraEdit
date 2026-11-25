"""Page de démarrage : pas d'onglets, « Commencer un edit », derniers projets, nouveautés."""
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from app.core import project
from version import __version__

from .style import RED, asset

WHATS_NEW = [
    "Fondus d'opacité et shakes coupe par coupe",
    "Confirmation des shakes avant le rendu",
    "Reproduire : comparer avec l'edit + voir le résultat"]


def ago(ts):
    """'il y a 5 min', 'hier'..."""
    d = max(0, time.time() - ts)
    if d < 60:
        return "à l'instant"
    if d < 3600:
        return f"il y a {int(d // 60)} min"
    if d < 86400:
        return f"il y a {int(d // 3600)} h"
    if d < 172800:
        return "hier"
    if d < 30 * 86400:
        return f"il y a {int(d // 86400)} jours"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


class RecentCard(QFrame):
    """Un projet récent : clic = ouvrir, × = retirer de la liste (le fichier n'est pas supprimé)."""
    open_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.path = info["path"]
        self.setObjectName("recent")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.path)
        name = QLabel(info["name"])
        name.setStyleSheet("font-weight: 700; font-size: 15px;")
        details = [ago(info["modified"]), f"{info['clips']} clip(s)"]
        if info.get("sons"):
            details.append(f"{info['sons']} son(s) IA")
        if info.get("music"):
            details.append("♪ " + info["music"])
        sub = QLabel("  ·  ".join(details))
        sub.setObjectName("hint")
        x = QPushButton("×")
        x.setObjectName("link")
        x.setFixedWidth(28)
        x.setToolTip("Retirer de la liste (le projet n'est pas supprimé)")
        x.clicked.connect(lambda: self.remove_requested.emit(self.path))
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(name)
        col.addWidget(sub)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        lay.addLayout(col, 1)
        lay.addWidget(x)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.path)


class StartPage(QWidget):
    new_edit = pyqtSignal()           # clic sur « Commencer un edit »
    open_project = pyqtSignal(str)    # ouverture d'un projet existant (chemin)
    check_updates = pyqtSignal()      # vérification manuelle des mises à jour

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startPage")

        # ---------------- colonne gauche : logo + bouton
        logo = QLabel()
        pix = QPixmap(asset("logo.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(132, 132, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        title = QLabel("AURAEDIT")
        title.setObjectName("title")
        subtitle = QLabel("Tes edits Valorant, automatiquement.")
        subtitle.setObjectName("subtitle")

        self.btn_start = QPushButton("COMMENCER UN EDIT")
        self.btn_start.setObjectName("big")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.new_edit.emit)
        btn_open = QPushButton("Ouvrir un projet...")
        btn_open.setObjectName("link")
        btn_open.clicked.connect(self._browse)

        steps = QLabel("Montage (Intro, Musique, Clips, Kunai, Dash)  →  Sons IA")
        steps.setObjectName("hint")

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addStretch(1)
        left.addWidget(logo)
        left.addSpacing(6)
        left.addWidget(title)
        left.addWidget(subtitle)
        left.addSpacing(26)
        left.addWidget(self.btn_start, alignment=Qt.AlignmentFlag.AlignLeft)
        left.addWidget(btn_open, alignment=Qt.AlignmentFlag.AlignLeft)
        left.addSpacing(18)
        left.addWidget(steps)
        left.addStretch(1)

        # ---------------- colonne droite : derniers edits + nouveautés
        self.recent_box = QFrame()
        self.recent_box.setObjectName("card")
        self.recent_lay = QVBoxLayout(self.recent_box)
        self.recent_lay.setContentsMargins(16, 14, 16, 14)
        self.recent_lay.setSpacing(8)

        news = QFrame()
        news.setObjectName("card")
        nl = QVBoxLayout(news)
        nl.setContentsMargins(16, 14, 16, 14)
        head = QLabel(f"Nouveautés de la version {__version__}")
        head.setStyleSheet(f"font-weight: 700; color: {RED};")
        nl.addWidget(head)
        for line in WHATS_NEW:
            lab = QLabel("•  " + line)
            lab.setWordWrap(True)
            nl.addWidget(lab)

        right = QVBoxLayout()
        right.setSpacing(16)
        right.addStretch(1)
        right.addWidget(self.recent_box)
        right.addWidget(news)
        right.addStretch(1)

        cols = QHBoxLayout()
        cols.setSpacing(48)
        cols.addLayout(left, 5)
        cols.addLayout(right, 4)

        # ---------------- pied de page
        version = QLabel(f"version {__version__}")
        version.setObjectName("version")
        btn_upd = QPushButton("Vérifier les mises à jour")
        btn_upd.setObjectName("link")
        btn_upd.clicked.connect(self.check_updates.emit)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(btn_upd)
        foot.addWidget(version)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(72, 32, 40, 16)
        lay.addLayout(cols, 1)
        lay.addLayout(foot)
        self.refresh()

    # ------------------------------------------------------------ fond
    def paintEvent(self, event):
        """Fond en dégradé + bandes diagonales rouges discrètes (style Valorant)."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor("#111d29"))
        g.setColorAt(1, QColor("#0b131b"))
        p.fillRect(0, 0, w, h, g)
        p.setPen(Qt.PenStyle.NoPen)
        for i, alpha in enumerate((26, 14, 8)):
            c = QColor(RED)
            c.setAlpha(alpha)
            p.setBrush(c)
            off = i * 70
            p.drawPolygon(QPolygonF([QPointF(w * 0.62 + off, h), QPointF(w * 0.80 + off, h),
                                     QPointF(w + off, h * 0.35), QPointF(w * 0.82 + off, h * 0.35)]))
        p.end()

    # --------------------------------------------------------- récents
    def refresh(self):
        """Recharge la liste des derniers projets."""
        while self.recent_lay.count():
            w = self.recent_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        head = QLabel("Derniers edits")
        head.setStyleSheet("font-weight: 700;")
        self.recent_lay.addWidget(head)
        infos = [i for i in (project.project_info(p) for p in project.load_recents()[:5]) if i]
        if not infos:
            empty = QLabel("Aucun edit pour l'instant.\nClique sur « Commencer un edit » pour te lancer.")
            empty.setObjectName("hint")
            self.recent_lay.addWidget(empty)
        for info in infos:
            card = RecentCard(info)
            card.open_requested.connect(self.open_project.emit)
            card.remove_requested.connect(self._remove)
            self.recent_lay.addWidget(card)
        self.recent_count = len(infos)

    def _remove(self, path):
        project.remove_recent(path)
        self.refresh()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(project.projects_dir()),
                                              "Projet AuraEdit (*.auraedit)")
        if path:
            self.open_project.emit(path)
