"""Markdown helpers for tests that read a reference page's tables."""

from __future__ import annotations


def section(text: str, heading: str) -> str:
    """The ``## heading`` section of ``text``: from its heading to the next ``## `` heading (or the end).

    Independent of the order of the page's sections, so moving a section never hands one test's table
    another's rows.
    """
    lines = text.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.rstrip("\n") == heading)
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "".join(lines[start:end])
