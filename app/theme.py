"""Theme palettes and QSS builder. / 主题配色与样式表生成（亮色/深色双主题）"""
from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#e8eef8",
        "card": "#ffffff",
        "card_border": "#d7e0ee",
        "text": "#1e293b",
        "text_dim": "#64748b",
        "accent": "#2563eb",
        "accent2": "#3b82f6",
        "accent_soft": "#dbeafe",
        "input_bg": "#f6f9fe",
        "track": "#dbe4f0",
        "danger": "#dc2626",
        "sidebar_start": "#1d4ed8",
        "sidebar_end": "#1e3a8a",
        "sidebar_text": "#dbeafe",
        "overlay": "#f4f8ff",
        "bg_image": "assets/bg_light.jpg",
    },
    "dark": {
        "bg": "#0b1220",
        "card": "#141f33",
        "card_border": "#263652",
        "text": "#e2e8f0",
        "text_dim": "#8b9bb4",
        "accent": "#3b82f6",
        "accent2": "#60a5fa",
        "accent_soft": "#1e3a5f",
        "input_bg": "#0f1830",
        "track": "#1c2942",
        "danger": "#f87171",
        "sidebar_start": "#0a1533",
        "sidebar_end": "#132c52",
        "sidebar_text": "#93c5fd",
        "overlay": "#0b1220",
        "bg_image": "assets/bg_dark.jpg",
    },
}


def palette(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES["light"])


def stylesheet(name: str) -> str:
    c = palette(name)
    return f"""
* {{ font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }}
QMainWindow, QWidget {{ color: {c['text']}; font-size: 13px; }}
QMainWindow {{ background: {c['bg']}; }}

QMenuBar {{ background: {c['card']}; border-bottom: 1px solid {c['card_border']}; padding: 2px; }}
QMenuBar::item {{ padding: 6px 14px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['accent_soft']}; color: {c['accent']}; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['card_border']}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; color: {c['accent']}; }}

QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['sidebar_start']}, stop:1 {c['sidebar_end']});
    border: none;
}}
QLabel#appTitle {{ color: #ffffff; font-size: 17px; font-weight: 700; }}
QLabel#appSub {{ color: {c['sidebar_text']}; font-size: 11px; }}

QPushButton#nav {{
    background: transparent; color: {c['sidebar_text']};
    border: none; border-radius: 10px;
    padding: 11px 16px; text-align: left; font-weight: 600; font-size: 13px;
}}
QPushButton#nav:hover {{ background: rgba(255, 255, 255, 30); color: #ffffff; }}
QPushButton#nav:checked {{
    background: #ffffff; color: {c['accent']};
}}

QLabel#hero {{ font-size: 24px; font-weight: 700; color: {c['text']}; }}
QLabel#subtitle {{ font-size: 13px; color: {c['text_dim']}; }}
QLabel#section {{ font-size: 14px; font-weight: 600; color: {c['text']}; }}
QLabel#dim {{ color: {c['text_dim']}; }}
QLabel#deviceName {{ font-size: 14px; font-weight: 600; }}
QLabel#camModel {{ font-size: 16px; font-weight: 700; }}

QFrame#card {{
    background: {c['card']};
    border: 1px solid {c['card_border']};
    border-radius: 14px;
}}
QFrame#deviceCard {{
    background: {c['card']};
    border: 1px solid {c['card_border']};
    border-radius: 12px;
}}
QFrame#deviceCard:hover {{ border: 1px solid {c['accent2']}; }}

QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['accent2']}, stop:1 {c['accent']});
    color: #ffffff; border: none; border-radius: 10px;
    padding: 9px 18px; font-weight: 600;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['accent']}, stop:1 {c['accent2']});
}}
QPushButton:pressed {{ background: {c['accent']}; padding-top: 11px; padding-bottom: 7px; }}
QPushButton:disabled {{ background: {c['track']}; color: {c['text_dim']}; }}
QPushButton#ghost {{
    background: transparent; color: {c['accent']};
    border: 1px solid {c['accent']};
}}
QPushButton#ghost:hover {{ background: {c['accent_soft']}; }}
QPushButton#mini {{
    background: transparent; color: {c['text_dim']};
    border: 1px solid {c['card_border']}; border-radius: 8px;
    padding: 5px 10px; font-weight: 400; font-size: 12px;
}}
QPushButton#mini:hover {{ color: {c['accent']}; border-color: {c['accent']}; background: {c['accent_soft']}; }}

QLineEdit, QComboBox {{
    background: {c['input_bg']}; color: {c['text']};
    border: 1px solid {c['card_border']}; border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {c['accent']};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {c['card']}; border: 1px solid {c['card_border']};
    border-radius: 8px; padding: 4px;
    selection-background-color: {c['accent_soft']};
    selection-color: {c['accent']};
}}

QListWidget {{ background: transparent; border: none; }}
QListWidget#photoGrid::item {{
    background: {c['card']}; border: 1px solid {c['card_border']};
    border-radius: 12px; color: {c['text']};
}}
QListWidget#photoGrid::item:selected {{
    border: 2px solid {c['accent']}; background: {c['accent_soft']};
}}
QListWidget#deviceList::item {{ background: transparent; border: none; }}
QListWidget#deviceList::item:selected {{ background: transparent; }}

QPlainTextEdit#logPanel {{
    background: {c['input_bg']}; color: {c['text_dim']};
    border: none; border-radius: 10px;
    font-family: Consolas, "Courier New", monospace; font-size: 12px;
    padding: 8px;
}}

QProgressBar {{
    background: {c['track']}; border: none; border-radius: 8px;
    height: 16px; text-align: center; color: transparent;
}}

QSlider::groove:horizontal {{ height: 6px; background: {c['track']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c['accent2']}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; background: {c['accent']};
}}
QSlider::handle:horizontal:hover {{ background: {c['accent2']}; }}

QLabel#exifKey {{ color: {c['text_dim']}; font-size: 12px; }}
QLabel#exifVal {{ color: {c['text']}; font-size: 12px; font-weight: 600; }}
QLabel#infoName {{ font-size: 13px; font-weight: 700; }}
QLabel#countLabel {{ color: {c['text_dim']}; font-size: 12px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['card_border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['accent2']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['card_border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {c['accent2']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QToolTip {{
    background: {c['card']}; color: {c['text']};
    border: 1px solid {c['card_border']}; border-radius: 6px; padding: 6px;
}}
QDialog {{ background: {c['bg']}; }}
QTextBrowser {{
    background: {c['card']}; border: 1px solid {c['card_border']};
    border-radius: 12px; padding: 12px;
}}
"""
