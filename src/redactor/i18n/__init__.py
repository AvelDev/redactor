"""Tiny JSON-based i18n.

Every user-visible string goes through ``tr("some.key", **params)``. Keys that
are stored in data structures and translated later are wrapped in ``N_(...)``
so ``redactor.i18n.check`` can find them. Set ``REDACTOR_I18N_DEBUG=1`` to show
raw keys in the UI and spot anything that bypasses translation.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

LANG_DIR = Path(__file__).parent
LANGUAGES = {"en": "English", "pl": "Polski"}
FALLBACK = "en"

# Plural categories per language; ``tr_n("x", n)`` looks up ``x.<category>``.
PLURAL_FORMS = {"en": ("one", "other"), "pl": ("one", "few", "many")}


def plural_category(lang: str, n: int) -> str:
    if lang == "pl":
        if n == 1:
            return "one"
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return "few"
        return "many"
    return "one" if n == 1 else "other"

_current = FALLBACK


@cache
def load(lang: str) -> dict[str, str]:
    with open(LANG_DIR / f"{lang}.json", encoding="utf-8") as f:
        return json.load(f)


def set_language(lang: str) -> None:
    global _current
    _current = lang if lang in LANGUAGES else FALLBACK


def language() -> str:
    return _current


def system_language() -> str:
    from PySide6.QtCore import QLocale

    name = QLocale.system().name().split("_")[0]
    return name if name in LANGUAGES else FALLBACK


def tr(key: str, **params: object) -> str:
    if os.environ.get("REDACTOR_I18N_DEBUG"):
        return key
    text = load(_current).get(key) or load(FALLBACK).get(key)
    if text is None:
        return f"⟦{key}⟧"
    return text.format(**params) if params else text


def tr_n(key: str, n: int, **params: object) -> str:
    """Translate with the plural form for ``n``; ``{n}`` is available in the text."""
    if os.environ.get("REDACTOR_I18N_DEBUG"):
        return key
    for lang in (_current, FALLBACK):
        text = load(lang).get(f"{key}.{plural_category(lang, n)}")
        if text is not None:
            return text.format(n=n, **params)
    return f"⟦{key}⟧"


def N_(key: str) -> str:  # noqa: N802 - gettext convention
    """Mark a key for extraction without translating it yet."""
    return key
