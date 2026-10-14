"""Read-only access to a source PDF: rendering and a character-level text model.

The source is loaded into memory once and the file on disk is never opened for
writing. All coordinates here are unrotated page coordinates (the space PyMuPDF
uses for text extraction and redaction annotations); the view converts them to
displayed coordinates with ``rotation_matrix``.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from redactor.core.marks import Rect

# PyMuPDF is not thread-safe, not even across separate Document objects. Every
# call into it from more than one thread (UI rendering, OCR, export) holds this.
PDF_LOCK = threading.RLock()


@dataclass
class TextLine:
    text: str
    boxes: list[Rect]  # one box per character of ``text``


@dataclass
class PageText:
    lines: list[TextLine] = field(default_factory=list)
    from_ocr: bool = False

    def char_count(self) -> int:
        return sum(len(line.text) for line in self.lines)


# PDFs often carry typographic variants that defeat plain searches: no-break and
# thin spaces instead of spaces, soft hyphens and dashes instead of "-". They are
# normalised one-to-one so every character keeps its own box.
_SAME_WIDTH = str.maketrans(
    {
        **dict.fromkeys("              　", " "),
        **dict.fromkeys("­‐‑‒–—−﹣－", "-"),
        "‘": "'", "’": "'", "‚": "'",
    }
)
# Ligatures expand to several characters; their box is split evenly.
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st",
              "ﬆ": "st"}


def normalize_text(text: str) -> str:
    """The same normalisation as the text model, for whole strings."""
    for lig, plain in _LIGATURES.items():
        text = text.replace(lig, plain)
    return text.translate(_SAME_WIDTH)


def _append_char(chars: list[str], boxes: list[Rect], c: str, box: Rect) -> None:
    expanded = _LIGATURES.get(c)
    if expanded is None:
        chars.append(c.translate(_SAME_WIDTH))
        boxes.append(box)
        return
    x0, y0, x1, y1 = box
    step = (x1 - x0) / len(expanded)
    for i, part in enumerate(expanded):
        chars.append(part)
        boxes.append((x0 + i * step, y0, x0 + (i + 1) * step, y1))


def extract_page_text(page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> PageText:
    """Build the per-character text model of a page (optionally from an OCR text page)."""
    flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    raw = page.get_text("rawdict", flags=flags, textpage=textpage)
    result = PageText(from_ocr=textpage is not None)
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            chars: list[str] = []
            boxes: list[Rect] = []
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    _append_char(chars, boxes, ch["c"], tuple(ch["bbox"]))  # type: ignore[arg-type]
            if chars and "".join(chars).strip():
                result.lines.append(TextLine("".join(chars), boxes))
    return result


def merge_char_boxes(boxes: list[Rect]) -> Rect:
    xs0, ys0, xs1, ys1 = zip(*boxes, strict=True)
    return min(xs0), min(ys0), max(xs1), max(ys1)


class PdfDocument:
    """A source PDF held in memory. Never writes to ``path``."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.data = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        with PDF_LOCK:
            self.doc = pymupdf.open(stream=self.data, filetype="pdf")
            if self.doc.needs_pass:
                raise PermissionError("encrypted")
            if not self.doc.is_pdf:
                raise ValueError("not a pdf")
            pages = list(self.doc)
            self._sizes = [(p.rect.width, p.rect.height) for p in pages]
            self._rot = [pymupdf.Matrix(p.rotation_matrix) for p in pages]
            self._derot = [pymupdf.Matrix(p.derotation_matrix) for p in pages]
        self._text: dict[int, PageText] = {}

    @property
    def page_count(self) -> int:
        return len(self._sizes)

    def display_size(self, index: int) -> tuple[float, float]:
        return self._sizes[index]

    def rotation_matrix(self, index: int) -> pymupdf.Matrix:
        """Unrotated page coordinates -> displayed coordinates."""
        return self._rot[index]

    def derotation_matrix(self, index: int) -> pymupdf.Matrix:
        """Displayed coordinates -> unrotated page coordinates."""
        return self._derot[index]

    def render(self, index: int, scale: float, clip: pymupdf.Rect | None = None) -> pymupdf.Pixmap:
        """Render the displayed page at ``scale`` pixels per point."""
        with PDF_LOCK:
            return self.doc[index].get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False, annots=False
            )

    def text(self, index: int) -> PageText:
        if index not in self._text:
            with PDF_LOCK:
                self._text[index] = extract_page_text(self.doc[index])
        return self._text[index]

    def set_ocr_text(self, index: int, text: PageText) -> None:
        self._text[index] = text

    def has_ocr(self, index: int) -> bool:
        return index in self._text and self._text[index].from_ocr

    def needs_ocr(self, index: int) -> bool:
        """Heuristic: a page with images but (almost) no extractable text is likely a scan."""
        if self.has_ocr(index):
            return False
        if self.text(index).char_count() >= 10:
            return False
        with PDF_LOCK:
            return bool(self.doc[index].get_images())

    def close(self) -> None:
        with PDF_LOCK:
            self.doc.close()
