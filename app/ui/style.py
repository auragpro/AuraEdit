"""Thème visuel (couleurs inspirées de l'interface de Valorant) et images."""
import sys
from pathlib import Path

# Dans le .exe, PyInstaller décompresse les fichiers dans sys._MEIPASS
_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def asset(name):
    """Chemin d'une image du dossier app/assets (marche aussi dans le .exe)."""
    return str(_ROOT / "app" / "assets" / name)


RED = "#ff4655"
DARK = "#0f1923"
PANEL = "#1b2733"
PANEL_2 = "#243342"
TEXT = "#ece8e1"
MUTED = "#8b978f"
GREEN = "#3ddc97"

STYLESHEET = f"""
QWidget {{
    background: {DARK};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}}
QLabel#title {{ font-size: 46px; font-weight: 800; letter-spacing: 6px; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 15px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
QLabel#hint {{ color: {MUTED}; }}
QLabel#version {{ color: {MUTED}; font-size: 12px; }}
QLabel#ok {{ color: {GREEN}; }}
QLabel#ko {{ color: {RED}; }}

QPushButton {{
    background: {PANEL_2};
    border: 1px solid #33475a;
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{ border-color: {RED}; }}
QPushButton:disabled {{ color: #5a6670; border-color: #26323d; }}
QPushButton#primary {{
    background: {RED};
    border: none;
    color: white;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: #ff5c69; }}
QPushButton#primary:disabled {{ background: #5c2a30; color: #a88; }}
QPushButton#big {{
    background: {RED};
    border: none;
    color: white;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 2px;
    padding: 18px 48px;
    border-radius: 8px;
}}
QPushButton#big:hover {{ background: #ff5c69; }}
QPushButton#link {{ background: transparent; border: none; color: {MUTED}; padding: 4px; }}
QPushButton#link:hover {{ color: {TEXT}; }}

QListWidget {{
    background: {PANEL};
    border: 1px solid #26323d;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{ padding: 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {PANEL_2}; color: {TEXT}; }}
QListWidget::item:hover {{ background: #1f2d3a; }}

QListWidget#sidebar {{
    background: {PANEL};
    border: none;
    border-radius: 0;
    padding: 8px 0;
    font-size: 15px;
}}
QListWidget#sidebar::item {{ padding: 14px 20px; border-radius: 0; border-left: 3px solid transparent; }}
QListWidget#sidebar::item:selected {{ background: {DARK}; border-left: 3px solid {RED}; }}

QLineEdit, QTextBrowser {{
    background: {PANEL};
    border: 1px solid #26323d;
    border-radius: 6px;
    padding: 6px;
}}
QFrame#card {{ background: {PANEL}; border-radius: 8px; }}
QFrame#card QLabel, QFrame#card QRadioButton, QFrame#card QCheckBox {{ background: transparent; }}
QWidget#startPage QLabel {{ background: transparent; }}
QWidget#startPage QPushButton#link {{ background: transparent; }}
QFrame#recent {{
    background: {PANEL_2};
    border: 1px solid transparent;
    border-radius: 6px;
}}
QFrame#recent:hover {{ border-color: {RED}; }}
QFrame#recent QLabel, QFrame#recent QPushButton {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {PANEL_2}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {RED}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; margin: -6px 0; border-radius: 7px;
}}
QComboBox {{
    background: {PANEL_2};
    border: 1px solid #33475a;
    border-radius: 6px;
    padding: 6px 10px;
}}
QProgressBar {{
    background: {PANEL};
    border: none;
    border-radius: 4px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {RED}; border-radius: 4px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}

/* ---------- finitions (1.0.2) ---------- */
QPushButton {{ font-weight: 600; }}
QPushButton:pressed {{ background: #1c2a37; border-color: {RED}; }}
QPushButton:focus {{ outline: none; }}
QPushButton#primary:pressed, QPushButton#big:pressed {{ background: #e03a48; }}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
    border: 1px solid {RED};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: #4a6378; }}
QLineEdit {{ selection-background-color: {RED}; }}

QSpinBox, QDoubleSpinBox {{
    background: {PANEL_2};
    border: 1px solid #33475a;
    border-radius: 6px;
    padding: 5px 8px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent; border: none; width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: #33475a; border-radius: 3px; }}

QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {PANEL};
    border: 1px solid #33475a;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {RED};
    selection-color: white;
    outline: none;
}}

QMenu {{
    background: {PANEL};
    border: 1px solid #33475a;
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{ padding: 8px 22px; border-radius: 5px; background: transparent; }}
QMenu::item:selected {{ background: {RED}; color: white; }}
QMenu::separator {{ height: 1px; background: #33475a; margin: 5px 8px; }}

QToolTip {{
    background: {PANEL_2};
    color: {TEXT};
    border: 1px solid {RED};
    border-radius: 6px;
    padding: 6px 8px;
}}

QTextEdit, QPlainTextEdit {{
    background: {PANEL};
    border: 1px solid #26323d;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {RED};
}}

QGroupBox {{
    background: {PANEL};
    border: 1px solid #26323d;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT};
}}

QTabWidget::pane {{ border: 1px solid #26323d; border-radius: 8px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 18px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {RED}; }}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid #4a6378;
    background: {PANEL_2};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {RED}; }}
QCheckBox::indicator:checked {{ background: {RED}; border-color: {RED}; }}
QRadioButton::indicator:checked {{ background: {RED}; border: 4px solid {PANEL_2}; }}
QCheckBox:disabled, QRadioButton:disabled, QLabel:disabled {{ color: #5a6670; }}

QListWidget::item:selected {{ background: #2c3e50; border: 1px solid {RED}; }}
QListWidget::item:selected:!active {{ background: #26384a; }}

QSlider::handle:horizontal:hover {{ background: white; }}
QSlider::groove:vertical {{ width: 4px; background: {PANEL_2}; border-radius: 2px; }}
QSlider::add-page:vertical {{ background: {RED}; border-radius: 2px; }}
QSlider::handle:vertical {{ background: {TEXT}; height: 14px; margin: 0 -6px; border-radius: 7px; }}
QSlider::groove:horizontal:disabled {{ background: #1c2731; }}
QSlider::sub-page:horizontal:disabled {{ background: #5c2a30; }}

/* barres de défilement fines et discrètes */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #33475a; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:horizontal {{ background: #33475a; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {RED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QAbstractScrollArea::corner {{ background: transparent; }}
QScrollArea {{ border: none; }}

QHeaderView::section {{
    background: {PANEL_2};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid #33475a;
    padding: 6px 8px;
    font-weight: 700;
}}
QTableWidget, QTableView, QTreeWidget, QTreeView {{
    background: {PANEL};
    border: 1px solid #26323d;
    border-radius: 6px;
    gridline-color: #26323d;
    selection-background-color: #2c3e50;
    outline: none;
}}
QProgressBar {{ min-height: 10px; }}
QDialog {{ background: {DARK}; }}
QMessageBox QLabel {{ font-size: 14px; }}
QSplitter::handle {{ background: #26323d; }}
QSplitter::handle:hover {{ background: {RED}; }}

/* ---------- look moderne + lumières (1.0.3) ---------- */
QLabel#title {{
    color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:0.55 #ffd9dc, stop:1 {RED});
}}
QLabel#h1 {{ color: #ffffff; }}

QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d4052, stop:1 #1d2b38);
    border: 1px solid #36506a;
    border-top-color: #4b6680;
    border-radius: 8px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a2f3d, stop:1 #24303d);
    border-color: {RED};
    color: #ffffff;
}}
QPushButton:pressed {{ background: #1a2633; }}
QPushButton:disabled {{ background: #18232d; border-color: #24313c; color: #56636e; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff7380, stop:0.5 #ff4655, stop:1 #e0303f);
    border: 1px solid #ff8a94;
    border-bottom-color: #b8222f;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff95a0, stop:0.5 #ff5a68, stop:1 #ff3a4a);
}}
QPushButton#primary:pressed {{ background: #d42f3d; }}
QPushButton#primary:disabled {{ background: #4a2329; border-color: #5c2a30; color: #a88; }}
QPushButton#big {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff7380, stop:0.5 #ff4655, stop:1 #d92c3b);
    border: 1px solid #ff9aa3;
    border-bottom-color: #a81f2b;
    border-radius: 12px;
}}
QPushButton#big:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffa0aa, stop:0.5 #ff5a68, stop:1 #ff3a4a);
}}
QPushButton#link {{ background: transparent; border: none; }}
QPushButton#link:hover {{ background: transparent; color: {RED}; }}

QListWidget {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1d2a36, stop:1 #16212b);
    border: 1px solid #263544;
    border-top-color: #34495d;
    border-radius: 10px;
}}
QListWidget::item:hover {{ background: rgba(255, 255, 255, 12); }}
QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255, 70, 85, 90), stop:1 rgba(255, 70, 85, 20));
    border: 1px solid rgba(255, 70, 85, 200);
    color: #ffffff;
}}
QListWidget::item:selected:!active {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255, 70, 85, 55), stop:1 rgba(255, 70, 85, 10));
}}

QListWidget#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1f2e3c, stop:0.6 #16212c, stop:1 #111a23);
    border: none;
    border-right: 1px solid #263544;
    border-radius: 0;
}}
QListWidget#sidebar::item {{ border: none; border-left: 3px solid transparent; margin: 2px 8px 2px 0; }}
QListWidget#sidebar::item:hover {{ background: rgba(255, 255, 255, 10); }}
QListWidget#sidebar::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255, 70, 85, 110), stop:0.7 rgba(255, 70, 85, 25), stop:1 transparent);
    border-left: 3px solid {RED};
    color: #ffffff;
    font-weight: 700;
}}

QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #223344, stop:1 #17232e);
    border: 1px solid #263544;
    border-top-color: #3d566e;
    border-radius: 12px;
}}
QFrame#recent {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a3c4e, stop:1 #1c2935);
    border: 1px solid #2c3f52;
    border-top-color: #44607a;
    border-radius: 10px;
}}
QFrame#recent:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a2f3d, stop:1 #222f3c);
    border-color: {RED};
}}

QLineEdit, QTextBrowser, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #142029;
    border: 1px solid #2a3b4b;
    border-bottom-color: #3a5166;
    border-radius: 8px;
}}
QComboBox {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #253646, stop:1 #1a2733); }}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    background: #18252f;
    border: 1px solid {RED};
}}

QSlider::groove:horizontal {{ height: 6px; background: #1a2733; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b3222f, stop:1 #ff6b78);
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.35, stop:0 #ffffff, stop:0.6 #f1ece6, stop:1 #ff8a94);
    border: 2px solid {RED};
    width: 14px; height: 14px; margin: -6px 0; border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.4, fy:0.35, stop:0 #ffffff, stop:1 #ffb3b9);
}}

QProgressBar {{ background: #142029; border: 1px solid #263544; border-radius: 6px; }}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c8263a, stop:0.6 #ff4655, stop:1 #ff9a6b);
    border-radius: 5px;
}}

QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff7380, stop:1 #e0303f);
    border-color: #ff8a94;
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ff7380, stop:0.45 {RED}, stop:0.55 {PANEL_2}, stop:1 {PANEL_2});
    border: 1px solid {RED};
}}

QScrollBar::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3a5166, stop:1 #2c4052);
}}
QScrollBar::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a5166, stop:1 #2c4052);
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff6b78, stop:1 #d92c3b);
}}

QMenu {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #223344, stop:1 #17232e);
    border: 1px solid #34495d;
    border-top-color: #4b6680;
}}
QMenu::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4655, stop:1 #c8263a);
}}
QToolTip {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d4052, stop:1 #1d2b38);
    border: 1px solid {RED};
}}
QTabBar::tab:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 transparent, stop:1 rgba(255, 70, 85, 45));
}}
QGroupBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #223344, stop:1 #17232e);
    border-top-color: #3d566e;
    border-radius: 12px;
}}
"""


