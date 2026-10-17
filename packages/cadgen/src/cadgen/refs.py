"""Every ref resolves here: ``read_scene``'s, ``cadgen store where``'s, a mate's ends and
axis, a snapshot's focus and hide, a clip's targets and a material's assignments.

A ref (``cad_ref_syntax``) names a node of a tree -- by its token (``o:…``) or by its
name -- and, for a leaf, may name one of its elements: ``#housing/f:bracket.cut1.2``.
:func:`resolve` answers which node and which element, the same way for every caller,
from a :class:`Space`: the tree's nodes with their names and, for a leaf, its elements'
names and, on demand, their geometric tokens.

1. A file prefix (``STEP/plate.step#…``) must name the space's document.
2. A node is its token, else its name: a name one node has means that node, a name
   several share is refused with the numbered aliases (``#arm_1``, ``#arm_2``) that each
   mean one (``label_refs.TreeNames``), an unknown name is refused. A bare element name
   (``#f:…``) means the element of a document's one leaf.
3. An element is found by its name among the leaf's: its lineage, or the geometric token
   of an element no lineage names. A ref by geometric token (``f:`` and twelve
   hexadecimal characters) that names no element so finds the element of the leaf with
   that geometry, whatever names it now: the fallback matcher
   (``_internal/geometric_tokens.py``), measured only when a ref asks for it.

Nothing here reads the store or imports the kernel; what a space knows of its elements
is what its owner hands it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from cadgen.cad_ref_syntax import (
    ELEMENT_SELECTOR_RE,
    MATE_SELECTOR_RE,
    OCCURRENCE_SELECTOR_RE,
    element_kind,
    ref_prefix_names,
    split_cad_ref,
    split_element_ref,
)
from cadgen.label_refs import TreeNames

__all__ = ["Resolved", "Space", "UnknownNode", "descriptor_nodes", "descriptor_space", "locate", "resolve"]

_PLURAL = {"face": "faces", "edge": "edges", "vertex": "vertices"}


class UnknownNode(ValueError):
    """A token or a name no node of the space has; ``token`` is the token, None for a name."""

    def __init__(self, message: str, *, token: str | None = None) -> None:
        super().__init__(message)
        self.token = token


@dataclass(frozen=True)
class Resolved:
    """What a ref names: a node, by its token, and for an element its kind, its ordinal
    in the leaf's component (from 1) and its name there."""

    occurrence: str
    kind: str = "occurrence"
    ordinal: int | None = None
    element: str | None = None


class Space:
    """What refs resolve in: ``members``, every node's leaf occurrences by its token, in
    tree order (a leaf's: itself), and ``names``, the nodes each name names, in tree order.
    For a leaf, ``elements(token, kind)`` lists its elements' names by ordinal (``kind``:
    ``"face"``, ``"edge"`` or ``"vertex"``) and ``tokens(token, kind)`` their geometric
    tokens, asked only for a ref by geometry no name matched; a space with neither resolves
    nodes alone. ``document`` is the file a ref's prefix must name (None: no prefix is
    taken), and ``explain(token, kind)`` may say why an element is unknown there."""

    def __init__(
        self,
        members: Mapping[str, Sequence[str]],
        names: Mapping[str, Sequence[str]],
        *,
        elements: Callable[[str, str], Sequence[str | None]] | None = None,
        tokens: Callable[[str, str], Sequence[str]] | None = None,
        document: str | None = None,
        explain: Callable[[str, str], str | None] | None = None,
    ) -> None:
        self.members = {token: tuple(leaves) for token, leaves in members.items()}
        self.document = document
        self._names = TreeNames(names)
        self._elements, self._tokens, self._explain = elements, tokens, explain

    def leaves(self) -> list[str]:
        return [token for token, leaves in self.members.items() if leaves == (token,)]

    def is_leaf(self, token: str) -> bool:
        return self.members.get(token) == (token,)

    def node(self, owner: str) -> str:
        """The token of the node ``owner`` -- a token, or a name -- names."""
        owner = owner.strip()
        if OCCURRENCE_SELECTOR_RE.match(owner):
            if owner not in self.members:
                raise UnknownNode(f"unknown occurrence: #{owner}", token=owner)
            return owner
        found = self._names.resolve(owner)  # a name several nodes share raises LabelResolutionError
        if found is None:
            raise UnknownNode(f"unknown part label '{owner}'; run snapshot --mode list to see part names")
        return found

    def labels(self) -> list[str]:
        """Every name that names one node, numbered aliases included."""
        return self._names.names()


