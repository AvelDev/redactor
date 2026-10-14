"""Background work: OCR and export run off the UI thread (PyMuPDF calls hold PDF_LOCK)."""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from redactor.core import ocr
from redactor.core.document import PageText


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    page = Signal(int, object)


_alive: set[_Relay] = set()


class _Task(QRunnable):
    def __init__(self, fn: Callable[[_Relay], object], relay: _Relay):
        super().__init__()
        self.fn, self.relay = fn, relay

    def run(self) -> None:
        try:
            result = self.fn(self.relay)
        except Exception as e:  # noqa: BLE001 - reported to the UI
            traceback.print_exc()
            self.relay.failed.emit(str(e) or type(e).__name__)
        else:
            self.relay.done.emit(result)


def run(
    fn: Callable[[], object],
    on_done: Callable[[object], None],
    on_error: Callable[[str], None],
) -> None:
    relay = _Relay()
    _alive.add(relay)
    relay.done.connect(on_done)
    relay.failed.connect(on_error)
    relay.done.connect(lambda _r: _alive.discard(relay))
    relay.failed.connect(lambda _e: _alive.discard(relay))
    QThreadPool.globalInstance().start(_Task(lambda _r: fn(), relay))


class OcrJob(QObject):
    """OCR a list of pages one by one; cancellable between pages."""

    progress = Signal(int, int)  # done, total
    pageDone = Signal(int, object)  # index, PageText
    finished = Signal(bool)  # completed (False if cancelled)
    failed = Signal(str)

    def __init__(self, data: bytes, pages: list[int], parent: QObject | None = None):
        super().__init__(parent)
        self.data = data
        self.pages = pages
        self.cancelled = False

    def start(self) -> None:
        relay = _Relay()
        _alive.add(relay)
        relay.progress.connect(self.progress)
        relay.page.connect(self.pageDone)
        relay.done.connect(lambda ok: (self.finished.emit(bool(ok)), _alive.discard(relay)))
        relay.failed.connect(lambda e: (self.failed.emit(e), _alive.discard(relay)))
        QThreadPool.globalInstance().start(_Task(self._work, relay))

    def _work(self, relay: _Relay) -> bool:
        total = len(self.pages)
        for n, index in enumerate(self.pages):
            if self.cancelled:
                return False
            relay.progress.emit(n, total)
            text: PageText = ocr.ocr_page(self.data, index)
            relay.page.emit(index, text)
        relay.progress.emit(total, total)
        return True