# ---------------------------------------------------------------- effets de lumière
def install_glow(app):
    """Halo lumineux rouge autour des boutons : permanent sur les gros boutons, au survol sur les autres."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QPushButton

    MAIN = ("primary", "big")
    WATCH = (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.Show, QEvent.Type.EnabledChange)

    class Glow(QObject):
        def eventFilter(self, obj, ev):
            try:
                if ev.type() in WATCH and isinstance(obj, QPushButton) and obj.objectName() != "link":
                    hover = ev.type() == QEvent.Type.Enter or (ev.type() != QEvent.Type.Leave and obj.underMouse())
                    self.apply(obj, hover and obj.isEnabled())
            except RuntimeError:
                pass
            return False

        @staticmethod
        def apply(b, hover):
            main = b.objectName() in MAIN and b.isEnabled()
            eff = b.graphicsEffect()
            if not hover and not main:
                if isinstance(eff, QGraphicsDropShadowEffect):
                    b.setGraphicsEffect(None)
                return
            if eff is not None and not isinstance(eff, QGraphicsDropShadowEffect):
                return                                   # effet posé ailleurs : on n'y touche pas
            if eff is None:
                eff = QGraphicsDropShadowEffect(b)
                eff.setOffset(0, 0)
                b.setGraphicsEffect(eff)
            c = QColor(RED)
            if main:
                eff.setBlurRadius(42 if hover else 24)
                c.setAlpha(230 if hover else 140)
            else:
                eff.setBlurRadius(26)
                c.setAlpha(150)
            eff.setColor(c)

    app._glow = Glow(app)
    app.installEventFilter(app._glow)
