"""What a GROUP occurrence ref means, for every command that accepts one.

ONE document, TWO occurrence namespaces (see :mod:`cadgen.assembly_lookup`): the
tree's instance hierarchy, and the selector index whose rows are that tree's
LEAVES, because only a leaf owns geometry. A subassembly node -- the very kind of
ref a kinematics mate names and poses without complaint -- carries no row, so
every command that resolved refs against rows alone refused it as "unknown".

A token holds no hierarchy (README law 20), so a group's members come from the
tree alone: ``SelectorIndex.members`` maps every node to the leaves beneath it,
filled from the tree's ``leafPartIds`` by
``assembly_lookup.merge_assembly_occurrences``. Every command that accepts a
group ref reads this one copy of that opinion, near-miss hint included: that hint
is exactly the kind of text that drifts unnoticed between two implementations
until two commands disagree about what a document contains.
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


def occurrence_group_ids(selector_index: lookup.SelectorIndex) -> set[str]:
    """Every instance-tree node that is NOT itself a rendered occurrence."""
    return set(selector_index.group_nodes) - set(selector_index.occurrence_by_id)


def occurrence_group_members(
    selector: str, selector_index: lookup.SelectorIndex
) -> list[str]:
    """The rendered occurrences under a group ref, in tree order. Empty if it has none."""
    if selector in selector_index.occurrence_by_id:
        return []
    return [leaf for leaf in selector_index.members.get(selector, []) if leaf in selector_index.occurrence_by_id]


def _shown(selector_index: lookup.SelectorIndex, node_id: str) -> str:
    row = selector_index.occurrence_by_id.get(node_id) or selector_index.group_nodes.get(node_id) or {}
    name = str(row.get("name") or "").strip()
    return f"#{node_id} {name}" if name and name != node_id else f"#{node_id}"


def occurrence_near_miss_hint(selector: str, selector_index: lookup.SelectorIndex) -> str:
    """What DOES exist near a ref that does not.

    A bare "unknown selector" leaves the caller guessing what the document holds. A ref
    carries no position to walk up from, so this names the root's children -- the parts
    and subassemblies a person would pick next -- with their names.
    """
    known = set(selector_index.occurrence_by_id) | set(selector_index.group_nodes)
    if not known:
        return "this document declares no part/subassembly occurrences"
    # ``members`` is in tree order, the root first; the root's children are the nodes it
    # alone contains.
    ordered = [node_id for node_id in selector_index.members if node_id in known]
    root = ordered[0] if ordered else ""
    containers = {node_id: set(leaves) for node_id, leaves in selector_index.members.items() if node_id in known}
    top = [node_id for node_id in ordered if node_id != root and not any(
        other not in (root, node_id) and containers[node_id] <= containers[other] and containers[node_id] != containers[other]
        for other in containers
    )] or [node_id for node_id in ordered if node_id != root]
    listed = ", ".join(_shown(selector_index, node_id) for node_id in top[:OCCURRENCE_NEAR_MISS_LIMIT])
    if len(top) > OCCURRENCE_NEAR_MISS_LIMIT:
        listed += f", ... ({len(top)} total)"
    if not listed:
        return "this document declares no part/subassembly occurrences"
    return f"the document holds: {listed}"


def expand_occurrence_selector(
    selector: str, *, selector_index: lookup.SelectorIndex, source_label: str
) -> list[str]:
    """The rendered occurrences a selection ref covers.

    An exact leaf returns itself. A group expands to its subtree's leaves, in tree order.
    Anything else raises :class:`UnknownOccurrenceSelector` with the near-miss hint
    attached.

    Expanded at the front door rather than passed through: the resolved job then says
    which parts it means, and a group with nothing rendered under it fails as a command
    error instead of as an empty answer.
    """
    if selector in selector_index.occurrence_by_id:
        return [selector]
    members = occurrence_group_members(selector, selector_index)
    if members:
        return members
    raise UnknownOccurrenceSelector(
        f"{source_label} references unknown part/subassembly occurrence selector: "
        f"{selector}; {occurrence_near_miss_hint(selector, selector_index)}"
    )
