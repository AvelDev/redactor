"""Save and restore a redaction session as ``*.redactor.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from redactor.core.marks import Mark, MarkKind

FORMAT = "redactor-project"
VERSION = 1
SUFFIX = ".redactor.json"


@dataclass
class Project:
    source: Path
    sha256: str
    marks: list[Mark]
    include_text: bool = False
    fill: str = "#000000"
    label: str = ""


def save(project: Project, path: str | Path) -> None:
    data = {
        "format": FORMAT,
        "version": VERSION,
        "source": {"path": str(project.source), "sha256": project.sha256},
        "include_text": project.include_text,
        "options": {"fill": project.fill, "label": project.label},
        "marks": [
            {
                "id": m.id,
                "page": m.page,
                "kind": m.kind.value,
                "rects": [list(r) for r in m.rects],
                "group": m.group,
                "color": m.color,
                "label": m.label,
                **({"text": m.text} if project.include_text else {}),
            }
            for m in project.marks
        ],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ProjectError(ValueError):
    pass


def load(path: str | Path) -> Project:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ProjectError(str(e)) from e
    if data.get("format") != FORMAT or data.get("version", 0) > VERSION:
        raise ProjectError("format")
    source = Path(data["source"]["path"])
    if not source.is_absolute():
        source = (Path(path).parent / source).resolve()
    marks = [
        Mark(
            page=int(m["page"]),
            rects=tuple(tuple(float(v) for v in r) for r in m["rects"]),  # type: ignore[misc]
            kind=MarkKind(m["kind"]),
            text=m.get("text", ""),
            group=m.get("group", ""),
            color=m.get("color"),
            label=m.get("label"),
            id=m["id"],
        )
        for m in data["marks"]
    ]
    opts = data.get("options", {})
    return Project(
        source,
        data["source"]["sha256"],
        marks,
        bool(data.get("include_text")),
        opts.get("fill", "#000000"),
        opts.get("label", ""),
    )
