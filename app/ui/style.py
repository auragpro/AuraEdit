"""Thème visuel (style « tableau de bord » moderne) + thèmes au choix, et images."""
import json
import sys
from pathlib import Path

# Dans le .exe, PyInstaller décompresse les fichiers dans sys._MEIPASS
_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def asset(name):
    """Chemin d'une image du dossier app/assets (marche aussi dans le .exe)."""
    return str(_ROOT / "app" / "assets" / name)


# ---------------------------------------------------------------- thèmes
THEMES = {
    "Aura (violet)": {"accent": "#7c5cff", "accent2": "#c06bff", "bg": "#0a0f1c", "panel": "#101828",
                      "panel2": "#172238", "border": "#1f2c45", "text": "#e8ecf5", "muted": "#8391ab"},
    "Valorant (rouge)": {"accent": "#ff4655", "accent2": "#ff8a5c", "bg": "#0c131b", "panel": "#131e29",
                         "panel2": "#1b2836", "border": "#26364a", "text": "#ece8e1", "muted": "#8b978f"},
    "Cyan": {"accent": "#16c7d9", "accent2": "#4f8cff", "bg": "#081218", "panel": "#0e1b24",
             "panel2": "#142632", "border": "#1d3442", "text": "#e6f3f7", "muted": "#7f9aa6"},
    "Émeraude": {"accent": "#22c98a", "accent2": "#a3e635", "bg": "#08130f", "panel": "#0e1c17",
                 "panel2": "#152820", "border": "#1e382d", "text": "#e7f5ee", "muted": "#7fa08f"},
    "Sunset": {"accent": "#ff6b3d", "accent2": "#ff3d8b", "bg": "#130b10", "panel": "#1d1219",
               "panel2": "#281a23", "border": "#3a2633", "text": "#f7ebef", "muted": "#a3899a"},
    "Or": {"accent": "#f5b82e", "accent2": "#ff7a2e", "bg": "#100e08", "panel": "#1a170e",
           "panel2": "#242014", "border": "#3a321c", "text": "#f6f1e4", "muted": "#a39b84"},
}
DEFAULT_THEME = "Aura (violet)"
KEYS = ("accent", "accent2", "bg", "panel", "panel2", "border", "text", "muted")


def _theme_file():
    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "AuraEdit" / "theme.json"


