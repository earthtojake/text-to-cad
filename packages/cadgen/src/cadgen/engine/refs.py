"""References to geometry: one grammar that names a part, an assembly or one element of a
document by the names the engine gives them, resolved against a document's structure
(``resolve_structure``, what ``cadgen inspect`` and the viewer read).

A ref is resolved by name in the document as it is now -- the latest build -- never in the one
it was copied from, and nothing of an earlier build is kept: an element a later build moved or
resized resolves to where it is now; one it deleted, or one whose making changed (a feature
started or stopped touching it, so it is named otherwise), fails, naming it and listing what
its atom is named now -- never picking one.

    REF       = [FILE "#"] SELECTOR ("," SELECTOR)*    a bare ELEMENT after an owner is that owner's
    SELECTOR  = OWNER | [OWNER "/"] ELEMENT             no OWNER: the document's root
    OWNER     = SEGMENT ("/" SEGMENT)*                  an occurrence's path from the root, or its last segments
    SEGMENT   = LABEL | LABEL "." N | QUOTED ["." N]    N: the N-th of the siblings so labelled, in order
    ELEMENT   = NAME | ("face" | "edge" | "vertex") " " N    NAME: f:..., e:..., v:... (``trace.ELEMENT_NAME``)

``FILE`` is the document, everything before the first ``#`` (JSON-quoted when it holds one, or a
quote): an on-disk CAD file's absolute path, the last segments of its path, or a document's id
(``ids``; a model's id, which ``python script.py`` prints, or a file's). A source given as a path,
an id or a model must be that document (an absolute ``FILE`` the same file, a relative one the
last segments of its path, an id that id). A script is never a ``FILE``. An occurrence is named by the labels on the
way to it: ``hand/finger.2`` is the second component labelled ``finger`` of ``hand``, a label
its siblings do not share needs no number (``hand/palm``), and an owner may start at any level
(``finger.2``, ``palm``) when what it names is one occurrence. A path whose first segment names the
root is read from the root. A segment is matched as a label first and as ``LABEL.N`` only where no
sibling bears it whole; a label holding ``/``, ``,`` or a quote, or one a plain segment would
misread, is written JSON-quoted (``"M3/M4 screw"``). An element of an assembly's part resolves
from the assembly when one part below it holds it (a document of one part: by the document's
name). A part's elements are numbered by their ``TopExp.MapShapes`` ordinals, the ones its
names, ``faceNames`` and the XBM2 buffer use.

The canonical ref of each thing resolved (``Hit.ref``): the element's name, else its ordinal,
under its part's owner -- the part's label where that names it alone, else its path from the
root -- or, in a document of one part, under the document's name.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

__all__ = ["Hit", "RefError", "Selector", "parse", "path_text", "placed_facts", "resolve_structure"]

_LETTERS = {"f": "face", "e": "edge", "v": "vertex"}
# The trace lineage's lists.
_PLURAL = {"face": "faces", "edge": "edges", "vertex": "vertices"}
_ORDINAL = re.compile(r"(face|edge|vertex)\s*([1-9][0-9]*)")
_INDEXED = re.compile(r"(.+)\.([1-9][0-9]*)", re.S)
_NUMBER = re.compile(r"\.([1-9][0-9]*)")


class RefError(ValueError):
    """A ref that names nothing in the document, or several things where it names one."""


def _element_name() -> Any:
    from cadgen.engine.kernel.trace import ELEMENT_NAME

    return ELEMENT_NAME


# --- the grammar ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """One step of an owner's path: its text as written, or a quoted label and its number."""

    text: str
    quoted: bool = False
    index: int | None = None

    def __str__(self) -> str:
        if not self.quoted:
            return self.text
        return json.dumps(self.text, ensure_ascii=False) + ("" if self.index is None else f".{self.index}")


@dataclass(frozen=True)
class Selector:
    """One selector of a ref: its owner's path (None: the root) and its element (None: the
    owner itself) -- a name, or a kind and an ordinal."""

    owner: tuple[Segment, ...] | None
    element: str | tuple[str, int] | None

    @property
    def kind(self) -> str | None:
        if self.element is None:
            return None
        return self.element[0] if isinstance(self.element, tuple) else _LETTERS[self.element[0]]

    def __str__(self) -> str:
        owner = "/".join(str(segment) for segment in self.owner or ())
        element = "" if self.element is None else _element_text(self.element)
        return "/".join(part for part in (owner, element) if part)


def _element_text(element: str | tuple[str, int]) -> str:
    return element if isinstance(element, str) else f"{element[0]} {element[1]}"


