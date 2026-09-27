"""Colours, spacing and the stylesheet, kept in one place.

Anything that decides how Flow looks belongs here rather than scattered
through the widgets, so a restyle is one file.
"""

# Surfaces, darkest to lightest.
BG = "#14171c"
SURFACE = "#1b1f26"
SURFACE_HI = "#232833"
SURFACE_SUNK = "#101317"
BORDER = "#2a3039"
BORDER_HI = "#39414d"

TEXT = "#e6e9ef"
TEXT_DIM = "#95a0b0"
TEXT_FAINT = "#6b7684"

ACCENT = "#3d9dff"
ACCENT_HI = "#6bb6ff"
ACCENT_SUNK = "#1e5f9e"

OK = "#34d399"
WARN = "#fbbf24"
ERROR = "#f87171"

# ShotGrid status short codes -> colour. Anything unknown falls back to grey.
STATUS_COLOURS = {
    "ip": ACCENT,        # in progress
    "rdy": "#a78bfa",    # ready to start
    "fin": OK,           # final
    "cmpt": OK,          # complete
    "apr": OK,           # approved
    "rev": "#f0abfc",    # pending review
    "hld": WARN,         # on hold
    "omt": TEXT_FAINT,   # omitted
    "na": TEXT_FAINT,
}

# Palette for generated thumbnails, so a project without an image still gets a
# stable, recognisable colour instead of flat grey.
TILE_COLOURS = [
    ("#1e3a5f", "#2d5a8f"), ("#3d2952", "#5c3d7a"), ("#1f4037", "#2d6a5a"),
    ("#4a2c2a", "#7a4340"), ("#2a3b52", "#3f5a7d"), ("#4a3b1f", "#7a6130"),
    ("#2f2a52", "#48407d"), ("#1f424a", "#2f6570"),
]

RADIUS = 8
RADIUS_SM = 5


def status_colour(code):
    return STATUS_COLOURS.get((code or "").lower(), TEXT_FAINT)


def tile_colours(name):
    """Same name always gets the same pair, so tiles stay put visually."""
    return TILE_COLOURS[sum(ord(c) for c in name or "?") % len(TILE_COLOURS)]


STYLE = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: 'Inter', 'Open Sans', 'Segoe UI', sans-serif;
    font-size: 13px;
}}

/* ---- header ---- */
#header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
/* The QWidget rule above paints every label {BG}, which on the {SURFACE}
   header shows as a dark block whose edge reads as a divider. Labels here are
   transparent; the avatar needs two ids to out-rank that and keep its fill. */
#header QLabel {{ background: transparent; }}
#header #avatar {{ background: {ACCENT_SUNK}; }}
#headerTitle {{ font-size: 16px; font-weight: 600; color: {TEXT}; }}
#crumb {{ color: {TEXT_FAINT}; font-size: 16px; padding: 0 2px; }}
#backBtn {{
    background: transparent; border: none; color: {TEXT_DIM};
    font-size: 13px; padding: 6px 10px; border-radius: {RADIUS_SM}px;
}}
#backBtn:hover {{ color: {TEXT}; background: {SURFACE_HI}; }}

#userChip {{
    background: {SURFACE_HI}; border: 1px solid {BORDER};
    border-radius: 13px; padding: 4px 12px 4px 4px; color: {TEXT_DIM};
}}
#avatar {{
    background: {ACCENT_SUNK}; color: {TEXT};
    border-radius: 10px; font-weight: 700; font-size: 10px;
}}

#taskSearch {{
    background: {SURFACE_SUNK}; border: 1px solid {BORDER};
    border-radius: 13px; padding: 5px 12px; margin-right: 10px;
    color: {TEXT}; font-size: 12px;
}}
#taskSearch:focus {{ border-color: {ACCENT_SUNK}; background: {SURFACE}; }}
#searchResults {{
    background: {SURFACE}; border: 1px solid {BORDER_HI};
    border-radius: {RADIUS_SM}px; color: {TEXT}; padding: 4px;
    outline: none;
}}
#searchResults::item {{ padding: 5px 8px; border-radius: {RADIUS_SM}px; }}
#searchResults::item:selected {{
    background: {ACCENT_SUNK}; color: {TEXT};
}}

#termBtn {{
    background: transparent; border: 1px solid {BORDER}; border-radius: {RADIUS_SM}px;
    color: {TEXT_DIM}; padding: 5px 12px; margin-right: 10px; font-size: 12px;
}}
#termBtn:hover {{ border-color: {BORDER_HI}; color: {TEXT}; }}
#termBtn:checked {{
    color: {ACCENT}; border-color: {ACCENT_SUNK}; background: rgba(61,157,255,0.10);
}}

/* ---- tiles ---- */
#tile {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
}}
#tile:hover {{ background: {SURFACE_HI}; border-color: {ACCENT_SUNK}; }}
#tileThumb {{ border-radius: {RADIUS_SM}px; }}
#tileName {{ color: {TEXT}; font-weight: 600; font-size: 13px; }}
#tileSub {{ color: {TEXT_FAINT}; font-size: 11px; }}

/* ---- inputs ---- */
QLineEdit {{
    background: {SURFACE_SUNK}; border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px; padding: 7px 12px; color: {TEXT};
    selection-background-color: {ACCENT_SUNK};
}}
QLineEdit:focus {{ border-color: {ACCENT_SUNK}; background: {SURFACE}; }}