def load_theme():
    """{"nom": ..., + couleurs}. Thème « Personnalisé » = couleurs choisies par l'utilisateur."""
    t = dict(THEMES[DEFAULT_THEME], nom=DEFAULT_THEME)
    try:
        d = json.loads(_theme_file().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            if d.get("nom") in THEMES:
                t = dict(THEMES[d["nom"]], nom=d["nom"])
            t.update({k: d[k] for k in KEYS if isinstance(d.get(k), str) and d[k].startswith("#")})
            if d.get("nom") == "Personnalisé":
                t["nom"] = "Personnalisé"
    except (OSError, ValueError):
        pass
    return t


def save_theme(t):
    try:
        f = _theme_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def rgba(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {a})"


THEME = load_theme()
RED = THEME["accent"]          # couleur d'accent (nom gardé pour le code existant)
ACCENT2 = THEME["accent2"]
DARK = THEME["bg"]
PANEL = THEME["panel"]
PANEL_2 = THEME["panel2"]
BORDER = THEME["border"]
TEXT = THEME["text"]
MUTED = THEME["muted"]
GREEN = "#3ddc97"


def build(t):
    A, A2, BG, P, P2, B, T, M = (t[k] for k in KEYS)
    GRAD = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {A}, stop:1 {A2})"
    return f"""
QWidget {{
    background: {BG};
    color: {T};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 46px; font-weight: 800; letter-spacing: 6px;
               color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:0.5 {A2}, stop:1 {A}); }}
QLabel#subtitle {{ color: {M}; font-size: 15px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; color: #ffffff; }}
QLabel#kicker {{ color: {M}; font-family: "Consolas", "Cascadia Mono", monospace; font-size: 11px;
                letter-spacing: 2px; }}
QLabel#hint {{ color: {M}; }}
QLabel#version {{ color: {M}; font-size: 12px; }}
QLabel#ok {{ color: {GREEN}; }}
QLabel#ko {{ color: #ff5d6c; }}
QLabel#appname {{ font-size: 20px; font-weight: 800; letter-spacing: 1px;
                 color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:0.4 {A2}, stop:1 {A}); }}

QWidget#topbar {{ background: {P}; border-bottom: 1px solid {B}; }}
QWidget#topbar QLabel {{ background: transparent; }}
QWidget#side {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {P}, stop:1 {BG});
               border-right: 1px solid {B}; }}
QWidget#side QLabel, QWidget#side QPushButton {{ background: transparent; }}

QPushButton {{
    background: {P2};
    border: 1px solid {B};
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {A}; background: {rgba(A, 0.12)}; color: #ffffff; }}
QPushButton:pressed {{ background: {rgba(A, 0.25)}; }}
QPushButton:checked {{ background: {rgba(A, 0.30)}; border-color: {A}; color: #ffffff; }}
QPushButton:disabled {{ color: {rgba(M, 0.6)}; border-color: {B}; background: {P}; }}
QPushButton:focus {{ outline: none; }}
QPushButton#primary {{ background: {GRAD}; border: none; color: white; font-weight: 700; }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {A2}, stop:1 {A}); }}
QPushButton#primary:disabled {{ background: {rgba(A, 0.25)}; color: {rgba(T, 0.5)}; }}
QPushButton#big {{ background: {GRAD}; border: none; color: white; font-size: 20px; font-weight: 800;
                  letter-spacing: 2px; padding: 18px 48px; border-radius: 16px; }}
QPushButton#big:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {A2}, stop:1 {A}); }}
QPushButton#link {{ background: transparent; border: none; color: {M}; padding: 4px; }}
QPushButton#link:hover {{ color: {A2}; background: transparent; }}
QPushButton#pill {{ border-radius: 15px; padding: 5px 14px; font-size: 13px; }}

QListWidget {{
    background: {P};
    border: 1px solid {B};
    border-radius: 14px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{ padding: 8px; border-radius: 10px; border: 1px solid transparent; }}
QListWidget::item:hover {{ background: {rgba(T, 0.05)}; }}
QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {rgba(A, 0.35)}, stop:1 {rgba(A2, 0.10)});
    border: 1px solid {rgba(A, 0.8)};
    color: #ffffff;
}}
QListWidget#sidebar {{ background: transparent; border: none; border-radius: 0; padding: 6px 8px;
                      font-size: 12px; }}
QListWidget#sidebar::item {{ padding: 10px 2px; margin: 3px 0; border-radius: 12px; color: {M}; }}
QListWidget#sidebar::item:hover {{ background: {rgba(T, 0.05)}; color: {T}; }}
QListWidget#sidebar::item:selected {{ background: {rgba(A, 0.18)}; border: 1px solid {rgba(A, 0.7)};
                                     color: #ffffff; font-weight: 700; }}

QLineEdit, QTextBrowser, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG};
    border: 1px solid {B};
    border-radius: 10px;
    padding: 6px 8px;
    selection-background-color: {A};
}}
QComboBox {{ background: {P2}; border: 1px solid {B}; border-radius: 10px; padding: 6px 10px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {P}; border: 1px solid {B}; border-radius: 10px; padding: 4px;
                              selection-background-color: {A}; selection-color: white; outline: none; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {rgba(A, 0.5)}; }}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {A}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent; border: none; width: 16px; }}

QFrame#card {{ background: {P}; border: 1px solid {B}; border-radius: 16px; }}
QFrame#card QLabel, QFrame#card QRadioButton, QFrame#card QCheckBox {{ background: transparent; }}
QFrame#glowcard {{ background: {P}; border: 1px solid {A}; border-radius: 16px; }}
QWidget#startPage QLabel {{ background: transparent; }}
QWidget#startPage QPushButton#link {{ background: transparent; }}
QFrame#recent {{ background: {P2}; border: 1px solid {B}; border-radius: 12px; }}
QFrame#recent:hover {{ border-color: {A}; background: {rgba(A, 0.10)}; }}
QFrame#recent QLabel, QFrame#recent QPushButton {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 6px; background: {P2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {A}, stop:1 {A2});
                               border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 3px solid {A}; width: 12px; height: 12px;
                             margin: -6px 0; border-radius: 9px; }}
QSlider::groove:vertical {{ width: 6px; background: {P2}; border-radius: 3px; }}
QSlider::add-page:vertical {{ background: {A}; border-radius: 3px; }}
QSlider::handle:vertical {{ background: #ffffff; border: 3px solid {A}; height: 12px; margin: 0 -6px;
                           border-radius: 9px; }}

QProgressBar {{ background: {P2}; border: none; border-radius: 5px; min-height: 10px; text-align: center;
               color: transparent; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {A}, stop:1 {A2});
                      border-radius: 5px; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {B};
                                                background: {BG}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {A}; }}
QCheckBox::indicator:checked {{ background: {GRAD}; border-color: {A}; }}
QRadioButton::indicator:checked {{ background: {A}; border: 4px solid {BG}; }}
QCheckBox:disabled, QRadioButton:disabled, QLabel:disabled {{ color: {rgba(M, 0.6)}; }}

QMenu {{ background: {P}; border: 1px solid {B}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 22px; border-radius: 8px; background: transparent; }}
QMenu::item:selected {{ background: {GRAD}; color: white; }}
QMenu::separator {{ height: 1px; background: {B}; margin: 5px 8px; }}
QToolTip {{ background: {P2}; color: {T}; border: 1px solid {A}; border-radius: 8px; padding: 6px 8px; }}

QGroupBox {{ background: {P}; border: 1px solid {B}; border-radius: 14px; margin-top: 14px;
            padding: 12px 10px 10px 10px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
QTabWidget::pane {{ border: 1px solid {B}; border-radius: 12px; background: {P}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {M}; padding: 8px 18px; border-bottom: 2px solid transparent;
               font-weight: 600; }}
QTabBar::tab:hover {{ color: {T}; }}
QTabBar::tab:selected {{ color: #ffffff; border-bottom: 2px solid {A}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {B}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:horizontal {{ background: {B}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {A}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QAbstractScrollArea::corner {{ background: transparent; }}
QScrollArea {{ border: none; }}
QHeaderView::section {{ background: {P2}; color: {M}; border: none; border-bottom: 1px solid {B};
                       padding: 6px 8px; font-weight: 700; }}
QTableWidget, QTableView, QTreeWidget, QTreeView {{ background: {P}; border: 1px solid {B}; border-radius: 12px;
    gridline-color: {B}; selection-background-color: {rgba(A, 0.3)}; outline: none; }}
QSplitter::handle {{ background: {B}; }}
QSplitter::handle:hover {{ background: {A}; }}
"""


