"""Resolve build123d part labels used as selector refs.

`#o1.12.f19` names a face by occurrence path. This module lets `#servo_end_plate.f19` name
the same face by the part's label, which is what the author actually wrote in the generator
and what `snapshot --mode list` already prints beside every ref.

Labels are surface syntax only. Everything resolves to the numeric form here, before any
selector crosses into a render job, an artifact, or emitted JSON, so the wire format is
unchanged and no renderer learns about labels.

Duplicates are allowed, because they are legitimate: a motorbike has two wheels and both
rims are honestly labelled `cast_rim:5spoke`. Each duplicate gets a numbered alias in
occurrence-tree order (`cast_rim:5spoke_1`, `_2`), and the bare shared label resolves to
nothing -- it raises, listing the numbered candidates. Silently picking the first match would
render the wrong wheel and look like it worked.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from cadgen.cad_ref_syntax import LABEL_SELECTOR_RE, parse_selector


AMBIGUOUS = "__ambiguous__"


class LabelResolutionError(ValueError):
    """A label selector that cannot be turned into exactly one occurrence id."""


def _occurrence_sort_key(occurrence_id: str) -> tuple[int, ...]:
    """Order occurrence ids by their numeric path, so o1.10 follows o1.2 rather than o1.1.

    Lexicographic ordering would number duplicates in an order that looks arbitrary to anyone
    reading the tree, and the numbering is user-facing.
    """
    body = str(occurrence_id or "").lstrip("oO")
    parts: list[int] = []
    for chunk in body.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            return (1 << 30,)
    return tuple(parts)


def _label_candidate(name: object) -> str:
    """The alias a row would claim, or "" when its name cannot be a label.

    A name that cannot round-trip through the grammar is not aliased at all: the row stays
    reachable by its numeric id. That is quieter than inventing a spelling the user cannot
    guess, and it is why rows named `f12` or `o1.4` are skipped rather than mangled.
    """
    text = str(name or "").strip()
    if not text or not LABEL_SELECTOR_RE.match(text):
        return ""
    parsed = parse_selector(text)
    # parse_selector claims numeric forms first, so a name like "f12", "o1" or "m2" comes back
    # as something other than a label and must not be aliased.
    if parsed is None or parsed.selector_type != "label" or parsed.label != text:
        return ""
    return text


def build_label_aliases(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Map label aliases to occurrence ids.

    Returns ``{"aliases": {alias: occurrence_id}, "ambiguous": {label: [alias, ...]}}``.
    """
    ordered: list[tuple[str, str]] = []
    for row in rows:
        # `occurrenceId` is the spelling the render package uses for the same
        # field (cadjs/common/cadScene.js reads `part.id || part.occurrenceId`
        # throughout), and buildLabelAliasMap accepts both. Reading only `id`
        # here dropped those rows, so a label the viewer resolves had no alias
        # in the CLI.
        occurrence_id = str(row.get("id") or row.get("occurrenceId") or "").strip()
        if not occurrence_id:
            continue
        candidate = _label_candidate(row.get("name"))
        if not candidate:
            continue
        ordered.append((occurrence_id, candidate))
    ordered.sort(key=lambda item: _occurrence_sort_key(item[0]))

    grouped: dict[str, list[str]] = {}
    for occurrence_id, candidate in ordered:
        grouped.setdefault(candidate, []).append(occurrence_id)

    # Authored names are reserved: if a generator literally labels a part `servo_end_mount_1`,
    # the numbering for a duplicated `servo_end_mount` must skip 1 rather than collide.
    authored = set(grouped)
    aliases: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}

    for candidate, occurrence_ids in grouped.items():
        if len(occurrence_ids) == 1:
            aliases[candidate] = occurrence_ids[0]
            continue
        numbered: list[str] = []
        next_index = 1
        for occurrence_id in occurrence_ids:
            while True:
                alias = f"{candidate}_{next_index}"
                next_index += 1
                if alias not in authored and alias not in aliases:
                    break
            aliases[alias] = occurrence_id
            numbered.append(alias)
        ambiguous[candidate] = numbered

    return {"aliases": aliases, "ambiguous": ambiguous}


