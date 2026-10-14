"""Export: before/after preview, options, then the verification report as proof."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from redactor.core.redaction import RedactionResult, is_same_file, preview_page, redact
from redactor.core.verify import Report, Status, verify
from redactor.i18n import tr, tr_n
from redactor.ui import theme, workers
from redactor.ui.panels import ColorButton, hint, section
from redactor.ui.session import Session

PREVIEW_W = 250


class ElidedLabel(QLabel):
    """Shows its full text middle-elided to the width it actually has."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(10)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(10, self.width())))


def _pix_to_qpixmap(pix, dpr: float) -> QPixmap:
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    pm = QPixmap.fromImage(img.copy())
    pm.setDevicePixelRatio(dpr)
    return pm


class ExportDialog(QDialog):
    def __init__(self, session: Session, page: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.session = session
        self.page = page if session.marks_on(page) else min(session.pages_with_marks(), default=page)
        self.options = replace(session.options)
        self.report: Report | None = None
        self.setWindowTitle(tr("export.title"))
        self.setModal(True)
        self.setMinimumWidth(820)

        self.stack = QStackedWidget()
        self.setup_page = self._build_setup()
        self.report_page = self._build_report()
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.report_page)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self._preview_timer = QTimer(self, singleShot=True, interval=150, timeout=self._update_preview)
        self._validate()
        QTimer.singleShot(0, self._update_preview)
        QTimer.singleShot(0, self.export_btn.setFocus)

    # ------------------------------------------------------------ setup page
    def _build_setup(self) -> QWidget:
        s = self.session
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        n_pages = len(s.pages_with_marks())
        summary = QLabel(
            tr("export.summary", marks=tr_n("export.marks", len(s.marks)), pages=tr_n("export.pages", n_pages))
        )
        summary.setObjectName("reportTitle")
        outer.addWidget(summary)

        body = QHBoxLayout()
        body.setSpacing(18)

        # before / after
        previews = QGridLayout()
        previews.setHorizontalSpacing(10)
        self.before = QLabel()
        self.after = QLabel()
        for col, (title, label) in enumerate(((tr("export.before"), self.before), (tr("export.after"), self.after))):
            frame = QFrame()
            frame.setObjectName("previewFrame")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 8, 8, 8)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(QSize(PREVIEW_W, 300))
            fl.addWidget(label)
            previews.addWidget(section(title), 0, col)
            previews.addWidget(frame, 1, col)
        self.page_note = hint("")
        previews.addWidget(self.page_note, 2, 0, 1, 2)
        body.addLayout(previews)

        # options
        opts = QVBoxLayout()
        opts.setSpacing(8)
        opts.addWidget(section(tr("export.appearance")))
        row = QHBoxLayout()
        self.color = ColorButton()
        self.color.set_color(self.options.fill)
        self.color.colorChosen.connect(self._set_fill)
        self.label = QLineEdit(self.options.label)
        self.label.setPlaceholderText(tr("props.no_label"))
        self.label.textChanged.connect(self._set_label)
        row.addWidget(QLabel(tr("props.fill")))
        row.addWidget(self.color)
        row.addSpacing(10)
        row.addWidget(QLabel(tr("props.label")))
        row.addWidget(self.label, 1)
        opts.addLayout(row)

        opts.addSpacing(6)
        opts.addWidget(section(tr("export.security")))
        self.flatten = QCheckBox(tr("export.flatten"))
        self.flatten.setChecked(self.options.flatten)
        self.flatten.toggled.connect(self._set_flatten)
        self.dpi = QComboBox()
        for dpi in (150, 200, 300):
            self.dpi.addItem(tr("export.dpi", dpi=dpi), dpi)
        self.dpi.setCurrentIndex([150, 200, 300].index(self.options.dpi) if self.options.dpi in (150, 200, 300) else 1)
        self.dpi.currentIndexChanged.connect(self._set_dpi)
        frow = QHBoxLayout()
        frow.addWidget(self.flatten, 1)
        frow.addWidget(self.dpi)
        opts.addLayout(frow)
        opts.addWidget(hint(tr("export.flatten_hint")))
        self.annots = QCheckBox(tr("export.remove_annotations"))
        self.annots.setChecked(self.options.remove_annotations)
        self.annots.toggled.connect(lambda v: self._set(remove_annotations=v))
        self.hidden = QCheckBox(tr("export.remove_hidden"))
        self.hidden.setChecked(self.options.remove_hidden_text)
        self.hidden.toggled.connect(lambda v: self._set(remove_hidden_text=v))
        self.touched = QCheckBox(tr("export.remove_touched"))
        self.touched.setChecked(self.options.remove_touched_graphics)
        self.touched.toggled.connect(lambda v: self._set(remove_touched_graphics=v))
        for box in (self.annots, self.hidden, self.touched):
            opts.addWidget(box)
        opts.addWidget(hint(tr("export.always")))

        opts.addSpacing(6)
        opts.addWidget(section(tr("export.output")))
        self.folder = s.export_path.parent
        self.folder_label = ElidedLabel()
        self.folder_label.setObjectName("hint")
        self.path = QLineEdit(s.export_path.name)
        self.path.textChanged.connect(self._validate)
        browse = QPushButton(tr("export.browse"))
        browse.clicked.connect(self._browse)
        frow2 = QHBoxLayout()
        frow2.addWidget(QLabel(tr("export.folder")))
        frow2.addWidget(self.folder_label, 1)
        frow2.addWidget(browse)
        prow = QHBoxLayout()
        prow.addWidget(QLabel(tr("export.file_name")))
        prow.addWidget(self.path, 1)
        opts.addLayout(frow2)
        opts.addLayout(prow)
        self.path_error = QLabel()
        self.path_error.setObjectName("danger")
        self.path_error.setWordWrap(True)
        opts.addWidget(self.path_error)
        opts.addWidget(hint(tr("export.original_safe")))
        opts.addStretch()
        body.addLayout(opts, 1)
        outer.addLayout(body, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.busy_label = hint(tr("export.working"))
        self.busy_label.hide()

        buttons = QHBoxLayout()
        buttons.addWidget(self.busy_label)
        buttons.addWidget(self.progress, 1)
        buttons.addStretch()
        self.cancel_btn = QPushButton(tr("common.cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        self.export_btn = QPushButton(tr("export.run"))
        self.export_btn.setProperty("primary", True)
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.export_btn)
        outer.addLayout(buttons)
        return w

    def _set(self, **changes) -> None:
        self.options = replace(self.options, **changes)
        self._preview_timer.start()

    def _set_fill(self, color: str) -> None:
        self._set(fill=color)

    def _set_label(self, text: str) -> None:
        self._set(label=text)

    def _set_flatten(self, on: bool) -> None:
        self.dpi.setEnabled(on)
        self._set(flatten=on)

    def _set_dpi(self, _i: int) -> None:
        self._set(dpi=self.dpi.currentData())

    def output_path(self) -> Path | None:
        name = self.path.text().strip()
        return self.folder / name if name else None

    def set_output(self, path: Path) -> None:
        self.folder = path.parent
        self.path.setText(path.name)
        self._validate()

    def _browse(self) -> None:
        current = self.output_path() or self.folder
        path, _ = QFileDialog.getSaveFileName(self, tr("export.title"), str(current), "PDF (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.set_output(Path(path))

    def _validate(self) -> None:
        self.folder_label.set_full_text(str(self.folder))
        out = self.output_path()
        text = str(out) if out else ""
        error = ""
        if not text:
            error = tr("export.err_empty")
        else:
            p = Path(text)
            if is_same_file(p, self.session.doc.path):
                error = tr("export.err_same")
            elif not p.parent.is_dir():
                error = tr("export.err_folder")
            elif p.exists():
                error = ""
                self.path_error.setText(tr("export.overwrite_warn"))
        if error:
            self.path_error.setText(error)
        elif not (text and Path(text).exists()):
            self.path_error.setText("")
        self.path.setProperty("invalid", bool(error))
        self.path.style().unpolish(self.path)
        self.path.style().polish(self.path)
        self.export_btn.setEnabled(not error and bool(self.session.marks))

    def _update_preview(self) -> None:
        s = self.session
        dpr = self.devicePixelRatioF()
        w, _ = s.doc.display_size(self.page)
        scale = PREVIEW_W * dpr / w
        self.before.setPixmap(_pix_to_qpixmap(s.doc.render(self.page, scale), dpr))
        marks = list(s.marks.values())
        self.after.setPixmap(_pix_to_qpixmap(preview_page(s.doc, marks, self.page, self.options, scale), dpr))
        self.page_note.setText(tr("export.preview_page", page=self.page + 1))

    # ------------------------------------------------------------ run
    def _export(self) -> None:
        s = self.session
        out = self.output_path()
        if out is None:
            return
        marks = list(s.marks.values())
        options = self.options
        rotations = [s.doc.rotation_matrix(i) for i in range(s.doc.page_count)]
        self._busy(True)

        def job() -> Report:
            result: RedactionResult = redact(s.doc, marks, out, options)
            return verify(result.path, marks, rotations, options, result.sha256)

        workers.run(job, self._done, self._failed)

    def _busy(self, on: bool) -> None:
        for wdg in (self.export_btn, self.cancel_btn, self.path, self.flatten, self.label, self.color):
            wdg.setEnabled(not on)
        self.progress.setVisible(on)
        self.busy_label.setVisible(on)

    def _done(self, report: Report) -> None:
        self._busy(False)
        self.report = report
        self.session.export_path = report.path
        self.session.options = replace(self.options)
        self.session.overlayChanged.emit()
        self._show_report(report)
        # a stack is as tall as its tallest page: take the setup page out while the report shows
        self.stack.setCurrentWidget(self.report_page)
        self.stack.removeWidget(self.setup_page)
        self.setup_page.hide()
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())
        self.close_btn.setDefault(True)
        self.close_btn.setFocus()

    def _failed(self, message: str) -> None:
        self._busy(False)
        self._validate()
        self.path_error.setText(tr("export.failed", error=message))

    # ------------------------------------------------------------ report page
    def _build_report(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        self.header = QFrame()
        self.header.setObjectName("reportHeader")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(12)
        self.header_icon = QLabel()
        text = QVBoxLayout()
        self.header_title = QLabel()
        self.header_title.setObjectName("reportTitle")
        self.header_body = hint("")
        text.addWidget(self.header_title)
        text.addWidget(self.header_body)
        hl.addWidget(self.header_icon, 0, Qt.AlignmentFlag.AlignTop)
        hl.addLayout(text, 1)
        lay.addWidget(self.header)

        lay.addWidget(section(tr("report.checks")))
        self.checks_box = QWidget()
        self.checks = QVBoxLayout(self.checks_box)
        self.checks.setContentsMargins(0, 0, 0, 0)
        self.checks.setSpacing(6)
        lay.addWidget(self.checks_box)
        lay.addStretch(1)

        buttons = QHBoxLayout()
        self.retry_btn = QPushButton(tr("report.retry_flatten"))
        self.retry_btn.clicked.connect(self._retry_flatten)
        folder = QPushButton(tr("report.show_folder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report.path.parent))))
        open_file = QPushButton(tr("report.open_file"))
        open_file.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report.path))))
        close = QPushButton(tr("common.close"))
        close.setProperty("primary", True)
        self.close_btn = close
        close.clicked.connect(self.accept)
        buttons.addWidget(self.retry_btn)
        buttons.addStretch()
        buttons.addWidget(folder)
        buttons.addWidget(open_file)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        return w

    def _show_report(self, report: Report) -> None:
        t = theme.T
        ok = report.passed
        self.header.setProperty("state", "ok" if ok else "fail")
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)
        self.header_icon.setPixmap(theme.pixmap("shield-check" if ok else "circle-x", t.ok if ok else t.fail, 32))
        self.header_title.setText(tr("report.ok_title") if ok else tr("report.fail_title"))
        self.header_body.setText(
            tr("report.ok_body", path=str(report.path)) if ok else tr("report.fail_body", path=str(report.path))
        )
        self.retry_btn.setVisible(not ok and not self.options.flatten)

        while self.checks.count():
            item = self.checks.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        icons = {
            Status.OK: ("circle-check", t.ok),
            Status.WARN: ("circle-alert", t.warn),
            Status.FAIL: ("circle-x", t.fail),
            Status.INFO: ("info", t.text_dim),
        }
        for check in report.checks:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(10)
            name, color = icons[check.status]
            ic = QLabel()
            ic.setPixmap(theme.pixmap(name, color, 18))
            col = QVBoxLayout()
            col.setSpacing(2)
            title = QLabel(tr(check.key, **check.params))
            title.setWordWrap(True)
            col.addWidget(title)
            if check.status == Status.WARN:
                col.addWidget(hint(tr("report.phrases_warn")))
            if check.details:
                details = QLabel("\n".join(check.details[:12]) + ("\n…" if len(check.details) > 12 else ""))
                details.setObjectName("mono")
                details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                col.addWidget(details)
            if check.status == Status.INFO and "hash" in check.params:
                title.setText(tr("verify.sha256_title"))
                mono = QLabel(str(check.params["hash"]))
                mono.setObjectName("mono")
                mono.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                copy = QPushButton(tr("report.copy"))
                copy.setProperty("flat", True)
                copy.clicked.connect(lambda _=False, h=check.params["hash"]: QGuiApplication.clipboard().setText(h))
                hr = QHBoxLayout()
                hr.addWidget(mono)
                hr.addWidget(copy)
                hr.addStretch()
                col.addLayout(hr)
            rl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            rl.addLayout(col, 1)
            self.checks.addWidget(row)

    def _retry_flatten(self) -> None:
        self.flatten.setChecked(True)
        self.stack.insertWidget(0, self.setup_page)
        self.stack.setCurrentWidget(self.setup_page)
        self.adjustSize()
        self._export()