def locate(ref: str, space: Space) -> tuple[str, str | None]:
    """The node ``ref`` names in ``space`` and the element name it then gives (None for a
    node): what :func:`resolve` resolves an element in, without looking at it."""
    prefix, text = split_cad_ref(ref)
    if prefix and (space.document is None or not ref_prefix_names(prefix, space.document)):
        raise ValueError(f"{ref!r} names the file {prefix!r}, not {space.document!r}")
    text = text.strip()
    text = text[1:] if text.startswith("#") else text
    if not text or MATE_SELECTOR_RE.match(text):
        raise ValueError(f"invalid reference: {ref!r}; pass one occurrence or element ref")
    pair = split_element_ref(text)
    if pair is not None:
        return space.node(pair[0]), pair[1]
    if ELEMENT_SELECTOR_RE.match(text):
        leaves = space.leaves()
        if len(leaves) != 1:
            raise ValueError(f"{ref!r} needs an occurrence token in an assembly")
        return leaves[0], text
    return space.node(text), None


def resolve(ref: str, space: Space) -> Resolved:
    """The node, and element, ``ref`` names in ``space`` (see the module). ``ValueError``
    says why it names nothing there: :class:`UnknownNode` for a token or a name no node has,
    ``label_refs.LabelResolutionError`` for a name several share."""
    occurrence, element = locate(ref, space)
    if element is None:
        return Resolved(occurrence)
    kind = element_kind(element)
    if not space.is_leaf(occurrence):
        raise ValueError(f"#{occurrence} is a group; enumerate its entities or specify a leaf occurrence")
    names = list(space._elements(occurrence, kind)) if space._elements is not None else []
    if element in names:
        return Resolved(occurrence, kind, names.index(element) + 1, element)
    from cadgen._internal.geometric_tokens import TOKEN_RE

    if TOKEN_RE.fullmatch(element):
        tokens = list(space._tokens(occurrence, kind)) if space._tokens is not None else []
        if element in tokens:
            ordinal = tokens.index(element) + 1
            named = names[ordinal - 1] if ordinal <= len(names) else None
            return Resolved(occurrence, kind, ordinal, named or element)
    elif space._explain is not None and (reason := space._explain(occurrence, kind)) is not None:
        raise ValueError(f"unknown {kind} reference: {ref!r}: {reason}")
    raise ValueError(f"unknown {kind} reference: {ref!r} ({len(names)} {_PLURAL[kind]} in #{occurrence})")


def descriptor_nodes(descriptor: Mapping[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """A flattened tree's (an ``assembly.json``'s) every node's leaf members and every
    name's nodes, in tree order: what a :class:`Space` over it holds.

    A node is named by its tree node; a leaf also by its occurrence row, which differs
    only for a single-part document, whose one node is the root (named for the document)
    and the part (named by its author's label): both names resolve to it."""
    rows = {str(item.get("id") or ""): str(item.get("name") or "").strip()
            for item in descriptor.get("occurrences") or [] if isinstance(item, Mapping)}
    members: dict[str, list[str]] = {}
    names: dict[str, list[str]] = {}

    def visit(node: object) -> list[str]:
        if not isinstance(node, Mapping):
            return []
        node_id = str(node.get("id") or "").strip()
        # Names are taken in tree order (a node before its children), the order a
        # shared name's numbered aliases follow in every API that reads a #name.
        name = str(node.get("name") or "").strip()
        if node_id and name:
            names.setdefault(name, []).append(node_id)
        row_name = rows.get(node_id, "")
        if node_id and row_name and row_name != name:
            names.setdefault(row_name, []).append(node_id)
        found = [node_id] if node_id in rows else []
        for child in node.get("children") or []:
            found.extend(visit(child))
        if node_id:
            members[node_id] = found
        return found

    assembly = descriptor.get("assembly")
    visit(assembly.get("root") if isinstance(assembly, Mapping) else None)
    return members, names


def descriptor_space(descriptor: Mapping[str, Any], **elements: Any) -> Space:
    """A :class:`Space` over a flattened tree's nodes (:func:`descriptor_nodes`); the
    keywords are its elements' (``elements``, ``tokens``, ``document``, ``explain``)."""
    members, names = descriptor_nodes(descriptor)
    return Space(members, names, **elements)
