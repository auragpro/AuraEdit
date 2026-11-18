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
"""
