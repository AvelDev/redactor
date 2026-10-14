import json

import pytest

from redactor import i18n
from redactor.i18n import check, plural_category, tr, tr_n


def test_translations_are_complete():
    res = check.check()
    assert res.errors == []
    assert res.warnings == []


@pytest.mark.parametrize(
    ("n", "form"), [(1, "one"), (2, "few"), (4, "few"), (5, "many"), (12, "many"), (22, "few"), (25, "many")]
)
def test_polish_plurals(n, form):
    assert plural_category("pl", n) == form


def test_tr_n_and_fallback():
    i18n.set_language("pl")
    try:
        assert tr_n("marks.count", 1) == "1 oznaczenie"
        assert tr_n("marks.count", 3) == "3 oznaczenia"
        assert tr_n("marks.count", 5) == "5 oznaczeń"
        assert tr("no.such.key").startswith("⟦")
    finally:
        i18n.set_language("en")


def test_checker_reports_problems(monkeypatch, tmp_path):
    en = {"a": "A {x}", "b.one": "{n} b", "b.other": "{n} bs", "only.en": "x"}
    pl = {"a": "A {y}", "b.one": "{n} b", "b.few": "{n} b", "c": ""}
    tables = {"en": en, "pl": pl}
    monkeypatch.setattr(check, "load", lambda lang: tables[lang])
    errors = "\n".join(check.check().errors)
    assert "[pl] missing key: only.en" in errors
    assert "[en] missing key: c" in errors
    assert "[pl] empty value: c" in errors
    assert "placeholders differ in a" in errors
    assert "plural forms of b" in errors  # Polish lacks "many"
    assert json.dumps(en)  # tables are plain JSON-able data
