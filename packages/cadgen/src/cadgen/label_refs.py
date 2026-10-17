"""The names of a tree's nodes, as refs read them (``cadgen.refs``, the one resolver).

``#o:4b1f9e2a7c03/f:plate.cut1.2`` names a face by occurrence token; ``#servo_end_plate/
f:plate.cut1.2`` names the same face by the part's label, which is what the author
actually wrote in the generator and what ``snapshot --mode list`` already prints beside
every ref.

Labels are surface syntax only. Every name resolves to its node's token before any
selector crosses into a render job, an artifact, or emitted JSON, so the wire format is
unchanged and no renderer learns about labels.

Duplicates are allowed, because they are legitimate: a motorbike has two wheels and both
rims are honestly labelled `cast_rim:5spoke`. Each duplicate gets a numbered alias in
occurrence-tree order (`cast_rim:5spoke_1`, `_2`), and the bare shared label resolves to
nothing -- it raises, listing the numbered candidates. Silently picking the first match would
render the wrong wheel and look like it worked.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from cadgen.cad_ref_syntax import LABEL_SELECTOR_RE, parse_selector


class LabelResolutionError(ValueError):
    """A label selector that cannot be turned into exactly one occurrence token."""


def _label_candidate(name: object) -> str:
    """The alias a row would claim, or "" when its name cannot be a label.

    A name that cannot round-trip through the grammar is not aliased at all: the row stays
    reachable by its token. That is quieter than inventing a spelling the user cannot
    guess, and it is why a row named like a token or a mate is skipped rather than mangled.
    """
    text = str(name or "").strip()
    if not text or not LABEL_SELECTOR_RE.match(text):
        return ""
    parsed = parse_selector(text)
    # parse_selector claims token forms first, so a name spelled like a token or "m2" comes
    # back as something other than a label and must not be aliased.
    if parsed is None or parsed.selector_type != "label" or parsed.label != text:
        return ""
    return text


def build_label_aliases(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Map label aliases to occurrence tokens.

    Returns ``{"aliases": {alias: occurrence_id}, "ambiguous": {label: [alias, ...]}}``.
    Duplicates are numbered in the order ``rows`` gives them, which is tree order: a token
    carries no position to order by.
    """
    ordered: list[tuple[str, str]] = []
    for row in rows:
        # `occurrenceId` is the spelling the tree uses for the same
        # field, so a row may carry either.
        occurrence_id = str(row.get("id") or row.get("occurrenceId") or "").strip()
        if not occurrence_id:
            continue
        candidate = _label_candidate(row.get("name"))
        if not candidate:
            continue
        ordered.append((occurrence_id, candidate))

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


class TreeNames:
    """The ``#name`` namespace of an instance tree, groups and parts alike: a name means
    the one node it names, and a name several nodes share is refused, listing the numbered
    aliases (``#arm_1``, ``#arm_2``) that each name one. Every ref's names resolve here
    (``cadgen.refs``), so a name means the same node, and a shared one fails the same way,
    wherever it is written."""

    def __init__(self, by_name: Mapping[str, Sequence[str]]):
        self._by_name = {name: tuple(node_ids) for name, node_ids in by_name.items()}
        self._aliases = build_label_aliases(
            {"id": node_id, "name": name} for name, node_ids in self._by_name.items() for node_id in node_ids
        )

    def resolve(self, name: str) -> str | None:
        """The node ``name`` (or a numbered alias) names, None when none does. A name
        several nodes share raises :class:`LabelResolutionError`, listing the numbered
        aliases that each name one."""
        node_ids = self._by_name.get(name, ())
        if len(node_ids) == 1:
            return node_ids[0]
        if not node_ids:
            return self._aliases["aliases"].get(name)
        numbered = self._aliases["ambiguous"].get(name)
        if numbered:
            shown = ", ".join(f"#{alias} ({self._aliases['aliases'][alias]})" for alias in numbered)
        else:  # a name outside the label grammar takes no aliases: its nodes go by token
            shown = ", ".join(f"#{node_id}" for node_id in node_ids)
        raise LabelResolutionError(f"label '{name}' matches {len(node_ids)} occurrences; use one of: {shown}")

    def names(self) -> list[str]:
        """Every name that resolves: each name one node has, and each numbered alias."""
        unique = {name for name, node_ids in self._by_name.items() if len(node_ids) == 1}
        return sorted(unique | set(self._aliases["aliases"]))