def parse(ref: str) -> tuple[str | None, list[Selector]]:
    """A ref's document (``FILE``, None when it names none) and its selectors (see the module)."""
    if not isinstance(ref, str):
        raise TypeError(f"a ref is a string, not {type(ref).__name__}")
    text = ref.strip()
    if not text:
        raise RefError("an empty ref names nothing")
    file, rest = _file(text)
    rest = rest.strip()
    if not rest:
        raise RefError(f"{ref!r} names a document and nothing in it")
    selectors: list[Selector] = []
    owner: tuple[Segment, ...] | None = None
    for segments in _split(rest, ref):
        found = _selector(segments, ref)
        if found.owner is None and found.element is not None and owner is not None and selectors:
            found = Selector(owner, found.element)  # a bare element after an owner is that owner's
        selectors.append(found)
        owner = found.owner
    return file, selectors


def _file(text: str) -> tuple[str | None, str]:
    if text.startswith("#"):
        return None, text[1:]
    if text.startswith('"'):
        try:
            name, end = json.JSONDecoder().raw_decode(text)
        except ValueError:
            name, end = None, 0
        if isinstance(name, str) and text[end:end + 1] == "#":
            return name, text[end + 1:]
    head, sep, tail = text.partition("#")
    if sep and head and '"' not in head:
        return head.strip(), tail
    return None, text


def _split(text: str, ref: str) -> list[list[Segment]]:
    """The selectors of ``text``, each its segments: ``,`` and ``/`` separate them outside a
    quoted segment."""
    selectors: list[list[Segment]] = []
    segments: list[Segment] = []
    at, size = 0, len(text)
    while True:
        while at < size and text[at] in " \t":
            at += 1
        if at < size and text[at] == '"':
            try:
                label, end = json.JSONDecoder().raw_decode(text, at)
            except ValueError:
                raise RefError(f"{ref!r}: a quoted segment that does not close") from None
            if not isinstance(label, str):
                raise RefError(f"{ref!r}: a quoted segment is a string")
            index = None
            number = _NUMBER.match(text, end)
            if number is not None:
                index, end = int(number[1]), number.end()
            while end < size and text[end] in " \t":
                end += 1
            if end < size and text[end] not in "/,":
                raise RefError(f"{ref!r}: {text[at:end + 1]!r} follows a quoted label with more than its number")
            segments.append(Segment(label, True, index))
            at = end
        else:
            end = at
            while end < size and text[end] not in "/,":
                end += 1
            piece = text[at:end].strip()
            if not piece:
                raise RefError(f"{ref!r} has an empty segment")
            segments.append(Segment(piece))
            at = end
        if at >= size:
            selectors.append(segments)
            return selectors
        if text[at] == ",":
            selectors.append(segments)
            segments = []
        at += 1
        if at >= size:
            raise RefError(f"{ref!r} ends in {text[-1]!r}")


def _selector(segments: list[Segment], ref: str) -> Selector:
    last = segments[-1]
    element: str | tuple[str, int] | None = None
    if not last.quoted:
        ordinal = _ORDINAL.fullmatch(last.text)
        if ordinal is not None:
            element = (ordinal[1], int(ordinal[2]))
        elif _element_name().fullmatch(last.text):
            element = last.text
    owner = segments[:-1] if element is not None else segments
    return Selector(tuple(owner) if owner else None, element)


# --- an occurrence tree --------------------------------------------------------------------


@dataclass(eq=False)
class Node:
    """An occurrence: its label, its place among its siblings, the components below it (none
    for a part), and what it is in the document it was made from (``payload``)."""

    label: str
    payload: Any
    part: bool
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    segment: str = ""
    # On a tree's root: each occurrence's canonical owner and path, worked out once.
    texts: dict[tuple[str, int], str] = field(default_factory=dict)

    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def path(self) -> list["Node"]:
        found = []
        node: Node | None = self
        while node is not None:
            found.append(node)
            node = node.parent
        return found[::-1]

    def parts(self) -> list["Node"]:
        return [node for node in self.walk() if node.part]


def _plain(label: str) -> bool:
    """Whether a label reads back as itself, unquoted, as a segment that ends an owner."""
    return (bool(label) and label == label.strip() and not any(ch in label for ch in '/,"')
            and not _ORDINAL.fullmatch(label) and not _element_name().fullmatch(label))


