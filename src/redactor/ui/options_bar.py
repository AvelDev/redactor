"""Context options for the active tool, Photoshop-style, plus preview and export."""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from redactor.i18n import N_, tr
from redactor.ui import theme
from redactor.ui.canvas import Tool

TOOL_ICONS = {Tool.HAND: "hand", Tool.TEXT: "text-cursor", Tool.AREA: "square-dashed", Tool.ZOOM: "zoom-in"}
TOOL_NAMES = {
    Tool.HAND: N_("tool.hand"),
    Tool.TEXT: N_("tool.text"),
    Tool.AREA: N_("tool.area"),
    Tool.ZOOM: N_("tool.zoom"),
}


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    return label


class OptionsBar(QWidget):
    wordsToggled = Signal(bool)
    snapToggled = Signal(bool)
    zoomActual = Signal()
    zoomWidth = Signal()
    zoomPage = Signal()

    def __init__(self, preview: QAction, export: QAction, parent: QWidget | None = None):
        super().__init__(parent)
        self.icon = QLabel()
        self.name = QLabel()
        self.name.setStyleSheet("font-weight: 600;")
        self.stack = QStackedWidget()
        self.pages: dict[Tool, int] = {}

        self.words = QCheckBox(tr("options.words"))
        self.words.toggled.connect(self.wordsToggled)
        self.snap = QCheckBox(tr("options.snap"))
        self.snap.setToolTip(tr("options.snap_tip"))
        self.snap.toggled.connect(self.snapToggled)

        def page(*widgets: QWidget) -> QWidget:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(14)
            for x in widgets:
                lay.addWidget(x)
            lay.addStretch()
            return w

        def text_button(text: str, signal: Signal) -> QToolButton:
            b = QToolButton()
            b.setObjectName("textButton")
            b.setText(text)
            b.clicked.connect(signal)
            return b

        for tool, w in (
            (Tool.HAND, page(_hint(tr("options.hand_hint")))),
            (Tool.TEXT, page(self.words, _hint(tr("options.text_hint")))),
            (Tool.AREA, page(self.snap, _hint(tr("options.area_hint")))),
            (
                Tool.ZOOM,
                page(
                    text_button(tr("view.actual_size"), self.zoomActual),
                    text_button(tr("view.fit_width"), self.zoomWidth),
                    text_button(tr("view.fit_page"), self.zoomPage),
                    _hint(tr("options.zoom_hint")),
                ),
            ),
        ):
            self.pages[tool] = self.stack.addWidget(w)

        preview_btn = QToolButton()
        preview_btn.setDefaultAction(preview)
        preview_btn.setIconSize(QSize(18, 18))
        preview_btn.setToolButtonStyle(preview_btn.toolButtonStyle().ToolButtonTextBesideIcon)
        export_btn = QPushButton(tr("action.export_short"))
        export_btn.setProperty("primary", True)
        export_btn.setIcon(theme.icon("file-output", 16, theme.T.accent_text))
        export_btn.setToolTip(export.toolTip())
        export_btn.clicked.connect(export.trigger)
        export.changed.connect(lambda: export_btn.setEnabled(export.isEnabled()))
        export_btn.setEnabled(export.isEnabled())

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.icon)
        lay.addWidget(self.name)
        sep = QLabel()
        sep.setFixedSize(1, 18)
        sep.setStyleSheet(f"background: {theme.T.line_soft};")
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)
        lay.addWidget(self.stack, 1)
        lay.addWidget(preview_btn)
        lay.addWidget(export_btn)

    def set_tool(self, tool: Tool) -> None:
        self.icon.setPixmap(theme.pixmap(TOOL_ICONS[tool], theme.T.text, 18))
        self.name.setText(tr(TOOL_NAMES[tool]))
        self.stack.setCurrentIndex(self.pages[tool])
