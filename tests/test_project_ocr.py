from __future__ import annotations

import pytest
from conftest import SCAN_WORD, SECRET

from redactor.core import ocr
from redactor.core import project as proj
from redactor.core.document import PdfDocument
from redactor.core.marks import Mark, MarkKind
from redactor.core.redaction import RedactionOptions, redact
from redactor.core.textops import scan_query
from redactor.core.verify import verify


def test_project_roundtrip_without_text(sample_pdf, tmp_path):
    doc = PdfDocument(sample_pdf)
    marks = [Mark(0, ((1, 2, 3, 4),), MarkKind.TEXT, text=SECRET, color="#ff0000", label="")]
    path = tmp_path / "p.redactor.json"
    proj.save(proj.Project(doc.path, doc.sha256, marks), path)
    assert SECRET not in path.read_text(encoding="utf-8")
    loaded = proj.load(path)
    assert loaded.sha256 == doc.sha256
    m = loaded.marks[0]
    assert (m.page, m.rects, m.kind, m.color, m.label, m.id, m.text) == (
        0, ((1.0, 2.0, 3.0, 4.0),), MarkKind.TEXT, "#ff0000", "", marks[0].id, ""
    )


def test_project_keeps_text_when_asked(sample_pdf, tmp_path):
    doc = PdfDocument(sample_pdf)
    path = tmp_path / "p.redactor.json"
    marks = [Mark(0, ((1, 2, 3, 4),), MarkKind.TEXT, text=SECRET)]
    proj.save(proj.Project(doc.path, doc.sha256, marks, include_text=True), path)
    assert proj.load(path).marks[0].text == SECRET


def test_project_rejects_garbage(tmp_path):
    bad = tmp_path / "x.redactor.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(proj.ProjectError):
        proj.load(bad)


@pytest.mark.skipif(not ocr.available(), reason="no tessdata")
def test_ocr_finds_and_redacts_scan(sample_pdf, tmp_path):
    doc = PdfDocument(sample_pdf)
    assert doc.needs_ocr(1)
    doc.set_ocr_text(1, ocr.ocr_page(doc.data, 1))
    assert doc.has_ocr(1)
    marks = scan_query(doc, [1], SCAN_WORD, regex=False, case_sensitive=False)
    assert len(marks) == 1
    out = tmp_path / "ocr.pdf"
    options = RedactionOptions()
    result = redact(doc, marks, out, options)
    report = verify(out, marks, [doc.rotation_matrix(i) for i in range(3)], options, result.sha256)
    assert report.passed
