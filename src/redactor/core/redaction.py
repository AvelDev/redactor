"""Apply marks to a copy of the source and write an irreversibly redacted PDF.

Pipeline (each step works on an in-memory copy; the source file is never touched):

1. a redaction annotation per mark rectangle,
2. ``apply_redactions``: glyphs under the rectangles are deleted, overlapping
   image pixels are blanked, covered vector art is removed,
3. remaining annotations dropped, ``scrub`` removes metadata, XMP, attachments,
   embedded files, JavaScript, links, form values, thumbnails and hidden text,
4. optional flattening: every page is rendered to an image and placed into a
   brand-new document, so not a single text object survives,
5. full rewrite with garbage collection (no incremental save), so the old
   objects cannot be recovered from the file.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from redactor.core.document import PDF_LOCK, PdfDocument
from redactor.core.marks import Mark, hex_to_rgb


class SameFileError(ValueError):
    """Raised when the output path points at the source document."""


@dataclass
class RedactionOptions:
    fill: str = "#000000"
    label: str = ""
    flatten: bool = False
    dpi: int = 200
    remove_touched_graphics: bool = False
    remove_annotations: bool = True
    remove_hidden_text: bool = True


@dataclass
class RedactionResult:
    path: Path
    sha256: str
    mark_count: int
    flattened: bool


def label_color(fill: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = fill
    return (0, 0, 0) if 0.299 * r + 0.587 * g + 0.114 * b > 0.5 else (1, 1, 1)


def is_same_file(a: Path, b: Path) -> bool:
    a, b = Path(a).resolve(), Path(b).resolve()
    if a == b or os.path.normcase(a) == os.path.normcase(b):
        return True
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def default_output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}-redacted.pdf")


def _add_annotations(page: pymupdf.Page, marks: Iterable[Mark], options: RedactionOptions) -> None:
    for mark in marks:
        fill = hex_to_rgb(mark.color or options.fill)
        label = options.label if mark.label is None else mark.label
        widest = max(mark.rects, key=lambda r: r[2] - r[0])
        for r in mark.rects:
            rect = pymupdf.Rect(r)
            if rect.is_empty:
                continue
            text = label if (label and r == widest) else None
            page.add_redact_annot(
                rect,
                text=text,
                fontname="helv",
                fontsize=max(4.0, min(9.0, rect.height * 0.7)),
                align=pymupdf.TEXT_ALIGN_CENTER,
                fill=fill,
                text_color=label_color(fill),
                cross_out=False,
            )


def _redact_in_memory(source: bytes, marks: list[Mark], options: RedactionOptions) -> pymupdf.Document:
    doc = pymupdf.open(stream=source, filetype="pdf")
    by_page: dict[int, list[Mark]] = {}
    for m in marks:
        by_page.setdefault(m.page, []).append(m)

    graphics = (
        pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
        if options.remove_touched_graphics
        else pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
    )
    for index, page_marks in by_page.items():
        page = doc[index]
        _add_annotations(page, page_marks, options)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
            graphics=graphics,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )

    if options.remove_annotations:
        for page in doc:
            for annot in list(page.annots() or []):
                page.delete_annot(annot)

    doc.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        hidden_text=options.remove_hidden_text,
        javascript=True,
        metadata=True,
        redactions=True,
        redact_images=1,
        remove_links=True,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
        xml_metadata=True,
    )
    doc.set_metadata({})
    doc.del_xml_metadata()
    return doc


def _flatten(doc: pymupdf.Document, dpi: int) -> pymupdf.Document:
    flat = pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, alpha=False, annots=True)
        out = flat.new_page(width=page.rect.width, height=page.rect.height)
        out.insert_image(out.rect, pixmap=pix)
    flat.set_metadata({})
    return flat


def redact(
    source: PdfDocument,
    marks: list[Mark],
    output: str | Path,
    options: RedactionOptions | None = None,
) -> RedactionResult:
    options = options or RedactionOptions()
    output = Path(output).resolve()
    if is_same_file(output, source.path):
        raise SameFileError(str(output))

    # Write next to the target and move into place, so a failure never leaves a half file.
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=output.parent)
    os.close(fd)
    try:
        with PDF_LOCK:
            doc = _redact_in_memory(source.data, marks, options)
            if options.flatten:
                flat = _flatten(doc, options.dpi)
                doc.close()
                doc = flat
            doc.save(tmp, garbage=4, deflate=True, clean=True)
            doc.close()
        os.replace(tmp, output)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return RedactionResult(output, digest, len(marks), options.flatten)


def preview_page(source: PdfDocument, marks: list[Mark], index: int, options: RedactionOptions,
                 scale: float) -> pymupdf.Pixmap:
    """Render one page exactly as it will look after export (used by the export dialog)."""
    page_marks = [m for m in marks if m.page == index]
    with PDF_LOCK:
        doc = _redact_in_memory(source.data, page_marks, options)
        try:
            if options.flatten:
                pix = doc[index].get_pixmap(dpi=options.dpi, alpha=False)
                return pymupdf.Pixmap(pix, int(pix.width * scale * 72 / options.dpi),
                                      int(pix.height * scale * 72 / options.dpi), None)
            return doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        finally:
            doc.close()
