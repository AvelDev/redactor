"""Design tokens, Qt palette, stylesheet and tinted icons.

The visual world is a dark graphite studio in the manner of professional image
editors: four neutral layers (pasteboard < panel < panel header < raised
control), input fields sunk below the panel, one blue accent reserved for
selection / focus / the primary action, and a separate signal red-orange that
only ever means "pending redaction".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QStyleFactory

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"


@dataclass(frozen=True)
class Tokens:
    pasteboard: str
    panel: str
    header: str
    raised: str
    raised_hover: str
    field: str
    line: str  # hairline between regions
    line_soft: str  # control borders
    text: str
    text_dim: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_text: str
    pending: str  # pending redaction mark
    candidate: str  # search hit not yet accepted
    ok: str
    warn: str
    fail: str
    page_shadow: str


DARK = Tokens(
    pasteboard="#1c1c1e",
    panel="#29292b",
    header="#313134",
    raised="#3a3a3d",
    raised_hover="#454549",
    field="#1f1f21",
    line="#151517",
    line_soft="#48484c",
    text="#e6e6e8",
    text_dim="#aeaeb3",
    text_faint="#94949a",
    accent="#3b82f6",
    accent_hover="#5b97f8",
    accent_text="#ffffff",
    pending="#ff5a36",
    candidate="#f5b83d",
    ok="#46c35a",
    warn="#e3a72f",
    fail="#ff5d55",
    page_shadow="#000000",
)

LIGHT = Tokens(
    pasteboard="#c9c9cc",
    panel="#ececee",
    header="#e1e1e4",
    raised="#f8f8f9",
    raised_hover="#ffffff",
    field="#ffffff",
    line="#b9b9bd",
    line_soft="#b4b4b9",
    text="#1d1d1f",
    text_dim="#4a4a50",
    text_faint="#66666c",
    accent="#1f6fe5",
    accent_hover="#3a82ee",
    accent_text="#ffffff",
    pending="#e2401d",
    candidate="#c98a00",
    ok="#1f8f3a",
    warn="#a86f00",
    fail="#d92d20",
    page_shadow="#000000",
)

THEMES = {"dark": DARK, "light": LIGHT}
T: Tokens = DARK  # active tokens; set by apply()

ICON_SIZE = 18
TOOL_ICON_SIZE = 20


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    c = QColor
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        p.setColor(group, QPalette.ColorRole.Window, c(t.panel))
        p.setColor(group, QPalette.ColorRole.WindowText, c(t.text))
        p.setColor(group, QPalette.ColorRole.Base, c(t.field))
        p.setColor(group, QPalette.ColorRole.AlternateBase, c(t.header))
        p.setColor(group, QPalette.ColorRole.Text, c(t.text))
        p.setColor(group, QPalette.ColorRole.Button, c(t.raised))
        p.setColor(group, QPalette.ColorRole.ButtonText, c(t.text))
        p.setColor(group, QPalette.ColorRole.Highlight, c(t.accent))
        p.setColor(group, QPalette.ColorRole.HighlightedText, c(t.accent_text))
        p.setColor(group, QPalette.ColorRole.ToolTipBase, c(t.header))
        p.setColor(group, QPalette.ColorRole.ToolTipText, c(t.text))
        p.setColor(group, QPalette.ColorRole.PlaceholderText, c(t.text_faint))
        p.setColor(group, QPalette.ColorRole.Link, c(t.accent_hover))
        p.setColor(group, QPalette.ColorRole.Mid, c(t.line_soft))
        p.setColor(group, QPalette.ColorRole.Dark, c(t.line))
        p.setColor(group, QPalette.ColorRole.Light, c(t.raised_hover))
    dis = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(dis, role, c(t.text_faint).darker(130) if t is DARK else c(t.text_faint))
    p.setColor(dis, QPalette.ColorRole.Window, c(t.panel))
    p.setColor(dis, QPalette.ColorRole.Base, c(t.panel))
    p.setColor(dis, QPalette.ColorRole.Button, c(t.panel))
    p.setColor(dis, QPalette.ColorRole.Highlight, c(t.line_soft))
    return p


def stylesheet(t: Tokens) -> str:
    sel = selection(t)
    return f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {t.panel}; }}
QMainWindow::separator {{ background: {t.line}; width: 2px; height: 2px; }}
QMainWindow::separator:hover {{ background: {t.accent}; }}

QToolTip {{
    background: {t.header}; color: {t.text}; border: 1px solid {t.line_soft};
    padding: 4px 6px; border-radius: 2px;
}}

/* ---- menus ---- */
QMenuBar {{ background: {t.panel}; border-bottom: 1px solid {t.line}; padding: 1px 2px; }}
QMenuBar::item {{ padding: 4px 9px; background: transparent; border-radius: 2px; }}
QMenuBar::item:selected {{ background: {t.raised}; }}
QMenu {{ background: {t.header}; border: 1px solid {t.line}; padding: 4px 0; }}
QMenu::item {{ padding: 5px 28px 5px 26px; }}
QMenu::item:selected {{ background: {t.accent}; color: {t.accent_text}; }}
QMenu::item:disabled {{ color: {t.text_faint}; }}
QMenu::separator {{ height: 1px; background: {t.line_soft}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 6px; }}
QMenu::indicator {{ width: 12px; height: 12px; left: 8px; }}

/* ---- toolbars ---- */
QToolBar {{ background: {t.panel}; border: none; spacing: 2px; }}
QToolBar#tools {{ border-right: 1px solid {t.line}; padding: 6px 4px; spacing: 3px; }}
QToolBar#options {{ border-bottom: 1px solid {t.line}; padding: 3px 8px; spacing: 6px; }}
QToolBar::separator {{ background: {t.line_soft}; width: 1px; height: 1px; margin: 4px 6px; }}
QToolBar#tools::separator {{ margin: 6px 4px; }}
QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 3px;
    padding: 4px; color: {t.text_dim};
}}
QToolButton:hover {{ background: {t.raised}; color: {t.text}; }}
QToolButton:pressed {{ background: {t.line}; }}
QToolButton:checked {{ background: {t.raised_hover}; border-color: {t.line_soft}; color: {t.text}; }}
QToolButton:disabled {{ color: {t.text_faint}; }}
QToolButton:focus {{ border-color: {t.accent}; }}
QToolButton[popupMode="1"] {{ padding-right: 14px; }}
QToolButton#textButton {{ padding: 3px 8px; }}

/* ---- buttons ---- */
QPushButton {{
    background: {t.raised}; color: {t.text}; border: 1px solid {t.line_soft};
    border-radius: 3px; padding: 5px 14px; min-height: 18px;
}}
QPushButton:hover {{ background: {t.raised_hover}; }}
QPushButton:pressed {{ background: {t.header}; }}
QPushButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.text_faint}; background: {t.panel}; border-color: {t.header}; }}
QPushButton[primary="true"] {{
    background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[primary="true"]:focus {{ border-color: {t.accent_text}; }}
QPushButton[primary="true"]:disabled {{
    background: {t.header}; color: {t.text_faint}; border-color: {t.header};
}}
QPushButton[flat="true"] {{ background: transparent; border-color: transparent; }}
QPushButton[flat="true"]:hover {{ background: {t.raised}; }}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {t.field}; color: {t.text}; border: 1px solid {t.line}; min-height: 18px;
    border-radius: 2px; padding: 3px 6px; selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {t.line_soft}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {t.accent}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {t.text_faint}; background: {t.panel}; }}
QLineEdit[invalid="true"] {{ border-color: {t.fail}; }}
QComboBox {{ padding-right: 20px; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ image: url({_icon_file("chevron-down", t.text_dim)}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {t.header}; border: 1px solid {t.line}; selection-background-color: {t.accent};
    outline: none; padding: 2px;
}}
QCheckBox {{ spacing: 7px; color: {t.text}; }}
QCheckBox:disabled {{ color: {t.text_faint}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {t.line_soft}; border-radius: 2px;
    background: {t.field};
}}
QCheckBox::indicator:hover {{ border-color: {t.text_dim}; }}
QCheckBox::indicator:focus {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked {{
    background: {t.accent}; border-color: {t.accent};
    image: url({_icon_file("check", t.accent_text)});
}}

/* ---- document tabs ---- */
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {t.panel}; }}
QTabBar::tab {{
    background: {t.panel}; color: {t.text_dim}; border: none; border-right: 1px solid {t.line};
    padding: 6px 10px 6px 12px; min-width: 80px;
}}
QTabBar::tab:selected {{ background: {t.pasteboard}; color: {t.text}; }}
QTabBar::tab:hover:!selected {{ background: {t.header}; color: {t.text}; }}
QTabBar::close-button {{ image: url({_icon_file("x", t.text_faint)}); subcontrol-position: right; margin: 2px; }}
QTabBar::close-button:hover {{ image: url({_icon_file("x", t.text)}); background: {t.raised}; border-radius: 2px; }}
QMainWindow > QTabBar {{ background: {t.header}; border-bottom: 1px solid {t.line}; }}
QMainWindow > QTabBar::tab {{
    background: {t.header}; color: {t.text_dim}; min-width: 0; padding: 5px 12px;
    border: none; border-right: 1px solid {t.line};
}}
QMainWindow > QTabBar::tab:selected {{ background: {t.panel}; color: {t.text}; }}
QMainWindow > QTabBar::tab:hover:!selected {{ color: {t.text}; }}

/* ---- docks ---- */
QDockWidget {{ color: {t.text}; titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {t.header}; padding: 5px 8px; border-bottom: 1px solid {t.line};
    text-align: left;
}}
QDockWidget > QWidget {{ background: {t.panel}; }}
QLabel#sectionTitle {{ color: {t.text_dim}; font-weight: 600; padding-top: 4px; }}
QLabel#hint {{ color: {t.text_faint}; }}
QLabel#danger {{ color: {t.fail}; }}

/* ---- item views ---- */
QTreeView, QListView {{
    background: {t.panel}; border: none; color: {t.text};
    selection-background-color: {sel}; selection-color: {t.text};
    show-decoration-selected: 1;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{ background: {sel}; color: {t.text}; }}
QTreeView::item, QListView::item {{ padding: 3px 2px; border: none; }}
QTreeView::item:hover:!selected, QListView::item:hover:!selected {{ background: {t.header}; }}
QTreeView::item:selected:!active, QListView::item:selected:!active {{
    background: {t.raised_hover}; color: {t.text};
}}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:selected:active {{ background: {sel}; }}
QTreeView::branch:selected:!active {{ background: {t.raised_hover}; }}
QTreeView::branch:has-children:closed {{ image: url({_icon_file("chevron-right", t.text_dim)}); }}
QTreeView::branch:has-children:open {{ image: url({_icon_file("chevron-down", t.text_dim)}); }}
QHeaderView::section {{
    background: {t.header}; color: {t.text_dim}; border: none; border-bottom: 1px solid {t.line};
    padding: 4px 6px;
}}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {t.raised_hover}; border-radius: 3px; border: 2px solid transparent; }}
QScrollBar::handle:vertical {{ min-height: 28px; margin: 2px; }}
QScrollBar::handle:horizontal {{ min-width: 28px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {t.text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QAbstractScrollArea::corner {{ background: transparent; }}

/* ---- status bar ---- */
QStatusBar {{ background: {t.panel}; border-top: 1px solid {t.line}; color: {t.text_dim}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t.text_dim}; padding: 0 8px; border-left: 1px solid {t.line}; }}
QStatusBar QLabel#statusFirst {{ border-left: none; }}
QProgressBar {{
    background: {t.field}; border: 1px solid {t.line}; border-radius: 2px; height: 8px;
    text-align: center; color: transparent; max-height: 8px;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 1px; }}

/* ---- canvas & empty state ---- */
QGraphicsView#canvas {{ background: {t.pasteboard}; border: none; }}
QWidget#emptyState {{ background: {t.pasteboard}; }}
QFrame#dropZone {{ border: 1px solid transparent; border-radius: 4px; background: transparent; }}
QFrame#dropZone[hot="true"] {{ border: 1px solid {t.accent}; }}
QLabel#emptyTitle {{ color: {t.text}; font-size: 15px; font-weight: 600; }}
QLabel#emptyBody {{ color: {t.text_dim}; }}
QPushButton#recent {{
    background: transparent; border: none; color: {t.text_dim}; text-align: left; padding: 3px 4px;
}}
QPushButton#recent:hover {{ color: {t.text}; background: {t.panel}; }}
QPushButton#recent:focus {{ color: {t.text}; background: {t.panel}; }}

/* ---- report ---- */
QFrame#reportHeader {{ background: {t.header}; border-radius: 4px; }}
QFrame#reportHeader[state="fail"] {{ border: 1px solid {t.fail}; }}
QFrame#reportHeader[state="ok"] {{ border: 1px solid {t.ok}; }}
QLabel#reportTitle {{ font-size: 15px; font-weight: 600; color: {t.text}; }}
QLabel#mono {{ font-family: "Cascadia Mono", "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace; color: {t.text_dim}; }}
QFrame#previewFrame {{ background: {t.pasteboard}; border: 1px solid {t.line}; border-radius: 3px; }}
"""


