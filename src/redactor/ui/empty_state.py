"""What the pasteboard shows before any document is open."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from redactor.i18n import tr
from redactor.ui import theme


class EmptyState(QWidget):
    openRequested = Signal()
    recentRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self.zone = QFrame()
        self.zone.setObjectName("dropZone")
        self.zone.setFixedWidth(440)
        z = QVBoxLayout(self.zone)
        z.setContentsMargins(32, 30, 32, 28)
        z.setSpacing(10)

        mark = QLabel()
        logo = QPixmap(str(theme.ICON_DIR.parent / "app.png"))
        logo.setDevicePixelRatio(logo.width() / 44)
        mark.setPixmap(logo)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(tr("empty.open_title"))
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(tr("empty.body"))
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        button = QPushButton(tr("empty.open"))
        button.setProperty("primary", True)
        button.setIcon(theme.icon("folder-open", 16, theme.T.accent_text))
        button.clicked.connect(self.openRequested)
        brow = QHBoxLayout()
        brow.addStretch()
        brow.addWidget(button)
        brow.addStretch()
        promise = QLabel(tr("empty.promise"))
        promise.setObjectName("hint")
        promise.setAlignment(Qt.AlignmentFlag.AlignCenter)
        promise.setWordWrap(True)

        z.addWidget(mark)
        z.addWidget(title)
        z.addWidget(body)
        z.addSpacing(6)
        z.addLayout(brow)
        z.addSpacing(6)
        z.addWidget(promise)

        self.recent_box = QWidget()
        self.recent_box.setFixedWidth(440)
        self.recent = QVBoxLayout(self.recent_box)
        self.recent.setContentsMargins(4, 0, 4, 0)
        self.recent.setSpacing(0)

        lay = QVBoxLayout(self)
        lay.addStretch(3)
        lay.addWidget(self.zone, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        lay.addWidget(self.recent_box, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(4)

    def set_recent(self, paths: list[str]) -> None:
        while self.recent.count():
            item = self.recent.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        existing = [p for p in paths if Path(p).exists()][:6]
        if not existing:
            self.recent_box.hide()
            return
        self.recent_box.show()
        head = QLabel(tr("empty.recent"))
        head.setObjectName("sectionTitle")
        self.recent.addWidget(head)
        for p in existing:
            b = QPushButton(Path(p).name)
            b.setObjectName("recent")
            b.setToolTip(p)
            b.setIcon(theme.icon("file-text", 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, path=p: self.recentRequested.emit(path))
            self.recent.addWidget(b)

    def set_hot(self, hot: bool) -> None:
        self.zone.setProperty("hot", hot)
        self.zone.style().unpolish(self.zone)
        self.zone.style().polish(self.zone)