def _segments(root: Node) -> None:
    """Each node's segment: its label, numbered among the siblings that share it (``finger.2``),
    JSON-quoted where that plain text would name another sibling or would not read back."""
    groups = [[root]] + [node.children for node in root.walk() if node.children]
    for group in groups:
        seen: dict[str, int] = {}
        counts: dict[str, int] = {}
        for node in group:
            counts[node.label] = counts.get(node.label, 0) + 1
        for node in group:
            n = seen[node.label] = seen.get(node.label, 0) + 1
            shared = counts[node.label] > 1
            text = f"{node.label}.{n}" if shared else node.label
            if not _plain(node.label) or _group(group, Segment(text)) != [node]:
                text = str(Segment(node.label, True, n if shared else None))
            node.segment = text


def structure_tree(structure: dict[str, Any]) -> Node:
    """A served document's structure (``serve``) as an occurrence tree: its ``tree``, a part
    by its prototype and instance."""

    def visit(entry: dict[str, Any], parent: Node | None) -> Node:
        node = Node(str(entry.get("name") or ""), entry, "prototype" in entry, parent)
        node.children = [visit(child, node) for child in entry.get("children") or ()]
        return node

    root = visit(structure["tree"], None)
    _segments(root)
    return root


def _group(nodes: list[Node], segment: Segment) -> list[Node]:
    """The nodes of one sibling group a segment names."""
    if segment.quoted:
        named = [node for node in nodes if node.label == segment.text]
        return named if segment.index is None else named[segment.index - 1:segment.index]
    exact = [node for node in nodes if node.label == segment.text]
    if exact:
        return exact
    numbered = _INDEXED.fullmatch(segment.text)
    if numbered is None:
        return []
    named = [node for node in nodes if node.label == numbered[1]]
    index = int(numbered[2])
    return named[index - 1:index]


def _down(start: list[Node], segments: tuple[Segment, ...]) -> list[Node]:
    current = start
    for segment in segments:
        current = [found for node in current for found in _group(node.children, segment)]
    return current


def owners(root: Node, segments: tuple[Segment, ...]) -> list[Node]:
    """The occurrences an owner's path names: read from the root when its first segment names the
    root, else the occurrences whose paths end with it."""
    if _group([root], segments[0]):
        found = _down([root], segments[1:])
        if found:
            return found
    found = []
    for node in root.walk():
        if node.children:
            found.extend(_down(_group(node.children, segments[0]), segments[1:]))
    return found


def owner_text(root: Node, node: Node) -> str:
    """The canonical owner of an occurrence: its label alone where that label names it alone in
    the document (``palm``), else its occurrence path from the root (``hand/finger.2``,
    ``path_text``). An unlabelled root -- a live shape -- is no segment: a ref with no owner is
    its."""
    key = ("owner", id(node))
    found = root.texts.get(key)
    if found is None:
        if node is root:
            found = node.segment if root.label else ""
        elif _unnumbered(node) and owners(root, (_as_segment(node.segment),)) == [node]:
            found = node.segment
        else:
            found = path_text(root, node)
        root.texts[key] = found
    return found


def path_text(root: Node, node: Node) -> str:
    """An occurrence's path from the root, each segment canonical (an unlabelled root's left out
    where the rest names it alone)."""
    key = ("path", id(node))
    found = root.texts.get(key)
    if found is None:
        steps = node.path()
        found = "/".join(step.segment for step in steps)
        if not root.label:
            found = ""
            if node is not root:
                tail = tuple(_as_segment(step.segment) for step in steps[1:])
                found = "/".join(step.segment for step in (steps[1:] if owners(root, tail) == [node] else steps))
        root.texts[key] = found
    return found


def _unnumbered(node: Node) -> bool:
    """Whether an occurrence's segment is its label alone, quoted or not: no sibling shares it."""
    segment = _as_segment(node.segment)
    return segment.index is None if segment.quoted else node.segment == node.label


def _as_segment(text: str) -> Segment:
    """A canonical segment read back."""
    if text.startswith('"'):
        label, end = json.JSONDecoder().raw_decode(text)
        number = _NUMBER.fullmatch(text, end)
        return Segment(label, True, int(number[1]) if number else None)
    return Segment(text)


# --- resolving -----------------------------------------------------------------------------


@dataclass
class Hit:
    """One thing a selector names: an occurrence (``kind`` None) or one element of a part, its
    ordinal and name, and its canonical ref."""

    node: Node
    kind: str | None
    ordinal: int | None
    name: str | None
    ref: str

    @property
    def root(self) -> Node:
        return self.node.path()[0]

    @property
    def path(self) -> str:
        """The occurrence's path from the root, every segment canonical."""
        return path_text(self.root, self.node)


