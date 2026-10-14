from __future__ import annotations

import pymupdf
import pytest
from conftest import EMAIL, PESEL, SECRET

from redactor.core.document import PdfDocument
from redactor.core.marks import Mark, MarkKind
from redactor.core.redaction import RedactionOptions, SameFileError, redact
from redactor.core.textops import scan_patterns, scan_query
from redactor.core.verify import Status, verify


def _marks(doc: PdfDocument) -> list[Mark]:
    marks = scan_query(doc, range(doc.page_count), SECRET, regex=False, case_sensitive=True)
    marks += scan_patterns(doc, range(doc.page_count), ["pattern.pesel", "pattern.email"])
    marks.append(Mark(page=1, rects=((72, 72, 372, 192),), kind=MarkKind.AREA))
    return marks


def _run(sample_pdf, tmp_path, **opts):
    doc = PdfDocument(sample_pdf)
    marks = _marks(doc)
    options = RedactionOptions(**opts)
    out = tmp_path / "out.pdf"
    result = redact(doc, marks, out, options)
    rotations = [doc.rotation_matrix(i) for i in range(doc.page_count)]
    report = verify(out, marks, rotations, options, result.sha256)
    return doc, marks, out, report


def test_marks_found_on_all_pages(sample_pdf):
    doc = PdfDocument(sample_pdf)
    marks = _marks(doc)
    assert {m.page for m in marks if m.text == SECRET} == {0, 2}
    assert any(m.text == PESEL for m in marks)
    assert any(m.text == EMAIL for m in marks)


@pytest.mark.parametrize("flatten", [False, True])
def test_redaction_removes_everything(sample_pdf, tmp_path, flatten):
    original = sample_pdf.read_bytes()
    _, _, out, report = _run(sample_pdf, tmp_path, flatten=flatten)

    assert sample_pdf.read_bytes() == original, "source must never change"
    assert report.passed, [(c.key, c.status, c.details) for c in report.checks]
    assert all(c.status in (Status.OK, Status.INFO) for c in report.checks)

    out_doc = pymupdf.open(out)
    text = "".join(p.get_text() for p in out_doc)
    for secret in (SECRET, PESEL, EMAIL):
        assert secret not in text
    if flatten:
        assert text.strip() == ""
    else:
        assert "Publiczny tekst zostaje." in text
    assert out_doc.embfile_count() == 0
    assert not out_doc.get_xml_metadata()
    assert all(v in ("", "none", None) for k, v in out_doc.metadata.items() if k not in ("format", "encryption"))
    raw = out.read_bytes()
    for secret in (SECRET, PESEL, EMAIL):
        assert secret.encode() not in raw
    for xref in range(1, out_doc.xref_length()):
        if out_doc.xref_is_stream(xref):
            stream = out_doc.xref_stream(xref) or b""
            assert SECRET.encode() not in stream


def test_scan_pixels_blanked(sample_pdf, tmp_path):
    _, _, out, _ = _run(sample_pdf, tmp_path)
    page = pymupdf.open(out)[1]
    pix = page.get_pixmap(clip=pymupdf.Rect(80, 80, 360, 180))
    assert set(pix.samples) == {0}, "image area must be uniformly black"
    out_doc = pymupdf.open(out)
    for xref in range(1, out_doc.xref_length()):
        if out_doc.xref_get_key(xref, "Subtype")[1] == "/Image":
            # the original scan must not survive anywhere in the file, referenced or not
            assert set(pymupdf.Pixmap(out_doc, xref).samples) <= {0}


def test_refuses_to_overwrite_source(sample_pdf):
    doc = PdfDocument(sample_pdf)
    with pytest.raises(SameFileError):
        redact(doc, _marks(doc), sample_pdf)
    with pytest.raises(SameFileError):
        redact(doc, _marks(doc), sample_pdf.parent / "." / sample_pdf.name.upper())


def test_label_and_color(sample_pdf, tmp_path):
    _, _, _, report = _run(sample_pdf, tmp_path, fill="#ffffff", label="[X]")
    assert report.passed, [(c.key, c.details) for c in report.checks]


def test_verify_detects_leak(sample_pdf, tmp_path):
    doc = PdfDocument(sample_pdf)
    marks = _marks(doc)
    out = tmp_path / "leak.pdf"
    result = redact(doc, marks[:1], out)
    rotations = [doc.rotation_matrix(i) for i in range(doc.page_count)]
    report = verify(out, marks, rotations, RedactionOptions(), result.sha256)
    assert not report.passed


def test_typographic_variants_are_found_and_removed(tmp_path):
    """No-break spaces, soft hyphens and ligatures must not hide data from search."""
    path = tmp_path / "variants.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "PESEL 44051401458 kod 31­147", fontsize=12)
    page.insert_text((72, 130), "Jan Kowalski", fontsize=12)
    doc.save(path)

    src = PdfDocument(path)
    marks = scan_patterns(src, [0], ["pattern.pesel", "pattern.postal_code"])
    marks += scan_query(src, [0], "Jan Kowalski", regex=False, case_sensitive=True)
    assert {m.text for m in marks} == {"44051401458", "31-147", "Jan Kowalski"}

    out = tmp_path / "out.pdf"
    options = RedactionOptions()
    result = redact(src, marks, out, options)
    report = verify(out, marks, [src.rotation_matrix(0)], options, result.sha256)
    assert report.passed, [(c.key, c.details) for c in report.checks]
    text = pymupdf.open(out)[0].get_text()
    assert "44051401458" not in text and "147" not in text and "Kowalski" not in text


def test_verify_sees_leak_behind_no_break_space(tmp_path):
    path = tmp_path / "leak.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Jan Kowalski", fontsize=12)
    doc.save(path)
    src = PdfDocument(path)
    fake = Mark(page=0, rects=((300, 300, 310, 310),), kind=MarkKind.AREA, text="Jan Kowalski")
    out = tmp_path / "out.pdf"
    result = redact(src, [fake], out)
    report = verify(out, [fake], [src.rotation_matrix(0)], RedactionOptions(), result.sha256)
    assert any(c.key == "verify.phrases_absent" and c.status == Status.WARN for c in report.checks)
