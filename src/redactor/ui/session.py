"""One open document: its marks, selection, undo history and export options."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from redactor.core.document import PdfDocument
from redactor.core.marks import Mark
from redactor.core.redaction import RedactionOptions, default_output_path
from redactor.i18n import tr, tr_n


class Session(QObject):
    marksChanged = Signal()
    selectionChanged = Signal()
    pageTextChanged = Signal(int)
    overlayChanged = Signal()  # hidden overlays / preview toggled

    def __init__(self, doc: PdfDocument, options: RedactionOptions, parent: QObject | None = None):
        super().__init__(parent)
        self.doc = doc
        self.options = options
        self.marks: dict[str, Mark] = {}
        self.selected: set[str] = set()
        self.hidden: set[str] = set()  # overlays hidden on the canvas (still redacted)
        self.preview = False
        self.undo = QUndoStack(self)
        self.project_path: Path | None = None
        self.export_path: Path = default_output_path(doc.path)
        self.include_text_in_project = False

    # ---------------------------------------------------------------- queries
    @property
    def title(self) -> str:
        return self.doc.path.name

    @property
    def dirty(self) -> bool:
        return not self.undo.isClean()

    def marks_on(self, page: int) -> list[Mark]:
        return [m for m in self.marks.values() if m.page == page]

    def ordered(self) -> list[Mark]:
        return sorted(self.marks.values(), key=lambda m: (m.page, m.bounds()[1], m.bounds()[0]))

    def pages_with_marks(self) -> set[int]:
        return {m.page for m in self.marks.values()}

    # ---------------------------------------------------------------- edits
    def add(self, marks: Iterable[Mark], text: str | None = None) -> None:
        marks = list(marks)
        if marks:
            self.undo.push(_Add(self, marks, text or tr_n("undo.add", len(marks))))

    def remove(self, ids: Iterable[str], text: str | None = None) -> None:
        marks = [self.marks[i] for i in ids if i in self.marks]
        if marks:
            self.undo.push(_Remove(self, marks, text or tr_n("undo.remove", len(marks))))

    def replace(self, new: Iterable[Mark], text: str | None = None, merge_id: int = -1) -> None:
        new = [m for m in new if m.id in self.marks]
        if new:
            old = [self.marks[m.id] for m in new]
            self.undo.push(_Replace(self, old, new, text or tr("undo.edit"), merge_id))

    # internal, used by commands only
    def _insert(self, marks: list[Mark]) -> None:
        for m in marks:
            self.marks[m.id] = m
        self.marksChanged.emit()

    def _delete(self, marks: list[Mark]) -> None:
        for m in marks:
            self.marks.pop(m.id, None)
            self.hidden.discard(m.id)
        if self.selected & {m.id for m in marks}:
            self.selected -= {m.id for m in marks}
            self.selectionChanged.emit()
        self.marksChanged.emit()

    # ---------------------------------------------------------------- selection
    def select(self, ids: Iterable[str], *, add: bool = False) -> None:
        ids = {i for i in ids if i in self.marks}
        new = (self.selected | ids) if add else ids
        if new != self.selected:
            self.selected = new
            self.selectionChanged.emit()

    def toggle_selected(self, mark_id: str) -> None:
        self.select(self.selected ^ {mark_id})

    def selected_marks(self) -> list[Mark]:
        return [self.marks[i] for i in self.selected if i in self.marks]

    # ---------------------------------------------------------------- overlays
    def set_hidden(self, mark_id: str, hidden: bool) -> None:
        (self.hidden.add if hidden else self.hidden.discard)(mark_id)
        self.overlayChanged.emit()

    def set_preview(self, on: bool) -> None:
        self.preview = on
        self.overlayChanged.emit()


class _Add(QUndoCommand):
    def __init__(self, s: Session, marks: list[Mark], text: str):
        super().__init__(text)
        self.s, self.marks = s, marks

    def redo(self) -> None:
        self.s._insert(self.marks)

    def undo(self) -> None:
        self.s._delete(self.marks)


class _Remove(_Add):
    def redo(self) -> None:
        self.s._delete(self.marks)

    def undo(self) -> None:
        self.s._insert(self.marks)


class _Replace(QUndoCommand):
    def __init__(self, s: Session, old: list[Mark], new: list[Mark], text: str, merge_id: int):
        super().__init__(text)
        self.s, self.old, self.new, self._id = s, old, new, merge_id

    def id(self) -> int:  # noqa: A003 - Qt API
        return self._id

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802 - Qt API
        if not isinstance(other, _Replace) or {m.id for m in other.new} != {m.id for m in self.new}:
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        self.s._insert(self.new)

    def undo(self) -> None:
        self.s._insert(self.old)
