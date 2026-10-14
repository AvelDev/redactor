"""OCR through the Tesseract engine built into MuPDF; only language data is needed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pymupdf

from redactor.core.document import PDF_LOCK, PageText, extract_page_text

LANGUAGES = "pol+eng"


def tessdata_dir() -> Path | None:
    """Bundled tessdata first, then TESSDATA_PREFIX, then a system Tesseract install."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [base / "resources" / "tessdata", base / "redactor" / "resources" / "tessdata"]
    if env := os.environ.get("TESSDATA_PREFIX"):
        candidates.append(Path(env))
    try:
        if found := pymupdf.get_tessdata():
            candidates.append(Path(found))
    except Exception:  # noqa: BLE001 - PyMuPDF raises when no Tesseract is installed
        pass
    for c in candidates:
        if (c / "eng.traineddata").is_file():
            return c
    return None


def available() -> bool:
    return tessdata_dir() is not None


def languages(tessdata: Path) -> str:
    wanted = [lang for lang in LANGUAGES.split("+") if (tessdata / f"{lang}.traineddata").is_file()]
    return "+".join(wanted) or "eng"


def ocr_page(data: bytes, index: int, dpi: int = 300) -> PageText:
    """Run OCR on one page. Opens its own document so it is safe in a worker thread."""
    tessdata = tessdata_dir()
    if tessdata is None:
        raise RuntimeError("tessdata")
    with PDF_LOCK:
        doc = pymupdf.open(stream=data, filetype="pdf")
        try:
            page = doc[index]
            tp = page.get_textpage_ocr(
                language=languages(tessdata), dpi=dpi, full=False, tessdata=str(tessdata)
            )
            return extract_page_text(page, tp)
        finally:
            doc.close()
