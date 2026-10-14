"""Built-in sensitive-data patterns with checksum validation, plus free search."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from redactor.i18n import N_


def _digits(s: str) -> list[int]:
    return [int(c) for c in s if c.isdigit()]


def valid_pesel(s: str) -> bool:
    d = _digits(s)
    if len(d) != 11:
        return False
    w = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    return (10 - sum(a * b for a, b in zip(w, d, strict=False)) % 10) % 10 == d[10]


def valid_nip(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10:
        return False
    w = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    c = sum(a * b for a, b in zip(w, d, strict=False)) % 11
    return c != 10 and c == d[9]


def valid_regon(s: str) -> bool:
    d = _digits(s)
    if len(d) == 9:
        w = (8, 9, 2, 3, 4, 5, 6, 7)
    elif len(d) == 14:
        w = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
    else:
        return False
    return sum(a * b for a, b in zip(w, d, strict=False)) % 11 % 10 == d[-1]


def valid_iban(s: str) -> bool:
    s = re.sub(r"\s", "", s).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def valid_id_card(s: str) -> bool:
    """Polish ID card: AAA999999, the first digit is the check digit."""
    s = s.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{3}\d{6}", s):
        return False
    vals = [ord(c) - 55 for c in s[:3]] + [int(c) for c in s[3:]]
    w = (7, 3, 1, 9, 7, 3, 1, 7, 3)
    return sum(a * b for a, b in zip(w, vals, strict=True)) % 10 == 0


def valid_luhn(s: str) -> bool:
    d = _digits(s)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(d)):
        if i % 2:
            n *= 2
            n -= 9 if n > 9 else 0
        total += n
    return total % 10 == 0


@dataclass(frozen=True)
class Pattern:
    key: str  # i18n key of the display name; also the stable identifier
    regex: re.Pattern[str]
    validate: Callable[[str], bool] | None = None


_B = r"(?<![\w@.])"  # left boundary that also refuses mid-email / mid-number hits
_E = r"(?![\w@])"

PATTERNS: tuple[Pattern, ...] = (
    Pattern(N_("pattern.pesel"), re.compile(_B + r"\d{11}" + _E), valid_pesel),
    Pattern(
        N_("pattern.nip"),
        re.compile(_B + r"(?:\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3}|\d{10})" + _E),
        valid_nip,
    ),
    Pattern(N_("pattern.regon"), re.compile(_B + r"(?:\d{14}|\d{9})" + _E), valid_regon),
    Pattern(
        N_("pattern.iban"),
        re.compile(_B + r"(?:[A-Z]{2}\s?)?\d{2}(?:\s?[A-Z0-9]{4}){5,7}(?:\s?[A-Z0-9]{1,3})?" + _E),
        lambda s: valid_iban(s if s[:2].isalpha() else "PL" + s),
    ),
    Pattern(
        N_("pattern.card"),
        re.compile(_B + r"\d{4}(?:[ -]?\d{4}){2}[ -]?\d{1,7}" + _E),
        valid_luhn,
    ),
    Pattern(N_("pattern.id_card"), re.compile(_B + r"[A-Z]{3}\s?\d{6}" + _E), valid_id_card),
    Pattern(
        N_("pattern.email"),
        re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}"),
    ),
    Pattern(
        N_("pattern.phone"),
        re.compile(
            r"(?<![\w+])(?:\+48[\s-]?|0048[\s-]?)?(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{2}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2})"
            + _E
        ),
    ),
    Pattern(N_("pattern.postal_code"), re.compile(_B + r"\d{2}-\d{3}" + _E)),
)

PATTERNS_BY_KEY = {p.key: p for p in PATTERNS}


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    text: str
    group: str  # pattern key or the search query


def find_patterns(text: str, keys: list[str]) -> Iterator[Match]:
    taken: list[tuple[int, int]] = []
    for key in keys:
        p = PATTERNS_BY_KEY[key]
        for m in p.regex.finditer(text):
            if p.validate and not p.validate(m.group()):
                continue
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue  # an earlier (more specific) pattern already claimed it
            taken.append((m.start(), m.end()))
            yield Match(m.start(), m.end(), m.group(), key)


def find_query(text: str, query: str, *, regex: bool, case_sensitive: bool) -> Iterator[Match]:
    if not query:
        return
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(query if regex else re.escape(query), flags)
    for m in pattern.finditer(text):
        if m.end() > m.start():
            yield Match(m.start(), m.end(), m.group(), query)
