"""Helpers shared by the URDF and SRDF readers and validators.

The two formats are different languages with different rules, so most of each
reader is rightly its own. What is genuinely common is the plumbing underneath: how a
path is named in a finding, how an XML tag is stripped of its namespace, how a duplicate
is spotted. Those had drifted into near-copies, which is how two spellings of "path
relative to the repo" ended up living side by side.

What deliberately did NOT move here, because the copies are not the same function:
SRDF's ``_local_name``, which also strips a ``ns:`` prefix that this one keeps. See
:func:`local_name` below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET


def display_path(path: Path) -> str:
    """How a file is named in a finding: relative to the cwd when it is under it.

    Findings are read next to the command that produced them, so an absolute path is
    noise; a path outside the tree keeps its absolute form because a bare basename there
    would be ambiguous.
    """
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def local_name(tag: object) -> str:
    """An ElementTree tag without its ``{namespace}`` prefix.

    ElementTree expands ``xmlns`` into ``{uri}tag``, so every tag comparison has to strip
    it first. This does NOT strip a literal ``ns:`` prefix: an unexpanded colon prefix
    means the document declared no such namespace, so the tag is not the one it looks
    like. SRDF keeps its own variant that strips both.
    """
    return str(tag).rsplit("}", 1)[-1]


def children(parent: ET.Element, tag_name: str) -> list[ET.Element]:
    """Child elements whose local name is `tag_name`.

    Namespace-insensitive by way of :func:`local_name`, and it skips comments and
    processing instructions for free -- their tags are callables, never a match.
    """
    return [child for child in list(parent) if local_name(child.tag) == tag_name]


def duplicate_values(values: Iterable[str]) -> list[str]:
    """Values appearing more than once, sorted — the shared half of duplicate checking.

    Only the detection is shared. What each format does about it is not: the URDF and
    SRDF validators add findings under different codes and wordings.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)
