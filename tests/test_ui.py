from __future__ import annotations

import pytest
from conftest import PESEL, SECRET
from PySide6.QtCore import QPoint, QSettings, Qt

from redactor.core.marks import MarkKind
from redactor.ui.canvas import Tool


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    # no modal dialog may ever block a test run
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    for name in ("warning", "information", "critical", "question"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Open))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    from redactor.app import create_app
    from redactor.ui.main_window import MainWindow

    _app, settings = create_app(["redactor"])
    settings.clear()
    win = MainWindow(settings)
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    yield win
    for c in win._canvases():
        c.session.undo.setClean()
    win.close()


def test_open_search_accept_undo(window, sample_pdf, qtbot):
    s = window.open_path(sample_pdf)
    assert s is not None and window.session is s
    panel = window.search_panel
    panel.query.setText(SECRET)
    panel.search_query()
    assert len(panel.candidates) == 2
    panel.results.setFocus()
    qtbot.keyClick(panel.results, Qt.Key.Key_Return)  # accept first
    assert len(s.marks) == 1 and len(panel.candidates) == 1
    qtbot.keyClick(panel.results, Qt.Key.Key_Delete)  # skip second
    assert len(s.marks) == 1 and not panel.candidates
    s.undo.undo()
    assert not s.marks
    s.undo.redo()
    assert len(s.marks) == 1


def test_patterns_and_rectangle_tool(window, sample_pdf, qtbot):
    s = window.open_path(sample_pdf)
    window.search_panel.search_patterns()
    window.search_panel.accept_all()
    assert any(m.text == PESEL for m in s.marks.values())

    window._set_tool(Tool.AREA)
    c = window.canvas
    qtbot.wait(50)  # let the initial fit-to-width happen first
    c.set_zoom(1.0)
    c.go_to_page(0)
    qtbot.wait(50)
    origin = c.mapFromScene(c.pages[0].pos())
    start = origin + QPoint(100, 400)
    end = origin + QPoint(220, 460)
    qtbot.mousePress(c.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(c.viewport(), end)
    qtbot.mouseRelease(c.viewport(), Qt.MouseButton.LeftButton, pos=end)
    areas = [m for m in s.marks.values() if m.kind == MarkKind.AREA]
    assert len(areas) == 1
    (x0, y0, x1, y1), = areas[0].rects
    assert abs((x1 - x0) - 120) < 2 and abs((y1 - y0) - 60) < 2

    c.setFocus()
    qtbot.keyClick(c, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    moved = s.marks[areas[0].id].rects[0]
    assert abs(moved[0] - (x0 + 10)) < 0.01
    qtbot.keyClick(c, Qt.Key.Key_Delete)
    assert areas[0].id not in s.marks


def test_text_selection_tool(window, sample_pdf, qtbot):
    s = window.open_path(sample_pdf)
    window._set_tool(Tool.TEXT)
    c = window.canvas
    qtbot.wait(50)
    c.set_zoom(1.0)
    c.go_to_page(0)
    qtbot.wait(50)
    line = s.doc.text(0).lines[0]  # "Klient: Jan Kowalski"
    box_a = line.boxes[line.text.index("Jan")]
    box_b = line.boxes[len(line.text) - 1]
    origin = c.mapFromScene(c.pages[0].pos())
    a = origin + QPoint(int(box_a[0] + 1), int((box_a[1] + box_a[3]) / 2))
    b = origin + QPoint(int(box_b[2] - 1), int((box_b[1] + box_b[3]) / 2))
    qtbot.mousePress(c.viewport(), Qt.MouseButton.LeftButton, pos=a)
    qtbot.mouseMove(c.viewport(), b)
    qtbot.mouseRelease(c.viewport(), Qt.MouseButton.LeftButton, pos=b)
    texts = [m.text for m in s.marks.values()]
    assert texts == [SECRET]


def test_project_roundtrip_in_ui(window, sample_pdf, tmp_path):
    from redactor.core import project as proj

    s = window.open_path(sample_pdf)
    window.search_panel.search_patterns()
    window.search_panel.accept_all()
    n = len(s.marks)
    s.project_path = tmp_path / "p.redactor.json"
    assert window.save_project()
    assert not s.dirty
    window.close_current()
    assert window.session is None
    s2 = window.open_path(tmp_path / "p.redactor.json")
    assert len(s2.marks) == n
    assert proj.load(tmp_path / "p.redactor.json").marks[0].text == ""


def test_background_ocr_makes_scan_searchable(window, sample_pdf, qtbot):
    from conftest import SCAN_WORD

    from redactor.core import ocr

    if not ocr.available():
        pytest.skip("no tessdata")
    s = window.open_path(sample_pdf)
    assert s.doc.needs_ocr(1)
    window.ocr_pages("scans")
    assert window.ocr_job is not None
    qtbot.waitUntil(lambda: window.ocr_job is None, timeout=60000)
    assert s.doc.has_ocr(1)
    panel = window.search_panel
    panel.query.setText(SCAN_WORD)
    panel.search_query()
    assert [c.page for c in panel.candidates] == [1]