class _Names:
    """What a tree's parts name their elements: ``names(node, kind)`` a ``{ordinal: name}``
    (None where the names are not known), ``count(node, kind)`` how many there are (None where
    that is not known), asked once per part and kind."""

    def __init__(self, names: Callable[[Node, str], dict[int, str] | None],
                 count: Callable[[Node, str], int | None]) -> None:
        self._names, self._count = names, count
        self._held: dict[tuple[int, str], dict[int, str] | None] = {}
        self._reverse: dict[tuple[int, str], dict[str, list[int]]] = {}

    def names(self, node: Node, kind: str) -> dict[int, str] | None:
        key = (id(node), kind)
        if key not in self._held:
            self._held[key] = self._names(node, kind)
        return self._held[key]

    def ordinals(self, node: Node, kind: str, name: str) -> list[int] | None:
        held = self.names(node, kind)
        if held is None:
            return None
        key = (id(node), kind)
        reverse = self._reverse.get(key)
        if reverse is None:
            reverse = self._reverse[key] = {}
            for ordinal, text in held.items():
                reverse.setdefault(text, []).append(ordinal)
        return reverse.get(name, [])

    def count(self, node: Node, kind: str) -> int | None:
        return self._count(node, kind)


def _shown(names: list[str], limit: int = 8) -> str:
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def _nearest(root: Node, text: str) -> str:
    """The occurrences an unknown owner most resembles, for its error: by their canonical owners
    and their paths."""
    import difflib

    candidates: dict[str, None] = {}
    for node in root.walk():
        candidates[owner_text(root, node)] = None
        candidates[path_text(root, node)] = None
    candidates.pop("", None)
    near = difflib.get_close_matches(text, list(candidates), n=5, cutoff=0.5)
    if not near:
        near = [owner_text(root, node) for node in root.walk()][:8]
    return _shown(near)


def resolve(root: Node, selectors: list[Selector], names: _Names, document: str) -> list[Hit]:
    """What each selector names in the tree (see the module), each once; RefError naming the
    selector where it names nothing, or several things."""
    one_part = len(root.parts()) == 1
    found: list[Hit] = []
    for selector in selectors:
        found.extend(_resolve(root, selector, names, document, one_part))
    return found


def _resolve(root: Node, selector: Selector, names: _Names, document: str, one_part: bool) -> list[Hit]:
    shown = str(selector)
    if selector.owner is None:
        owner = root
    else:
        held = owners(root, selector.owner)
        if not held:
            raise RefError(f"{document} has no part or assembly {'/'.join(map(str, selector.owner))}; "
                           f"nearest: {_nearest(root, '/'.join(map(str, selector.owner)))}")
        if len(held) > 1:
            raise RefError(f"{'/'.join(map(str, selector.owner))} names {len(held)} occurrences in {document}: "
                           f"{_shown([owner_text(root, node) for node in held])}")
        owner = held[0]
    if selector.element is None:
        return [Hit(owner, None, None, None, owner_text(root, owner))]
    kind = selector.kind
    assert kind is not None
    parts = owner.parts()
    if not parts:
        raise RefError(f"{owner_text(root, owner) or document} holds no part, so no {kind}")
    if isinstance(selector.element, tuple):
        ordinal = selector.element[1]
        if len(parts) > 1:
            raise RefError(f"{shown}: a {kind} is numbered within its part, and {owner_text(root, owner) or document} "
                           f"holds {len(parts)}: {_shown([owner_text(root, part) for part in parts])}")
        part = parts[0]
        count = names.count(part, kind)
        if count is not None and not 1 <= ordinal <= count:
            shown_part = owner_text(root, root if one_part else part)
            raise RefError(f"{shown_part or document} has no {kind} {ordinal} (it has {count})")
        name = (names.names(part, kind) or {}).get(ordinal)
        return [Hit(part, kind, ordinal, name, _element_ref(root, part, kind, ordinal, name, one_part))]
    name = selector.element
    holding: list[tuple[Node, int]] = []
    unknown: list[Node] = []
    for part in parts:
        ordinals = names.ordinals(part, kind, name)
        if ordinals is None:
            unknown.append(part)
            continue
        holding.extend((part, ordinal) for ordinal in ordinals)
    if len(holding) == 1:
        part, ordinal = holding[0]
        return [Hit(part, kind, ordinal, name, _element_ref(root, part, kind, ordinal, name, one_part))]
    if len(holding) > 1:
        raise RefError(f"{shown} names {len(holding)} {_PLURAL[kind]} in {document}: "
                       f"{_shown([_element_ref(root, part, kind, ordinal, name, False) for part, ordinal in holding])}")
    if unknown and len(unknown) == len(parts):
        raise RefError(f"{shown}: the elements of {owner_text(root, unknown[0]) or 'this shape'} have no names here -- "
                       "a document's are its own, a live shape's its build's -- so name it by its ordinal "
                       f"({kind} N), or name it in the document")
    raise RefError(_missing(root, owner, parts, names, kind, name, document))


