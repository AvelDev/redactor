"""``Redactor --self-test``: prove a build can redact, verify and OCR. Exit code 0 = OK."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf

from redactor.core import ocr
from redactor.core.document import PdfDocument
from redactor.core.redaction import RedactionOptions, redact
from redactor.core.textops import scan_patterns, scan_query
from redactor.core.verify import verify


def run() -> list[str]:
    problems: list[str] = []
    folder = Path(tempfile.mkdtemp(prefix="redactor-selftest-"))
    src = folder / "in.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "PESEL 44051401458 Jan Kowalski", fontsize=12)
    scan = pymupdf.open()
    sp = scan.new_page(width=300, height=100)
    sp.insert_text((20, 60), "CONFIDENTIAL", fontsize=30)
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 372, 172), pixmap=sp.get_pixmap(dpi=200))
    doc.save(src)

    pdf = PdfDocument(src)
    marks = scan_patterns(pdf, [0], ["pattern.pesel"]) + scan_query(
        pdf, [0], "Jan Kowalski", regex=False, case_sensitive=True
    )
    if not ocr.available():
        problems.append("OCR data not found")
    else:
        pdf.set_ocr_text(1, ocr.ocr_page(pdf.data, 1))
        marks += scan_query(pdf, [1], "CONFIDENTIAL", regex=False, case_sensitive=False)
    if len(marks) != (3 if ocr.available() else 2):
        problems.append(f"expected marks not found: {[m.text for m in marks]}")

    for flatten in (False, True):
        options = RedactionOptions(flatten=flatten)
        out = folder / f"out-{flatten}.pdf"
        result = redact(pdf, marks, out, options)
        report = verify(out, marks, [pdf.rotation_matrix(i) for i in range(pdf.page_count)], options, result.sha256)
        problems += [f"{c.key} {c.details}" for c in report.checks if c.status == "fail"]
    return problems


def main() -> int:
    try:
        problems = run()
    except Exception as e:  # noqa: BLE001
        problems = [f"crash: {e!r}"]
    log = Path(tempfile.gettempdir()) / "redactor-selftest.log"
    log.write_text("OK\n" if not problems else "\n".join(problems) + "\n", encoding="utf-8")
    print(log.read_text(encoding="utf-8"), end="")
    return 1 if problems else 0
