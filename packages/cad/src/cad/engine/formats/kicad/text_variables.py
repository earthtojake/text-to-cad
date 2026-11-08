"""The text variables a board's texts name (``${TITLE}``, ``${REVISION}``, a project's own): its
title block, its file and paper, and the project's ``.kicad_pro`` ``text_variables``.

Pure: reads the parsed board and the project file, nothing else.
"""

from __future__ import annotations

import json
from pathlib import Path

from cad.engine.formats.kicad import sexpr

__all__ = ["title_variables"]


def title_variables(tree: list, *, file_name: str, project: Path | None = None) -> dict[str, str]:
    """What a board text's ``${...}`` names: the title block, the file, the paper, and the
    project's own text variables."""
    paper = sexpr.find(tree, "paper")
    version = str(sexpr.value(tree, "generator_version") or "")
    block = sexpr.find(tree, "title_block") or []
    names = {"title": "TITLE", "date": "ISSUE_DATE", "rev": "REVISION", "company": "COMPANY"}
    values = {"KICAD_VERSION": f"KiCad E.D.A. {version}".strip(), "FILENAME": file_name,
              "PAPER": str(paper[1]) if paper is not None and len(paper) > 1 else "A4",
              "TITLE": "", "ISSUE_DATE": "", "REVISION": "", "COMPANY": ""}
    values.update({f"COMMENT{n}": "" for n in range(1, 10)})
    for entry in block[1:]:
        head = sexpr.head(entry)
        if head in names and len(entry) > 1:
            values[names[head]] = str(entry[1])
        elif head == "comment" and len(entry) > 2:
            values[f"COMMENT{int(sexpr.number(entry[1], 0))}"] = str(entry[2])
    for name, value in _project_variables(project).items():
        values.setdefault(name, value)
    return values


def _project_variables(project: Path | None) -> dict[str, str]:
    """The project's own text variables (``.kicad_pro``'s ``text_variables``)."""
    if project is None or not project.is_file():
        return {}
    try:
        found = json.loads(project.read_text(encoding="utf-8")).get("text_variables") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {str(key): str(value) for key, value in found.items()} if isinstance(found, dict) else {}