def _missing(root: Node, owner: Node, parts: list[Node], names: _Names, kind: str, name: str, document: str) -> str:
    """Why a name names nothing: what its atom is named now, where the parts hold names of it,
    or that nothing is made of it any more."""
    where = owner_text(root, owner)
    text = f"{document} has no {kind} {name}" + (f" in {where}" if where else "")
    atom = name.split(":", 1)[1].split(";", 1)[0]
    if "~" in atom:
        return text  # a folded name: its digest says nothing of what it became
    now = sorted({other for part in parts for other in (names.names(part, kind) or {}).values()
                  if other.split(":", 1)[1].split(";", 1)[0] == atom})
    if now:
        return f"{text}: {atom} is now {_shown(now)}"
    return f"{text}: no {kind} is made of {atom} now"


def _element_ref(root: Node, part: Node, kind: str, ordinal: int, name: str | None, one_part: bool) -> str:
    owner = owner_text(root, root if one_part else part)
    element = name or f"{kind} {ordinal}"
    return f"{owner}/{element}" if owner else element


def _same_document(file: str, document: Path) -> bool:
    """Whether a ref's ``FILE`` is the document: the same id, the same file, or the last segments
    of its path. A document known by its id alone (a model's) is named by that id alone."""
    from cadgen.engine.ids import file_id, is_id

    if is_id(str(document)):
        return file == str(document)
    if is_id(file):
        return file == file_id(document)
    given = Path(file).expanduser()
    if given.is_absolute():
        return os.path.normcase(str(given.resolve())) == os.path.normcase(str(document.resolve()))
    wanted = [part for part in given.parts if part not in (".", "")]
    held = list(document.resolve().parts)
    if not wanted or ".." in wanted or len(wanted) > len(held):
        return False
    return [os.path.normcase(part) for part in held[-len(wanted):]] == [os.path.normcase(part) for part in wanted]


def check_file(file: str | None, document: Path | None) -> None:
    """A ref's ``FILE`` against the document it is resolved in: refused when it names another."""
    if file is None or document is None:
        return
    if not _same_document(file, document):
        raise RefError(f"the ref names {file}, not {os.path.basename(str(document))}")


# --- a served document's structure (``cadgen inspect``) ----------------------------------------


def resolve_structure(structure: dict[str, Any], ref: str, document: Path | None = None) -> list[Hit]:
    """What ``ref`` names in a served document's structure: each hit's node a structure node (a
    part's holds its ``prototype`` and ``instance``)."""
    file, selectors = parse(ref)
    check_file(file, document)
    root = structure_tree(structure)
    prototypes = structure["prototypes"]

    def named(node: Node, kind: str) -> dict[int, str]:
        held = prototypes[node.payload["prototype"]].get(f"{kind}Names") or {}
        return {int(ordinal): text for ordinal, text in held.items()}

    from cadgen.engine.ids import is_id

    shown = (os.path.basename(str(document)) if document is not None and not is_id(str(document))
             else str(structure.get("name") or "the document"))
    return resolve(root, selectors, _Names(named, lambda _node, _kind: None), shown)


def placed_facts(facts: dict[str, Any], matrix: list[float]) -> dict[str, Any]:
    """An element's facts (``mesh.Topology``, measured in its part's frame) with their points
    where the occurrence stands: ``matrix`` its placement, 4x4 column-major as the structure
    holds it. A box is the box of its placed corners (the exact box, where the placement only
    moves it)."""
    if [round(value, 12) for value in matrix] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]:
        return dict(facts)
    m = matrix

    def point(p: list[float]) -> list[float]:
        x, y, z = p
        return [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13],
                m[2] * x + m[6] * y + m[10] * z + m[14]]

    found = dict(facts)
    for key in ("centroid", "position"):
        if found.get(key) is not None:
            found[key] = point(found[key])
    if found.get("endpoints"):
        found["endpoints"] = [point(p) for p in found["endpoints"]]
    box = found.get("box")
    if box:
        corners = [point([(box["min"], box["max"])[i >> axis & 1][axis] for axis in range(3)]) for i in range(8)]
        found["box"] = {"min": [min(c[axis] for c in corners) for axis in range(3)],
                        "max": [max(c[axis] for c in corners) for axis in range(3)]}
    return found
