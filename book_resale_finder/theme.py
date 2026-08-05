from __future__ import annotations

LIGHT = {
    "bg": "#f5f7fa",
    "panel": "#ffffff",
    "text": "#172033",
    "muted": "#607089",
    "line": "#d8dee8",
    "field": "#f9fbfd",
    "green": "#167447",
    "green_dark": "#105d38",
    "blue": "#2563eb",
    "amber": "#a85f00",
    "danger": "#b4234a",
    "stat": "#fbfcfe",
}

DARK = {
    "bg": "#121312",
    "panel": "#1c1d1f",
    "text": "#f4f6f3",
    "muted": "#aeb8ad",
    "line": "#3a403a",
    "field": "#111411",
    "green": "#52b788",
    "green_dark": "#94d2bd",
    "blue": "#7aa2ff",
    "amber": "#ffc857",
    "danger": "#ff7a90",
    "stat": "#171a17",
}


def stylesheet(theme: dict[str, str]) -> str:
    return f"""
    QMainWindow, QWidget#root, QDialog, QMessageBox, QMenu {{
        background: {theme['bg']};
        color: {theme['text']};
        font-family: "Segoe UI";
        font-size: 10pt;
    }}
    QLabel {{ color: {theme['text']}; }}
    QLabel#title {{ font-size: 24px; font-weight: 800; }}
    QLabel#subtitle, QLabel#muted, QLabel[class~="statLabel"] {{ color: {theme['muted']}; }}
    QLabel#sectionTitle {{ color: {theme['muted']}; font-size: 10px; font-weight: 800; }}
    QFrame[class~="card"] {{
        background: {theme['panel']};
        border: 1px solid {theme['line']};
        border-radius: 8px;
    }}
    QFrame[class~="stat"] {{
        background: {theme['stat']};
        border: 1px solid {theme['line']};
        border-radius: 8px;
    }}
    QLabel[class~="statValue"] {{ font-size: 16px; font-weight: 800; }}
    QLineEdit, QComboBox, QSpinBox {{
        min-height: 36px;
        padding: 0 10px;
        background: {theme['field']};
        color: {theme['text']};
        border: 1px solid {theme['line']};
        border-radius: 8px;
        selection-background-color: {theme['blue']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {theme['blue']}; }}
    QComboBox::drop-down {{ border: 0; width: 28px; }}
    QComboBox QAbstractItemView {{
        background: {theme['panel']};
        color: {theme['text']};
        border: 1px solid {theme['line']};
        selection-background-color: {theme['stat']};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 20px;
        border: 0;
        background: {theme['stat']};
    }}
    QPushButton {{
        min-height: 38px;
        padding: 0 16px;
        border: 1px solid {theme['green_dark']};
        border-radius: 8px;
        background: {theme['green']};
        color: white;
        font-weight: 800;
    }}
    QPushButton:hover {{ background: {theme['green_dark']}; }}
    QPushButton:disabled {{ background: {theme['line']}; border-color: {theme['line']}; color: {theme['muted']}; }}
    QPushButton[class~="secondary"] {{
        background: {theme['panel']};
        border-color: {theme['line']};
        color: {theme['text']};
    }}
    QPushButton[class~="secondary"]:hover {{ background: {theme['stat']}; }}
    QPushButton[class~="danger"] {{ background: {theme['danger']}; border-color: {theme['danger']}; }}
    QProgressBar {{
        min-height: 18px;
        border: 1px solid {theme['line']};
        border-radius: 8px;
        background: {theme['field']};
        color: {theme['text']};
        text-align: center;
        font-weight: 700;
    }}
    QProgressBar::chunk {{ background: {theme['green']}; border-radius: 7px; }}
    QCheckBox {{ color: {theme['text']}; spacing: 8px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; }}
    QCheckBox::indicator:unchecked {{ border: 1px solid {theme['line']}; border-radius: 4px; background: {theme['field']}; }}
    QCheckBox::indicator:checked {{ border: 1px solid {theme['green']}; border-radius: 4px; background: {theme['green']}; }}
    QRadioButton {{ color: {theme['muted']}; font-weight: 700; spacing: 5px; }}
    QTextEdit {{
        background: {theme['field']};
        color: {theme['text']};
        border: 1px solid {theme['line']};
        border-radius: 8px;
        padding: 8px;
    }}
    QMenu::item {{ padding: 7px 24px; }}
    QMenu::item:selected {{ background: {theme['stat']}; }}
    QToolTip {{ background: {theme['panel']}; color: {theme['text']}; border: 1px solid {theme['line']}; }}
    """