QCheckBox {{ color: {TEXT_DIM}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 13px; height: 13px; border-radius: 3px;
    border: 1px solid {BORDER_HI}; background: {SURFACE_SUNK};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---- tables ---- */
QTableWidget {{
    background: {BG}; border: none; gridline-color: transparent;
    alternate-background-color: {BG};
    selection-background-color: rgba(61,157,255,0.14);
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 0 12px; border-bottom: 1px solid {SURFACE}; }}
QTableWidget::item:selected {{ color: {TEXT}; }}
QTableWidget::item:hover {{ background: {SURFACE}; }}
QHeaderView::section {{
    background: {BG}; color: {TEXT_FAINT}; border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 12px; font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px;
}}

/* ---- tabs ---- */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_FAINT};
    padding: 10px 4px; margin-right: 22px; font-weight: 600; font-size: 13px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT_DIM}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

/* ---- context bar + status ---- */
#contextBar {{
    background: {SURFACE}; color: {TEXT_DIM};
    border-top: 1px solid {BORDER}; font-size: 12px;
}}
#contextBarEmpty {{
    background: {SURFACE}; color: {TEXT_FAINT};
    border-top: 1px solid {BORDER}; font-size: 12px;
}}
QStatusBar {{
    background: {SURFACE}; color: {TEXT_FAINT};
    border-top: 1px solid {BORDER}; font-size: 12px;
}}
QStatusBar::item {{ border: none; }}

/* ---- console ---- */
#console {{ background: {SURFACE_SUNK}; }}
#consoleBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
#consoleTitle {{ color: {TEXT}; font-weight: 600; font-size: 12px; }}
#consoleSource {{ color: {TEXT_FAINT}; padding-left: 8px; font-size: 11px; }}
#consoleBtn {{
    background: transparent; border: none; color: {TEXT_FAINT};
    padding: 3px 9px; border-radius: {RADIUS_SM}px; font-size: 12px;
}}
#consoleBtn:hover {{ color: {TEXT}; background: {SURFACE_HI}; }}
#consoleView {{
    background: {SURFACE_SUNK}; color: {TEXT_DIM}; border: none;
    selection-background-color: {ACCENT_SUNK};
}}

/* ---- combo boxes ---- */
QComboBox {{
    background: {SURFACE_SUNK}; border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px; padding: 5px 10px; color: {TEXT_DIM};
    min-height: 18px;
}}
QComboBox:hover {{ border-color: {BORDER_HI}; color: {TEXT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI}; border: 1px solid {BORDER_HI};
    selection-background-color: {ACCENT_SUNK}; color: {TEXT};
    outline: none; padding: 4px;
}}
#filterLabel {{ color: {TEXT_FAINT}; font-size: 11px; }}
#warnText {{ color: {WARN}; font-size: 12px; }}
#errorText {{ color: {ERROR}; font-size: 12px; }}

/* ---- notes ---- */
#noteCard {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-left: 2px solid {ACCENT_SUNK}; border-radius: {RADIUS_SM}px;
}}
#replyCard {{
    background: {SURFACE_SUNK}; border: 1px solid {BORDER};
    border-left: 2px solid {BORDER_HI}; border-radius: {RADIUS_SM}px;
}}
#noteSubject {{ color: {TEXT}; font-weight: 600; font-size: 12px; }}
#noteBody {{ color: {TEXT_DIM}; font-size: 12px; }}
#roleChip {{
    background: {SURFACE_HI}; color: {TEXT_FAINT}; border: 1px solid {BORDER};
    border-radius: 3px; padding: 1px 6px; font-size: 9px;
    font-weight: 700; letter-spacing: 0.6px;
}}

/* ---- preflight ---- */
#checkOk {{ color: {OK}; font-size: 12px; }}
#checkWarn {{ color: {WARN}; font-size: 12px; }}
#checkError {{ color: {ERROR}; font-size: 12px; }}
#checkSection {{
    color: {TEXT_FAINT}; font-size: 10px; font-weight: 700;
    letter-spacing: 0.6px;
}}

/* ---- drop zone ---- */
#dropZone {{
    background: {SURFACE}; border: 1px dashed {BORDER_HI};
    border-radius: {RADIUS}px;
}}
#dropZoneActive {{
    background: rgba(61,157,255,0.10); border: 1px dashed {ACCENT};
    border-radius: {RADIUS}px;
}}
#dropHint {{ color: {TEXT_FAINT}; font-size: 12px; }}

/* ---- empty states ---- */
#emptyIcon {{ color: {BORDER_HI}; font-size: 34px; }}
#emptyTitle {{ color: {TEXT_DIM}; font-size: 14px; font-weight: 600; }}
#emptyHint {{ color: {TEXT_FAINT}; font-size: 12px; }}

/* ---- menus ---- */
QMenu {{
    background: {SURFACE_HI}; border: 1px solid {BORDER_HI};
    border-radius: {RADIUS_SM}px; padding: 5px;
}}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 4px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT_SUNK}; }}
QMenu::item:disabled {{ color: {TEXT_FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

/* ---- scrollbars ---- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER_HI}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_HI}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: {BORDER}; height: 1px; }}
QToolTip {{
    background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER_HI};
    padding: 5px 8px; border-radius: 4px;
}}
"""
