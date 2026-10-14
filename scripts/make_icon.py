"""Render the application icon (packaging/icon.png, 1024 px)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "icon.png"


def main() -> int:
    """Graphite tile, a white sheet, text lines, two of them blacked out."""
    _app = QGuiApplication(sys.argv)
    size = 1024
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QRectF(64, 64, size - 128, size - 128)
    path = QPainterPath()
    path.addRoundedRect(tile, 190, 190)
    grad = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    grad.setColorAt(0, QColor("#3a3a3e"))
    grad.setColorAt(1, QColor("#1f1f22"))
    p.fillPath(path, grad)

    sheet = QRectF(262, 196, 500, 632)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 90))
    p.drawRoundedRect(sheet.translated(0, 14), 26, 26)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(sheet, 26, 26)

    x0, width, h = sheet.left() + 64, sheet.width() - 128, 34
    rows = [(1.0, "#c9c9ce"), (0.82, "#111113"), (0.92, "#c9c9ce"), (0.66, "#c9c9ce"),
            (0.88, "#111113"), (0.74, "#c9c9ce")]
    y = sheet.top() + 88
    for frac, color in rows:
        p.setBrush(QColor(color))
        bar = QRectF(x0, y, width * frac, h if color == "#111113" else h * 0.62)
        if color != "#111113":
            bar.translate(0, h * 0.19)
        p.drawRoundedRect(bar, 6, 6)
        y += 78
    p.end()
    OUT.parent.mkdir(exist_ok=True)
    img.save(str(OUT))
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
