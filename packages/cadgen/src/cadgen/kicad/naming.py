"""Names as KiCad gives them: the order it sorts them in, a net's shown name and class.

Shared by the documents cadgen writes and the readers of any KiCad board or schematic.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

__all__ = ["GENERATOR", "GENERATOR_VERSION", "natural", "netclass_of", "project_netclasses", "unescape_net_name"]

#: What a document cadgen writes says made it, and the KiCad version it is written for.
GENERATOR = "cadgen"
GENERATOR_VERSION = "10.0"

_ESCAPES = {
    "slash": "/", "backslash": "\\", "lt": "<", "gt": ">", "colon": ":", "dblquote": '"', "quote": "'",
    "bar": "|", "comma": ",", "tab": "\t", "return": "\n", "space": " ", "dollar": "$", "brace": "{",
}


def natural(text: str) -> tuple:
    """A sort key that orders ``R2`` before ``R10``; total, so any two texts compare."""
    return tuple((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk) for chunk in re.split(r"(\d+)", str(text)) if chunk)


def unescape_net_name(name: str) -> str:
    """A net's name as KiCad shows it: ``TX{slash}RX`` is ``TX/RX``."""
    return re.sub(r"\{([a-z]+)\}", lambda match: _ESCAPES.get(match.group(1), match.group(0)), str(name))


def project_netclasses(project: Path | None) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """A project's net class assignments and patterns (``.kicad_pro``'s ``net_settings``)."""
    if project is None or not project.is_file():
        return {}, []
    try:
        settings = json.loads(project.read_text(encoding="utf-8")).get("net_settings") or {}
    except (OSError, ValueError, AttributeError):
        return {}, []
    assigned: dict[str, str] = {}
    for net, classes in (settings.get("netclass_assignments") or {}).items():
        name = classes[0] if isinstance(classes, list) and classes else classes
        if isinstance(name, str) and name:
            assigned[unescape_net_name(net)] = name
    patterns = [
        (str(entry.get("pattern", "")), str(entry.get("netclass", "")))
        for entry in settings.get("netclass_patterns") or []
        if isinstance(entry, dict) and entry.get("pattern") and entry.get("netclass")
    ]
    return assigned, patterns


def netclass_of(name: str, assigned: Mapping[str, str], patterns: Sequence[tuple[str, str]]) -> str:
    """The class of the net ``name``, from :func:`project_netclasses`' assignments and patterns."""
    if name in assigned:
        return assigned[name]
    for pattern, netclass in patterns:
        if pattern == name or fnmatch.fnmatchcase(name.lower(), pattern.lower()):
            return netclass
        try:
            if re.fullmatch(pattern, name, re.IGNORECASE):
                return netclass
        except re.error:
            continue
    return "Default"
