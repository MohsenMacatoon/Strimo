"""Dark theme for Strimo."""

ACCENT = "#22C3A6"
ACCENT_HOVER = "#3BD9BC"
BG = "#121419"
BG_PANEL = "#181B22"
BG_RAISED = "#20242D"
BG_HOVER = "#2A2F3A"
BORDER = "#2C313C"
TEXT = "#E7EAF0"
TEXT_DIM = "#9AA2B1"
WARN = "#F5B942"
DANGER = "#EF5B5B"

STYLE = f"""
* {{
    font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#controlBar {{ background: {BG_PANEL}; border-top: 1px solid {BORDER}; }}
QWidget#panelRoot, QDockWidget > QWidget {{ background: {BG_PANEL}; }}
QDockWidget::title {{ background: {BG_PANEL}; padding: 6px 10px; text-align: left; color: {TEXT_DIM}; }}

QMenuBar {{ background: {BG_PANEL}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {BG_HOVER}; }}
QMenu {{ background: {BG_RAISED}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 26px; border-radius: 6px; }}
QMenu::item:selected {{ background: {BG_HOVER}; }}
QMenu::item:disabled {{ color: #5d6472; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}
QMenu::indicator:checked {{ image: none; background: {ACCENT}; border-radius: 7px; }}

QToolButton, QPushButton {{
    background: transparent; border: none; border-radius: 8px; padding: 5px;
}}
QToolButton:hover, QPushButton:hover {{ background: {BG_HOVER}; }}
QToolButton:pressed, QPushButton:pressed {{ background: {BORDER}; }}
QToolButton:checked {{ background: {BG_HOVER}; color: {ACCENT}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#playButton {{ background: {ACCENT}; border-radius: 19px; }}
QToolButton#playButton:hover {{ background: {ACCENT_HOVER}; }}
QToolButton#speedButton {{
    font-weight: 600; padding: 4px 10px; border: 1px solid {BORDER}; border-radius: 13px;
}}
QToolButton#speedButton[changed="true"] {{ color: {ACCENT}; border-color: {ACCENT}; }}
QPushButton {{ background: {BG_RAISED}; border: 1px solid {BORDER}; padding: 6px 14px; }}
QPushButton:default, QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #08110f; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:disabled {{ color: #5d6472; }}
QPushButton[chip="true"] {{ padding: 4px 10px; border-radius: 12px; }}

QLabel#timeLabel {{ color: {TEXT_DIM}; font-family: "Segoe UI", "Consolas", monospace; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#title {{ font-size: 12pt; font-weight: 600; }}
QLabel#badge {{ color: {ACCENT}; font-weight: 600; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 7px; padding: 5px 8px;
    selection-background-color: {ACCENT}; selection-color: #08110f;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {BG_RAISED}; border: 1px solid {BORDER}; selection-background-color: {BG_HOVER}; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #4a5160; border-radius: 4px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTabWidget::pane {{ border: none; background: {BG_PANEL}; }}
QTabBar::tab {{ background: transparent; padding: 7px 10px; color: {TEXT_DIM}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QListWidget {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 6px 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {BG_HOVER}; color: {TEXT}; }}
QListWidget::item:hover {{ background: #1f232b; }}

QProgressBar {{ background: {BORDER}; border: none; border-radius: 3px; height: 6px; text-align: center; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QProgressBar[state="paused"]::chunk {{ background: {WARN}; }}
QProgressBar[state="failed"]::chunk {{ background: {DANGER}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a404d; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4a5160; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3a404d; border-radius: 4px; min-width: 30px; }}

QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {TEXT_DIM}; }}

QToolTip {{ background: {BG_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 7px; border-radius: 6px; }}
QFrame#card {{ background: {BG_RAISED}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#sep {{ background: {BORDER}; max-height: 1px; min-height: 1px; }}
"""
