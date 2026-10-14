"""Main window: tool strip, options bar, document tabs, docked panels, status bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from redactor import __version__
from redactor.core import ocr
from redactor.core import project as proj
from redactor.core.document import PdfDocument
from redactor.core.redaction import RedactionOptions
from redactor.i18n import LANGUAGES, N_, language, tr, tr_n
from redactor.ui import theme
from redactor.ui.canvas import Canvas, Tool
from redactor.ui.empty_state import EmptyState
from redactor.ui.export_dialog import ExportDialog
from redactor.ui.options_bar import TOOL_ICONS, TOOL_NAMES, OptionsBar
from redactor.ui.panels import MarksPanel, PagesPanel, PropertiesPanel, SearchPanel
from redactor.ui.session import Session
from redactor.ui.workers import OcrJob

MAX_RECENT = 8
TOOL_KEYS = {Tool.HAND: "H", Tool.TEXT: "T", Tool.AREA: "R", Tool.ZOOM: "Z"}


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.ocr_job: OcrJob | None = None
        self.setWindowTitle("Redactor")
        self.setAcceptDrops(True)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        self.setDocumentMode(True)

        self._create_actions()
        self._create_menus()
        self._create_central()
        self._create_toolbars()
        self._create_docks()
        self._create_status()

        self.resize(1440, 900)
        if geo := settings.value("geometry"):
            self.restoreGeometry(geo)
        if state := settings.value("state"):
            self.restoreState(state)
        self._set_tool(Tool(settings.value("tool", Tool.TEXT.value)))
        self._session_changed()

    # ================================================================ setup
    def _action(self, text: str, slot=None, shortcut=None, icon: str | None = None, tip: str | None = None,
                checkable: bool = False) -> QAction:
        a = QAction(text, self)
        if icon:
            a.setIcon(theme.icon(icon))
        if shortcut:
            seqs = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(s) for s in seqs])
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setCheckable(checkable)
        if slot:
            (a.toggled if checkable else a.triggered).connect(slot)
        shown = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        a.setToolTip(f"{tip or text}  ({shown})" if shown else (tip or text))
        a.setStatusTip(tip or "")
        return a

    def _create_actions(self) -> None:
        A = self._action
        self.a_open = A(tr("action.open"), self.open_dialog, QKeySequence.StandardKey.Open, "folder-open")
        self.a_open_project = A(tr("action.open_project"), self.open_project_dialog)
        self.a_save = A(tr("action.save_project"), self.save_project, QKeySequence.StandardKey.Save, "save")
        self.a_save_as = A(tr("action.save_project_as"), lambda: self.save_project(ask=True), "Ctrl+Shift+S")
        self.a_include_text = A(tr("action.include_text"), self._set_include_text, checkable=True,
                                tip=tr("action.include_text_tip"))
        self.a_include_text.setChecked(self.settings.value("include_text", False, bool))
        self.a_export = A(tr("action.export"), self.export, ["Ctrl+Shift+E", "Ctrl+Return"], "file-output",
                          tip=tr("action.export_tip"))
        self.a_close = A(tr("action.close"), self.close_current, QKeySequence.StandardKey.Close)
        self.a_quit = A(tr("action.quit"), self.close, QKeySequence.StandardKey.Quit)

        self.a_delete = A(tr("action.delete"), self.delete_selected, icon="trash-2")
        self.a_select_all = A(tr("action.select_all"), self.select_all_marks, QKeySequence.StandardKey.SelectAll)
        self.a_deselect = A(tr("action.deselect"), lambda: self.session and self.session.select([]), "Ctrl+D")

        self.a_zoom_in = A(tr("view.zoom_in"), lambda: self.canvas and self.canvas.zoom_by(1.25),
                           ["Ctrl++", "Ctrl+="], "zoom-in")
        self.a_zoom_out = A(tr("view.zoom_out"), lambda: self.canvas and self.canvas.zoom_by(0.8), "Ctrl+-",
                            "zoom-out")
        self.a_fit_page = A(tr("view.fit_page"), lambda: self.canvas and self.canvas.fit_page(), "Ctrl+0",
                            "maximize-2")
        self.a_actual = A(tr("view.actual_size"), lambda: self.canvas and self.canvas.set_zoom(1.0), "Ctrl+1")
        self.a_fit_width = A(tr("view.fit_width"), lambda: self.canvas and self.canvas.fit_width(), "Ctrl+2")
        self.a_preview = A(tr("action.preview"), self._toggle_preview, "P", "eye", checkable=True,
                           tip=tr("action.preview_tip"))
        self.a_next_page = A(tr("view.next_page"), lambda: self._step_page(1), "PgDown")
        self.a_prev_page = A(tr("view.prev_page"), lambda: self._step_page(-1), "PgUp")

        self.tool_group = QActionGroup(self)
        self.tool_actions: dict[Tool, QAction] = {}
        for tool in (Tool.HAND, Tool.TEXT, Tool.AREA, Tool.ZOOM):
            a = A(tr(TOOL_NAMES[tool]), lambda _=False, t=tool: self._set_tool(t), TOOL_KEYS[tool],
                  TOOL_ICONS[tool], checkable=False)
            a.setCheckable(True)
            a.setIcon(theme.icon(TOOL_ICONS[tool], theme.TOOL_ICON_SIZE))
            self.tool_group.addAction(a)
            self.tool_actions[tool] = a
        self.a_search = A(tr("tool.search"), self.focus_search, ["S", "Ctrl+F"], "search")
        self.a_search.setIcon(theme.icon("search", theme.TOOL_ICON_SIZE))
        has_ocr = ocr.available()
        self.a_ocr = A(tr("tool.ocr"), self.ocr_current, "O", "scan-text",
                       tip=tr("tool.ocr_tip") if has_ocr else tr("tool.ocr_missing"))
        self.a_ocr.setIcon(theme.icon("scan-text", theme.TOOL_ICON_SIZE))
        self.a_ocr_scans = A(tr("action.ocr_scans"), lambda: self.ocr_pages("scans"))
        self.a_ocr_all = A(tr("action.ocr_all"), lambda: self.ocr_pages("all"))
        self.ocr_available = has_ocr

        self.a_shortcuts = A(tr("action.shortcuts"), self.show_shortcuts, "F1")
        self.a_about = A(tr("action.about"), self.show_about)

    def _create_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu(tr("menu.file"))
        m.addAction(self.a_open)
        self.recent_menu = m.addMenu(tr("menu.recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addAction(self.a_open_project)
        m.addSeparator()
        m.addAction(self.a_save)
        m.addAction(self.a_save_as)
        m.addAction(self.a_include_text)
        m.addSeparator()
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_close)
        m.addAction(self.a_quit)

        m = mb.addMenu(tr("menu.edit"))
        self.undo_action = QAction(tr("action.undo"), self)
        self.undo_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Undo))
        self.undo_action.triggered.connect(lambda: self.session and self.session.undo.undo())
        self.undo_action.setIcon(theme.icon("undo-2"))
        self.redo_action = QAction(tr("action.redo"), self)
        self.redo_action.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.Redo) + [QKeySequence("Ctrl+Y")]
        )
        self.redo_action.triggered.connect(lambda: self.session and self.session.undo.redo())
        self.redo_action.setIcon(theme.icon("redo-2"))
        m.addAction(self.undo_action)
        m.addAction(self.redo_action)
        m.addSeparator()
        m.addAction(self.a_delete)
        m.addAction(self.a_select_all)
        m.addAction(self.a_deselect)

        m = mb.addMenu(tr("menu.view"))
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_fit_page, self.a_fit_width, self.a_actual):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_prev_page)
        m.addAction(self.a_next_page)
        m.addSeparator()
        m.addAction(self.a_preview)
        self.panels_menu = m.addMenu(tr("menu.panels"))
        m.addSeparator()
        theme_menu = m.addMenu(tr("menu.theme"))
        group = QActionGroup(self)
        for key, name in (("dark", tr("theme.dark")), ("light", tr("theme.light"))):
            a = theme_menu.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.settings.value("theme", "dark") == key)
            a.triggered.connect(lambda _=False, k=key: self._set_pref("theme", k))
            group.addAction(a)
        lang_menu = m.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        for code, name in LANGUAGES.items():
            a = lang_menu.addAction(name)
            a.setCheckable(True)
            a.setChecked(code == language())
            a.triggered.connect(lambda _=False, c=code: self._set_pref("language", c))
            group.addAction(a)

        m = mb.addMenu(tr("menu.tools"))
        for a in self.tool_actions.values():
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_search)
        m.addSeparator()
        m.addAction(self.a_ocr)
        m.addAction(self.a_ocr_scans)
        m.addAction(self.a_ocr_all)

        m = mb.addMenu(tr("menu.help"))
        m.addAction(self.a_shortcuts)
        m.addAction(self.a_about)

        # canvas-level single-key shortcuts must not fire while typing in a text field
        for a in [*self.tool_actions.values(), self.a_search, self.a_ocr, self.a_preview]:
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(a)

    def _create_central(self) -> None:
        self.empty = EmptyState()
        self.empty.openRequested.connect(self.open_dialog)
        self.empty.recentRequested.connect(self.open_path)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _i: self._session_changed())
        self.central = QStackedWidget()
        self.central.addWidget(self.empty)
        self.central.addWidget(self.tabs)
        self.setCentralWidget(self.central)
        self.empty.set_recent(self._recent())

    def _create_toolbars(self) -> None:
        tools = QToolBar(tr("toolbar.tools"))
        tools.setObjectName("tools")
        tools.setMovable(False)
        tools.setFloatable(False)
        tools.setIconSize(QSize(theme.TOOL_ICON_SIZE, theme.TOOL_ICON_SIZE))
        tools.setOrientation(Qt.Orientation.Vertical)
        for a in self.tool_actions.values():
            tools.addAction(a)
        tools.addSeparator()
        tools.addAction(self.a_search)
        tools.addAction(self.a_ocr)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tools)

        self.options = OptionsBar(self.a_preview, self.a_export)
        self.options.words.setChecked(self.settings.value("words", True, bool))
        self.options.snap.setChecked(self.settings.value("snap", True, bool))
        self.options.wordsToggled.connect(lambda v: self._canvas_opt("words", v))
        self.options.snapToggled.connect(lambda v: self._canvas_opt("snap", v))
        self.options.zoomActual.connect(self.a_actual.trigger)
        self.options.zoomWidth.connect(self.a_fit_width.trigger)
        self.options.zoomPage.connect(self.a_fit_page.trigger)
        bar = QToolBar(tr("toolbar.options"))
        bar.setObjectName("options")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.addWidget(self.options)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)

    def _dock(self, key: str, widget: QWidget, area=Qt.DockWidgetArea.RightDockWidgetArea) -> QDockWidget:
        d = QDockWidget(tr(key), self)
        d.setObjectName(key)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(area, d)
        self.panels_menu.addAction(d.toggleViewAction())
        return d

    def _create_docks(self) -> None:
        self.props = PropertiesPanel()
        self.marks_panel = MarksPanel()
        self.search_panel = SearchPanel(lambda: self.canvas.current_page if self.canvas else 0)
        self.pages_panel = PagesPanel()
        self.d_props = self._dock(N_("panel.properties"), self.props)
        self.d_marks = self._dock(N_("panel.marks"), self.marks_panel)
        self.d_search = self._dock(N_("panel.search"), self.search_panel)
        self.d_pages = self._dock(N_("panel.pages"), self.pages_panel)
        self.setTabPosition(Qt.DockWidgetArea.RightDockWidgetArea, QTabWidget.TabPosition.North)
        self.tabifyDockWidget(self.d_marks, self.d_search)
        self.tabifyDockWidget(self.d_search, self.d_pages)
        for d in (self.d_marks, self.d_search, self.d_pages):
            d.setTitleBarWidget(QWidget())  # the panel tab already names it
        self.d_marks.raise_()
        self.props.setMinimumHeight(200)
        self.resizeDocks([self.d_props], [330], Qt.Orientation.Horizontal)
        self.resizeDocks([self.d_props, self.d_marks], [210, 600], Qt.Orientation.Vertical)

        self.marks_panel.focusMark.connect(self._focus_mark)
        self.search_panel.candidatesChanged.connect(self._candidates)
        self.search_panel.ocrRequested.connect(lambda: self.ocr_pages("scans"))
        self.pages_panel.pageClicked.connect(lambda i: self.canvas and self.canvas.go_to_page(i))

    def _create_status(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.ocr_box = QWidget()
        ol = QHBoxLayout(self.ocr_box)
        ol.setContentsMargins(0, 0, 6, 0)
        ol.setSpacing(6)
        self.ocr_label = QLabel()
        self.ocr_label.setObjectName("statusFirst")
        self.ocr_progress = QProgressBar()
        self.ocr_progress.setFixedWidth(120)
        cancel = QToolButton()
        cancel.setIcon(theme.icon("x", 14))
        cancel.setToolTip(tr("ocr.cancel"))
        cancel.clicked.connect(self._cancel_ocr)
        ol.addWidget(self.ocr_label)
        ol.addWidget(self.ocr_progress)
        ol.addWidget(cancel)
        self.ocr_box.hide()
        self.page_label = QLabel()
        self.zoom_label = QLabel()
        self.count_label = QLabel()
        self.no_doc_label = QLabel(tr("props.no_document"))
        self.no_doc_label.setObjectName("statusFirst")
        sb.addWidget(self.no_doc_label)
        self.lock_label = QLabel(tr("status.original_locked"))
        self.lock_label.setToolTip(tr("status.original_locked_tip"))
        for w in (self.page_label, self.zoom_label, self.count_label):
            w.setFont(theme.tabular(w.font()))
        sb.addPermanentWidget(self.ocr_box)
        for w in (self.page_label, self.zoom_label, self.count_label, self.lock_label):
            sb.addPermanentWidget(w)

    # ================================================================ session plumbing
    @property
    def canvas(self) -> Canvas | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, Canvas) else None

    @property
    def session(self) -> Session | None:
        c = self.canvas
        return c.session if c else None

    def _canvases(self) -> list[Canvas]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def _session_changed(self) -> None:
        s, c = self.session, self.canvas
        self.central.setCurrentIndex(1 if s else 0)
        self.props.set_session(s)
        self.marks_panel.set_session(s)
        self.search_panel.set_session(s)
        self.pages_panel.set_session(s)
        for cv in self._canvases():
            cv.set_candidates([], None)
        has = s is not None
        for a in (self.a_save, self.a_save_as, self.a_close, self.a_select_all, self.a_deselect,
                  self.a_zoom_in, self.a_zoom_out, self.a_fit_page, self.a_fit_width, self.a_actual,
                  self.a_preview, self.a_next_page, self.a_prev_page, self.a_search):
            a.setEnabled(has)
        for a in (self.a_ocr, self.a_ocr_scans, self.a_ocr_all):
            a.setEnabled(has and self.ocr_available and self.ocr_job is None)
        for a in self.tool_actions.values():
            a.setEnabled(has)
        self.options.stack.setEnabled(has)
        self.a_preview.blockSignals(True)
        self.a_preview.setChecked(bool(s and s.preview))
        self.a_preview.blockSignals(False)
        self.page_label.setVisible(has)
        self.zoom_label.setVisible(has)
        self.count_label.setVisible(has)
        self.lock_label.setVisible(has)
        self.no_doc_label.setVisible(not has)
        if c is not None:
            c.set_tool(self._tool)
            c.words = self.options.words.isChecked()
            c.snap = self.options.snap.isChecked()
            self._page_changed(c.current_page)
            self._zoom_changed(c.zoom)
            c.setFocus()
        self._marks_changed()
        self._update_title()
        self.empty.set_recent(self._recent())

    def _wire(self, s: Session, c: Canvas) -> None:
        s.marksChanged.connect(self._marks_changed)
        s.selectionChanged.connect(self._selection_changed)
        s.undo.cleanChanged.connect(lambda _clean: self._update_title())
        s.undo.indexChanged.connect(lambda _i: self._update_undo())
        c.zoomChanged.connect(self._zoom_changed)
        c.currentPageChanged.connect(self._page_changed)
        c.hint.connect(lambda text: self.statusBar().showMessage(text, 6000))
        c.markActivated.connect(lambda _id: (self.d_props.show(), self.d_props.raise_()))

    def _marks_changed(self) -> None:
        s = self.session
        n = len(s.marks) if s else 0
        self.count_label.setText(tr_n("marks.count", n))
        self.a_export.setEnabled(n > 0)
        self._selection_changed()
        self._update_undo()

    def _selection_changed(self) -> None:
        s = self.session
        self.a_delete.setEnabled(bool(s and s.selected))

    def _update_undo(self) -> None:
        s = self.session
        self.undo_action.setEnabled(bool(s and s.undo.canUndo()))
        self.redo_action.setEnabled(bool(s and s.undo.canRedo()))
        if s:
            self.undo_action.setText(tr("action.undo_named", what=s.undo.undoText()) if s.undo.canUndo()
                                     else tr("action.undo"))
            self.redo_action.setText(tr("action.redo_named", what=s.undo.redoText()) if s.undo.canRedo()
                                     else tr("action.redo"))
        self._update_title()

    def _update_title(self) -> None:
        for i, c in enumerate(self._canvases()):
            s = c.session
            self.tabs.setTabText(i, f"{s.title} @ {round(c.zoom * 100)}%{' *' if s.dirty else ''}")
            self.tabs.setTabToolTip(i, str(s.doc.path))
            self.tabs.setTabIcon(i, theme.icon("lock", 14))
        s = self.session
        self.setWindowTitle(f"{s.title}{' *' if s.dirty else ''} — Redactor" if s else "Redactor")

    def _zoom_changed(self, z: float) -> None:
        self.zoom_label.setText(f"{round(z * 100)}%")
        self._update_title()

    def _page_changed(self, page: int) -> None:
        s = self.session
        if s:
            self.page_label.setText(tr("status.page", page=page + 1, pages=s.doc.page_count))
            self.pages_panel.set_current(page)

    def _focus_mark(self, mark_id: str) -> None:
        s, c = self.session, self.canvas
        if s and c and mark_id in s.marks:
            c.scroll_to(s.marks[mark_id])

    def _candidates(self, marks: list, current) -> None:
        c = self.canvas
        if c is None:
            return
        c.set_candidates(marks, current)
        for m in marks:
            if m.id == current:
                c.scroll_to(m)
                break

    # ================================================================ tools & options
    def _set_tool(self, tool: Tool) -> None:
        self._tool = tool
        self.tool_actions[tool].setChecked(True)
        self.options.set_tool(tool)
        for c in self._canvases():
            c.set_tool(tool)
        self.settings.setValue("tool", tool.value)

    def _canvas_opt(self, name: str, value: bool) -> None:
        self.settings.setValue(name, value)
        for c in self._canvases():
            setattr(c, name, value)

    def _toggle_preview(self, on: bool) -> None:
        if self.session:
            self.session.set_preview(on)

    def _step_page(self, delta: int) -> None:
        if self.canvas:
            self.canvas.go_to_page(self.canvas.current_page + delta)

    def focus_search(self) -> None:
        if self.session:
            self.d_search.show()
            self.d_search.raise_()
            self.search_panel.focus_query()

    def delete_selected(self) -> None:
        if self.session and self.session.selected:
            self.session.remove(list(self.session.selected))

    def select_all_marks(self) -> None:
        if self.session:
            self.session.select(self.session.marks.keys())

    def _set_pref(self, key: str, value: str) -> None:
        if self.settings.value(key) == value:
            return
        self.settings.setValue(key, value)
        QMessageBox.information(self, tr("prefs.restart_title"), tr("prefs.restart_body"))

    def _set_include_text(self, on: bool) -> None:
        self.settings.setValue("include_text", on)

    # ================================================================ files
    def _recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        return [value] if isinstance(value, str) else list(value or [])

    def _add_recent(self, path: Path) -> None:
        items = [str(path)] + [p for p in self._recent() if Path(p) != path]
        self.settings.setValue("recent", items[:MAX_RECENT])

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        paths = [p for p in self._recent() if Path(p).exists()]
        for p in paths:
            self.recent_menu.addAction(Path(p).name, lambda path=p: self.open_path(path)).setToolTip(p)
        if not paths:
            self.recent_menu.addAction(tr("menu.recent_empty")).setEnabled(False)

    def open_dialog(self) -> None:
        start = str(Path(self._recent()[0]).parent) if self._recent() else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("action.open"), start, f"{tr('file.filter_all')} (*.pdf *{proj.SUFFIX});;PDF (*.pdf)"
        )
        for p in paths:
            self.open_path(p)

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.open_project"), "", f"{tr('file.filter_project')} (*{proj.SUFFIX})"
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> Session | None:
        path = Path(path)
        if path.name.endswith(proj.SUFFIX):
            return self.open_project(path)
        for i, c in enumerate(self._canvases()):
            if c.session.doc.path == path.resolve():
                self.tabs.setCurrentIndex(i)
                return c.session
        try:
            doc = PdfDocument(path)
        except PermissionError:
            QMessageBox.warning(self, tr("error.title"), tr("error.encrypted", name=path.name))
            return None
        except Exception as e:  # noqa: BLE001 - any parse error is shown to the user
            QMessageBox.warning(self, tr("error.title"), tr("error.open", name=path.name, error=str(e)))
            return None
        options = RedactionOptions(
            fill=self.settings.value("fill", "#000000"),
            label=self.settings.value("label", ""),
        )
        s = Session(doc, options)
        c = Canvas(s)
        s.setParent(c)  # the session lives and dies with its tab
        self._wire(s, c)
        index = self.tabs.addTab(c, s.title)
        self.tabs.setCurrentIndex(index)
        self._add_recent(doc.path)
        QTimer.singleShot(0, lambda: (c.set_zoom(min(1.25, c.viewport().width() / c.scene().sceneRect().width()
                                                        * 0.98)), c.go_to_page(0)))
        scans = [i for i in range(doc.page_count) if doc.needs_ocr(i)]
        if scans:
            self.statusBar().showMessage(tr_n("hint.scans_found", len(scans)), 10000)
        return s

    def open_project(self, path: Path) -> Session | None:
        try:
            project = proj.load(path)
        except proj.ProjectError as e:
            QMessageBox.warning(self, tr("error.title"), tr("error.project", name=path.name, error=str(e)))
            return None
        source = project.source
        if not source.exists():
            QMessageBox.information(self, tr("project.missing_title"), tr("project.missing_body", path=str(source)))
            found, _ = QFileDialog.getOpenFileName(self, tr("project.locate"), str(path.parent), "PDF (*.pdf)")
            if not found:
                return None
            source = Path(found)
        s = self.open_path(source)
        if s is None:
            return None
        if s.doc.sha256 != project.sha256:
            answer = QMessageBox.warning(
                self, tr("project.changed_title"), tr("project.changed_body"),
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Open:
                return s
        valid = [m for m in project.marks if 0 <= m.page < s.doc.page_count]
        s._insert(valid)
        s.options.fill, s.options.label = project.fill, project.label
        s.project_path = path
        s.undo.clear()
        s.undo.setClean()
        self._session_changed()
        self._add_recent(path.resolve())
        return s

    def save_project(self, ask: bool = False) -> bool:
        s = self.session
        if s is None:
            return False
        path = s.project_path
        if ask or path is None:
            suggestion = str(path or s.doc.path.with_name(s.doc.path.stem + proj.SUFFIX))
            chosen, _ = QFileDialog.getSaveFileName(
                self, tr("action.save_project_as"), suggestion, f"{tr('file.filter_project')} (*{proj.SUFFIX})"
            )
            if not chosen:
                return False
            if not chosen.endswith(proj.SUFFIX):
                chosen = chosen.removesuffix(".json") + proj.SUFFIX
            path = Path(chosen)
        include = self.a_include_text.isChecked()
        try:
            proj.save(
                proj.Project(s.doc.path, s.doc.sha256, list(s.marks.values()), include, s.options.fill,
                             s.options.label),
                path,
            )
        except OSError as e:
            QMessageBox.warning(self, tr("error.title"), tr("error.save", error=str(e)))
            return False
        s.project_path = path
        s.undo.setClean()
        self.statusBar().showMessage(tr("status.project_saved", name=path.name), 5000)
        return True

    def export(self) -> None:
        s, c = self.session, self.canvas
        if not s or not s.marks:
            return
        if self.ocr_job is not None:
            self.statusBar().showMessage(tr("ocr.busy"), 5000)
            return
        dialog = ExportDialog(s, c.current_page, self)
        dialog.exec()
        if dialog.report is not None:
            self.settings.setValue("fill", s.options.fill)
            self.settings.setValue("label", s.options.label)

    # ================================================================ closing
    def _confirm_close(self, s: Session) -> bool:
        if not s.dirty or not s.marks:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("close.title"))
        box.setText(tr("close.body", name=s.title))
        box.setInformativeText(tr("close.info"))
        save = box.addButton(tr("close.save"), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(tr("close.discard"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project()
        return box.clickedButton() is discard

    def close_tab(self, index: int) -> None:
        c = self.tabs.widget(index)
        if not isinstance(c, Canvas):
            return
        self.tabs.setCurrentIndex(index)
        if not self._confirm_close(c.session):
            return
        c.session.undo.blockSignals(True)
        self.tabs.removeTab(index)
        c.session.doc.close()
        c.deleteLater()
        self._session_changed()

    def close_current(self) -> None:
        if self.tabs.currentIndex() >= 0:
            self.close_tab(self.tabs.currentIndex())

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        for i in range(self.tabs.count()):
            self.tabs.setCurrentIndex(i)
            if not self._confirm_close(self.tabs.widget(i).session):
                e.ignore()
                return
        if self.ocr_job:
            self.ocr_job.cancelled = True
        for c in self._canvases():
            c.session.blockSignals(True)
            c.session.undo.blockSignals(True)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        e.accept()

    # ================================================================ OCR
    def ocr_current(self) -> None:
        if self.canvas:
            self._start_ocr([self.canvas.current_page])

    def ocr_pages(self, which: str) -> None:
        s = self.session
        if s is None:
            return
        pages = range(s.doc.page_count)
        targets = [i for i in pages if s.doc.needs_ocr(i)] if which == "scans" else list(pages)
        if not targets:
            self.statusBar().showMessage(tr("ocr.nothing"), 5000)
            return
        self._start_ocr(targets)

    def _start_ocr(self, pages: list[int]) -> None:
        s = self.session
        if s is None or self.ocr_job is not None or not self.ocr_available:
            return
        job = OcrJob(s.doc.data, pages, self)
        self.ocr_job = job
        self.ocr_box.show()
        self.ocr_label.setText(tr("ocr.running"))
        self.ocr_progress.setRange(0, len(pages))
        self.ocr_progress.setValue(0)
        self._session_changed()

        def page_done(index: int, text) -> None:
            s.doc.set_ocr_text(index, text)
            s.pageTextChanged.emit(index)

        def progress(done: int, total: int) -> None:
            self.ocr_progress.setValue(done)
            self.ocr_label.setText(tr("ocr.progress", done=done, total=total))

        def finished(completed: bool) -> None:
            self.ocr_job = None
            self.ocr_box.hide()
            self._session_changed()
            message = tr_n("ocr.done", len(pages)) if completed else tr("ocr.cancelled")
            self.statusBar().showMessage(message, 8000)

        def failed(error: str) -> None:
            self.ocr_job = None
            self.ocr_box.hide()
            self._session_changed()
            QMessageBox.warning(self, tr("error.title"), tr("ocr.failed", error=error))

        job.pageDone.connect(page_done)
        job.progress.connect(progress)
        job.finished.connect(finished)
        job.failed.connect(failed)
        job.start()

    def _cancel_ocr(self) -> None:
        if self.ocr_job:
            self.ocr_job.cancelled = True
            self.ocr_label.setText(tr("ocr.cancelling"))

    # ================================================================ drag & drop
    def _dropped(self, e) -> list[str]:
        if not e.mimeData().hasUrls():
            return []
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        return [p for p in paths if p.lower().endswith(".pdf") or p.endswith(proj.SUFFIX)]

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:  # noqa: N802
        if self._dropped(e):
            e.acceptProposedAction()
            self.empty.set_hot(True)

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.empty.set_hot(False)

    def dropEvent(self, e: QDropEvent) -> None:  # noqa: N802
        self.empty.set_hot(False)
        for p in self._dropped(e):
            self.open_path(p)

    # ================================================================ help
    def show_shortcuts(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("action.shortcuts"))
        dlg.resize(520, 560)
        tree = QTreeWidget()
        tree.setHeaderLabels([tr("shortcuts.action"), tr("shortcuts.keys")])
        tree.setRootIsDecorated(False)
        rows = [
            *((tr(TOOL_NAMES[t]), TOOL_KEYS[t]) for t in self.tool_actions),
            (tr("tool.search"), "S, Ctrl+F"),
            (tr("tool.ocr"), "O"),
            (tr("shortcuts.temp_hand"), tr("shortcuts.space")),
            (tr("shortcuts.add_select"), tr("shortcuts.shift_click")),
            (tr("shortcuts.rubber"), tr("shortcuts.alt_drag")),
            (tr("shortcuts.nudge"), tr("shortcuts.arrows")),
            (tr("action.delete"), "Delete"),
            (tr("search.accept_key"), "Enter"),
            (tr("search.reject_key"), "Delete"),
            (tr("action.preview"), "P"),
            (tr("action.export"), "Ctrl+Shift+E, Ctrl+Enter"),
            (tr("action.undo"), "Ctrl+Z"),
            (tr("action.redo"), "Ctrl+Y, Ctrl+Shift+Z"),
            (tr("view.zoom_in"), "Ctrl++, Ctrl+" + tr("shortcuts.wheel")),
            (tr("view.fit_page"), "Ctrl+0"),
            (tr("view.actual_size"), "Ctrl+1"),
            (tr("view.fit_width"), "Ctrl+2"),
            (tr("view.next_page"), "PgDown / PgUp"),
        ]
        for name, keys in rows:
            item = QTreeWidgetItem([name, keys])
            tree.addTopLevelItem(item)
        tree.resizeColumnToContents(0)
        lay = QVBoxLayout(dlg)
        lay.addWidget(tree)
        dlg.exec()

    def show_about(self) -> None:
        QMessageBox.about(self, tr("action.about"), tr("about.body", version=__version__))
