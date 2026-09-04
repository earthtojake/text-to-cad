"""What a GROUP occurrence ref means, for every command that accepts one.

ONE document, TWO occurrence namespaces (see :mod:`cadgen.assembly_lookup`): the
assembly.json's instance tree, and the flat selector index whose rows are that tree's
LEAVES, because only a leaf owns geometry. A subassembly node -- ``#o1.1``, the very
kind of ref a kinematics mate names and poses without complaint -- carries no row, so
every command that resolved refs against rows alone refused it as "unknown".

An occurrence id IS its path through the tree, so a group is an id PREFIX of its
subtree, exactly as kinematicsModule.js and cadScene.js treat it. Everything here is
derived from the leaf ids on that basis rather than read out of ``assembly.json``,
which keeps it in step with how the runtime resolves a group instead of introducing
another opinion about what the tree contains.

This module exists because there were about to be two copies of that opinion --
``snapshot``'s and ``step inspect``'s -- and the interesting part is the near-miss
hint, which is exactly the kind of text that drifts unnoticed between two
implementations until the two commands disagree about what a document contains.
"""

from __future__ import annotations

from cadgen import lookup

# How many sibling refs an "unknown selector" error names before it stops listing. A
# 160-part assembly's child list is not a hint, it is a wall of text.
OCCURRENCE_NEAR_MISS_LIMIT = 12


class UnknownOccurrenceSelector(ValueError):
    """A ref that names neither a rendered occurrence nor a group of them.

    Carries the full message, near-miss hint included, so each caller re-raises it as
    its own error type without re-deriving the wording.
    """


def occurrence_sort_key(occurrence_id: str) -> tuple[int, ...]:
    """Order occurrence ids by their numeric PATH, so o1.1.10 follows o1.1.2.

    Mirrors ``label_refs._occurrence_sort_key``; these lists are user-facing, and
    lexicographic order reads as arbitrary to anyone holding the instance tree.
    """
    body = str(occurrence_id or "").lstrip("oO")
    parts: list[int] = []
    for chunk in body.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            return (1 << 30,)
    return tuple(parts)


def occurrence_group_ids(selector_index: lookup.SelectorIndex) -> set[str]:
    """Every instance-tree node that is NOT itself a rendered occurrence.

    Derived from the leaf ids: an occurrence id IS its path through the tree, so the
    strict prefixes of a leaf are exactly its ancestors.
    """
    leaves = set(selector_index.occurrence_by_id)
    groups: set[str] = set()
    for occurrence_id in leaves:
        parts = str(occurrence_id).split(".")
        for depth in range(1, len(parts)):
            groups.add(".".join(parts[:depth]))
    return groups - leaves


def occurrence_group_members(
    selector: str, selector_index: lookup.SelectorIndex
) -> list[str]:
    """The rendered occurrences under a group ref, in tree order. Empty if it has none."""
    prefix = f"{selector}."
    return sorted(
        (
            occurrence_id
            for occurrence_id in selector_index.occurrence_by_id
            if occurrence_id.startswith(prefix)
        ),
        key=occurrence_sort_key,
    )


def occurrence_near_miss_hint(selector: str, selector_index: lookup.SelectorIndex) -> str:
    """What DOES exist near a ref that does not.

    A bare "unknown selector: o1.4" leaves the caller guessing whether the document has no
    such branch or whether they mistyped a depth. This walks up to the deepest ancestor of
    the ref that the document really has and names that node's children.
    """
    known = set(selector_index.occurrence_by_id) | occurrence_group_ids(selector_index)
    if not known:
        return "this document declares no part/subassembly occurrences"
    parts = str(selector).split(".")
    ancestor = ""
    for depth in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:depth])
        if candidate in known:
            ancestor = candidate
            break
    scope = f"{ancestor}." if ancestor else ""
    child_depth = len(ancestor.split(".")) + 1 if ancestor else 1
    siblings = sorted(
        {
            occurrence_id
            for occurrence_id in known
            if occurrence_id.startswith(scope) and len(occurrence_id.split(".")) == child_depth
        },
        key=occurrence_sort_key,
    )
    if not siblings:
        return "this document declares no part/subassembly occurrences"
    listed = ", ".join(siblings[:OCCURRENCE_NEAR_MISS_LIMIT])
    if len(siblings) > OCCURRENCE_NEAR_MISS_LIMIT:
        listed += f", ... ({len(siblings)} total)"
    if ancestor:
        return f"{ancestor} does exist, and holds: {listed}"
    return f"known occurrence refs start at: {listed}"


def expand_occurrence_selector(
    selector: str, *, selector_index: lookup.SelectorIndex | None, source_label: str
) -> list[str]:
    """The rendered occurrences a selection ref covers.

    An exact leaf returns itself. A group expands to its subtree's leaves, sorted in
    tree order. Anything else raises :class:`UnknownOccurrenceSelector` with the
    near-miss hint attached.

    Expanded at the front door rather than passed through: the resolved job then says
    which parts it means, and a group with nothing rendered under it fails as a command
    error instead of as an empty answer.

    With no selector index (no topology to check against) the ref travels unchanged, as
    it always has.
    """
    if selector_index is None:
        return [selector]
    if selector in selector_index.occurrence_by_id:
        return [selector]
    members = occurrence_group_members(selector, selector_index)
    if members:
        return members
    raise UnknownOccurrenceSelector(
        f"{source_label} references unknown part/subassembly occurrence selector: "
        f"{selector}; {occurrence_near_miss_hint(selector, selector_index)}"
    )
