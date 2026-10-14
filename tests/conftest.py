from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

SECRET = "Jan Kowalski"
PESEL = "44051401458"
EMAIL = "jan.kowalski@example.com"
SCAN_WORD = "CONFIDENTIAL"


def _scan_pixmap() -> pymupdf.Pixmap:
    src = pymupdf.open()
    p = src.new_page(width=300, height=120)
    p.insert_text((20, 70), SCAN_WORD, fontsize=32)
    return p.get_pixmap(dpi=200)


def build_sample(path: Path) -> Path:
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 100), f"Klient: {SECRET}", fontsize=12)
    p1.insert_text((72, 130), f"PESEL: {PESEL}", fontsize=12)
    p1.insert_text((72, 160), f"E-mail: {EMAIL}", fontsize=12)
    p1.insert_text((72, 190), "Publiczny tekst zostaje.", fontsize=12)
    p1.add_text_annot((300, 300), f"Notatka o {SECRET}")

    p2 = doc.new_page()
    p2.insert_image(pymupdf.Rect(72, 72, 372, 192), pixmap=_scan_pixmap())

    p3 = doc.new_page(width=400, height=600)
    p3.insert_text((50, 100), f"Obrocona strona {SECRET}", fontsize=12)
    p3.set_rotation(90)

    doc.set_metadata({"author": SECRET, "title": "Tajne", "subject": PESEL})
    doc.embfile_add("dane.txt", SECRET.encode())
    doc.save(path)
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return build_sample(tmp_path / "sample.pdf")