# ---------------------------------------------------------------- icons

def _svg(name: str, color: str, stroke: float = 1.75) -> bytes:
    raw = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    raw = raw.replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return raw.encode()


@cache
def _icon_file(name: str, color: str) -> str:
    """Tinted icon written to a cache file, for use inside the stylesheet (url(...))."""
    import tempfile

    folder = Path(tempfile.gettempdir()) / "redactor-icons"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_bytes(_svg(name, color, 2.25))
    return path.as_posix()


def pixmap(name: str, color: str, size: int = ICON_SIZE, dpr: float | None = None) -> QPixmap:
    dpr = dpr or (QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0)
    pm = QPixmap(QSize(round(size * dpr), round(size * dpr)))
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_svg(name, color)))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = ICON_SIZE, color: str | None = None) -> QIcon:
    """Icon with state colours: dim at rest, bright on hover/checked, faint when disabled."""
    ic = QIcon()
    base = color or T.text_dim
    hot = color or T.text
    ic.addPixmap(pixmap(name, base, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, hot, size), QIcon.Mode.Active, QIcon.State.Off)
    ic.addPixmap(pixmap(name, hot, size), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(pixmap(name, hot, size), QIcon.Mode.Active, QIcon.State.On)
    ic.addPixmap(pixmap(name, T.text, size), QIcon.Mode.Selected, QIcon.State.Off)
    disabled = mix(T.text_faint, T.panel, 0.45)
    ic.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled, QIcon.State.Off)
    ic.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled, QIcon.State.On)
    return ic


def selection(t: Tokens) -> str:
    """Muted accent for selected rows: legible with normal text colour in both themes."""
    return mix(t.accent, t.panel, 0.55 if t is DARK else 0.78)


def mix(a: str, b: str, amount: float) -> str:
    """Opaque blend of ``a`` towards ``b`` (SVG has no #AARRGGBB, so no alpha tricks)."""
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * amount),
        round(ca.green() + (cb.green() - ca.green()) * amount),
        round(ca.blue() + (cb.blue() - ca.blue()) * amount),
    ).name()


def ui_font() -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    f.setPixelSize(12)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def tabular(font: QFont) -> QFont:
    """Same font with tabular figures, for counters and numeric fields."""
    f = QFont(font)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):  # Qt < 6.7
        pass
    return f


def apply(app: QApplication, theme: str = "dark") -> Tokens:
    global T
    T = THEMES.get(theme, DARK)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(ui_font())
    app.setPalette(_palette(T))
    app.setStyleSheet(stylesheet(T))
    return T


def qcolor(hex_color: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c
