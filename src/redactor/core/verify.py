"""Re-open a redacted file and prove that the marked content is gone."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import pymupdf

from redactor.core.document import PDF_LOCK, normalize_text
from redactor.core.marks import Mark, hex_to_rgb
from redactor.core.redaction import RedactionOptions
from redactor.i18n import N_


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"


@dataclass
class Check:
    key: str  # i18n key of the check title
    status: Status
    params: dict[str, object] = field(default_factory=dict)
    details: list[str] = field(default_factory=list)


@dataclass
class Report:
    path: Path
    checks: list[Check]

    @property
    def passed(self) -> bool:
        return all(c.status != Status.FAIL for c in self.checks)


_JS = re.compile(r"/(JS|JavaScript)\b")
_EMPTY_META = {"", "none", None}


def _ws(s: str) -> str:
    return " ".join(normalize_text(s).split()).casefold()


def _coverage(page: pymupdf.Page, rect: pymupdf.Rect, fill: tuple[float, float, float]) -> float:
    """Share of rendered pixels inside ``rect`` (displayed coords) that have the fill colour."""
    inner = rect + (1, 1, -1, -1)
    if inner.width < 2 or inner.height < 2:
        return 1.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=inner, alpha=False)
    target = [round(c * 255) for c in fill]
    samples = pix.samples
    n = pix.n
    total = len(samples) // n
    hits = sum(
        1
        for i in range(0, len(samples), n)
        if all(abs(samples[i + k] - target[k]) <= 24 for k in range(3))
    )
    return hits / total if total else 1.0


def verify(
    output: Path,
    marks: list[Mark],
    rotations: list[pymupdf.Matrix],
    options: RedactionOptions,
    sha256: str,
) -> Report:
    """``rotations[i]`` maps unrotated source coordinates of page ``i`` to displayed ones."""
    with PDF_LOCK:
        return _verify(output, marks, rotations, options, sha256)


def _verify(
    output: Path,
    marks: list[Mark],
    rotations: list[pymupdf.Matrix],
    options: RedactionOptions,
    sha256: str,
) -> Report:
    checks: list[Check] = []
    doc = pymupdf.open(output)
    try:
        page_texts = [page.get_text() for page in doc]

        if options.flatten:
            pages_with_text = [str(i + 1) for i, t in enumerate(page_texts) if t.strip()]
            checks.append(
                Check(
                    N_("verify.no_text"),
                    Status.FAIL if pages_with_text else Status.OK,
                    details=pages_with_text,
                )
            )
        else:
            leaks: list[str] = []
            for m in marks:
                page = doc[m.page]
                label = options.label if m.label is None else m.label
                for r in m.rects:
                    found = page.get_text("text", clip=pymupdf.Rect(r))
                    if label:
                        found = found.replace(label, "")
                    found = found.strip()
                    if found:
                        leaks.append(f"{m.page + 1}: {found[:40]}")
            checks.append(
                Check(
                    N_("verify.text_under_marks"),
                    Status.FAIL if leaks else Status.OK,
                    {"count": sum(len(m.rects) for m in marks)},
                    leaks,
                )
            )

        all_text = [_ws(t) for t in page_texts]
        elsewhere: list[str] = []
        for m in marks:
            needle = _ws(m.text)
            if len(needle) < 3:
                continue
            pages = [str(i + 1) for i, t in enumerate(all_text) if needle in t]
            if pages:
                elsewhere.append(f"„{m.text[:40]}”: {', '.join(pages)}")
        checks.append(
            Check(N_("verify.phrases_absent"), Status.WARN if elsewhere else Status.OK, details=elsewhere)
        )

        uncovered: list[str] = []
        for m in marks:
            fill = hex_to_rgb(m.color or options.fill)
            label = options.label if m.label is None else m.label
            threshold = 0.8 if label else 0.97
            page = doc[m.page]
            for r in m.rects:
                shown = pymupdf.Rect(r) * rotations[m.page]
                if _coverage(page, shown, fill) < threshold:
                    uncovered.append(str(m.page + 1))
        checks.append(
            Check(
                N_("verify.covered"),
                Status.FAIL if uncovered else Status.OK,
                details=sorted(set(uncovered), key=int),
            )
        )

        meta = {k: v for k, v in doc.metadata.items() if k not in ("format", "encryption")}
        leftover = [f"{k}: {v}" for k, v in meta.items() if v not in _EMPTY_META]
        if doc.get_xml_metadata().strip():
            leftover.append("XMP")
        checks.append(Check(N_("verify.metadata"), Status.FAIL if leftover else Status.OK, details=leftover))

        files = doc.embfile_count()
        checks.append(Check(N_("verify.embedded"), Status.FAIL if files else Status.OK, {"count": files}))

        js = [str(x) for x in range(1, doc.xref_length()) if _JS.search(doc.xref_object(x, compressed=True))]
        checks.append(Check(N_("verify.javascript"), Status.FAIL if js else Status.OK, details=js))

        if options.remove_annotations:
            annots = sum(1 for page in doc for _ in page.annots() or [])
            checks.append(
                Check(N_("verify.annotations"), Status.FAIL if annots else Status.OK, {"count": annots})
            )

        checks.append(Check(N_("verify.sha256"), Status.INFO, {"hash": sha256}))
    finally:
        doc.close()
    return Report(output, checks)