STYLESHEET = build(THEME)


def apply_theme(t):
    """Change le thème tout de suite (et pour les prochains lancements)."""
    global STYLESHEET
    save_theme(t)
    STYLESHEET = build(dict(THEMES[DEFAULT_THEME], **{k: t[k] for k in KEYS if k in t}))
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(STYLESHEET)
        glow = getattr(app, "_glow", None)
        if glow is not None:
            glow.color = t.get("accent", RED)


# ---------------------------------------------------------------- effets de lumière
def install_glow(app):
    """Halo lumineux autour des boutons : permanent sur les gros boutons, au survol sur les autres."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QPushButton

    MAIN = ("primary", "big")
    WATCH = (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.Show, QEvent.Type.EnabledChange)

    class Glow(QObject):
        color = RED

        def eventFilter(self, obj, ev):
            try:
                if ev.type() in WATCH and isinstance(obj, QPushButton) and obj.objectName() != "link":
                    hover = ev.type() == QEvent.Type.Enter or (ev.type() != QEvent.Type.Leave and obj.underMouse())
                    self.apply(obj, hover and obj.isEnabled())
            except RuntimeError:
                pass
            return False

        def apply(self, b, hover):
            main = b.objectName() in MAIN and b.isEnabled()
            eff = b.graphicsEffect()
            if not hover and not main:
                if isinstance(eff, QGraphicsDropShadowEffect):
                    b.setGraphicsEffect(None)
                return
            if eff is not None and not isinstance(eff, QGraphicsDropShadowEffect):
                return
            if eff is None:
                eff = QGraphicsDropShadowEffect(b)
                eff.setOffset(0, 0)
                b.setGraphicsEffect(eff)
            c = QColor(self.color)
            if main:
                eff.setBlurRadius(40 if hover else 22)
                c.setAlpha(220 if hover else 120)
            else:
                eff.setBlurRadius(24)
                c.setAlpha(140)
            eff.setColor(c)

    app._glow = Glow(app)
    app.installEventFilter(app._glow)
