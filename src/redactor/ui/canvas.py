"""The document canvas: pages on a dark pasteboard, mark overlays and the tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from redactor.core.document import PDF_LOCK
from redactor.core.marks import Mark, MarkKind, Rect, hex_to_rgb, normalize_rect
from redactor.core.redaction import label_color
from redactor.core.textops import CharPos, char_at, select_range, text_in_rect
from redactor.i18n import tr
from redactor.ui import theme
from redactor.ui.session import Session

GAP = 18.0  # points between pages
MARGIN = 36.0  # points around the stack
MIN_ZOOM, MAX_ZOOM = 0.1, 8.0
MAX_RENDER_SCALE = 6.0  # pixels per point
HANDLE = 7.0  # handle size in device pixels
NUDGE_MERGE_ID = 0x4E55


class Tool(StrEnum):
    HAND = "hand"
    TEXT = "text"
    AREA = "area"
    ZOOM = "zoom"


class Drag(Enum):
    NONE = 0
    TEXT = 1
    MARQUEE = 2
    MOVE = 3
    RESIZE = 4
    RUBBER = 5  # select marks with a rectangle


@dataclass
class _DragState:
    kind: Drag = Drag.NONE
    page: int = -1
    start: QPointF = field(default_factory=QPointF)  # scene
    current: QPointF = field(default_factory=QPointF)
    anchor: CharPos | None = None
    head: CharPos | None = None
    handle: int = -1  # 0..7 clockwise from top-left
    originals: dict[str, Mark] | None = None
    moved: bool = False


def _qrect(r: Rect | pymupdf.Rect) -> QRectF:
    x0, y0, x1, y1 = tuple(r)
    return QRectF(QPointF(x0, y0), QPointF(x1, y1))


def tool_cursor(name: str, hotspot: tuple[int, int] = (9, 9)) -> QCursor:
    """Icon cursor with a dark halo, legible on both white paper and the dark pasteboard."""
    size = 22
    halo = theme.pixmap(name, "#000000", size)
    fg = theme.pixmap(name, "#ffffff", size)
    pm = QPixmap(halo.size())
    pm.setDevicePixelRatio(halo.devicePixelRatio())
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawPixmap(QPointF(dx, dy), halo)
    p.drawPixmap(0, 0, fg)
    p.end()
    return QCursor(pm, *hotspot)


class PageItem(QGraphicsItem):
    def __init__(self, canvas: Canvas, index: int, w: float, h: float):
        super().__init__()
        self.canvas = canvas
        self.index = index
        self.w, self.h = w, h
        self.image: QImage | None = None
        self.image_scale = 0.0
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-8, -4, self.w + 16, self.h + 16)

    def page_rect(self) -> QRectF:
        return QRectF(0, 0, self.w, self.h)

    def paint(self, p: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        lod = option.levelOfDetailFromTransform(p.worldTransform())
        # soft shadow: six device-pixel layers, slightly offset downwards
        p.setPen(Qt.PenStyle.NoPen)
        unit = 1.0 / max(lod, 0.01)
        for i in range(6, 0, -1):
            p.setBrush(theme.qcolor(theme.T.page_shadow, 0.07))
            d = i * unit
            p.drawRoundedRect(QRectF(-d, -d * 0.4, self.w + 2 * d, self.h + d * 1.8), d, d)
        p.setBrush(QColor("#ffffff"))
        p.drawRect(self.page_rect())

        needed = min(lod * self.canvas.devicePixelRatioF(), MAX_RENDER_SCALE)
        if self.image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self.page_rect(), self.image)
        if self.image is None or abs(self.image_scale - needed) / needed > 0.08:
            self.canvas.request_render(self.index, needed)
        self.canvas.paint_overlays(p, self.index, lod)


class Canvas(QGraphicsView):
    zoomChanged = Signal(float)
    currentPageChanged = Signal(int)
    hint = Signal(str)
    markActivated = Signal(str)  # double-click on a mark

    def __init__(self, session: Session, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("canvas")
        self.session = session
        self.tool = Tool.TEXT
        self.words = True
        self.snap = True
        self.candidates: list[Mark] = []
        self.current_candidate: str | None = None
        self._drag = _DragState()
        self._override: dict[str, tuple[Rect, ...]] = {}
        self._hover: str | None = None
        self._space = False
        self._current_page = 0
        self._pending: dict[int, float] = {}
        self._render_timer = QTimer(self, singleShot=True, interval=0, timeout=self._render_pending)

        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(QColor(theme.T.pasteboard))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self.pages: list[PageItem] = []
        self._origins: list[QPointF] = []
        self._layout()
        self.verticalScrollBar().valueChanged.connect(self._track_page)

        session.marksChanged.connect(self._repaint)
        session.selectionChanged.connect(self._repaint)
        session.overlayChanged.connect(self._repaint)
        session.pageTextChanged.connect(lambda _i: self._repaint())
        self.set_tool(Tool.TEXT)

    # ------------------------------------------------------------ layout & geometry
    def _layout(self) -> None:
        doc = self.session.doc
        sizes = [doc.display_size(i) for i in range(doc.page_count)]
        width = max(w for w, _ in sizes)
        y = MARGIN
        for i, (w, h) in enumerate(sizes):
            item = PageItem(self, i, w, h)
            origin = QPointF(MARGIN + (width - w) / 2, y)
            item.setPos(origin)
            self.scene().addItem(item)
            self.pages.append(item)
            self._origins.append(origin)
            y += h + GAP
        self.scene().setSceneRect(QRectF(0, 0, width + 2 * MARGIN, y - GAP + MARGIN))

    def page_at(self, scene_pt: QPointF, *, slack: float = 0) -> int | None:
        for item in self.pages:
            if item.page_rect().adjusted(-slack, -slack, slack, slack).contains(scene_pt - item.pos()):
                return item.index
        return None

    def to_page(self, index: int, scene_pt: QPointF) -> tuple[float, float]:
        """Scene point -> unrotated page coordinates."""
        local = scene_pt - self._origins[index]
        pt = pymupdf.Point(local.x(), local.y()) * self.session.doc.derotation_matrix(index)
        return pt.x, pt.y

    def display_rect(self, index: int, r: Rect) -> QRectF:
        """Unrotated page rectangle -> displayed rectangle in page-item coordinates."""
        return _qrect(pymupdf.Rect(r) * self.session.doc.rotation_matrix(index))

    def scene_rect_of(self, mark: Mark) -> QRectF:
        rect = QRectF()
        for r in self._rects(mark):
            rect = rect.united(self.display_rect(mark.page, r))
        return rect.translated(self._origins[mark.page])

    def _to_unrotated(self, index: int, displayed: QRectF) -> Rect:
        r = pymupdf.Rect(displayed.left(), displayed.top(), displayed.right(), displayed.bottom())
        return normalize_rect(tuple(r * self.session.doc.derotation_matrix(index)))  # type: ignore[arg-type]

    # ------------------------------------------------------------ zoom
    @property
    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, z: float, *, anchor_mouse: bool = False) -> None:
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
            if anchor_mouse
            else QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self.setTransform(QTransform.fromScale(z, z))
        self.zoomChanged.emit(z)

    def zoom_by(self, factor: float, *, anchor_mouse: bool = False) -> None:
        self.set_zoom(self.zoom * factor, anchor_mouse=anchor_mouse)

    def fit_width(self) -> None:
        avail = self.viewport().width() - 24
        self.set_zoom(avail / self.scene().sceneRect().width())

    def fit_page(self) -> None:
        item = self.pages[self._current_page]
        vw, vh = self.viewport().width() - 24, self.viewport().height() - 24
        self.set_zoom(min(vw / (item.w + 2 * MARGIN), vh / (item.h + GAP)))
        self.go_to_page(self._current_page)

    def go_to_page(self, index: int) -> None:
        item = self.pages[max(0, min(index, len(self.pages) - 1))]
        top = item.pos() + QPointF(item.w / 2, 0)
        view_h = self.viewport().height() / self.zoom
        self.centerOn(top + QPointF(0, view_h / 2 - GAP))
        self._track_page()

    def scroll_to(self, mark: Mark) -> None:
        rect = self.scene_rect_of(mark)
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        if not visible.contains(rect):
            self.centerOn(rect.center())

    @property
    def current_page(self) -> int:
        return self._current_page

    def _track_page(self) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        best = min(
            self.pages,
            key=lambda it: abs(it.pos().y() + it.h / 2 - center.y()),
        )
        if best.index != self._current_page:
            self._current_page = best.index
            self.currentPageChanged.emit(best.index)

    # ------------------------------------------------------------ rendering
    def request_render(self, index: int, scale: float) -> None:
        self._pending[index] = scale
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _render_pending(self) -> None:
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        pending, self._pending = self._pending, {}
        for index, scale in pending.items():
            item = self.pages[index]
            if not visible.intersects(item.sceneBoundingRect()):
                continue
            if not PDF_LOCK.acquire(blocking=False):  # OCR/export busy: try again shortly
                self._pending[index] = scale
                continue
            try:
                pix = self.session.doc.render(index, scale)
            finally:
                PDF_LOCK.release()
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            item.image = img.copy()
            item.image_scale = scale
            item.update()
        # free memory of pages far from the viewport
        for item in self.pages:
            if item.image is not None and not visible.adjusted(0, -2000, 0, 2000).intersects(
                item.sceneBoundingRect()
            ):
                item.image = None
        if self._pending:
            self._render_timer.start(60)

    def _repaint(self) -> None:
        self.scene().update()

    # ------------------------------------------------------------ overlays
    def _rects(self, mark: Mark) -> tuple[Rect, ...]:
        return self._override.get(mark.id, mark.rects)

    def paint_overlays(self, p: QPainter, index: int, lod: float) -> None:
        t = theme.T
        s = self.session
        px = 1.0 / max(lod, 0.01)  # one device pixel in item units

        for c in self.candidates:
            if c.page != index:
                continue
            current = c.id == self.current_candidate
            pen = QPen(QColor(t.candidate), 2.0 if current else 1.0)
            pen.setCosmetic(True)
            pen.setStyle(Qt.PenStyle.SolidLine if current else Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(theme.qcolor(t.candidate, 0.28 if current else 0.10))
            for r in c.rects:
                p.drawRect(self.display_rect(index, r).adjusted(-px, -px, px, px))

        for m in s.marks_on(index):
            if m.id in s.hidden:
                continue
            rects = [self.display_rect(index, r) for r in self._rects(m)]
            if s.preview:
                self._paint_final(p, m, rects)
            else:
                self._paint_pending(p, m, rects, px)

        for m in s.marks_on(index):
            if m.id in s.selected:
                rects = [self.display_rect(index, r) for r in self._rects(m)]
                pen = QPen(QColor(t.accent), 1.5)
                pen.setCosmetic(True)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                for r in rects:
                    p.drawRect(r.adjusted(-2 * px, -2 * px, 2 * px, 2 * px))
                if m.kind == MarkKind.AREA and len(rects) == 1 and len(s.selected) == 1:
                    self._paint_handles(p, rects[0], px)

        d = self._drag
        if d.kind == Drag.TEXT and d.page == index and d.anchor and d.head:
            rects, _ = select_range(s.doc.text(index), d.anchor, d.head, words=self.words)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(t.accent, 0.35))
            for r in rects:
                p.drawRect(self.display_rect(index, r))

    def _paint_pending(self, p: QPainter, m: Mark, rects: list[QRectF], px: float) -> None:
        t = theme.T
        hot = m.id == self._hover
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(t.pending, 0.16 if hot else 0.10))
        for r in rects:
            p.drawRect(r)
        # diagonal hatch every 4 device pixels, readable even on 10 px high text marks
        hatch = QPen(theme.qcolor(t.pending, 0.75), 1.0)
        hatch.setCosmetic(True)
        p.setPen(hatch)
        step = 4 * px
        for r in rects:
            p.save()
            p.setClipRect(r, Qt.ClipOperation.IntersectClip)
            x = r.left() - r.height()
            while x < r.right():
                p.drawLine(QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()))
                x += step
            p.restore()
        pen = QPen(QColor(t.pending), 1.5 if hot else 1.0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in rects:
            p.drawRect(r)

    def _paint_final(self, p: QPainter, m: Mark, rects: list[QRectF]) -> None:
        opts = self.session.options
        fill = m.color or opts.fill
        label = opts.label if m.label is None else m.label
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fill))
        for r in rects:
            p.drawRect(r)
        if label:
            widest = max(rects, key=lambda r: r.width())
            rgb = label_color(hex_to_rgb(fill))
            p.setPen(QColor.fromRgbF(*rgb))
            f = QFont("Helvetica")
            f.setPointSizeF(max(4.0, min(9.0, widest.height() * 0.7)))
            p.setFont(f)
            p.drawText(widest, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_handles(self, p: QPainter, r: QRectF, px: float) -> None:
        size = HANDLE * px
        pen = QPen(QColor(theme.T.accent), 1.0)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor("#ffffff"))
        for c in self._handle_points(r):
            p.drawRect(QRectF(c.x() - size / 2, c.y() - size / 2, size, size))

    @staticmethod
    def _handle_points(r: QRectF) -> list[QPointF]:
        cx, cy = r.center().x(), r.center().y()
        return [
            r.topLeft(), QPointF(cx, r.top()), r.topRight(), QPointF(r.right(), cy),
            r.bottomRight(), QPointF(cx, r.bottom()), r.bottomLeft(), QPointF(r.left(), cy),
        ]

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:  # noqa: N802
        d = self._drag
        if d.kind not in (Drag.MARQUEE, Drag.RUBBER):
            return
        r = QRectF(d.start, d.current).normalized()
        pen = QPen(QColor(theme.T.accent if d.kind == Drag.RUBBER else theme.T.pending), 1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine if d.kind == Drag.RUBBER else Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.setBrush(theme.qcolor(theme.T.accent if d.kind == Drag.RUBBER else theme.T.pending, 0.12))
        p.drawRect(r)
        if d.kind == Drag.MARQUEE:
            # live dimensions next to the cursor, in millimetres
            mm = 25.4 / 72
            text = tr("canvas.size_mm", w=f"{r.width() * mm:.1f}", h=f"{r.height() * mm:.1f}")
            p.save()
            p.resetTransform()
            pos = self.mapFromScene(d.current) + QPointF(14, 18).toPoint()
            fm = p.fontMetrics()
            box = QRectF(pos.x(), pos.y(), fm.horizontalAdvance(text) + 12, fm.height() + 6)
            p.setPen(QColor(theme.T.line))
            p.setBrush(QColor(theme.T.header))
            p.drawRoundedRect(box, 2, 2)
            p.setPen(QColor(theme.T.text))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
            p.restore()

    # ------------------------------------------------------------ hit testing
    def mark_at(self, scene_pt: QPointF) -> Mark | None:
        index = self.page_at(scene_pt)
        if index is None:
            return None
        local = scene_pt - self._origins[index]
        tol = 3 / self.zoom
        hits = [
            m for m in self.session.marks_on(index)
            if m.id not in self.session.hidden
            and any(
                self.display_rect(index, r).adjusted(-tol, -tol, tol, tol).contains(local)
                for r in self._rects(m)
            )
        ]
        if not hits:
            return None
        # prefer the smallest mark under the cursor
        return min(hits, key=lambda m: self.scene_rect_of(m).width() * self.scene_rect_of(m).height())

    def handle_at(self, scene_pt: QPointF) -> tuple[Mark, int] | None:
        sel = self.session.selected_marks()
        if len(sel) != 1 or sel[0].kind != MarkKind.AREA or len(sel[0].rects) != 1:
            return None
        m = sel[0]
        r = self.display_rect(m.page, self._rects(m)[0]).translated(self._origins[m.page])
        tol = (HANDLE / 2 + 2) / self.zoom
        for i, c in enumerate(self._handle_points(r)):
            if abs(c.x() - scene_pt.x()) <= tol and abs(c.y() - scene_pt.y()) <= tol:
                return m, i
        return None

    # ------------------------------------------------------------ tools
    def set_tool(self, tool: Tool) -> None:
        self.tool = tool
        self._drag = _DragState()
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if tool == Tool.HAND else QGraphicsView.DragMode.NoDrag
        )
        self._update_cursor(None)

    def _update_cursor(self, scene_pt: QPointF | None) -> None:
        if self._space or self.tool == Tool.HAND:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.tool == Tool.ZOOM:
            alt = QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier
            self.viewport().setCursor(tool_cursor("zoom-out" if alt else "zoom-in"))
            return
        shape = Qt.CursorShape.ArrowCursor
        if scene_pt is not None:
            handle = self.handle_at(scene_pt)
            mark = self.mark_at(scene_pt)
            if handle:
                shape = (
                    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
                    Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor,
                )[handle[1] % 4]
            elif mark is not None:
                shape = (
                    Qt.CursorShape.SizeAllCursor
                    if self.tool == Tool.AREA and mark.kind == MarkKind.AREA
                    else Qt.CursorShape.PointingHandCursor
                )
            elif self.page_at(scene_pt) is not None:
                shape = Qt.CursorShape.IBeamCursor if self.tool == Tool.TEXT else Qt.CursorShape.CrossCursor
        self.viewport().setCursor(shape)

    def set_candidates(self, marks: list[Mark], current: str | None) -> None:
        self.candidates = marks
        self.current_candidate = current
        self._repaint()

    # ------------------------------------------------------------ mouse
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or self._space or self.tool == Tool.HAND:
            if self._space:
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            super().mousePressEvent(e)
            return
        self.setFocus()
        pt = self.mapToScene(e.position().toPoint())
        mods = e.modifiers()
        s = self.session

        if self.tool == Tool.ZOOM:
            self.zoom_by(0.8 if mods & Qt.KeyboardModifier.AltModifier else 1.25, anchor_mouse=True)
            return

        if mods & Qt.KeyboardModifier.AltModifier:
            self._drag = _DragState(Drag.RUBBER, -1, pt, pt)
            return

        handle = self.handle_at(pt) if self.tool == Tool.AREA else None
        if handle:
            m, i = handle
            self._drag = _DragState(Drag.RESIZE, m.page, pt, pt, handle=i, originals={m.id: m})
            return

        mark = self.mark_at(pt)
        if mark is not None:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                s.toggle_selected(mark.id)
            elif mark.id not in s.selected:
                s.select([mark.id])
            if self.tool == Tool.AREA and mark.id in s.selected:
                movable = {m.id: m for m in s.selected_marks() if m.kind == MarkKind.AREA}
                if movable:
                    self._drag = _DragState(Drag.MOVE, mark.page, pt, pt, originals=movable)
            return

        index = self.page_at(pt)
        if not mods & Qt.KeyboardModifier.ShiftModifier:
            s.select([])
        if index is None:
            return
        if self.tool == Tool.TEXT:
            pt_text = s.doc.text(index)
            if not pt_text.lines:
                self.hint.emit(tr("hint.scan_needs_ocr") if s.doc.needs_ocr(index) else tr("hint.no_text"))
                return
            pos = char_at(pt_text, *self.to_page(index, pt))
            self._drag = _DragState(Drag.TEXT, index, pt, pt, anchor=pos, head=pos)
        elif self.tool == Tool.AREA:
            self._drag = _DragState(Drag.MARQUEE, index, pt, pt)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        pt = self.mapToScene(e.position().toPoint())
        d = self._drag
        if d.kind == Drag.NONE:
            super().mouseMoveEvent(e)
            if not (e.buttons() & Qt.MouseButton.LeftButton):
                hover = self.mark_at(pt)
                hover_id = hover.id if hover else None
                if hover_id != self._hover:
                    self._hover = hover_id
                    self._repaint()
                self._update_cursor(pt)
            return
        d.current = pt
        d.moved = d.moved or (pt - d.start).manhattanLength() * self.zoom > 3
        if d.kind == Drag.TEXT:
            d.head = char_at(self.session.doc.text(d.page), *self.to_page(d.page, pt))
            self._repaint()
        elif d.kind == Drag.MARQUEE:
            item = self.pages[d.page]
            local = pt - item.pos()
            local.setX(max(0.0, min(item.w, local.x())))
            local.setY(max(0.0, min(item.h, local.y())))
            d.current = local + item.pos()
            self.viewport().update()
        elif d.kind == Drag.RUBBER:
            self.viewport().update()
        elif d.kind in (Drag.MOVE, Drag.RESIZE):
            self._override = self._dragged_rects()
            self._repaint()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        d, self._drag = self._drag, _DragState()
        s = self.session
        if d.kind == Drag.NONE:
            super().mouseReleaseEvent(e)
            self._update_cursor(self.mapToScene(e.position().toPoint()))
            return
        if d.kind == Drag.TEXT and d.anchor and d.head:
            rects, text = select_range(s.doc.text(d.page), d.anchor, d.head, words=self.words)
            if rects and (d.moved or self.words):
                mark = Mark(page=d.page, rects=tuple(rects), kind=MarkKind.TEXT, text=text)
                s.add([mark])
                s.select([mark.id])
        elif d.kind == Drag.MARQUEE and d.moved:
            self._commit_marquee(d)
        elif d.kind == Drag.RUBBER:
            area = QRectF(d.start, d.current).normalized()
            hit = [m.id for m in s.marks.values() if area.intersects(self.scene_rect_of(m))]
            s.select(hit, add=bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        elif d.kind in (Drag.MOVE, Drag.RESIZE) and d.moved:
            new = self._dragged_rects()
            self._override = {}
            s.replace([s.marks[i].with_rects(r) for i, r in new.items()], tr("undo.move"))
        self._override = {}
        self._repaint()
        self.viewport().update()

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        mark = self.mark_at(self.mapToScene(e.position().toPoint()))
        if mark is not None:
            self.markActivated.emit(mark.id)
        else:
            super().mouseDoubleClickEvent(e)

    def _commit_marquee(self, d: _DragState) -> None:
        s = self.session
        local = QRectF(d.start, d.current).normalized().translated(-self._origins[d.page])
        rect = self._to_unrotated(d.page, local)
        text, chars = text_in_rect(s.doc.text(d.page), rect)
        if self.snap and chars:
            rect = (
                min(rect[0], chars[0]), min(rect[1], chars[1]),
                max(rect[2], chars[2]), max(rect[3], chars[3]),
            )
        mark = Mark(page=d.page, rects=(rect,), kind=MarkKind.AREA, text=text)
        s.add([mark])
        s.select([mark.id])

    def _dragged_rects(self) -> dict[str, tuple[Rect, ...]]:
        d = self._drag
        if not d.originals:
            return {}
        delta = d.current - d.start
        out: dict[str, tuple[Rect, ...]] = {}
        for mid, m in d.originals.items():
            item = self.pages[m.page]
            disp = self.display_rect(m.page, m.rects[0])
            if d.kind == Drag.MOVE:
                dx = max(-disp.left(), min(item.w - disp.right(), delta.x()))
                dy = max(-disp.top(), min(item.h - disp.bottom(), delta.y()))
                moved = [self.display_rect(m.page, r).translated(dx, dy) for r in m.rects]
            else:
                r = QRectF(disp)
                x, y = delta.x(), delta.y()
                h = d.handle
                if h in (0, 6, 7):
                    r.setLeft(r.left() + x)
                if h in (2, 3, 4):
                    r.setRight(r.right() + x)
                if h in (0, 1, 2):
                    r.setTop(r.top() + y)
                if h in (4, 5, 6):
                    r.setBottom(r.bottom() + y)
                moved = [r.normalized().intersected(item.page_rect())]
            out[mid] = tuple(self._to_unrotated(m.page, r) for r in moved)
        return out

    # ------------------------------------------------------------ keyboard & wheel
    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        s = self.session
        key = e.key()
        if key == Qt.Key.Key_Space and not e.isAutoRepeat() and self._drag.kind == Drag.NONE:
            self._space = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._update_cursor(None)
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and s.selected:
            s.remove(list(s.selected))
            return
        if key == Qt.Key.Key_Escape:
            if self._drag.kind != Drag.NONE:
                self._drag = _DragState()
                self._override = {}
                self._repaint()
                self.viewport().update()
            else:
                s.select([])
            return
        arrows = {
            Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
        }
        movable = [m for m in s.selected_marks() if m.kind == MarkKind.AREA]
        if key in arrows and movable:
            step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            dx, dy = (v * step for v in arrows[key])
            new = []
            for m in movable:
                item = self.pages[m.page]
                rects = []
                for r in m.rects:
                    disp = self.display_rect(m.page, r)
                    ddx = max(-disp.left(), min(item.w - disp.right(), dx))
                    ddy = max(-disp.top(), min(item.h - disp.bottom(), dy))
                    rects.append(self._to_unrotated(m.page, disp.translated(ddx, ddy)))
                new.append(m.with_rects(tuple(rects)))
            s.replace(new, tr("undo.nudge"), NUDGE_MERGE_ID)
            return
        if key == Qt.Key.Key_Alt:
            self._update_cursor(None)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat() and self._space:
            self._space = False
            self.set_tool(self.tool)
            return
        if e.key() == Qt.Key.Key_Alt:
            self._update_cursor(None)
        super().keyReleaseEvent(e)

    def wheelEvent(self, e: QWheelEvent) -> None:  # noqa: N802
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = e.angleDelta().y() / 120
            self.zoom_by(1.15**steps, anchor_mouse=True)
            e.accept()
            return
        super().wheelEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        if self._hover:
            self._hover = None
            self._repaint()
        super().leaveEvent(e)
