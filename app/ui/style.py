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
"""
