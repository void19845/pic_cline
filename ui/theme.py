from __future__ import annotations
"""
ui.theme — palette + QSS stylesheet.

The palette is ported as-is from photo_organizer_ui.py (Tkinter) --
it was already deliberate and consistent with the rest of the ecosystem
(ACCENT = #7c6af7 matches AutoDJ / Document Parser). What changes here
is the finish PyQt6's QSS makes possible that Tkinter's styling can't
really do: real hover/pressed/focus states, consistent radii and
spacing, a focus ring that doesn't fight the dark background.

No PyQt import needed at parse time other than the type used for the
returned string -- kept dependency-free so this module can be imported
by anything, including tests, without pulling in Qt widgets.
"""

# ── Palette (ported 1:1 from photo_organizer_ui.py) ─────────────────────────
BG       = "#0f0f11"
BG2      = "#1a1a1f"
BG3      = "#25252d"
BORDER   = "#2e2e38"
ACCENT   = "#7c6af7"
ACCENT2  = "#5dcaa5"
DANGER   = "#e05b5b"
WARN     = "#f0c060"
DUP_C    = "#b07cf0"
VID_C    = "#5bb8d4"
FG       = "#e8e6f0"
FG2      = "#8e8ba0"
FG3      = "#5a5870"

# Derived, used only for hover/pressed states (kept close to BG3/ACCENT
# rather than introducing new hues -- one accent, used consistently)
ACCENT_HOVER   = "#8f7ff9"
ACCENT_PRESSED = "#6a58e0"
BG3_HOVER      = "#2c2c36"

SIDEBAR_W = 340
RADIUS    = 8


def stylesheet() -> str:
    """Full application QSS. Applied once at QApplication level."""
    return f"""
    * {{
        font-family: -apple-system, "Segoe UI", "Inter", sans-serif;
        color: {FG};
        outline: none;
    }}

    QMainWindow, QWidget {{
        background-color: {BG};
    }}

    /* ── Sidebar / panels ─────────────────────────────────────────── */
    QWidget#sidebar {{
        background-color: {BG2};
        border-right: 1px solid {BORDER};
    }}
    QWidget#card {{
        background-color: {BG2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
    }}

    /* ── Labels ───────────────────────────────────────────────────── */
    QLabel {{
        color: {FG};
        background: transparent;
    }}
    QLabel#sectionLabel {{
        color: {FG2};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }}
    QLabel#hintLabel {{
        color: {FG3};
        font-size: 11px;
    }}
    QLabel#titleLabel {{
        color: {FG};
        font-size: 18px;
        font-weight: 600;
    }}

    /* ── Line edits / path fields ─────────────────────────────────── */
    QLineEdit {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        border-radius: {RADIUS - 2}px;
        padding: 7px 10px;
        color: {FG};
        selection-background-color: {ACCENT};
    }}
    QLineEdit:hover {{
        border: 1px solid {FG3};
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QLineEdit:disabled {{
        color: {FG3};
    }}

    /* ── Buttons ──────────────────────────────────────────────────── */
    QPushButton {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        border-radius: {RADIUS - 2}px;
        padding: 7px 14px;
        color: {FG};
    }}
    QPushButton:hover {{
        background-color: {BG3_HOVER};
        border: 1px solid {FG3};
    }}
    QPushButton:pressed {{
        background-color: {BORDER};
    }}
    QPushButton:disabled {{
        color: {FG3};
        border: 1px solid {BORDER};
    }}
    QPushButton#primary {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
        color: white;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background-color: {ACCENT_HOVER};
        border: 1px solid {ACCENT_HOVER};
    }}
    QPushButton#primary:pressed {{
        background-color: {ACCENT_PRESSED};
    }}
    QPushButton#primary:disabled {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        color: {FG3};
    }}
    QPushButton#danger {{
        background-color: transparent;
        border: 1px solid {DANGER};
        color: {DANGER};
    }}
    QPushButton#danger:hover {{
        background-color: {DANGER};
        color: white;
    }}
    QPushButton#ghost {{
        background-color: transparent;
        border: 1px solid transparent;
        color: {FG2};
    }}
    QPushButton#ghost:hover {{
        color: {FG};
        background-color: {BG3};
    }}

    /* ── Checkboxes / radio ───────────────────────────────────────── */
    QCheckBox, QRadioButton {{
        color: {FG};
        spacing: 8px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        background-color: {BG3};
        border-radius: 4px;
    }}
    QRadioButton::indicator {{
        border-radius: 8px;
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
    }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border: 1px solid {FG3};
    }}

    /* ── Combo box ────────────────────────────────────────────────── */
    QComboBox {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        border-radius: {RADIUS - 2}px;
        padding: 6px 10px;
        color: {FG};
    }}
    QComboBox:hover {{
        border: 1px solid {FG3};
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT};
        color: {FG};
    }}

    /* ── Tabs ─────────────────────────────────────────────────────── */
    QTabWidget::pane {{
        border: none;
        background-color: {BG};
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {FG2};
        padding: 10px 18px;
        margin-right: 2px;
        border-bottom: 2px solid transparent;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        color: {FG};
    }}
    QTabBar::tab:selected {{
        color: {FG};
        border-bottom: 2px solid {ACCENT};
    }}

    /* ── Progress bar ─────────────────────────────────────────────── */
    QProgressBar {{
        background-color: {BG3};
        border: 1px solid {BORDER};
        border-radius: {RADIUS - 2}px;
        text-align: center;
        color: {FG};
        height: 22px;
    }}
    QProgressBar::chunk {{
        background-color: {ACCENT};
        border-radius: {RADIUS - 3}px;
    }}

    /* ── Scroll areas / lists ─────────────────────────────────────── */
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BG3};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {FG3};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    /* ── Plain text log view ──────────────────────────────────────── */
    QPlainTextEdit#logView {{
        background-color: {BG2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        color: {FG2};
        font-family: "SF Mono", "Cascadia Code", Consolas, monospace;
        font-size: 12px;
        padding: 8px;
    }}

    /* ── List widget (duplicate pairs, face clusters) ────────────── */
    QListWidget {{
        background-color: {BG2};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        padding: 4px;
    }}
    QListWidget::item {{
        border-radius: {RADIUS - 3}px;
        padding: 8px;
        margin: 2px;
    }}
    QListWidget::item:hover {{
        background-color: {BG3};
    }}
    QListWidget::item:selected {{
        background-color: {BG3};
        border: 1px solid {ACCENT};
    }}

    /* ── Status pill labels (used for OK / warning / error text) ───── */
    QLabel#pillOk {{
        color: {ACCENT2};
        font-weight: 600;
    }}
    QLabel#pillWarn {{
        color: {WARN};
        font-weight: 600;
    }}
    QLabel#pillDanger {{
        color: {DANGER};
        font-weight: 600;
    }}
    QLabel#pillVideo {{
        color: {VID_C};
        font-weight: 600;
    }}
    QLabel#pillDup {{
        color: {DUP_C};
        font-weight: 600;
    }}

    QSplitter::handle {{
        background-color: {BORDER};
    }}

    QToolTip {{
        background-color: {BG3};
        color: {FG};
        border: 1px solid {BORDER};
        padding: 4px 8px;
        border-radius: 4px;
    }}
    """
