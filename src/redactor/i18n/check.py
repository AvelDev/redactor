"""Translation completeness checker.

Usage: ``python -m redactor.i18n.check`` (exit code 1 on errors).

Errors: keys missing in a language, empty values, mismatched ``{placeholders}``,
keys used in code (``tr("...")`` / ``tr_n("...")`` / ``N_("...")``) but absent
from the files, plural keys without every plural form of the language.
Warnings: keys defined in the files but never used in code.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from redactor.i18n import FALLBACK, LANGUAGES, PLURAL_FORMS, load

SRC = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def used_keys(root: Path = SRC, funcs: tuple[str, ...] = ("tr", "N_")) -> dict[str, list[str]]:
    """Map of string literal keys passed to the given functions -> source locations."""
    found: dict[str, list[str]] = {}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in funcs
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                loc = f"{path.relative_to(root.parent)}:{node.lineno}"
                found.setdefault(node.args[0].value, []).append(loc)
    return found


def _split(table: dict[str, str], lang: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Separate plain keys from plural keys (``base.<form>``) of one language."""
    plain: dict[str, str] = {}
    plural: dict[str, dict[str, str]] = {}
    all_forms = {f for forms in PLURAL_FORMS.values() for f in forms}
    for key, value in table.items():
        base, _, form = key.rpartition(".")
        if base and form in all_forms:
            plural.setdefault(base, {})[form] = value
        else:
            plain[key] = value
    return plain, plural


def check() -> Result:
    res = Result()
    split = {lang: _split(load(lang), lang) for lang in LANGUAGES}
    ref_plain, ref_plural = split[FALLBACK]
    all_plain = set().union(*(p.keys() for p, _ in split.values()))
    all_plural = set().union(*(q.keys() for _, q in split.values()))

    for lang, (plain, plural) in split.items():
        for key in sorted(all_plain - plain.keys()):
            res.errors.append(f"[{lang}] missing key: {key}")
        for key in sorted(all_plural - plural.keys()):
            res.errors.append(f"[{lang}] missing plural key: {key}")
        for key, forms in sorted(plural.items()):
            expected = set(PLURAL_FORMS[lang])
            if set(forms) != expected:
                res.errors.append(
                    f"[{lang}] plural forms of {key}: have {sorted(forms)}, need {sorted(expected)}"
                )
        entries = list(plain.items()) + [
            (f"{base}.{form}", v) for base, forms in plural.items() for form, v in forms.items()
        ]
        for key, value in sorted(entries):
            if not value.strip():
                res.errors.append(f"[{lang}] empty value: {key}")
        if lang == FALLBACK:
            continue
        for key, value in plain.items():
            if key in ref_plain:
                ours = set(PLACEHOLDER.findall(value))
                theirs = set(PLACEHOLDER.findall(ref_plain[key]))
                if ours != theirs:
                    res.errors.append(
                        f"[{lang}] placeholders differ in {key}: {sorted(ours)} vs {sorted(theirs)}"
                    )
        for base, forms in plural.items():
            theirs = set().union(*(set(PLACEHOLDER.findall(v)) for v in ref_plural.get(base, {}).values()))
            for form, value in forms.items():
                ours = set(PLACEHOLDER.findall(value))
                if not ours <= theirs | {"n"}:
                    res.errors.append(
                        f"[{lang}] placeholders differ in {base}.{form}: {sorted(ours)} vs {sorted(theirs)}"
                    )

    used = used_keys(funcs=("tr", "N_"))
    used_plural = used_keys(funcs=("tr_n",))
    for key in sorted(used.keys() - all_plain):
        res.errors.append(f"key used in code but not translated: {key} ({used[key][0]})")
    for key in sorted(used_plural.keys() - all_plural):
        res.errors.append(f"plural key used in code but not translated: {key} ({used_plural[key][0]})")
    for key in sorted(all_plain - used.keys()):
        res.warnings.append(f"key not used in code: {key}")
    for key in sorted(all_plural - used_plural.keys()):
        res.warnings.append(f"plural key not used in code: {key}")
    return res


def main() -> int:
    res = check()
    counts = ", ".join(f"{lang}: {len(load(lang))}" for lang in LANGUAGES)
    print(f"Translations ({counts} keys)")
    for w in res.warnings:
        print(f"  warning  {w}")
    for e in res.errors:
        print(f"  ERROR    {e}")
    print("OK" if not res.errors else f"{len(res.errors)} error(s)")
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main())
