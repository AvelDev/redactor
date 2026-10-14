"""Dockable panels: marks (the layers of a redaction), search, properties, pages."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from redactor.core.document import PDF_LOCK
from redactor.core.marks import Mark, MarkKind
from redactor.core.patterns import PATTERNS
from redactor.core.textops import scan_patterns, scan_query
from redactor.i18n import tr, tr_n
from redactor.ui import theme
from redactor.ui.session import Session

ID_ROLE = Qt.ItemDataRole.UserRole
GROUP_ROLE = Qt.ItemDataRole.UserRole + 1
MM = 25.4 / 72


def snippet(text: str, limit: int = 42) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def describe(mark: Mark) -> str:
    if mark.text.strip():
        return snippet(mark.text)
    x0, y0, x1, y1 = mark.bounds()
    return tr("marks.area_size", w=f"{(x1 - x0) * MM:.0f}", h=f"{(y1 - y0) * MM:.0f}")


def group_key(mark: Mark) -> str:
    return f"{mark.kind.value}:{mark.group}"


def group_title(mark: Mark) -> str:
    if mark.kind == MarkKind.PATTERN:
        return tr(mark.group)
    if mark.kind == MarkKind.SEARCH:
        return tr("marks.group_search", query=snippet(mark.group, 24))
    if mark.kind == MarkKind.TEXT:
        return tr("marks.group_text")
    return tr("marks.group_area")


KIND_ICON = {
    MarkKind.TEXT: "text-cursor",
    MarkKind.AREA: "square-dashed",
    MarkKind.SEARCH: "search",
    MarkKind.PATTERN: "scan-search",
}


def small_button(icon_name: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setIcon(theme.icon(icon_name, 16))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    return b


def section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


# =================================================================== marks
class MarksPanel(QWidget):
    focusMark = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session: Session | None = None
        self._syncing = False

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setIconSize(QSize(16, 16))
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 26)
        self.tree.itemSelectionChanged.connect(self._tree_selection)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(self._activated)
        self.tree.installEventFilter(self)

        self.empty = hint(tr("marks.empty"))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setContentsMargins(16, 24, 16, 24)

        self.count = QLabel()
        self.count.setFont(theme.tabular(self.count.font()))
        self.delete_btn = small_button("trash-2", tr("marks.delete_tip"))
        self.delete_btn.clicked.connect(self.delete_selected)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 4, 4)
        bar.addWidget(self.count)
        bar.addStretch()
        bar.addWidget(self.delete_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.empty, 1)
        lay.addLayout(bar)
        self.set_session(None)

    def set_session(self, session: Session | None) -> None:
        if self.session is not None:
            for sig, slot in self._connections():
                sig.disconnect(slot)
        self.session = session
        if session is not None:
            for sig, slot in self._connections():
                sig.connect(slot)
        self.rebuild()

    def _connections(self) -> list[tuple]:
        s = self.session
        return [
            (s.marksChanged, self.rebuild),
            (s.selectionChanged, self._sync_from_session),
            (s.overlayChanged, self._refresh_eyes),
        ]

    def rebuild(self) -> None:
        s = self.session
        expanded = {
            self.tree.topLevelItem(i).data(0, GROUP_ROLE)
            for i in range(self.tree.topLevelItemCount())
            if self.tree.topLevelItem(i).isExpanded()
        }
        known = {
            self.tree.topLevelItem(i).data(0, GROUP_ROLE) for i in range(self.tree.topLevelItemCount())
        }
        self._syncing = True
        self.tree.clear()
        marks = s.ordered() if s else []
        groups: dict[str, QTreeWidgetItem] = {}
        for m in marks:
            key = group_key(m)
            if key not in groups:
                g = QTreeWidgetItem([group_title(m), "", ""])
                g.setData(0, GROUP_ROLE, key)
                g.setIcon(0, theme.icon(KIND_ICON[m.kind], 16))
                g.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tree.addTopLevelItem(g)
                groups[key] = g
            item = QTreeWidgetItem([describe(m), tr("marks.page_short", page=m.page + 1), ""])
            item.setData(0, ID_ROLE, m.id)
            item.setToolTip(0, m.text or describe(m))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setFont(1, theme.tabular(item.font(1)))
            groups[key].addChild(item)
        for key, g in groups.items():
            g.setText(1, str(g.childCount()))
            g.setFont(1, theme.tabular(g.font(1)))
            g.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            g.setExpanded(key in expanded or key not in known)
        self._syncing = False
        self._refresh_eyes()
        self._sync_from_session()
        has = bool(marks)
        self.tree.setVisible(has)
        self.empty.setVisible(not has)
        self.count.setText(tr_n("marks.count", len(marks)))
        self.delete_btn.setEnabled(bool(s and s.selected))

    def _children(self):
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                yield g.child(j)

    def _refresh_eyes(self) -> None:
        s = self.session
        if s is None:
            return
        on, off = theme.icon("eye", 16), theme.icon("eye-off", 16)
        for item in self._children():
            hidden = item.data(0, ID_ROLE) in s.hidden
            item.setIcon(2, off if hidden else on)
            item.setToolTip(2, tr("marks.eye_tip"))

    def _sync_from_session(self) -> None:
        s = self.session
        if s is None or self._syncing:
            return
        self._syncing = True
        self.tree.clearSelection()
        first = None
        for item in self._children():
            if item.data(0, ID_ROLE) in s.selected:
                item.setSelected(True)
                first = first or item
        if first is not None:
            self.tree.scrollToItem(first)
        self._syncing = False
        self.delete_btn.setEnabled(bool(s.selected))

    def _selected_ids(self) -> list[str]:
        ids: list[str] = []
        for item in self.tree.selectedItems():
            if item.data(0, ID_ROLE):
                ids.append(item.data(0, ID_ROLE))
            else:  # a group header selects all of its marks
                ids += [item.child(j).data(0, ID_ROLE) for j in range(item.childCount())]
        return ids

    def _tree_selection(self) -> None:
        if self._syncing or self.session is None:
            return
        self._syncing = True
        self.session.select(self._selected_ids())
        self._syncing = False
        current = self.tree.currentItem()
        if current is not None and current.data(0, ID_ROLE):
            self.focusMark.emit(current.data(0, ID_ROLE))
        self.delete_btn.setEnabled(bool(self.session.selected))

    def _clicked(self, item: QTreeWidgetItem, column: int) -> None:
        mid = item.data(0, ID_ROLE)
        if column == 2 and mid and self.session:
            self.session.set_hidden(mid, mid not in self.session.hidden)

    def _activated(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, ID_ROLE):
            self.focusMark.emit(item.data(0, ID_ROLE))

    def delete_selected(self) -> None:
        if self.session:
            self.session.remove(self._selected_ids() or list(self.session.selected))

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if obj is self.tree and isinstance(e, QKeyEvent) and e.type() == QKeyEvent.Type.KeyPress:
            if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected()
                return True
        return super().eventFilter(obj, e)


# =================================================================== search
class SearchPanel(QWidget):
    candidatesChanged = Signal(list, object)  # list[Mark], current id
    ocrRequested = Signal()

    def __init__(self, current_page: Callable[[], int], parent: QWidget | None = None):
        super().__init__(parent)
        self.session: Session | None = None
        self.current_page = current_page
        self.candidates: list[Mark] = []

        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("search.placeholder"))
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.search_query)
        self.query.textChanged.connect(lambda: self.query.setProperty("invalid", False))
        self.case = small_button("case-sensitive", tr("search.case_tip"))
        self.case.setCheckable(True)
        self.regex = small_button("regex", tr("search.regex_tip"))
        self.regex.setCheckable(True)
        go = QPushButton(tr("search.find"))
        go.clicked.connect(self.search_query)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self.query, 1)
        row.addWidget(self.case)
        row.addWidget(self.regex)
        row.addWidget(go)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self.pattern_boxes: dict[str, QCheckBox] = {}
        for i, p in enumerate(PATTERNS):
            box = QCheckBox(tr(p.key))
            box.setChecked(p.key not in ("pattern.postal_code",))
            self.pattern_boxes[p.key] = box
            grid.addWidget(box, i // 2, i % 2)
        find_patterns = QPushButton(tr("search.find_patterns"))
        find_patterns.clicked.connect(self.search_patterns)

        self.scope = QComboBox()
        self.scope.addItem(tr("search.scope_all"))
        self.scope.addItem(tr("search.scope_page"))

        self.ocr_note = QWidget()
        note = QHBoxLayout(self.ocr_note)
        note.setContentsMargins(0, 0, 0, 0)
        self.ocr_label = hint("")
        ocr_btn = QPushButton(tr("search.run_ocr"))
        ocr_btn.clicked.connect(self.ocrRequested)
        note.addWidget(self.ocr_label, 1)
        note.addWidget(ocr_btn)
        self.ocr_note.hide()

        self.results = QTreeWidget()
        self.results.setHeaderHidden(True)
        self.results.setColumnCount(2)
        self.results.setRootIsDecorated(True)
        self.results.setIndentation(14)
        self.results.header().setStretchLastSection(False)
        self.results.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results.currentItemChanged.connect(self._current_changed)
        self.results.itemDoubleClicked.connect(lambda *_: self.accept_current())
        self.results.installEventFilter(self)

        self.summary = QLabel()
        self.summary.setFont(theme.tabular(self.summary.font()))
        self.accept_all_btn = QPushButton()
        self.accept_all_btn.setProperty("primary", True)
        self.accept_all_btn.clicked.connect(self.accept_all)
        clear = QPushButton(tr("search.clear"))
        clear.setProperty("flat", True)
        clear.clicked.connect(self.clear)

        foot = QHBoxLayout()
        foot.addWidget(self.summary, 1)
        foot.addWidget(clear)
        foot.addWidget(self.accept_all_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(section(tr("search.phrase")))
        lay.addLayout(row)
        lay.addSpacing(4)
        lay.addWidget(section(tr("search.patterns")))
        lay.addLayout(grid)
        pat_row = QHBoxLayout()
        pat_row.addWidget(QLabel(tr("search.scope")))
        pat_row.addWidget(self.scope, 1)
        pat_row.addWidget(find_patterns)
        lay.addLayout(pat_row)
        lay.addWidget(self.ocr_note)
        lay.addSpacing(4)
        lay.addWidget(section(tr("search.results")))
        lay.addWidget(self.results, 1)
        lay.addWidget(hint(tr("search.keys_hint")))
        lay.addLayout(foot)
        self._refresh()

    def set_session(self, session: Session | None) -> None:
        if self.session is not None:
            self.session.marksChanged.disconnect(self._prune)
        self.session = session
        if session is not None:
            session.marksChanged.connect(self._prune)
        self.clear()

    def focus_query(self) -> None:
        self.query.setFocus()
        self.query.selectAll()

    # ------------------------------------------------------------ searching
    def _pages(self) -> list[int]:
        s = self.session
        if s is None:
            return []
        if self.scope.currentIndex() == 1:
            return [self.current_page()]
        return list(range(s.doc.page_count))

    def search_query(self) -> None:
        s = self.session
        q = self.query.text()
        if s is None or not q:
            return
        try:
            found = scan_query(
                s.doc, self._pages(), q, regex=self.regex.isChecked(), case_sensitive=self.case.isChecked()
            )
        except Exception:  # noqa: BLE001 - invalid regular expression
            self.query.setProperty("invalid", True)
            self.query.style().unpolish(self.query)
            self.query.style().polish(self.query)
            self.summary.setText(tr("search.bad_regex"))
            return
        self._set_candidates(found)

    def search_patterns(self) -> None:
        s = self.session
        keys = [k for k, b in self.pattern_boxes.items() if b.isChecked()]
        if s is None or not keys:
            return
        self._set_candidates(scan_patterns(s.doc, self._pages(), keys))

    def _set_candidates(self, found: list[Mark]) -> None:
        s = self.session
        assert s is not None
        existing = list(s.marks.values())
        fresh = [c for c in found if not any(_covers(m, c) for m in existing)]
        seen = {(c.page, c.rects) for c in self.candidates}
        self.candidates += [c for c in fresh if (c.page, c.rects) not in seen]
        scans = [i for i in self._pages() if s.doc.needs_ocr(i)]
        self.ocr_label.setText(tr_n("search.scans_note", len(scans)))
        self.ocr_note.setVisible(bool(scans))
        self._rebuild()
        if not found:
            self.summary.setText(tr("search.nothing"))
        if self.candidates:
            self.results.setFocus()

    # ------------------------------------------------------------ results
    def _rebuild(self, select: str | None = None) -> None:
        self.results.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        target = None
        for c in sorted(self.candidates, key=lambda c: (c.group, c.page, c.rects[0][1])):
            if c.group not in groups:
                title = tr(c.group) if c.kind == MarkKind.PATTERN else f"„{snippet(c.group, 24)}”"
                g = QTreeWidgetItem([title, ""])
                g.setIcon(0, theme.icon(KIND_ICON[c.kind], 16))
                g.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.results.addTopLevelItem(g)
                groups[c.group] = g
                g.setExpanded(True)
            item = QTreeWidgetItem([snippet(c.text), tr("marks.page_short", page=c.page + 1)])
            item.setData(0, ID_ROLE, c.id)
            item.setFont(1, theme.tabular(item.font(1)))
            groups[c.group].addChild(item)
            if target is None or c.id == select:
                target = item
        for g in groups.values():
            g.setText(1, str(g.childCount()))
        if target is not None:
            self.results.setCurrentItem(target)
        self._refresh()

    def _refresh(self) -> None:
        n = len(self.candidates)
        self.summary.setText(tr_n("search.found", n) if n else "")
        self.accept_all_btn.setText(tr_n("search.accept_all", n))
        self.accept_all_btn.setEnabled(n > 0)
        current = self.results.currentItem()
        cid = current.data(0, ID_ROLE) if current else None
        self.candidatesChanged.emit(self.candidates, cid)

    def _current_changed(self, *_args) -> None:
        self._refresh()

    def _take(self, cid: str) -> Mark | None:
        for i, c in enumerate(self.candidates):
            if c.id == cid:
                return self.candidates.pop(i)
        return None

    def _next_id(self, cid: str) -> str | None:
        order = [self.results.topLevelItem(i).child(j).data(0, ID_ROLE)
                 for i in range(self.results.topLevelItemCount())
                 for j in range(self.results.topLevelItem(i).childCount())]
        if cid not in order:
            return None
        idx = order.index(cid)
        rest = order[idx + 1 :] or order[:idx]
        return rest[0] if rest else None

    def accept_current(self) -> None:
        self._consume(accept=True)

    def reject_current(self) -> None:
        self._consume(accept=False)

    def _consume(self, *, accept: bool) -> None:
        item = self.results.currentItem()
        cid = item.data(0, ID_ROLE) if item else None
        if not cid or self.session is None:
            return
        nxt = self._next_id(cid)
        mark = self._take(cid)
        self._rebuild(select=nxt)
        if accept and mark is not None:
            self.session.add([mark])

    def accept_all(self) -> None:
        if self.session is None or not self.candidates:
            return
        marks, self.candidates = self.candidates, []
        self._rebuild()
        self.session.add(marks)

    def clear(self) -> None:
        self.candidates = []
        self.ocr_note.hide()
        self._rebuild()

    def _prune(self) -> None:
        """Drop candidates that became marks some other way."""
        if self.session is None:
            return
        existing = list(self.session.marks.values())
        before = len(self.candidates)
        self.candidates = [c for c in self.candidates if not any(_covers(m, c) for m in existing)]
        if len(self.candidates) != before:
            item = self.results.currentItem()
            self._rebuild(select=item.data(0, ID_ROLE) if item else None)

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if obj is self.results and isinstance(e, QKeyEvent) and e.type() == QKeyEvent.Type.KeyPress:
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept_current()
                return True
            if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.reject_current()
                return True
        return super().eventFilter(obj, e)


def _covers(mark: Mark, cand: Mark) -> bool:
    if mark.page != cand.page:
        return False
    for a in mark.rects:
        for b in cand.rects:
            if a[0] <= b[0] + 0.5 and a[1] <= b[1] + 0.5 and a[2] >= b[2] - 0.5 and a[3] >= b[3] - 0.5:
                return True
    return False


# =================================================================== properties
class ColorButton(QPushButton):
    colorChosen = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.color = "#000000"
        self.setFixedSize(46, 24)
        self.clicked.connect(self._pick)

    def set_color(self, color: str) -> None:
        self.color = color
        t = theme.T
        self.setStyleSheet(
            f"QPushButton {{ background: {color}; border: 1px solid {t.line_soft}; border-radius: 2px; }}"
            f"QPushButton:hover {{ border-color: {t.text_dim}; }}"
            f"QPushButton:focus {{ border-color: {t.accent}; }}"
        )

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self, tr("props.pick_color"))
        if c.isValid():
            self.set_color(c.name())
            self.colorChosen.emit(c.name())


class PropertiesPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session: Session | None = None
        self._loading = False

        self.title = section("")
        self.info = hint("")
        self.color = ColorButton()
        self.color.colorChosen.connect(self._color)
        self.label = QLineEdit()
        self.label.setMaxLength(40)
        self.label.editingFinished.connect(self._label)
        self.reset = QPushButton(tr("props.reset"))
        self.reset.setProperty("flat", True)
        self.reset.clicked.connect(self._reset)
        self.note = hint("")

        self.form_box = QWidget()
        form = QFormLayout(self.form_box)
        form.setContentsMargins(0, 4, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        crow = QHBoxLayout()
        crow.addWidget(self.color)
        crow.addStretch()
        crow.addWidget(self.reset)
        form.addRow(tr("props.fill"), crow)
        form.addRow(tr("props.label"), self.label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        lay.addWidget(self.form_box)
        lay.addWidget(self.note)
        lay.addStretch()
        self.set_session(None)

    def set_session(self, session: Session | None) -> None:
        if self.session is not None:
            self.session.selectionChanged.disconnect(self.load)
            self.session.marksChanged.disconnect(self.load)
        self.session = session
        if session is not None:
            session.selectionChanged.connect(self.load)
            session.marksChanged.connect(self.load)
        self.load()

    def load(self) -> None:
        s = self.session
        self._loading = True
        self.form_box.setVisible(s is not None)
        if s is None:
            self.title.setText(tr("props.no_document"))
            self.info.setText("")
            self.note.setText("")
            self._loading = False
            return
        sel = s.selected_marks()
        opts = s.options
        if not sel:
            self.title.setText(tr("props.defaults"))
            self.info.setText(tr("props.defaults_info"))
            self.color.set_color(opts.fill)
            self.label.setText(opts.label)
            self.label.setPlaceholderText(tr("props.no_label"))
            self.reset.hide()
            self.note.setText(tr("props.label_note"))
        else:
            self.title.setText(tr_n("props.selected", len(sel)))
            if len(sel) == 1:
                m = sel[0]
                self.info.setText(tr("props.info", kind=group_title(m), page=m.page + 1))
            else:
                self.info.setText(tr_n("props.pages", len({m.page for m in sel})))
            colors = {m.color or opts.fill for m in sel}
            self.color.set_color(colors.pop() if len(colors) == 1 else opts.fill)
            labels = {opts.label if m.label is None else m.label for m in sel}
            self.label.setText(labels.pop() if len(labels) == 1 else "")
            self.label.setPlaceholderText(tr("props.no_label"))
            self.reset.show()
            self.reset.setEnabled(any(m.color is not None or m.label is not None for m in sel))
            self.note.setText("")
        self._loading = False

    def _color(self, color: str) -> None:
        s = self.session
        if s is None or self._loading:
            return
        sel = s.selected_marks()
        if sel:
            s.replace([_with(m, color=color) for m in sel], tr("undo.color"))
        else:
            s.options.fill = color
            s.overlayChanged.emit()

    def _label(self) -> None:
        s = self.session
        if s is None or self._loading:
            return
        text = self.label.text()
        sel = s.selected_marks()
        if sel:
            if any((s.options.label if m.label is None else m.label) != text for m in sel):
                s.replace([_with(m, label=text) for m in sel], tr("undo.label"))
        elif text != s.options.label:
            s.options.label = text
            s.overlayChanged.emit()

    def _reset(self) -> None:
        s = self.session
        if s and (sel := s.selected_marks()):
            s.replace([_with(m, color=None, label=None) for m in sel], tr("undo.reset_style"))


def _with(m: Mark, **changes) -> Mark:
    from dataclasses import replace

    return replace(m, **changes)


# =================================================================== pages
THUMB_W = 116


class _PageDelegate(QStyledItemDelegate):
    def __init__(self, panel: PagesPanel):
        super().__init__(panel)
        self.panel = panel

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        w, h = self.panel.thumb_size(index.row())
        return QSize(THUMB_W + 24, h + 30)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index) -> None:
        t = theme.T
        row = index.row()
        w, h = self.panel.thumb_size(row)
        r = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        x = r.x() + (r.width() - w) // 2
        y = r.y() + 8
        frame = QRectF(x - 3, y - 3, w + 6, h + 6)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(frame, 3, 3)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.raised))
            p.drawRoundedRect(frame, 3, 3)
        thumb = self.panel.thumbs.get(row)
        target = QRectF(x, y, w, h)
        if thumb is not None:
            p.drawPixmap(target.toRect(), thumb)
        else:
            p.fillRect(target, QColor("#ffffff"))
            self.panel.request(row)
        p.setPen(QColor(t.text if selected else t.text_dim))
        p.setFont(theme.tabular(option.font))
        num_rect = QRectF(r.x(), y + h + 4, r.width(), 16)
        p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, str(row + 1))
        s = self.panel.session
        if s and row in s.pages_with_marks():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.pending))
            p.drawEllipse(QRectF(x + w - 10, y + 4, 7, 7))


class PagesPanel(QListWidget):
    pageClicked = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session: Session | None = None
        self.thumbs: dict[int, QPixmap] = {}
        self._queue: list[int] = []
        self._timer = QTimer(self, singleShot=True, interval=0, timeout=self._render)
        self.setItemDelegate(_PageDelegate(self))
        self.setUniformItemSizes(False)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.currentRowChanged.connect(lambda r: r >= 0 and self.pageClicked.emit(r))

    def set_session(self, session: Session | None) -> None:
        if self.session is not None:
            self.session.marksChanged.disconnect(self.viewport().update)
        self.session = session
        self.thumbs.clear()
        self._queue.clear()
        self.blockSignals(True)
        self.clear()
        if session is not None:
            session.marksChanged.connect(self.viewport().update)
            for _ in range(session.doc.page_count):
                QListWidgetItem(self)
        self.blockSignals(False)

    def thumb_size(self, row: int) -> tuple[int, int]:
        if self.session is None:
            return THUMB_W, THUMB_W
        w, h = self.session.doc.display_size(row)
        return THUMB_W, max(20, round(THUMB_W * h / w))

    def set_current(self, page: int) -> None:
        self.blockSignals(True)
        self.setCurrentRow(page)
        self.blockSignals(False)
        self.scrollToItem(self.item(page))

    def request(self, row: int) -> None:
        if row not in self._queue:
            self._queue.append(row)
        if not self._timer.isActive():
            self._timer.start()

    def _render(self) -> None:
        if self.session is None:
            return
        while self._queue:
            row = self._queue[0]
            if not PDF_LOCK.acquire(blocking=False):
                self._timer.start(120)
                return
            try:
                w, _ = self.session.doc.display_size(row)
                pix = self.session.doc.render(row, THUMB_W * self.devicePixelRatioF() / w)
            finally:
                PDF_LOCK.release()
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            pm = QPixmap.fromImage(img.copy())
            pm.setDevicePixelRatio(self.devicePixelRatioF())
            self.thumbs[row] = pm
            self._queue.pop(0)
            self.viewport().update()
            break
        if self._queue:
            self._timer.start(0)