def attach_label_aliases(index: Any) -> Any:
    """Return ``index`` with its label aliases computed from its final occurrence rows.

    Called from ``assembly_lookup.index_with_assembly_occurrences``, which is the one place both
    index construction sites funnel through -- attaching anywhere else reopens the two-site gap
    that PR #277 closed.
    """
    if index is None:
        return index
    rows = getattr(index, "occurrences", None)
    if not rows:
        return index
    built = build_label_aliases(rows)
    if not built["aliases"] and not built["ambiguous"]:
        # Nothing to attach, so hand back the very same object. Inputs whose parts carry no
        # usable labels are the common path, and "returned untouched" is a promise the callers
        # (and their tests) rely on literally.
        return index
    from dataclasses import replace

    return replace(index, label_aliases=built)


def label_ref_for_occurrence(alias_map: Mapping[str, Any], occurrence_id: str) -> str:
    """The `#alias` a user should paste for this occurrence, or "" when it has none."""
    aliases = alias_map.get("aliases") if isinstance(alias_map, Mapping) else None
    if not isinstance(aliases, Mapping):
        return ""
    target = str(occurrence_id or "").strip()
    for alias, mapped in aliases.items():
        if mapped == target:
            return f"#{alias}"
    return ""


def _resolve_label(alias_map: Mapping[str, Any], label: str) -> str:
    aliases = alias_map.get("aliases") if isinstance(alias_map, Mapping) else None
    ambiguous = alias_map.get("ambiguous") if isinstance(alias_map, Mapping) else None
    aliases = aliases if isinstance(aliases, Mapping) else {}
    ambiguous = ambiguous if isinstance(ambiguous, Mapping) else {}

    occurrence_id = aliases.get(label)
    if isinstance(occurrence_id, str) and occurrence_id:
        return occurrence_id

    candidates = ambiguous.get(label)
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        shown = ", ".join(
            f"#{alias} ({aliases.get(alias, '?')})" for alias in candidates
        )
        raise LabelResolutionError(
            f"label '{label}' matches {len(candidates)} occurrences; use one of: {shown}"
        )

    raise LabelResolutionError(
        f"unknown part label '{label}'; run snapshot --mode list to see part names"
    )


def resolve_label_selectors(
    selectors: Iterable[str],
    alias_map: Mapping[str, Any] | None,
) -> list[str]:
    """Rewrite label selectors to their numeric equivalents, leaving everything else alone.

    Numeric and opaque selectors pass through untouched, so every ref that worked before this
    module existed still works and still means exactly what it meant.
    """
    resolved: list[str] = []
    for raw in selectors or []:
        text = str(raw or "").strip()
        if not text:
            continue
        parsed = parse_selector(text)
        if parsed is None or not parsed.label:
            resolved.append(text)
            continue
        if not alias_map:
            raise LabelResolutionError(
                f"label '{parsed.label}' cannot be resolved: this input has no part labels"
            )
        occurrence_id = _resolve_label(alias_map, parsed.label)
        leading_hash = "#" if text.startswith("#") else ""
        if parsed.selector_type == "label":
            resolved.append(f"{leading_hash}{occurrence_id}")
            continue
        kind = _KIND_FOR_TYPE.get(parsed.selector_type, "")
        resolved.append(f"{leading_hash}{occurrence_id}.{kind}{parsed.ordinal}")
    return resolved


_KIND_FOR_TYPE = {"shape": "s", "face": "f", "edge": "e", "vertex": "v"}


def selectors_contain_label(selectors: Iterable[str]) -> bool:
    """True when any selector needs an alias map to resolve."""
    for raw in selectors or []:
        parsed = parse_selector(str(raw or "").strip())
        if parsed is not None and parsed.label:
            return True
    return False
