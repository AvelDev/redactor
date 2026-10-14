import pytest

from redactor.core.patterns import (
    find_patterns,
    find_query,
    valid_iban,
    valid_id_card,
    valid_luhn,
    valid_nip,
    valid_pesel,
    valid_regon,
)


@pytest.mark.parametrize(
    ("fn", "good", "bad"),
    [
        (valid_pesel, "44051401458", "44051401459"),
        (valid_nip, "123-456-32-18", "123-456-32-19"),
        (valid_regon, "123456785", "123456786"),
        (valid_regon, "12345678512347", "12345678512348"),
        (valid_iban, "PL61 1090 1014 0000 0712 1981 2874", "PL61 1090 1014 0000 0712 1981 2875"),
        (valid_id_card, "ABA300000", "ABA300001"),
        (valid_luhn, "4111 1111 1111 1111", "4111 1111 1111 1112"),
    ],
)
def test_validators(fn, good, bad):
    assert fn(good)
    assert not fn(bad)


def test_find_patterns_validates_and_dedupes():
    text = "PESEL 44051401458, zly 44051401459, mail a.b@c.pl, tel. +48 600 123 456, 00-950"
    found = {(m.group, m.text) for m in find_patterns(text, [
        "pattern.pesel", "pattern.email", "pattern.phone", "pattern.postal_code", "pattern.nip",
    ])}
    assert ("pattern.pesel", "44051401458") in found
    assert ("pattern.email", "a.b@c.pl") in found
    assert ("pattern.phone", "+48 600 123 456") in found
    assert ("pattern.postal_code", "00-950") in found
    assert all(t != "44051401459" for _, t in found)


def test_find_query_plain_and_regex():
    assert [m.text for m in find_query("Ala ma ALA", "ala", regex=False, case_sensitive=False)] == ["Ala", "ALA"]
    assert [m.text for m in find_query("a1 b22", r"\d+", regex=True, case_sensitive=True)] == ["1", "22"]
    assert list(find_query("x.y", ".", regex=False, case_sensitive=True))[0].start == 1
