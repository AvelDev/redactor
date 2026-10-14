"""Redaction marks: what the user wants removed, in page coordinates (PDF points)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from enum import StrEnum

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in displayed page space


class MarkKind(StrEnum):
    TEXT = "text"  # mouse text selection
    AREA = "area"  # free rectangle
    SEARCH = "search"  # phrase / regex search hit
    PATTERN = "pattern"  # built-in data pattern hit (PESEL, IBAN, ...)


@dataclass(frozen=True)
class Mark:
    page: int
    rects: tuple[Rect, ...]
    kind: MarkKind
    text: str = ""  # the redacted content; sensitive, kept in memory only by default
    group: str = ""  # pattern key or search query, used for grouping in the UI
    color: str | None = None  # "#rrggbb" override of the default fill
    label: str | None = None  # override of the default overlay label
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def with_rects(self, rects: tuple[Rect, ...]) -> Mark:
        return replace(self, rects=rects)

    def bounds(self) -> Rect:
        xs0, ys0, xs1, ys1 = zip(*self.rects, strict=True)
        return min(xs0), min(ys0), max(xs1), max(ys1)


def normalize_rect(r: Rect) -> Rect:
    x0, y0, x1, y1 = r
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    return tuple(int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
