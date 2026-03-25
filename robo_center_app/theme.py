"""Shared theme constants for the Robo Neural UI."""

C = {
    "void": "#04060a",
    "deep": "#070c12",
    "surface": "#0c1420",
    "panel": "#101a28",
    "raised": "#141f30",
    "border": "#1a2840",
    "border2": "#243650",
    "cyan": "#00e5ff",
    "cyan_dim": "#0099bb",
    "blue": "#1464dc",
    "green": "#00ff9d",
    "green_dim": "#007744",
    "amber": "#ffb300",
    "red": "#ff2244",
    "purple": "#9945ff",
    "text": "#c8dcea",
    "text2": "#6888a8",
    "text3": "#304860",
}

SS = f"""
* {{ font-family: 'Courier New', 'Consolas', monospace; font-size: 12px; }}
QMainWindow, QWidget {{ background: {C['void']}; color: {C['text']}; }}
QGroupBox {{
    border: 1px solid {C['border']};
    border-radius: 2px;
    margin-top: 14px;
    padding: 8px 6px 6px 6px;
    background: {C['panel']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {C['cyan']};
    font-size: 9px;
    letter-spacing: 4px;
    text-transform: uppercase;
}}
QPushButton {{
    background: {C['raised']};
    color: {C['text']};
    border: 1px solid {C['border2']};
    border-radius: 2px;
    padding: 5px 12px;
    font-size: 10px;
    letter-spacing: 2px;
}}
QPushButton:hover {{
    background: {C['surface']};
    border-color: {C['cyan']};
    color: {C['cyan']};
}}
QPushButton:pressed {{ background: {C['cyan']}; color: {C['void']}; border-color: {C['cyan']}; }}
QPushButton:disabled {{ color: {C['text3']}; border-color: {C['border']}; background: {C['deep']}; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {C['deep']};
    color: {C['text']};
    border: 1px solid {C['border']};
    border-radius: 2px;
    padding: 4px 7px;
    selection-background-color: {C['blue']};
}}
QLineEdit:focus {{ border-color: {C['cyan']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QTextEdit {{
    background: {C['deep']};
    color: {C['green']};
    border: 1px solid {C['border']};
    border-radius: 2px;
    font-size: 11px;
}}
QCheckBox {{ color: {C['text2']}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 13px; height: 13px;
    border: 1px solid {C['border2']};
    border-radius: 1px;
    background: {C['deep']};
}}
QCheckBox::indicator:checked {{ background: {C['cyan']}; border-color: {C['cyan']}; }}
QTabWidget::pane {{
    border: 1px solid {C['border']};
    background: {C['panel']};
    top: -1px;
}}
QTabBar::tab {{
    background: {C['deep']};
    color: {C['text2']};
    padding: 5px 14px;
    border: 1px solid {C['border']};
    border-bottom: none;
    font-size: 9px;
    letter-spacing: 3px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {C['panel']}; color: {C['cyan']}; border-color: {C['cyan_dim']}; }}
QScrollBar:vertical {{ background: {C['deep']}; width: 5px; border-radius: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border2']}; border-radius: 2px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: {C['cyan_dim']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QSlider::groove:horizontal {{
    background: {C['border']}; height: 3px; border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: {C['cyan']}; width: 12px; height: 12px;
    border-radius: 6px; margin: -4px 0;
}}
QSlider::sub-page:horizontal {{ background: {C['blue']}; border-radius: 1px; }}
QProgressBar {{
    background: {C['deep']}; border: 1px solid {C['border']};
    border-radius: 2px; text-align: center; color: {C['text2']};
    font-size: 9px; height: 14px;
}}
QProgressBar::chunk {{ background: {C['cyan_dim']}; border-radius: 1px; }}
QSplitter::handle {{ background: {C['border']}; }}
"""

