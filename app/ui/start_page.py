"""Page de démarrage : pas d'onglets, « Commencer un edit », derniers projets, nouveautés."""
import time
from pathlib import Path

import math

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import (QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from app.core import project
from version import __version__

from . import style
from .style import ACCENT2, BORDER, DARK, MUTED, PANEL, RED, asset

WHATS_NEW = [
    "Accueil redessiné, animations et personnalisation (🎨)",
    "Étape Textes : biseautage + incrustation, polices du PC",
    "Lecture continue avec time remap, shakes par groupes"]


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


def fade_in(widgets, delay=0, step=90, dist=18):
    """Apparition en douceur (fondu + petite montée), l'un après l'autre."""
    if not style.option("animations"):
        return
    for i, w in enumerate(widgets):
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(520)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda w=w: w.setGraphicsEffect(None))      # plus d'effet une fois apparu
        QTimer.singleShot(delay + i * step, a.start)
        w._fade = a


class StatChip(QFrame):
    """Petite pastille de chiffre (projets, clips, skins)."""

    def __init__(self, value, label, parent=None):
        super().__init__(parent)
        self.setObjectName("chip")
        self.setStyleSheet(f"QFrame#chip {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}"
                           "QFrame#chip QLabel { background: transparent; }")
        v = QLabel(str(value))
        v.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        t = QLabel(label.upper())
        t.setStyleSheet(f"font-size: 10px; letter-spacing: 2px; color: {MUTED}; font-weight: 700;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 22, 10)
        lay.setSpacing(0)
        lay.addWidget(v)
        lay.addWidget(t)


class FeatureCard(QFrame):
    """Carte de fonction avec un trait de couleur qui s'allume au survol."""

    def __init__(self, icon, title, text, parent=None):
        super().__init__(parent)
        self.setObjectName("feat")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setStyleSheet(
            f"QFrame#feat {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 16px; }}"
            f"QFrame#feat:hover {{ border: 1px solid {RED}; }}"
            "QFrame#feat QLabel { background: transparent; }")
        i = QLabel(icon)
        i.setStyleSheet("font-size: 24px;")
        t = QLabel(title)
        t.setStyleSheet("font-weight: 800; font-size: 14px; color: #ffffff;")
        d = QLabel(text)
        d.setWordWrap(True)
        d.setObjectName("hint")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        lay.addWidget(i)
        lay.addWidget(t)
        lay.addWidget(d)
        lay.addStretch(1)


class StartPage(QWidget):
    new_edit = pyqtSignal()           # clic sur « Commencer un edit »
    open_project = pyqtSignal(str)    # ouverture d'un projet existant (chemin)
    check_updates = pyqtSignal()      # vérification manuelle des mises à jour

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startPage")
        self.phase = 0.0
        self.bg_img = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)

        # ---------------- héros (gauche)
        logo = QLabel()
        pix = QPixmap(asset("logo.png"))
        if not pix.isNull():
            logo.setPixmap(self._round_pix(pix, 96))
        kick = QLabel("AURAEDIT  ·  STUDIO D'EDIT VALORANT")
        kick.setObjectName("kicker")
        title = QLabel("AURAEDIT")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 64px; letter-spacing: 10px;")
        subtitle = QLabel("Tes edits Valorant, du clip brut à l'export : reproduis un edit, time remap, shakes, "
                          "textes — tout au même endroit.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(560)

        self.btn_start = QPushButton("COMMENCER UN EDIT")
        self.btn_start.setObjectName("big")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.new_edit.emit)
        btn_open = QPushButton("📂  Ouvrir un projet")
        btn_open.setMinimumHeight(56)
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self._browse)
        brow = QHBoxLayout()
        brow.setSpacing(12)
        brow.addWidget(self.btn_start)
        brow.addWidget(btn_open)
        brow.addStretch(1)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(10)

        feats = QGridLayout()
        feats.setSpacing(12)
        for i, (ic, t, d) in enumerate([
                ("🎞", "Reproduire un edit", "Copie un edit fini plan par plan, avec tes propres clips."),
                ("⏱", "Time remap", "Ralentis, reverse, keyframes et courbes comme After Effects."),
                ("💥", "Shakes & textes", "Shakes Motion Bro par coupe, textes biseautés en incrustation.")]):
            feats.addWidget(FeatureCard(ic, t, d), 0, i)

        self.hero = QWidget()
        self.hero.setObjectName("clear")
        left = QVBoxLayout(self.hero)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        left.addStretch(1)
        left.addWidget(logo)
        left.addSpacing(6)
        left.addWidget(kick)
        left.addWidget(title)
        left.addWidget(subtitle)
        left.addSpacing(22)
        left.addLayout(brow)
        left.addSpacing(18)
        left.addLayout(self.chips)
        left.addSpacing(26)
        left.addLayout(feats)
        left.addStretch(1)

        # ---------------- colonne droite : derniers edits + nouveautés
        self.recent_box = QFrame()
        self.recent_box.setObjectName("card")
        self.recent_lay = QVBoxLayout(self.recent_box)
        self.recent_lay.setContentsMargins(18, 16, 18, 16)
        self.recent_lay.setSpacing(8)

        self.news = QFrame()
        self.news.setObjectName("card")
        nl = QVBoxLayout(self.news)
        nl.setContentsMargins(18, 16, 18, 16)
        k2 = QLabel(f"NOUVEAUTÉS  ·  VERSION {__version__}")
        k2.setObjectName("kicker")
        nl.addWidget(k2)
        for line in WHATS_NEW:
            lab = QLabel(f"<span style='color:{RED}'>▸</span>  " + line)
            lab.setWordWrap(True)
            nl.addWidget(lab)

        self.side = QWidget()
        self.side.setObjectName("clear")
        right = QVBoxLayout(self.side)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)
        right.addStretch(1)
        right.addWidget(self.recent_box)
        right.addWidget(self.news)
        right.addStretch(1)

        cols = QHBoxLayout()
        cols.setSpacing(56)
        cols.addWidget(self.hero, 6)
        cols.addWidget(self.side, 4)

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
        lay.setContentsMargins(72, 28, 48, 16)
        lay.addLayout(cols, 1)
        lay.addLayout(foot)
        self.refresh()

    @staticmethod
    def _round_pix(pix, size):
        from PyQt6.QtGui import QPainterPath
        out = QPixmap(size, size)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size, size), size * 0.26, size * 0.26)
        p.setClipPath(path)
        p.drawPixmap(0, 0, pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.5))
        p.drawPath(path)
        p.end()
        return out

    # ------------------------------------------------------------ animations
    def showEvent(self, e):
        super().showEvent(e)
        img = style.option("fond_image")
        self.bg_img = QPixmap(img) if img and Path(img).is_file() else None
        if style.option("fond_anime") and style.option("animations"):
            self.timer.start(33)
        fade_in([self.hero, self.side])

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()

    def _animate(self):
        self.phase += 0.012
        self.update()

    def paintEvent(self, event):
        """Fond : image perso (optionnelle) + lueurs colorées qui bougent doucement + fine grille."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(DARK))
        if self.bg_img is not None and not self.bg_img.isNull():
            sc = self.bg_img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    Qt.TransformationMode.SmoothTransformation)
            p.setOpacity(0.22)
            p.drawPixmap((w - sc.width()) // 2, (h - sc.height()) // 2, sc)
            p.setOpacity(1.0)
        t = self.phase
        for (cx, cy, r, col, sp) in ((0.78, 0.30, 0.55, RED, 1.0), (0.18, 0.85, 0.45, ACCENT2, 0.7),
                                      (0.55, 0.95, 0.35, RED, 1.3)):
            x = w * (cx + 0.06 * math.sin(t * sp + cx * 6))
            y = h * (cy + 0.05 * math.cos(t * sp * 0.8 + cy * 5))
            g = QRadialGradient(QPointF(x, y), max(w, h) * r)
            c = QColor(col)
            c.setAlpha(46)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(0, 0, w, h, g)
        p.setPen(QPen(QColor(255, 255, 255, 9), 1))            # grille discrète
        step = 46
        for gx in range(0, w, step):
            p.drawLine(gx, 0, gx, h)
        for gy in range(0, h, step):
            p.drawLine(0, gy, w, gy)
        p.setPen(Qt.PenStyle.NoPen)                            # bandes diagonales
        for i, alpha in enumerate((22, 12, 6)):
            c = QColor(RED)
            c.setAlpha(alpha)
            p.setBrush(c)
            off = i * 70 + 30 * math.sin(t * 0.6)
            p.drawPolygon(QPolygonF([QPointF(w * 0.66 + off, h), QPointF(w * 0.82 + off, h),
                                     QPointF(w + off, h * 0.38), QPointF(w * 0.84 + off, h * 0.38)]))
        g = QLinearGradient(0, 0, 0, h)                        # vignette
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0, 110))
        p.fillRect(0, 0, w, h, g)
        p.end()

    # --------------------------------------------------------- récents
    def refresh(self):
        """Recharge la liste des derniers projets + les chiffres."""
        while self.recent_lay.count():
            w = self.recent_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        head = QLabel("DERNIERS EDITS")
        head.setObjectName("kicker")
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
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        try:
            folders = project.load_clip_folders()
        except Exception:                          # noqa: BLE001
            folders = {}
        nclips = sum(len(v) for v in folders.values()) if isinstance(folders, dict) else 0
        for v, lab in ((len(project.load_recents()), "projets"), (nclips, "clips"),
                       (len(folders) if isinstance(folders, dict) else 0, "skins & parties")):
            self.chips.addWidget(StatChip(v, lab))
        self.chips.addStretch(1)

    def _remove(self, path):
        project.remove_recent(path)
        self.refresh()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(project.projects_dir()),
                                              "Projet AuraEdit (*.auraedit)")
        if path:
            self.open_project.emit(path)
