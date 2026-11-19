"""Photo récap des sons utilisés dans l'edit (à partager)."""
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPixmap

from app.core import sound_ai as sa

from .style import asset

W = 1080


def _fmt(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:04.1f}"


def make_photo(placements, music=None, title="Mon edit", path="sons.png"):
    counts = Counter(Path(p.sound).stem for p in placements)
    cats = Counter(p.category for p in placements)
    first = {}
    for p in sorted(placements, key=lambda p: p.t):
        first.setdefault(Path(p.sound).stem, p.t)
    rows = counts.most_common()
    row_h = 64
    H = max(1080, 430 + len(rows) * row_h + 120)
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor("#0f1923"))
    g.setColorAt(1, QColor("#1f2b38"))
    p.fillRect(0, 0, W, H, g)
    p.fillRect(0, 0, W, 12, QColor("#ff4655"))

    logo = QPixmap(asset("logo.png"))
    if not logo.isNull():
        p.drawPixmap(60, 50, 110, 110, logo)
    p.setPen(QColor("#ece8e1"))
    p.setFont(QFont("Segoe UI", 44, QFont.Weight.Black))
    p.drawText(QRectF(195, 45, W - 250, 70), Qt.AlignmentFlag.AlignVCenter, "SONS UTILISÉS")
    p.setFont(QFont("Segoe UI", 22))
    p.setPen(QColor("#ff4655"))
    p.drawText(QRectF(195, 112, W - 250, 50), Qt.AlignmentFlag.AlignVCenter, title)

    y = 200
    p.setPen(QColor("#9aa4ad"))
    p.setFont(QFont("Segoe UI", 20))
    if music:
        p.drawText(QRectF(60, y, W - 120, 40), Qt.AlignmentFlag.AlignVCenter, "♪  " + Path(music).stem)
        y += 46
    resume = "   ·   ".join(f"{sa.LABELS.get(c, c)} {n}" for c, n in cats.most_common())
    p.drawText(QRectF(60, y, W - 120, 40), Qt.AlignmentFlag.AlignVCenter,
               f"{len(placements)} sound kills   ·   {len(rows)} sons différents")
    y += 42
    if resume:
        p.drawText(QRectF(60, y, W - 120, 40), Qt.AlignmentFlag.AlignVCenter, resume)
        y += 42
    y += 30

    top = max(counts.values()) if counts else 1
    for i, (name, n) in enumerate(rows):
        r = QRectF(60, y, W - 120, row_h - 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(r, 10, 10)
        bar = QRectF(60, y, (W - 120) * n / top, row_h - 10)
        p.setBrush(QColor(255, 70, 85, 60))
        p.drawRoundedRect(bar, 10, 10)
        p.setPen(QColor("#ece8e1"))
        p.setFont(QFont("Segoe UI", 21, QFont.Weight.Bold))
        p.drawText(r.adjusted(22, 0, -220, 0), Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(r.width() - 260)))
        p.setFont(QFont("Segoe UI", 19))
        p.setPen(QColor("#9aa4ad"))
        p.drawText(r.adjusted(0, 0, -22, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   f"×{n}   dès {_fmt(first[name])}")
        y += row_h

    p.setPen(QColor("#5c6670"))
    p.setFont(QFont("Segoe UI", 16))
    p.drawText(QRectF(0, H - 70, W, 40), Qt.AlignmentFlag.AlignCenter, "Fait avec AuraEdit")
    p.end()
    if not img.save(str(path), "PNG"):
        raise OSError("Impossible d'enregistrer l'image.")
    return path
