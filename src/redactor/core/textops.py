"""Turn text matches and mouse selections into mark rectangles."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from redactor.core.document import PageText, PdfDocument, merge_char_boxes
from redactor.core.marks import Mark, MarkKind, Rect
from redactor.core.patterns import Match, find_patterns, find_query

CharPos = tuple[int, int]  # (line index, char index)


def match_rect(page_text: PageText, line_index: int, match: Match) -> Rect:
    boxes = page_text.lines[line_index].boxes[match.start : match.end]
    return merge_char_boxes(boxes)


def _scan(
    doc: PdfDocument,
    pages: Iterable[int],
    finder: Callable[[str], Iterator[Match]],
    kind: MarkKind,
) -> list[Mark]:
    marks: list[Mark] = []
    for p in pages:
        pt = doc.text(p)
        for li, line in enumerate(pt.lines):
            for m in finder(line.text):
                marks.append(
                    Mark(page=p, rects=(match_rect(pt, li, m),), kind=kind, text=m.text, group=m.group)
                )
    return marks


def scan_patterns(doc: PdfDocument, pages: Iterable[int], keys: list[str]) -> list[Mark]:
    return _scan(doc, pages, lambda t: find_patterns(t, keys), MarkKind.PATTERN)


def scan_query(
    doc: PdfDocument, pages: Iterable[int], query: str, *, regex: bool, case_sensitive: bool
) -> list[Mark]:
    return _scan(
        doc,
        pages,
        lambda t: find_query(t, query, regex=regex, case_sensitive=case_sensitive),
        MarkKind.SEARCH,
    )


def _distance(box: Rect, x: float, y: float) -> float:
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    return dx * dx + 4 * dy * dy  # vertical distance weighs more: stay on the line


def char_at(page_text: PageText, x: float, y: float) -> CharPos | None:
    best: CharPos | None = None
    best_d = float("inf")
    for li, line in enumerate(page_text.lines):
        for ci, box in enumerate(line.boxes):
            d = _distance(box, x, y)
            if d < best_d:
                best, best_d = (li, ci), d
    return best


def _expand_word(text: str, ci: int, forward: bool) -> int:
    if forward:
        while ci + 1 < len(text) and not text[ci + 1].isspace():
            ci += 1
    else:
        while ci > 0 and not text[ci - 1].isspace():
            ci -= 1
    return ci


def select_range(
    page_text: PageText, a: CharPos, b: CharPos, *, words: bool = False
) -> tuple[list[Rect], str]:
    """Rectangles (one per line) and text covering characters from ``a`` to ``b`` inclusive."""
    start, end = sorted((a, b))
    if words:
        start = (start[0], _expand_word(page_text.lines[start[0]].text, start[1], False))
        end = (end[0], _expand_word(page_text.lines[end[0]].text, end[1], True))
    rects: list[Rect] = []
    parts: list[str] = []
    for li in range(start[0], end[0] + 1):
        line = page_text.lines[li]
        c0 = start[1] if li == start[0] else 0
        c1 = end[1] if li == end[0] else len(line.text) - 1
        while c0 <= c1 and line.text[c0].isspace():
            c0 += 1
        while c1 >= c0 and line.text[c1].isspace():
            c1 -= 1
        if c0 > c1:
            continue
        rects.append(merge_char_boxes(line.boxes[c0 : c1 + 1]))
        parts.append(line.text[c0 : c1 + 1])
    return rects, "\n".join(parts)


def _overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def text_in_rect(page_text: PageText, rect: Rect) -> tuple[str, Rect | None]:
    """Text of all characters touching ``rect`` and the union of their boxes.

    Redaction deletes every glyph whose box overlaps the rectangle, so snapping
    the rectangle to that union keeps the black box honest about what vanishes.
    """
    parts: list[str] = []
    boxes: list[Rect] = []
    for line in page_text.lines:
        chars = [
            (c, b) for c, b in zip(line.text, line.boxes, strict=True)
            if not c.isspace() and _overlaps(b, rect)
        ]
        if chars:
            parts.append("".join(c for c, _ in chars))
            boxes.extend(b for _, b in chars)
    if not boxes:
        return "", None
    return "\n".join(parts), merge_char_boxes(boxes)
