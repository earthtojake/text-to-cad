"""Features and lineage: what the kernel boundary saw during one model run, and
the names it gives the faces, edges and vertices of what the run made.

A **feature** is one call of a patched kernel construction (``kernel_memo``)
made from the model's own code: the operation, the innermost first-party
frame that called it (the file, relative to the model's folder, the line and
the enclosing function) and the features that made the shapes it was given. A
call with no first-party frame on the stack is cadgen's own and is not a
feature; a call nested inside another feature's operation belongs to that
feature. A feature is named by the author's name for its result, within a part,
among the features the part descends from -- those that made it and, transitively,
whatever they were given -- in call order. A call made by an assignment statement
(``relief = body - hole``, ``self.body = ...``, each target of ``a, b = ...``; read
from the source at the call's instruction, ``sources.assigned``) is that target's:
the call whose result the statement stores is ``<function>.<target>`` (``dial.relief``),
the calls the same run of the statement made before it ``<function>.<target>_<operation><n>``
(``dial.relief_make_cylinder1``). The first statement of a function to assign a target
names it as it is; a later one, a reassignment, by the target and six letters of its
statement's skeleton -- the statement with every literal masked (``sources._named_sites``:
``plate_cfjpgj``) -- so the n-th run of an assignment to one target, of one skeleton, in
one function that the part descends from -- a loop, a repeated step -- is ``<target>``,
then ``<target>2``, ``<target>3``... (``_2`` after a digit). A helper making a shape in
its ``return`` statement, unassigned, makes it for the model code that called it: the
call is named by that caller's assignment, as a call its statement made on the way
(``Feature.assigner``, ``Trace._returned``). A call whose result is not assigned (a
return expression, an argument of a call that is no assignment, an expression statement)
is ``<function>.<operation><count>``: the enclosing function, the operation (``extrude``,
``fillet``, ``cut``, a constructor's class in lower case) and how many of the part's
unassigned features before it, this one included, that function's calls of that
operation were: ``dial.extrude1``. Calls counted together that were given the same
features' results, a piece of them each -- a construction looping over a sketch's faces --
count among themselves by where their pieces are, not by when they ran: OCCT hands a
boolean's or a text's pieces back in an order the heap picks, so no name of a run
depends on it (``Trace._counting_order``). So an edit elsewhere in the model -- another
part's feature, a call no element of this part descends from -- renames nothing here,
an inserted statement renames only what it touches, and renaming a variable renames
that feature's elements and nothing else. An author's label pins the
name instead, in what is made of the labelled shape: a shape the model labels
and hands to another construction names the feature that FIRST made it by that label
(``lid``) -- back from the feature that last made it, along what each was made of, to
the first of the features that alone made something of the one before (``_labels``),
so a feature applied after it never takes the label over -- in every part made from
that call on that the feature is an ancestor
of, the part's first feature to claim a label keeping it -- never in a part made
before the label reached a construction, and not in the part that shape is itself:
there (an assembly's leaf) the label names the occurrence, and the elements keep
their construction's names, so identical constructions labelled apart are one
part. A label on one of several shapes a feature made (a part of a file read) names what
is made of that one alone; a shape handed on under two labels -- placements of one
shape, which share it, labelled apart -- pins neither (``_resolved``). A function or a
label that is not an ASCII identifier is written as its ASCII form and a digest of it
(``identifier``), so no two are written alike. Lines and files are not in a name: they are where the trace
says a feature ran: the provenance the worker serves while it holds the run, never
written.

**Lineage is the kernel's history, composed as FreeCAD 1.0 composes it**
(``TopoShape::makeShapeWithElementMap``). The makers a feature runs report, of each
element of its results, the elements of its inputs it was modified, generated or
copied from (``kernel_history``), and the feature names every element of its
results from its inputs' names, in this order:

1. **Identity.** An element one of its inputs holds where the operation saw it --
   the kernel keeps what an operation leaves alone, and every boolean here leaves
   alone what it does not change -- or holds at another place of the same shape (a
   placement), or a copy of one, is that element, and has its name.
2. **History.** An element the makers report is named from its first source -- a
   vertex before an edge before a face, then the input it is of, then by name --
   and the step the feature took: modified (``M``), generated from an element of a
   kind (``G<kind>``), both (``MG<kind>``), with up to four further sources.
3. **Reverse pass.** An unnamed edge of a named face, then an unnamed vertex of a
   named edge, is named from its first named parent (by name) and its number among
   that parent's unnamed sub-elements (``U``).
4. **Forward pass.** An unnamed edge whose vertices are all named, then an unnamed
   face whose outer wire's edges are, is named from the first of them by name, with
   up to four more (``L``).
5. **Made.** An element still unnamed is the feature's own: its number among the
   elements of its kind the feature made, in the order of its results, as every
   element of a primitive is -- a result holding several pieces (a compound) taken
   piece by piece in the order of where they are (``_in_place_order``), not as OCCT held them.

An element passed on unchanged from a shape no feature made (a shape built outside the
patched surface) has no name here and names nothing: it is no parent
or lower element of a name, and a source from it is skipped, so an element made out of
one alone falls to the passes, and to the feature. Nothing here measures geometry:
what a step says is what the kernel reported.

An element's **name** is its kind and its derivation: the atom it
starts from (the n-th element of its kind a feature made, ``dial.plate.6``) and a
step per feature that made it out of another (``f:dial.plate.6;M:dial.relief``,
``e:sk.make_rect1.2;Ge:part.extrude1``). A derivation longer than ``FOLD_LENGTH``
characters is **folded** to the feature of its last step and a digest of it
(``dial.relief~5d1e0c2f9a3b``), and a further source that is not an atom is folded
whatever its length, so every name stays short; the component's lineage keeps what each
folded atom stands for (its ``table``), every one its names or that table reach.
Elements of one result a step made alike -- from the same sources, the same way: the
pieces of a face one cut splits, the pieces of a ruled loft's long edge, which it
reports as generated from every vertex on it -- are numbered in the step, the second
and later by their place among what was reported of their first source (``;M2:``,
``;Gv2:``, FreeCAD's index), so a later operation that changes one leaves the others'
numbers alone. Of a component's elements still named alike (two places of one shape
in one body), the second and later, in the order of where they are, take ``;D2``,
``;D3``: never in the B-rep's order, which is OCCT's.

The **structure** of a feature's naming -- each element's rule: the input element it
is, its sources, its parent candidates, its lower elements, its number -- is computed
from its history and the live shapes once, the first time a component needs it, and kept
with the history, so a hit's feature (whose history is its miss's) reuses it; it depends
on whether the elements of the feature's inputs have names, so it is kept per account of
that (``_skey``). A complete result made entirely of first-input identities can be
computed alone; its s/x rules are cached separately from full feature structures.
Every unproved result uses the full result-ordered algorithm, including its global made
ordinals. The native first-owner indexes stay in the Trace and are released when all
results or the full feature are completed. The names themselves are rendered per part, as a feature's name is the
part's: strings, from those structures, with no maker run and no map built on a warm run.

A complete whole-body Copy certificate also preserves the source component's naming
context and ordinal links at that boundary. The copy's elements render in that context,
including when a later feature follows them, so placing an assembly never counts a
sibling's makers in a leaf's names. Histories retain only copy ordinals; each run binds
them to its own feature nodes, and no copy invents lineage for foreign elements.

``Trace.account`` is a part's whole account: the feature that made the body, per element
ordinal its name, the table, and the feature each feature name it holds stands for.
"""

from __future__ import annotations

import bisect
import functools
import hashlib
import itertools
import re
import sys
import weakref
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher, IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

from cadgen.engine.kernel.history import _map, _object_key, listed
from cadgen.engine.kernel.imported import ELEMENT_NAMES
from cadgen.engine.refs import ELEMENT_NAME
from cadgen.engine.sources import assigned as _assigned_names
from cadgen.engine.sources import returning as _returning

# Every execution of an assignment statement a feature ran in, numbered process-wide: a
# replayed body's features keep the executions of the run that recorded them, never one
# of this run's.
_EXECUTIONS = itertools.count(1)
# The operations that read a file: what they make is named per product of the file
# (``_read_structure``).
_FILE_READS = frozenset({"read_step", "read_xbf", "import_step", "import_brep", "import_stl"})
# What a STEP writer names an element it gives no name ('NONE' is the schema's empty name).
_UNNAMED = frozenset({"", "NONE", "NULL"})
# The operations that only place or hold the shapes they are given: an element of an
# input no name reaches stays unnamed in what they return, never theirs.
_PLACEMENTS = frozenset({"moved", "located", "compound", "copy", "deepcopy"})

# A shape's map of one kind of its sub-shapes in its own frame, by TShape and orientation:
# what naming asks of every result on every run. A TShape's sub-shapes never change once
# it is built and a hit hands back the same TShapes, so a map is made once per process and
# kept for the shapes runs keep naming, the least recently asked dropped past the bound.
_FRAME_MAPS: "OrderedDict[tuple, Any]" = OrderedDict()
_FRAME_MAPS_HELD = 1 << 16


def _frame_map(shape: Any, topabs: Any) -> Any:
    key = (shape.TShape(), int(shape.Orientation()), int(topabs))
    found = _FRAME_MAPS.get(key)
    if found is not None:
        _FRAME_MAPS.move_to_end(key)
        return found
    found = _FRAME_MAPS[key] = _map(shape.Located(TopLoc_Location()), topabs)
    while len(_FRAME_MAPS) > _FRAME_MAPS_HELD:
        _FRAME_MAPS.popitem(last=False)
    return found

__all__ = ["FOLD_LENGTH", "Feature", "Trace", "identifier", "operation_name"]

# A derivation longer than this many characters is folded (``cad_ref_syntax``): long enough
# for a made atom and a step or two, short enough for a STEP file and a prompt.
FOLD_LENGTH = 48
# Further sources (history) and lower elements (forward pass) a step lists, as FreeCAD does.
_EXTRAS = 4
# The element kinds, by their index in ``kernel_history.KINDS``: vertex, edge, face.
_TOPABS = (TopAbs_VERTEX, TopAbs_EDGE, TopAbs_FACE)
_LETTER = "vef"
_PLURAL = ("vertices", "edges", "faces")
VERTEX, EDGE, FACE = 0, 1, 2
_HERE = Path(__file__).resolve().parent
# A kernel call reached through the engine's own machinery before any model frame
# (a file it reads, a document it builds) is the engine's, not the model's: no
# feature. The rest of cadgen, a library a model may call, counts as build123d does.
_ENGINE = _HERE.parent
_OWN = (_ENGINE,)
# The functions a model calls (``cadgen.engine.model``: its decorators, ``read_step``,
# ``paint``; ``cadgen.engine.refs``: ``select``; ``cadgen.engine.reader``: ``read_mesh``) count
# as build123d does: what they run for the model is the model's call (a document ``select``
# reads is the model's read).
_API = frozenset({_ENGINE / "model.py", _ENGINE / "refs.py", _ENGINE / "reader.py"})
_NOT_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]+")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# What a digest of a name looks like at its end, which a name written as it is never has.
_DIGESTED = re.compile(r"_[0-9a-f]{8}$")
# The frames Python names itself, each written as its word; a function of that name
# is not one of them, and takes a digest.
_FRAMES = {"<module>": "module", "<lambda>": "lambda", "<genexpr>": "genexpr", "<listcomp>": "listcomp",
           "<dictcomp>": "dictcomp", "<setcomp>": "setcomp"}
_FRAME_WORDS = frozenset(_FRAMES.values())
# Placements compare rounded, as an occurrence's placement does (tree_tokens): only to tell
# the places of one shape in another apart.
_POSITION_QUANTUM = 1e-6
_DIRECTION_QUANTUM = 1e-9


def identifier(text: str) -> str:
    """``text`` as one name segment, no two texts alike: an ASCII identifier as it is,
    and the frame Python names ``<module>`` (or ``<lambda>``, ``<genexpr>``) as its
    word. Anything else -- a name beyond ASCII, a label with a colon, an identifier
    that is one of those words or ends as a digest does -- is its ASCII form (its runs
    of anything but ASCII letters, digits and underscores one underscore, trimmed)
    and the first eight hex digits of its sha256 (``корпус`` is ``_9f1c0b2e``,
    ``mounting_eye:lower`` is ``mounting_eye_lower_`` and its digest), so it is never
    a name another text is written as. Every feature's function and every label is
    written through it, so a text is written once (``_identifier``)."""
    return _identifier(str(text))


@functools.lru_cache(maxsize=16384)
def _identifier(text: str) -> str:
    word = _FRAMES.get(text)
    if word is not None:
        return word
    if _IDENTIFIER.fullmatch(text) and text not in _FRAME_WORDS and not _DIGESTED.search(text):
        return text
    form = _NOT_IDENTIFIER.sub("_", text).strip("_")
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    if not form:
        return f"_{digest}"
    return f"{'_' if form[0].isdigit() else ''}{form}_{digest}"


@functools.lru_cache(maxsize=4096)
def operation_name(op: str) -> str:
    """A feature's operation as its name spells it: the method without its class
    (``Solid.extrude`` is ``extrude``), a constructor's class in lower case."""
    return identifier(op.rsplit(".", 1)[-1].lower())


@dataclass
class Feature:
    """One kernel construction the model's code called."""

    index: int
    op: str
    file: str
    line: int
    function: str
    # The feature of each shape the call was given, in call order; None for a
    # shape no feature of this run made.
    inputs: list[int | None]
    # The input shapes as passed and the results as returned: handle copies,
    # so a later in-place move of the object does not move what the operation
    # saw; None for an empty shape or a child model's promise not yet forced.
    handles: list[Any] = field(default_factory=list, repr=False)
    results: list[Any] = field(default_factory=list, repr=False)
    # The author's label for what this feature made, when one pins its name, and the
    # feature whose call pinned it: a part made before that call is named as if the
    # label had never been set.
    label: str | None = None
    pinned_at: int | None = None
    # What the makers the call ran report of its results (``kernel_history.History``),
    # with the structures of its naming kept in it; None where it could not be composed.
    history: Any = field(default=None, repr=False)
    # The assignment statement the call ran in (``Trace.frame``): which execution of it,
    # the names it assigns (one, or a tuple target's each) and, for a tuple target given
    # as many shapes, the target each result position belongs to.
    execution: int | None = None
    targets: tuple[str, ...] | None = None
    groups: tuple[int, ...] | None = field(default=None, repr=False)
    # Where the call ran in a helper that returns what it makes, unassigned: the caller
    # whose assignment names it, ``(file, function)`` (``Trace.frame``); else None.
    assigner: tuple[str, str] | None = None
    # A file read's: per result position, what the file names that product's elements
    # (``kernel.imported``), by kind and ordinal.
    imported: dict[int, dict] = field(default_factory=dict, repr=False)
    # Per result, the source's naming context at a certified whole-body copy.
    # This is rebound for every run, including hits: histories contain ordinals,
    # never the feature indices of the run that first computed them.
    copies: dict[int, "_CopyContext"] = field(default_factory=dict, repr=False)
    # Functions of the feature alone, computed once: the operation as its name spells
    # it, the unassigned name without its count (``<function>.<operation>``) -- every
    # part's naming reads them for each feature it descends from -- and, on first use,
    # the first position at which each TShape was returned.
    operation: str = field(init=False, repr=False)
    stem: str = field(init=False, repr=False)
    _positions: dict[Any, int] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.operation = operation_name(self.op)
        self.stem = f"{identifier(self.function)}.{self.operation}"

    @property
    def target(self) -> str | None:
        """The name the feature's assignment gives it, its targets joined for a tuple."""
        return None if self.targets is None else "_".join(self.targets)

    @property
    def namer(self) -> str:
        """The function whose assignment names the feature: its own, or for a call a helper
        returned unassigned, its caller's (``assigner``)."""
        return self.function if self.assigner is None else self.assigner[1]

    def position_of(self, tshape: Any) -> int | None:
        """The first position among the results at which ``tshape`` was returned, or None."""
        positions = self._positions
        if positions is None:
            positions = self._positions = {}
            for position, result in enumerate(self.results):
                if result is not None:
                    positions.setdefault(result.TShape(), position)
        return positions.get(tshape)


@dataclass
class _Structure:
    """One feature's naming: ``rules[position][kind][ordinal - 1]`` for each element of
    each result (None for an empty result), each rule one of ``("x",)`` passed on from
    a shape no feature made, no name; ``("s", input, ordinal)`` that input's element;
    ``("h", sources, rank, place)`` named by history, each source ``(input, kind,
    ordinal, how)``, ``rank`` its number among the elements one step named alike;
    ``("u", candidates)`` from a parent, each ``(kind, ordinal, number)``; ``("l",
    lowers)`` from its lower elements, each ``(kind, ordinal)``; ``("m", number)`` made;
    ``("n", atom)`` read from a file that names it (``_read_structure``);
    ``("c", position, kind, ordinal)`` in that result's frozen source context."""

    rules: list[list[list[tuple]] | None]


_MISSING = object()


class _IdentityInputs:
    """A feature's first geometric owners, shared by requested and full results.

    Native indexes stay in this Trace only. Build one kind at a time, keeping
    the inputs' maps of it and their owner ordinals (``_input_index``).
    """

    def __init__(self, handles: list[Any]) -> None:
        self.handles = [(j, handle) for j, handle in enumerate(handles) if handle is not None]
        self.indexes: dict[int, tuple[Any, list[tuple[int, int]] | None]] = {}
        self.counts: dict[tuple[int, int], int] = {}

    def _index(self, kind: int) -> tuple[Any, list[tuple[int, int]] | None]:
        found = self.indexes.get(kind)
        if found is None:
            if len(self.handles) == 1:
                j, handle = self.handles[0]
                elements = _map(handle, _TOPABS[kind])
                self.counts[(j, kind)] = elements.Extent()
                found = self.indexes[kind] = (elements, None)
                return found
            given = []
            for j, handle in self.handles:
                maps = [None, None, None]
                maps[kind] = _map(handle, _TOPABS[kind])
                self.counts[(j, kind)] = maps[kind].Extent()
                given.append((j, maps))
            found = self.indexes[kind] = _input_index(given, kind)
        return found

    def owner(self, kind: int, element: Any) -> tuple[int, int] | None:
        if not self.handles:
            return None
        elements, owners = self._index(kind)
        at = elements.FindIndex(element)
        if not at:
            return None
        return (self.handles[0][0], at) if owners is None else owners[at - 1]

    def count(self, j: int, kind: int) -> int:
        self._index(kind)
        return self.counts[(j, kind)]


def _same_rule(j: int, ordinal: int, rule: tuple | None) -> tuple | None:
    """Translate the source's knownness once, for both identity completion modes."""
    return None if rule is None else ("x",) if rule[0] == "x" else ("s", j, ordinal)


@dataclass
class _CopyContext:
    """A source's derivation nodes and naming boundary, without rendered lineage.

    Nodes are in source ordinal order. A copy chain remaps these tuples rather
    than retaining another chain of contexts. Structures are captured while the
    source still has the topology the copy saw; strings are rendered on demand.
    """

    names: "_Names | None"
    made: int | None
    nodes: tuple[tuple[tuple | None, ...], ...]
    renderer: "_Renderer | None" = field(default=None, repr=False)
    owner: tuple[int, int] = (-1, -1)
    identity: int = -1
    label: str | None = None
    pinned_at: int | None = None
    labelled: dict[tuple[str, int], "_Renderer"] = field(default_factory=dict, repr=False)


class Trace:
    """The features of one run, in call order, and the lineage they give."""

    def __init__(self, model_dir: Path | None) -> None:
        self.model_dir = Path(model_dir).resolve() if model_dir is not None else None
        self.features: list[Feature] = []
        self._first_party: dict[str, str] = {}
        self._display: dict[str, str] = {}
        self._paths: dict[str, str] = {}
        # _object_key(shape) -> (weakref, feature index): the feature that returned each
        # live result object. A dead reference, or a recycled key, answers nothing.
        self._by_object: dict[int, tuple[weakref.ref, int]] = {}
        # The same for the call that made each live object: the first feature that
        # returned it itself, never one that only held it (a compound it was attached to).
        self._made_object: dict[int, tuple[weakref.ref, int]] = {}
        self._made_by: Callable[[Any], int | None] = lambda _tshape: None
        # Per feature, as it is recorded: the features it descends from (itself and,
        # transitively, every feature that made what it was given) as bits by index; per
        # stem, the features of that stem; per label, the features that claim it, in order.
        self._ancestors: list[int] = []
        self._copy_ancestors: list[int] = []
        self._copy_contexts: list[_CopyContext] = []
        self._copy_labels: dict[str, int] = {}
        self._stems: dict[str, int] = {}
        self._labelled: dict[str, list[int]] = {}
        # Per feature whose shape was handed on labelled -- or per feature of several results
        # and position, one of its results -- each label it was handed on with and the call
        # that did (``_pin``); the label that pins it, and the call (``_resolved``); resolved
        # to the features they name (``_labels``).
        self._pins: dict[Any, list[tuple[str, int]]] = {}
        self._pinned: dict[int, tuple[str, int]] = {}
        self._pinned_results: dict[tuple[int, int], tuple[str, int]] = {}
        self._labels_count = -1
        # Per model frame making calls, the assignment it is executing (``_execution``):
        # the frame, the statement, the instruction, the frame it called and the
        # execution's number. Held only while the run records (``release``).
        self._executing: dict[int, tuple] = {}
        self._executing_bound = 64
        # Built from the features once naming asks (``_assignments``): per assignment
        # execution and target, its features in order; its head, the last of them -- the
        # call whose result the statement assigns --; per ``<function>.<target>``, the heads
        # as bits by index; and per feature that is no head, its number among its
        # execution's features of its operation (``_number``, counted once asked).
        self._assigned_count = -1
        self._heads: dict[tuple[int, str], int] = {}
        self._target_stems: dict[str, int] = {}
        self._members: dict[tuple[int, str], list[int]] = {}
        self._within: dict[int, int] = {}
        # Per unassigned feature with siblings (``_counting_order``), its class; and per
        # feature whose place it was asked, where the shapes it was given are.
        self._siblings: dict[int, tuple[int, ...]] = {}
        self._fingerprints: dict[int, tuple] = {}
        # Per run: where each input came from (``_source``), the structure each feature is
        # named by and what it was computed from (``_skey``), the element each element that is
        # an input's resolves to (``_origin``), and maps of results in their own frames.
        self._sources: dict[tuple[int, int], tuple] = {}
        self._structures: dict[int, _Structure] = {}
        self._results: dict[int, dict[int, tuple | None]] = {}
        self._identity_inputs: dict[int, _IdentityInputs] = {}
        self._skeys: dict[int, bytes] = {}
        self._origins: dict[tuple, tuple | None] = {}
        self._inputs: dict[tuple, tuple | None] = {}
        self._places: dict[tuple, dict[Any, list[int]]] = {}

    # --- recording ---------------------------------------------------------------------

    def _verdict(self, filename: str) -> str:
        verdict = self._first_party.get(filename)
        if verdict is None:
            verdict = self._first_party[filename] = _classify(filename)
        return verdict

    def frame(self) -> tuple | None:
        """The innermost first-party frame of the current stack: ``(file, line,
        function, assignment, assigner)``, the file relative to the model's folder, the
        assignment the call runs in (``_execution``: which execution of the statement and
        the names it assigns), or None, and the caller that assignment is made in, when it
        is not the frame's own (``_returned``), or None; None when the call is cadgen's own
        (one of its internal frames comes first) or no model code is on the stack."""
        frame = sys._getframe(1)
        below = None
        while frame is not None:
            filename = frame.f_code.co_filename
            verdict = self._verdict(filename)
            if verdict == "model":
                assignment = self._execution(frame, below)
                assigner = None
                if assignment is None:
                    found = self._returned(frame)
                    if found is not None:
                        assignment, caller = found
                        assigner = (self._display_path(caller.f_code.co_filename), caller.f_code.co_name)
                return (self._display_path(filename), frame.f_lineno, frame.f_code.co_name, assignment, assigner)
            if verdict == "own":
                return None
            below = frame
            frame = frame.f_back
        return None

    def called_by_model(self) -> bool:
        """Whether the call being made is the model's own, as ``frame`` tells it -- the
        innermost first-party frame of the stack is the model's, not cadgen's -- with nothing
        recorded of the statement it runs in."""
        frame = sys._getframe(1)
        while frame is not None:
            verdict = self._verdict(frame.f_code.co_filename)
            if verdict != "other":
                return verdict == "model"
            frame = frame.f_back
        return False

    def _returned(self, frame: Any) -> tuple[tuple[int, tuple[str, ...]], Any] | None:
        """The assignment a helper's call is named by, when the helper makes it in its
        ``return`` statement -- what it makes flows out unassigned -- and the first-party
        function that called it directly (through further helpers returning it) assigns
        it: that caller's execution of its statement, and the caller. None where the result
        is assigned nowhere, or the helper was not called by model code directly -- a
        child model, which the engine calls, names its own result whatever its caller."""
        while _returning(frame.f_code, frame.f_lasti):
            caller = frame.f_back
            if caller is None or self._verdict(caller.f_code.co_filename) != "model":
                return None
            assignment = self._execution(caller, frame)
            if assignment is not None:
                return assignment, caller
            frame = caller
        return None

    def _execution(self, frame: Any, below: Any) -> tuple[int, tuple[str, ...]] | None:
        """The assignment ``frame`` is executing as it calls ``below``: ``(execution,
        names)``, or None where the statement assigns nothing (``sources.assigned``). An
        execution is one run of the statement: the calls a frame makes from one statement
        while its instruction only moves forward -- or stays in one call of the same frame,
        which a constructor making several shapes is -- are one; a statement run again (a
        loop) is the next."""
        offset = frame.f_lasti
        found = _assigned_names(frame.f_code, offset)
        if found is None:
            return None
        statement, names = found
        held = self._executing.get(id(frame))
        if held is not None and held[0] is frame and held[1] == statement and (
                held[2] < offset or (held[2] == offset and held[3] is below)):
            execution = held[4]
        else:
            execution = next(_EXECUTIONS)
        self._executing[id(frame)] = (frame, statement, offset, below, execution)
        if len(self._executing) > self._executing_bound:
            # Only the frames still on the stack can call again.
            live = set()
            current = frame
            while current is not None:
                live.add(id(current))
                current = current.f_back
            self._executing = {key: value for key, value in self._executing.items() if key in live}
            self._executing_bound = max(64, 2 * len(self._executing))
        return execution, names

    def release(self) -> None:
        """The run recorded its last call: let go of the frames it held."""
        self._executing = {}

    def _assignments(self) -> None:
        """The tables naming reads of the features assignments name, built once the run's
        features are all recorded (and again if more were)."""
        if self._assigned_count == len(self.features):
            return
        members: dict[tuple[int, str], list[int]] = {}
        for feature in self.features:
            if feature.execution is not None:
                members.setdefault((feature.execution, feature.target), []).append(feature.index)
        heads: dict[tuple[int, str], int] = {}
        stems: dict[str, int] = {}
        for key, indices in members.items():
            # The call whose result the statement stores: its last, or what that only wraps
            # or places (build123d wraps every part it makes in a compound of one).
            head = self.unwrapped(indices[-1])
            if head not in indices:
                head = indices[-1]
            heads[key] = head
            feature = self.features[head]
            function = identifier(feature.namer)
            names = [feature.target]
            if feature.groups is not None:
                names.extend(feature.targets)
            for name in names:
                stem = f"{function}.{name}"
                stems[stem] = stems.get(stem, 0) | (1 << head)
        # The unassigned calls of one stem made of the same features' results: the classes
        # of siblings ``_Names._name`` counts in their geometric order.
        classes: dict[tuple, list[int]] = {}
        for feature in self.features:
            if feature.execution is None and feature.inputs:
                classes.setdefault((feature.stem, tuple(feature.inputs)), []).append(feature.index)
        siblings: dict[int, tuple[int, ...]] = {}
        for held in classes.values():
            if len(held) > 1 and not self._alike(held):
                for index in held:
                    siblings[index] = tuple(held)
        self._heads, self._target_stems, self._siblings = heads, stems, siblings
        self._members, self._within = members, {}
        self._assigned_count = len(self.features)

    def _number(self, index: int) -> int:
        """Feature ``index``'s number among its execution's features of its operation, the
        head left out (``_counting_order``): counted the first time naming asks, for that
        execution and operation alone -- placing siblings reads their geometry, which a part
        no one names (a warm build's replayed parts) never needs."""
        found = self._within.get(index)
        if found is None:
            feature = self.features[index]
            key = (feature.execution, feature.target)
            head = self._heads[key]
            members = [member for member in self._members[key]
                       if member != head and self.features[member].operation == feature.operation]
            for number, member in enumerate(self._counting_order(members), 1):
                self._within[member] = number
            found = self._within[index]
        return found

    def _counting_order(self, members: list[int]) -> list[int]:
        """``members`` (calls of one operation counted together, in call order) in the order
        they are counted: call order, but siblings -- calls given the same features' results,
        a piece of them each, as a construction that loops over a shape's faces makes --
        among themselves by where their pieces are (``_fingerprint``), in the places the
        siblings take in call order. OCCT hands a boolean's pieces back in an order that
        depends on the heap, so the n-th piece of a shape is no function of the code; a
        piece's place is, and nothing else is counted otherwise."""
        classes: dict[tuple, list[int]] = {}
        for index in members:
            inputs = self.features[index].inputs
            if inputs:
                classes.setdefault(tuple(inputs), []).append(index)
        order = list(members)
        at = {index: place for place, index in enumerate(members)}
        for siblings in classes.values():
            if len(siblings) < 2 or self._alike(siblings):
                continue
            for place, index in zip(sorted(at[s] for s in siblings), self._by_place(siblings)):
                order[place] = index
        return order

    def _alike(self, members: list[int]) -> bool:
        """Whether every one of ``members`` was given the very same shapes: no pieces to order."""
        first = self.features[members[0]].handles
        for index in members[1:]:
            handles = self.features[index].handles
            if len(handles) != len(first) or any(
                    (a is None) != (b is None) or (a is not None and not a.IsEqual(b))
                    for a, b in zip(first, handles)):
                return False
        return True

    def _by_place(self, members: list[int]) -> list[int]:
        """``members`` ordered by where the shapes they were given are, then call order."""
        return sorted(members, key=lambda index: (self._fingerprint(index), index))

    def _fingerprint(self, index: int) -> tuple:
        """Where the shapes feature ``index`` was given are, rounded (``_place``): a function
        of the geometry alone, read once per feature."""
        found = self._fingerprints.get(index)
        if found is None:
            found = self._fingerprints[index] = tuple(
                () if handle is None else _place(handle) for handle in self.features[index].handles)
        return found

    def _display_path(self, filename: str) -> str:
        shown = self._display.get(filename)
        if shown is None:
            path = Path(filename)
            shown = path.as_posix()
            if self.model_dir is not None:
                try:
                    shown = path.resolve().relative_to(self.model_dir).as_posix()
                except (ValueError, OSError):
                    shown = path.as_posix()
            self._display[filename] = shown
            self._paths[shown] = filename
        return shown

    def path_of(self, shown: str) -> str | None:
        """The file a feature's ``file`` (as shown, relative to the model's folder) is --
        also a replayed feature's, which another run's trace showed."""
        found = self._paths.get(shown)
        if found is None and self.model_dir is not None and not Path(shown).is_absolute():
            found = str(self.model_dir / shown)
        return found if found is not None else shown

    def feature_of(self, shape: Any) -> int | None:
        """The feature that returned this very object, or None."""
        found = self._by_object.get(_object_key(shape))
        if found is None:
            return None
        reference, index = found
        return index if reference() is shape else None

    def made(self, shape: Any) -> int | None:
        """The feature whose call made this very object -- the first that returned it
        itself -- or None."""
        found = self._made_object.get(_object_key(shape))
        if found is None:
            return None
        reference, index = found
        return index if reference() is shape else None

    def given(self, shapes: list[Any], feature_of: Callable[[Any], int | None]) -> list[tuple[Any, int | None, Any]]:
        """The inputs of a call as it is given them, taken before it runs: each shape,
        the feature that made it (``feature_of``) and a handle of its ``TopoDS`` then --
        an in-place operation (``clean``) leaves its input object wrapping the result."""
        # Complete every feature still owed a structure before this call runs: a later
        # kernel call can mutate native topology, constructors with implicit builder
        # inputs included.
        if self._results:
            for index in sorted(self._results):
                self._structure(index)
        return [(shape, feature_of(shape), handle_of(shape)) for shape in shapes]

    def record(self, op: str, frame: tuple[str, int, str], inputs: list[tuple[Any, int | None, Any]],
               results: list[Any], made: list[Any] = (), *, labels: list[Any] | None = None,
               result_handles: list[Any] | None = None) -> Feature:
        """One feature: ``inputs`` are the call's, as :meth:`given` took them,
        ``results`` the live result objects the call returned and the children they hold,
        ``made`` the objects it returned itself. A labelled input pins the name of the
        feature that made it. A replayed call (a model body the memo did not run) gives
        the labels its inputs had and the handles of its results when it was recorded:
        the objects are the same, their state since then may not be."""
        file, line, function = frame[:3]
        feature = Feature(
            index=len(self.features), op=op, file=file, line=line, function=function,
            inputs=[index for _shape, index, _handle in inputs],
            handles=[handle for _shape, _index, handle in inputs],
            results=list(result_handles) if result_handles is not None else [handle_of(shape) for shape in results],
        )
        if op in _FILE_READS:
            # What the file names its products' elements, per result position.
            for position, shape in enumerate(results):
                found = getattr(shape, "__dict__", {}).get(ELEMENT_NAMES)
                if found:
                    feature.imported[position] = found
        assignment = frame[3] if len(frame) > 3 else None
        if assignment is not None:
            feature.assigner = frame[4] if len(frame) > 4 else None
            feature.execution = assignment[0]
            feature.targets = tuple(identifier(name) for name in assignment[1])
            if len(feature.targets) > 1:
                feature.groups = _groups(results, made, len(feature.targets))
        self.features.append(feature)
        ancestors = 1 << feature.index
        copied_inputs = 0
        contexts = [None if given is None or handle is None else self._copy_of(handle, self._made_by)
                    for _shape, given, handle in inputs]
        for (_shape, given, handle), context in zip(inputs, contexts):
            if given is not None:
                if context is not None:
                    ancestors |= (1 << given) | (1 << context.owner[0])
                    if context.names is not None:
                        ancestors |= context.names.ancestors
                        copied_inputs |= context.names.copies
                    copied_inputs |= 1 << context.identity
                else:
                    ancestors |= self._ancestors[given]
                    copied_inputs |= self._copy_ancestors[given]
        self._ancestors.append(ancestors)
        self._copy_ancestors.append(copied_inputs)
        if feature.execution is None:
            # Only the calls an assignment does not name count in ``<operation><count>``:
            # a statement added that assigns renumbers none of them.
            self._stems[feature.stem] = self._stems.get(feature.stem, 0) | (1 << feature.index)
        for j, ((shape, index, _handle), context) in enumerate(zip(inputs, contexts)):
            if index is not None:
                label = labels[j] if labels is not None else getattr(shape, "__dict__", {}).get("label")
                if context is None:
                    self._pin(index, label, at=feature.index, handle=_handle)
                elif context.label is None:
                    if isinstance(label, str) and label:
                        context.label, context.pinned_at = identifier(label), feature.index
                        self._copy_labels[context.label] = self._copy_labels.get(context.label, 0) | (1 << context.identity)
        for shape in results:
            try:
                self._by_object[_object_key(shape)] = (weakref.ref(shape), feature.index)
            except TypeError:
                pass
        for shape in made:
            try:
                found = self._made_object.get(_object_key(shape))
                if found is None or found[0]() is not shape:
                    self._made_object[_object_key(shape)] = (weakref.ref(shape), feature.index)
            except TypeError:
                pass
        return feature

    def _pin(self, index: int, label: object, *, at: int, handle: Any = None) -> None:
        """Note that the shape feature ``index`` made is handed on labelled ``label`` by the
        call of feature ``at``. Its label (``_resolved``) names the feature that first made
        that shape (``_labels``) in what is made of it from the first such call on
        (:meth:`_names`). Of a part's features, the first to claim a label keeps it. A shape
        that is one of several a feature made -- a part of a file read -- is one result of
        it: its label names what is made of that result alone, never its siblings'. Every
        placement of a shape (``moved``, ``located``, a copy) shares it: placements labelled
        apart name their occurrences, and pin none of their labels on the shape they share."""
        if not isinstance(label, str) or not label:
            return
        maker = self.unwrapped(index)
        key: Any = maker
        feature = self.features[maker]
        if handle is not None and len(feature.results) > 1:
            position = feature.position_of(handle.TShape())
            if position:
                key = (maker, position)
        self._pins.setdefault(key, []).append((identifier(label), at))

    def _resolved(self) -> None:
        """Each shape's pin (``_pin``): the label it was handed on with, by the first call that
        did -- where every label it was handed on with is that one. A shape handed on under
        two labels -- placements of it labelled apart, each its occurrence's name -- pins
        neither: one label would rename what is made of every other placement. A feature's
        pin in ``_pinned``, one result's of several in ``_pinned_results``."""
        self._pinned, self._pinned_results = {}, {}
        for key, pins in self._pins.items():
            label, at = pins[0]
            if any(other != label for other, _at in pins):
                continue
            if isinstance(key, tuple):
                self._pinned_results[key] = (label, at)
            else:
                self._pinned[key] = (label, at)

    def _labels(self) -> None:
        """Resolve each label to the feature it names, once the run's features are all
        recorded (and again if more were): the feature that FIRST made the labelled shape
        -- back from the one that last made it along what each was made of (its first
        input), through every feature that alone made something of the one before, to
        the first, stopping at a shape something else was made of too, at a shape another
        label names, and at an assembly. So a feature applied to a labelled shape after
        another -- a cut appended, one inserted -- never takes the label over, and the
        elements the label names keep their names."""
        if self._labels_count == len(self.features):
            return
        self._resolved()
        unwrapped: dict[int, int] = {}

        def through(index: int) -> int:
            found = unwrapped.get(index)
            if found is None:
                found = unwrapped[index] = self.unwrapped(index)
            return found

        # What each feature was made of is its first input: the shape it changes. (Its other
        # inputs -- a tool, the edges a fillet rounds -- are not, and an edge left alone keeps
        # the maker of the shape it was first made in.) A feature counts as made of it only
        # when something is made of what it made in turn: an attempt the model threw away (a
        # fillet it found wanting) branches nothing.
        real = [feature for feature in self.features if through(feature.index) == feature.index]
        used = {through(up) for feature in real
                for up in feature.inputs if up is not None and through(up) != feature.index}
        consumers: Counter = Counter()
        for feature in real:
            first = next((up for up in feature.inputs if up is not None), None)
            if first is not None and through(first) != feature.index and feature.index in used:
                consumers[through(first)] += 1
        for feature in self.features:
            feature.label = feature.pinned_at = None
        labelled: dict[str, list[int]] = {}
        for maker, (label, at) in sorted(self._pinned.items(), key=lambda pin: (pin[1][1], pin[0])):
            root = maker
            seen = {root}
            while self.features[root].operation != "compound":
                given = next((up for up in self.features[root].inputs if up is not None), None)
                if given is None:
                    break
                given = through(given)
                pinned = self._pinned.get(given)
                if given in seen or consumers[given] > 1 or (pinned is not None and pinned[0] != label):
                    break
                seen.add(given)
                root = given
            feature = self.features[root]
            if feature.label is None:
                feature.label, feature.pinned_at = label, at
                bisect.insort(labelled.setdefault(label, []), root)
        self._labelled = labelled
        self._labels_count = len(self.features)

    def unwrapped(self, index: int) -> int:
        """The feature that made what feature ``index`` returned, through the features
        that only place or hold another's: a placement (``moved``, ``located``, a copy
        that keeps the shape) returns the very shape it was given, and a compound built
        of one shape (build123d wraps every part it builds in one) is that shape."""
        while True:
            inner = self._inner(index)
            if inner is None:
                return index
            index = inner

    def _inner(self, index: int) -> int | None:
        """The feature whose shape feature ``index`` returned as its own (``unwrapped``'s
        one step), or None."""
        from OCP.TopoDS import TopoDS_Iterator

        feature = self.features[index]
        result = feature.results[0] if len(feature.results) == 1 else None
        if result is None:
            return None
        held = result.TShape()
        if feature.operation == "compound":
            children = TopoDS_Iterator(result)
            child = children.Value() if children.More() else None
            if child is None:
                return None
            children.Next()
            if children.More():
                return None
            held = child.TShape()
        return next((feature.inputs[j] for j, handle in enumerate(feature.handles)
                     if handle is not None and feature.inputs[j] is not None and feature.inputs[j] != index
                     and handle.TShape() == held), None)

    def preserve_copies(self, feature: Feature, copies: dict, made_by: Callable[[Any], int | None]) -> None:
        """Bind whole-copy certificates to this run's original component context.

        The enclosing assembly's other makers must not count in a copied leaf's
        feature names, and a copied foreign leaf must remain unnamed.
        """
        self._made_by = made_by
        sources: dict[Any, _CopyContext] = {}
        for position, copy in copies.items():
            top = copy.source.TShape()
            context = sources.get(top)
            if context is None:
                context = sources[top] = self._copy_context(copy.source, copy.ordinals, made_by)
            preserved = _CopyContext(
                context.names, context.made,
                tuple(tuple(context.nodes[kind][ordinal - 1] for ordinal in ordinals)
                      for kind, ordinals in enumerate(copy.ordinals)),
                owner=(feature.index, position), identity=len(self._copy_contexts))
            feature.copies[position] = preserved
            self._copy_contexts.append(preserved)

    def _copy_of(self, body: Any, made_by: Callable[[Any], int | None]) -> _CopyContext | None:
        index = made_by(body.TShape())
        if index is None:
            return None
        position = self.features[index].position_of(body.TShape())
        return self.features[index].copies.get(position)

    def reject_copies(self, feature: Feature) -> None:
        """Withdraw a current call's inheritance before any later feature sees it."""
        feature.copies.clear()
        self._structures.pop(feature.index, None)
        self._results.pop(feature.index, None)
        self._identity_inputs.pop(feature.index, None)
        self._skeys.pop(feature.index, None)
        self._origins = {node: origin for node, origin in self._origins.items() if node[0] != feature.index}
        if feature.history is not None:
            feature.history.copies.clear()
            feature.history.structures.clear()
            feature.history.result_rules.clear()

    def _copy_context(self, body: Any, ordinals: tuple, made_by: Callable[[Any], int | None]) -> _CopyContext:
        previous = self._copy_of(body, made_by)
        if previous is not None:
            return previous
        maker = self._maker(made_by, body)
        owners = self._owners(made_by, body)
        made = None if maker is None else self.unwrapped(maker)
        roots = [index for _shape, index in owners] + ([made] if made is not None else [])
        if not roots:
            return _CopyContext(None, None, tuple(tuple(None for _ordinal in kind) for kind in ordinals))
        names = self._names(roots, made, made_at=max(roots))
        for _shape, index in owners:
            self._structure(index)
        # The usual case is a whole result: its ordinals are already the source
        # nodes. No new element map, payload or rendered string is needed.
        if len(owners) == 1 and owners[0][0] is body:
            index = owners[0][1]
            located = self._located(index, body)
            if located is not None and located[1] is None:
                position = located[0]
                return self._frozen_copy_context(names, made, tuple(tuple(self._copy_node((index, position, kind, ordinal))
                    for ordinal in range(1, len(held) + 1)) for kind, held in enumerate(ordinals)))
        nodes = []
        for kind in range(3):
            elements = _map(body, _TOPABS[kind])
            nodes.append(tuple(self._copy_node(self._component_node(body, owners, elements.FindKey(ordinal), kind, ordinal))
                               for ordinal in range(1, elements.Extent() + 1)))
        return self._frozen_copy_context(names, made, tuple(nodes))

    def _copy_node(self, node: tuple | None) -> tuple | None:
        return node if node is not None and self._origin(node) is not None else None

    def _frozen_copy_context(self, names: "_Names", made: int | None, nodes: tuple) -> _CopyContext:
        """Resolve derivation links now, before native source maps can change.

        Structures alone do not resolve a history source extracted from a
        located parent. Freeze those ordinal links too, without rendering names.
        """
        pending = [node for kind in nodes for node in kind if node is not None]
        seen = set()
        while pending:
            node = self._origin(pending.pop())
            if node is None or node in seen:
                continue
            seen.add(node)
            rule = self._rule(node)
            index, position, _kind, _ordinal = node
            if rule[0] == "h":
                more = [self._input_node(index, j, kind, ordinal) for j, kind, ordinal, _how in rule[1]]
            elif rule[0] == "u":
                more = [(index, position, kind, ordinal) for kind, ordinal, _number in rule[1]]
            elif rule[0] == "l":
                more = [(index, position, kind, ordinal) for kind, ordinal in rule[1]]
            else:
                continue
            pending.extend(source for source in more if source is not None)
        return _CopyContext(names, made, nodes)

    # --- the payload ---------------------------------------------------------------------

    def account(self, body: Any, made_by: Callable[[Any], int | None],
                holder: Callable[[Any], int | None] | None = None) -> tuple[dict[str, Any] | None, dict[str, int]]:
        """The lineage of one unlocated component ``body`` (a ``TopoDS_Shape``):
        ``{"made": <feature name or None>, "faces": [...], "edges": [...],
        "vertices": [...], "table": {<folded atom>: <derivation>}}``, each list
        holding an element name or None per ``TopExp.MapShapes_s`` ordinal, the table
        every folded atom the names reach; None when no feature of the run made any of
        it. ``made_by`` answers, for a ``TopoDS_TShape``, the feature of this run that
        made it. With it, the feature (its index in the run) each feature name the
        lineage holds stands for, with the features those were given: what the
        worker's provenance answers a name of this part with."""
        self._made_by = made_by
        copied = self._copy_of(body, made_by)
        if copied is not None and copied.names is None and copied.made is None:
            # The complete source context proved that no feature named any of
            # this body. Do not open an enclosing assembly just to render x's.
            return None, {}
        maker = self._maker(made_by, body)
        owners = self._owners(made_by, body)
        if maker is None and not owners and holder is not None:
            # No call returned it, but a result holds it -- a part of an assembly a
            # placement copied whole: it is that result's sub-shape, named there.
            for entity in (body, *shape_entities(body)):
                held = holder(entity)
                if held is not None and self._located(held, entity) is not None:
                    owners.append((entity, held))
                    if entity is body:
                        break
        if maker is None and not owners:
            return None, {}
        # A body build123d only wrapped or placed was made by what it wraps.
        made_feature = copied.made if copied is not None else None if maker is None else self.unwrapped(maker)
        roots = [index for _shape, index in owners] + ([made_feature] if made_feature is not None else [])
        names = self._names(roots, made_feature, made_at=max(roots))
        renderer = _Renderer(self, names)
        made_name = (None if made_feature is None else copied.names[made_feature]
                     if copied is not None else names[made_feature])
        payload: dict[str, Any] = {"made": made_name}
        named = False
        # The features the names hold, spelled out or folded into the table, as bits.
        held = 0
        for kind in (FACE, EDGE, VERTEX):
            elements = _map(body, _TOPABS[kind])
            texts = []
            for ordinal in range(1, elements.Extent() + 1):
                node = self._component_node(body, owners, elements.FindKey(ordinal), kind, ordinal)
                rendered = None if node is None else renderer.rendered(node)
                texts.append(None if rendered is None else rendered[0])
                held |= 0 if rendered is None else rendered[2]
            written = renderer.distinct(texts, elements)
            payload[_PLURAL[kind]] = [None if text is None else f"{_LETTER[kind]}:{text}" for text in written]
            named = named or any(text is not None for text in written)
        if maker is None and not named:
            return None, {}
        payload["table"] = renderer.closed([name for kind in (FACE, EDGE, VERTEX)
                                            for name in payload[_PLURAL[kind]] if name is not None])
        stands: set[int] = set() if made_feature is None else {made_feature}
        while held:
            low = held & -held
            stands.add(low.bit_length() - 1)
            held ^= low
        for index in list(stands):
            stands.update(given for given in self.features[index].inputs if given is not None)
        rendered_indices = set(renderer.namings.values())
        named_features = {names[index]: index for index in sorted(stands)
                          if index in names and index not in rendered_indices}
        named_features.update(renderer.namings)
        if made_name is not None:
            named_features[made_name] = made_feature
        return payload, named_features

    def _names(self, roots: list[int], body: int | None, *, made_at: int) -> "_Names":
        """The names of the features a part descends from -- ``roots`` and, transitively,
        every feature that made what one of them was given (:class:`_Names`)."""
        ancestors = 0
        copies = 0
        for index in roots:
            if index is not None:
                ancestors |= self._ancestors[index]
                copies |= self._copy_ancestors[index]
        return _Names(self, ancestors, body, made_at, copies)

    def _maker(self, made_by: Callable[[Any], int | None], body: Any) -> int | None:
        """The feature that made ``body``, or None: the one its TShape is
        registered to, unless that feature was handed the TShape it returned
        (a placement of a shape no feature made)."""
        index = made_by(body.TShape())
        copied = self._copy_of(body, made_by)
        if copied is not None and copied.made is None:
            return None
        if index is not None and self._passed_through(index, body.TShape()):
            return None
        return index

    def _passed_through(self, index: int, tshape: Any) -> bool:
        return any(handle is not None and handle.TShape() == tshape for handle in self.features[index].handles)

    def _owners(self, made_by: Callable[[Any], int | None], body: Any) -> list[tuple[Any, int]]:
        """The shapes of a component some feature made, with that feature: the
        body itself when it is one feature's result, else each solid or shell
        of it that is."""
        index = made_by(body.TShape())
        if index is not None:
            return [(body, index)]
        found = []
        for entity in shape_entities(body):
            index = made_by(entity.TShape())
            if index is not None:
                found.append((entity, index))
        return found

    def _component_node(self, body: Any, owners: list[tuple[Any, int]], element: Any, kind: int,
                        ordinal: int) -> tuple | None:
        """The element of a feature's result that element ``ordinal`` of the component
        ``body`` is: ``(feature, position, kind, ordinal there)``, or None."""
        for shape, index in owners:
            whole = shape is body
            local = element if whole else _relative(element, shape)
            if not whole and not self._own_map(shape, kind).Contains(local):
                continue
            located = self._located(index, shape)
            if located is None:
                return None
            position, location = located
            if whole and location is None:
                return index, position, kind, ordinal
            found = self._local_map(index, position, kind).FindIndex(local if location is None else local.Moved(location))
            return (index, position, kind, found) if found else None
        return None

    # --- where things are ----------------------------------------------------------------

    def _own_map(self, shape: Any, kind: int) -> Any:
        return _frame_map(shape, _TOPABS[kind])

    def _local_map(self, index: int, position: int, kind: Any) -> Any:
        """``TopExp.MapShapes`` of result ``position`` of feature ``index`` in its own frame,
        of one kind (an index of ``_TOPABS``, or a ``TopAbs`` type)."""
        return _frame_map(self.features[index].results[position], _TOPABS[kind] if isinstance(kind, int) else kind)

    def _located(self, index: int, shape: Any) -> tuple[int, Any] | None:
        """Where feature ``index`` returned ``shape``: ``(position, None)`` for a result
        that is it, else ``(position, location)`` for the first result holding it --
        where ``shape`` is placed, if a place of it is, else its first place -- the
        location of it inside that result (unlocated); None when no result holds it."""
        feature = self.features[index]
        tshape = shape.TShape()
        position = feature.position_of(tshape)
        if position is not None:
            return position, None
        topabs = shape.ShapeType()
        for position, result in enumerate(feature.results):
            if result is None:
                continue
            key = (index, position, topabs)
            places = self._places.get(key)
            if places is None:
                elements = self._local_map(index, position, topabs)
                places = self._places[key] = {}
                for ordinal in range(1, elements.Extent() + 1):
                    places.setdefault(elements.FindKey(ordinal).TShape(), []).append(ordinal)
            found = places.get(tshape)
            if not found:
                continue
            elements = self._local_map(index, position, topabs)
            if len(found) == 1:
                return position, elements.FindKey(found[0]).Location()
            relative = _transform(result.Location().Inverted().Multiplied(shape.Location()))
            ordinal = next((at for at in found if _transform(elements.FindKey(at).Location()) == relative), found[0])
            return position, elements.FindKey(ordinal).Location()
        return None

    def _source(self, index: int, j: int) -> tuple:
        """Where input ``j`` of feature ``index`` came from: ``("followed", feature,
        position, location)`` -- the feature that made it, where it returned it
        (:meth:`_located`); ``("foreign",)`` for a shape no other feature made;
        ``("lost",)`` for one a feature made that the trace cannot find in what it
        returned."""
        found = self._sources.get((index, j))
        if found is not None:
            return found
        feature = self.features[index]
        handle = feature.handles[j]
        found = ("foreign",)
        if handle is not None:
            # A later mutation can re-register the same TShape; it made no earlier input.
            makers = [up for up in dict.fromkeys((self._made_by(handle.TShape()), feature.inputs[j]))
                      if up is not None and up < index]
            if makers:
                found = ("lost",)
                for up in makers:
                    located = self._located(up, handle)
                    if located is not None:
                        found = ("followed", up, *located)
                        break
        self._sources[(index, j)] = found
        return found

    def _input_node(self, index: int, j: int, kind: int, ordinal: int) -> tuple | None:
        """The element of a result of the feature that made input ``j`` of feature
        ``index`` that that input's element ``ordinal`` of ``kind`` is, or None."""
        key = (index, j, kind, ordinal)
        found = self._inputs.get(key, False)
        if found is not False:
            return found
        source = self._source(index, j)
        if source[0] != "followed":
            found = None
        else:
            _followed, up, position, location = source
            if location is None:
                found = up, position, kind, ordinal
            else:
                local = self._own_map(self.features[index].handles[j], kind).FindKey(ordinal)
                at = self._local_map(up, position, kind).FindIndex(local.Moved(location))
                found = (up, position, kind, at) if at else None
        self._inputs[key] = found
        return found

    # --- structures ----------------------------------------------------------------------

    def _rule(self, node: tuple) -> tuple | None:
        index, position, kind, ordinal = node
        rules = self._result_rules(index, position)
        if rules is None or not 0 < ordinal <= len(rules[kind]):
            return None
        return rules[kind][ordinal - 1]

    def _cached_result(self, index: int, position: int) -> Any:
        full = self._structures.get(index)
        if full is not None:
            return full.rules[position]
        partial = self._results.get(index)
        if partial is not None and position in partial:
            return partial[position]
        history = self.features[index].history
        if history is not None:
            key = self._skey(index)
            full = history.structures.get(key)
            if full is not None:
                # Full structures retain the original completed-ancestry
                # invariant, including when the current run adopts a hit.
                return self._structure(index).rules[position]
            found = history.result_rules.get((key, position), _MISSING)
            if found is not _MISSING:
                self._local_result(index, position, found)
                return found
        return _MISSING

    def _identity(self, index: int) -> _IdentityInputs:
        found = self._identity_inputs.get(index)
        if found is None:
            found = self._identity_inputs[index] = _IdentityInputs(self.features[index].handles)
        return found

    def _local_result(self, index: int, position: int, rules: tuple | None) -> None:
        partial = self._results.setdefault(index, {})
        partial[position] = rules
        if len(partial) == len(self.features[index].results):
            self._identity_inputs.pop(index, None)

    def _proven_result(self, index: int, position: int, rules: tuple | None) -> None:
        self._local_result(index, position, rules)
        history = self.features[index].history
        if history is not None:
            history.result_rules[(self._skey(index), position)] = rules

    def _identity_nodes(self, index: int, position: int) -> tuple | None:
        """First-owner correspondences for every ordinal, or an unproved result.

        The pending tuples contain no native handles: input index, its ordinal,
        and the source node (None only for an actually foreign input).
        """
        feature = self.features[index]
        if position in feature.copies or not any(handle is not None for handle in feature.handles):
            return None
        identity = self._identity(index)
        kinds = []
        for kind, topabs in enumerate(_TOPABS):
            elements = _map(feature.results[position], topabs)
            nodes = []
            for ordinal in range(1, elements.Extent() + 1):
                owner = identity.owner(kind, elements.FindKey(ordinal))
                if owner is None:
                    return None
                j, source_ordinal = owner
                source = self._source(index, j)
                if source[0] == "foreign":
                    node = None
                else:
                    node = self._input_node(index, j, kind, source_ordinal)
                    if node is None or not 0 <= node[0] < index:
                        return None
                nodes.append((j, source_ordinal, node))
            kinds.append(tuple(nodes))
        return tuple(kinds)

    def _result_rules(self, index: int, position: int) -> Any:
        """Complete one all-identity result, or fall back to the full feature.

        Only complete s/x tables escape this postorder worklist. Mixed results
        retain the full algorithm's global, result-ordered made numbering.
        """
        found = self._cached_result(index, position)
        if found is not _MISSING:
            return found
        stack = [(index, position, False)]
        pending: dict[tuple[int, int], tuple] = {}
        while stack:
            current, at, ready = stack.pop()
            if self._cached_result(current, at) is not _MISSING:
                pending.pop((current, at), None)
                continue
            if self.features[current].results[at] is None:
                self._proven_result(current, at, None)
                continue
            if not ready:
                nodes = self._identity_nodes(current, at)
                if nodes is None:
                    self._structure(current)
                    continue
                pending[(current, at)] = nodes
                stack.append((current, at, True))
                dependencies = dict.fromkeys((node[0], node[1]) for kind in nodes
                                             for _j, _ordinal, node in kind if node is not None)
                stack.extend((up, place, False) for up, place in dependencies
                             if self._cached_result(up, place) is _MISSING)
                continue
            table = []
            complete = True
            for kind, nodes in enumerate(pending.pop((current, at))):
                held = []
                for j, ordinal, node in nodes:
                    source_rule = ("x",)
                    if node is not None:
                        up, place, source_kind, source_ordinal = node
                        source = self._cached_result(up, place)
                        source_rule = (source[source_kind][source_ordinal - 1]
                                       if source is not _MISSING and source is not None
                                       and 0 < source_ordinal <= len(source[source_kind]) else None)
                    rule = _same_rule(j, ordinal, source_rule)
                    if rule is None:
                        complete = False
                        break
                    held.append(rule)
                if not complete:
                    break
                table.append(tuple(held))
            if complete:
                self._proven_result(current, at, tuple(table))
            else:
                self._structure(current)
        return self._cached_result(index, position)

    def _structure(self, index: int) -> _Structure:
        """Feature ``index``'s naming (:class:`_Structure`), with every feature it descends
        from named first, without recursion."""
        found = self._structures.get(index)
        if found is not None:
            return found
        stack = [(index, False)]
        while stack:
            current, ready = stack.pop()
            if current in self._structures:
                continue
            if ready:
                self._structures[current] = self._built(current)
                self._results.pop(current, None)
                self._identity_inputs.pop(current, None)
                continue
            stack.append((current, True))
            for j in range(len(self.features[current].handles)):
                source = self._source(current, j)
                if source[0] == "followed" and source[1] not in self._structures:
                    stack.append((source[1], False))
        return self._structures[index]

    def _skey(self, index: int) -> bytes:
        """What a feature's structure was computed from, beside its own history and shapes:
        for each input, the same of the feature that made it, or that none of this run did.
        The same in every run of the same code, so a hit's structure is its miss's."""
        found = self._skeys.get(index)
        if found is not None:
            return found
        stack = [(index, False)]
        while stack:
            current, ready = stack.pop()
            if current in self._skeys:
                continue
            sources = [self._source(current, j) for j in range(len(self.features[current].handles))]
            if ready:
                parts = [self._skeys[source[1]] if source[0] == "followed" else source[0].encode()
                         for source in sources]
                self._skeys[current] = hashlib.blake2b(b"|".join(parts), digest_size=12).digest()
            else:
                stack.append((current, True))
                stack.extend((source[1], False) for source in sources
                             if source[0] == "followed" and source[1] not in self._skeys)
        return self._skeys[index]

    def _built(self, index: int) -> _Structure:
        feature = self.features[index]
        key = self._skey(index)
        history = feature.history
        if history is not None:
            found = history.structures.get(key)
            if found is not None:
                return found
        structure = self._computed(index)
        if history is not None:
            history.structures[key] = structure
            for partial in [partial for partial in history.result_rules if partial[0] == key]:
                del history.result_rules[partial]
        return structure

    def _same(self, index: int, j: int, kind: int, ordinal: int) -> tuple | None:
        """The rule of an element that is input ``j``'s element ``ordinal``: that element,
        nothing where it is a shape's no feature made, unnamed where the trace cannot
        follow the input."""
        source = self._source(index, j)
        if source[0] == "foreign":
            return _same_rule(j, ordinal, ("x",))
        node = self._input_node(index, j, kind, ordinal)
        if node is None:
            return None
        rule = self._rule(node)
        return _same_rule(j, ordinal, rule)

    def _sames(self, index: int, j: int, kind: int, count: int) -> list[tuple | None]:
        """:meth:`_same` of each of the ``count`` elements of one kind of input ``j`` of
        feature ``index``, by ordinal, together: an input that is a result as it was
        returned has its elements' rules in that result's structure, by the same ordinals."""
        source = self._source(index, j)
        if source[0] == "foreign":
            return [("x",)] * count
        if source[0] != "followed":
            return [None] * count
        _followed, up, position, location = source
        if location is not None:
            return [self._same(index, j, kind, ordinal) for ordinal in range(1, count + 1)]
        rules = self._result_rules(up, position)
        held = () if rules is None else rules[kind]
        return [_same_rule(j, ordinal, held[ordinal - 1] if ordinal <= len(held) else None)
                for ordinal in range(1, count + 1)]

    def _computed(self, index: int) -> _Structure:
        feature = self.features[index]
        if feature.op in _FILE_READS and not any(handle is not None for handle in feature.handles):
            self._identity_inputs.pop(index, None)
            return _read_structure(feature)
        origins = feature.history.origins if feature.history is not None else {}
        placement = feature.operation in _PLACEMENTS
        identity = self._identity(index)
        sames: dict[tuple[int, int], list[tuple | None]] = {}

        def same(j: int, kind: int, ordinal: int) -> tuple | None:
            found = sames.get((j, kind))
            if found is None:
                found = sames[(j, kind)] = self._sames(index, j, kind, identity.count(j, kind))
            return found[ordinal - 1]

        # What the feature made, numbered per kind in the order of its results, each result's
        # pieces in the order of where they are (``_in_place_order``) -- per target, for a tuple
        # assignment's (``Feature.groups``), each named by its own.
        made_by_group: dict[int, list[Any]] = {}
        rules: list[list[list[tuple]] | None] = []
        for position, result in enumerate(feature.results):
            if result is None:
                rules.append(None)
                continue
            proven = self._results.get(index, {}).get(position, _MISSING)
            if proven is _MISSING and feature.history is not None:
                proven = feature.history.result_rules.get((self._skey(index), position), _MISSING)
            if proven is not _MISSING:
                rules.append(None if proven is None else [list(kind) for kind in proven])
                continue
            copied = feature.copies.get(position)
            if copied is not None:
                rules.append([[("x",) if node is None else ("c", position, kind, ordinal)
                               for ordinal, node in enumerate(held, 1)]
                              for kind, held in enumerate(copied.nodes)])
                continue
            maps = [_map(result, topabs) for topabs in _TOPABS]
            partners = [j for j, handle in enumerate(feature.handles)
                        if handle is not None and handle.TShape() == result.TShape() and not handle.IsSame(result)]
            table: list[list[tuple | None]] = [[None] * maps[kind].Extent() for kind in range(3)]
            for kind in range(3):
                by_history = False
                held = table[kind]
                if not held:
                    continue
                find = maps[kind].FindKey
                for ordinal in range(1, len(held) + 1):
                    element = find(ordinal)
                    rule = None
                    owner = identity.owner(kind, element)
                    if owner is not None:
                        j, source_ordinal = owner
                        rule = same(j, kind, source_ordinal)
                        if rule is None and placement:
                            # An input's element no name reaches: placing or holding it
                            # makes it no element of this feature's.
                            rule = ("x",)
                    if rule is None and partners:
                        rule = same(partners[0], kind, ordinal)
                    if rule is None and origins:
                        rule = self._history_rule(origins.get((position, kind, ordinal)), kind, same)
                        by_history = by_history or rule is not None
                    held[ordinal - 1] = rule
                if by_history:
                    _ranked(held)
            _passes(result, maps, table)
            group = feature.groups[position] if feature.groups is not None else 0
            made = made_by_group.get(group)
            if made is None:
                made = made_by_group[group] = [IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher() for _kind in _TOPABS]
            leaves = _MISSING
            for kind in range(3):
                held, find, add = table[kind], maps[kind].FindKey, made[kind].Add
                if None not in held:
                    continue
                if leaves is _MISSING:
                    leaves = _leaves(result)
                for ordinal in _in_place_order(leaves, maps[kind], _TOPABS[kind], held):
                    if held[ordinal - 1] is None:
                        held[ordinal - 1] = ("m", add(find(ordinal)))
            rules.append(table)
        self._identity_inputs.pop(index, None)
        return _Structure(rules)

    @staticmethod
    def _history_rule(found: tuple | None, kind: int,
                      same: Callable[[int, int, int], tuple | None]) -> tuple | None:
        """The rule history gives an element with origins ``found``: a copy is its source;
        else its sources that have names, with the places it has among what was reported of
        them (``_ranked`` reads them), or nothing (the element falls to the passes).
        ``same`` is :meth:`_same` of the feature's inputs."""
        if not found:
            return None
        for j, source_kind, ordinal, how, _place in found:
            if how == "I" and source_kind == kind:
                return same(j, kind, ordinal)
        named = []
        for j, source_kind, ordinal, how, place in found:
            if how == "I":
                continue
            rule = same(j, source_kind, ordinal)
            if rule is not None and rule[0] != "x":
                named.append((j, source_kind, ordinal, how, place))
        if not named:
            return None
        named.sort()
        return "h", tuple(source[:4] for source in named), 1, named[0][4]

    def _origin(self, node: tuple) -> tuple | None:
        """The element ``node`` resolves to through the inputs it is: the first, back
        through the features, that is no input's; None where that is a shape's no
        feature made."""
        found = self._origins.get(node, False)
        if found is not False:
            return found
        path = []
        current: tuple | None = node
        while current is not None:
            known = self._origins.get(current, False)
            if known is not False:
                current = known
                break
            path.append(current)
            rule = self._rule(current)
            if rule is None or rule[0] == "x":
                current = None
                break
            if rule[0] != "s":
                break
            index, _position, kind, _ordinal = current
            current = self._input_node(index, rule[1], kind, rule[2])
        for visited in path:
            self._origins[visited] = current
        return current


class _Names:
    """The names of the features one part descends from (``ancestors``, bits by index),
    each computed when first asked: counted among them in call order -- a label pinned
    by the time the part was made (by feature ``made_at``, the last of its own), the first
    of the part's features to claim it keeping it, else its assignment's target
    (``_name``), else ``<function>.<operation><count>``, every unassigned feature counting
    in its stem. ``body`` is the feature that made the part's body,
    whose own label names the occurrence and pins nothing here: identical constructions
    labelled apart are one part, named alike. A label pinned later -- set on a shape after
    it was given to the construction that made this part -- renames nothing here."""

    def __init__(self, trace: Trace, ancestors: int, body: int | None, made_at: int,
                 copies: int = 0) -> None:
        self.trace = trace
        self.ancestors = ancestors
        self.body = body
        self.made_at = made_at
        self.found: dict[int, str] = {}
        self.copies = copies
        self.overrides: dict[int, tuple[str, int]] = {}
        self._claims: dict[str, tuple[int, int] | None] = {}
        # Per class of siblings (``Trace._siblings``): each one this part descends from, and
        # the place it is counted in.
        self._places: dict[tuple[int, ...], dict[int, int]] = {}

    def __contains__(self, index: object) -> bool:
        return isinstance(index, int) and index >= 0 and (self.ancestors >> index) & 1 == 1

    def __getitem__(self, index: int) -> str:
        name = self.get(index)
        if name is None:
            raise KeyError(index)
        return name

    def get(self, index: int, default: str | None = None) -> str | None:
        if index not in self:
            return default
        if index in self.overrides:
            return self.overrides[index][0]
        name = self.found.get(index)
        if name is None:
            name = self.found[index] = self._name(index)
        return name

    def at(self, index: int, position: int) -> str | None:
        """Feature ``index``'s name for what it made at result ``position``: its name
        (``get``), but a tuple assignment's own target for each shape it returned."""
        if index not in self:
            return None
        feature = self.trace.features[index]
        self.trace._labels()
        pinned = self.trace._pinned_results.get((index, position)) if index not in self.overrides else None
        if pinned is not None and pinned[1] <= self.made_at and index != self.body:
            return pinned[0]
        if feature.groups is None or index in self.overrides or position >= len(feature.groups):
            return self.get(index)
        name = self.get(index)
        if name is None or self._labelled_name(index) is not None:
            return name
        self.trace._assignments()
        if self.trace._heads.get((feature.execution, feature.target)) != index:
            return name
        function = identifier(feature.namer)
        return f"{function}.{self._counted(index, feature.targets[feature.groups[position]], function)}"

    def binding(self, index: int) -> int:
        return self.overrides[index][1] if index in self.overrides else index

    def labelled(self, index: int, label: str, binding: int) -> "_Names":
        names = _Names(self.trace, self.ancestors, self.body, self.made_at, self.copies)
        names.overrides = {**self.overrides, index: (label, binding)}
        return names

    def _claimer(self, label: str) -> tuple[int, int] | None:
        if label in self._claims:
            return self._claims[label]
        self.trace._labels()
        claims = [(index, -1) for index in self.trace._labelled.get(label, ())
                  if index in self and self._pins(index)]
        copied = self.copies & self.trace._copy_labels.get(label, 0)
        while copied:
            low = copied & -copied
            context = self.trace._copy_contexts[low.bit_length() - 1]
            if context.owner[0] in self and context.pinned_at is not None and context.pinned_at <= self.made_at:
                claims.append(context.owner)
            copied ^= low
        claim = self._claims[label] = min(claims) if claims else None
        return claim

    def copy_label(self, context: _CopyContext) -> tuple[str, int] | None:
        if context.label is None or context.made is None or context.pinned_at is None or context.pinned_at > self.made_at:
            return None
        claim = self._claimer(context.label)
        if claim == context.owner or claim == (context.made, -1):
            return context.label, claim[0]
        return None

    def _labelled_name(self, index: int) -> str | None:
        self.trace._labels()
        label = self.trace.features[index].label
        if label is not None and self._pins(index) and self._claimer(label) == (index, -1):
            return label
        return None

    def _name(self, index: int) -> str:
        """A label that pins it; else ``<function>.<target>`` for the call whose result an
        assignment stores, and ``<function>.<target>_<operation><n>`` for the calls the same
        execution of that statement made before it; else ``<function>.<operation><count>``."""
        trace = self.trace
        feature = trace.features[index]
        label = self._labelled_name(index)
        if label is not None:
            return label
        if feature.execution is not None:
            trace._assignments()
            head = trace._heads[(feature.execution, feature.target)]
            function = identifier(feature.namer)
            base = self._counted(head, feature.target, function)
            if index == head:
                return f"{function}.{base}"
            return f"{function}.{base}_{feature.operation}{trace._number(index)}"
        stem = feature.stem
        trace._assignments()
        place = index
        siblings = trace._siblings.get(index)
        if siblings is not None:
            # Counted in the place its piece's position gives it among the siblings this
            # part descends from (``Trace._counting_order``).
            places = self._places.get(siblings)
            if places is None:
                held = [member for member in siblings if member in self]
                places = self._places[siblings] = (
                    {} if len(held) < 2 or trace._alike(held) else dict(zip(trace._by_place(held), held)))
            place = places.get(index, index)
        return f"{stem}{(self.ancestors & trace._stems[stem] & ((2 << place) - 1)).bit_count()}"

    def _counted(self, head: int, target: str, function: str) -> str:
        """``target`` as the n-th execution of an assignment to it in ``function`` that this
        part descends from -- of a reassignment, the n-th of its skeleton, whose tag its
        target carries (``sources._named_sites``) -- head ``head`` the n-th: the first as it
        is, then ``target2``, ``target3``... (``target_2`` for a target ending in a digit)."""
        stem = self.trace._target_stems.get(f"{function}.{target}", 0)
        count = (self.ancestors & stem & ((1 << head) - 1)).bit_count() + 1
        if count == 1:
            return target
        return f"{target}{'_' if target[-1].isdigit() else ''}{count}"

    def _pins(self, index: int) -> bool:
        feature = self.trace.features[index]
        return feature.pinned_at is not None and feature.pinned_at <= self.made_at and index != self.body


class _Renderer:
    """The names of one part's elements: each element's derivation rendered with the
    part's feature names (``Trace._names``), folded where long, and the table of what
    each folded atom stands for."""

    def __init__(self, trace: Trace, names: _Names) -> None:
        self.trace = trace
        self.names = names
        # node -> (text, the feature of its last step, or of its atom, and every feature the
        # text names -- spelled out or in what it folds -- as bits by index), or None
        self.texts: dict[tuple, tuple[str, str, int] | None] = {}
        self.table: dict[str, str] = {}
        self.namings: dict[str, int] = {}
        self._copied: dict[_Renderer, None] = {}

    def rendered(self, node: tuple) -> tuple[str, str, int] | None:
        """The element's name -- its text, its last feature and the features it holds -- or
        None, each element it is made of rendered first, without recursion."""
        origin = self.trace._origin(node)
        if origin is None:
            return None
        texts = self.texts
        if origin in texts:
            return texts[origin]
        stack = [origin]
        open_: set[tuple] = set()
        depends: dict[tuple, tuple[tuple, list[tuple | None]]] = {}
        while stack:
            current = stack[-1]
            if current in texts:
                stack.pop()
                continue
            found = depends.get(current)
            if found is None:
                found = depends[current] = self._depends(current)
            needs = [need for need in found[1] if need is not None and need not in texts]
            if needs and current not in open_:
                open_.add(current)
                stack.extend(need for need in needs if need not in open_)
                continue
            texts[current] = self._composed(current, *found)
            stack.pop()
        return texts[origin]

    def _depends(self, node: tuple) -> tuple[tuple, list[tuple | None]]:
        """An element's rule, and the elements its name is made of -- its sources, its
        parent candidates, its lower elements, in the rule's order -- each as the element it
        resolves to (``Trace._origin``), or None."""
        rule = self.trace._rule(node) or ("x",)
        index, position, _kind, _ordinal = node
        if rule[0] == "h":
            found = [self.trace._input_node(index, j, source_kind, ordinal)
                     for j, source_kind, ordinal, _how in rule[1]]
        elif rule[0] == "u":
            found = [(index, position, parent_kind, parent) for parent_kind, parent, _number in rule[1]]
        elif rule[0] == "l":
            found = [(index, position, lower_kind, lower) for lower_kind, lower in rule[1]]
        else:
            return rule, []
        return rule, [None if element is None else self.trace._origin(element) for element in found]

    def _composed(self, node: tuple, rule: tuple, origins: list[tuple | None]) -> tuple[str, str, int] | None:
        """The name of ``node`` by its ``rule``, the elements it is made of (``origins``,
        :meth:`_depends`) rendered."""
        texts = self.texts
        index = node[0]
        if rule[0] == "c":
            _tag, position, kind, ordinal = rule
            context = self.trace.features[index].copies[position]
            source = context.nodes[kind][ordinal - 1]
            if source is None or context.names is None:
                return None
            if context.renderer is None:
                context.renderer = _Renderer(self.trace, context.names)
            renderer = context.renderer
            labelled = self.names.copy_label(context)
            if labelled is not None:
                renderer = context.labelled.get(labelled)
                if renderer is None:
                    renderer = context.labelled[labelled] = _Renderer(
                        self.trace, context.names.labelled(context.made, *labelled))
            rendered = renderer.rendered(source)
            self._copied[renderer] = None
            return rendered
        feature = self.names.at(index, node[1])
        if feature is None or rule[0] in ("x", "s"):
            return None
        binding = self.names.binding(index)
        self.namings[feature] = binding
        if rule[0] == "m":
            return f"{feature}.{rule[1]}", feature, 1 << binding
        if rule[0] == "n":
            return rule[1], feature, 1 << binding
        if rule[0] == "h":
            sources = []
            for (j, source_kind, _ordinal, how), origin in zip(rule[1], origins):
                rendered = None if origin is None else texts.get(origin)
                if rendered is not None:
                    sources.append((source_kind, j, rendered, how))
            if not sources:
                return None
            sources.sort(key=lambda source: (source[0], source[1], source[2][0]))
            hows = {how for _kind, _j, _rendered, how in sources}
            base_kind = sources[0][0]
            op = "M" if hows == {"M"} else ("G" if hows == {"G"} else "MG") + _LETTER[base_kind]
            if rule[2] > 1:
                op += str(rule[2])
            extras = _distinct([(source_kind, rendered) for source_kind, _j, rendered, _how in sources])
            return self._step(sources[0][2], op, feature, binding, extras[1:1 + _EXTRAS])
        if rule[0] == "u":
            candidates = []
            for (_parent_kind, _parent, number), origin in zip(rule[1], origins):
                rendered = None if origin is None else texts.get(origin)
                if rendered is not None:
                    candidates.append((rendered[0], number, rendered))
            if not candidates:
                return None
            _text, number, rendered = min(candidates)
            return self._step(rendered, f"U{number}" if number > 1 else "U", feature, binding, [])
        if rule[0] == "l":
            lowers = []
            for (lower_kind, _lower), origin in zip(rule[1], origins):
                rendered = None if origin is None else texts.get(origin)
                if rendered is None:
                    return None
                lowers.append((rendered[0], lower_kind, rendered))
            lowers.sort(key=lambda lower: lower[0])
            extras = _distinct([(lower_kind, rendered) for _text, lower_kind, rendered in lowers])
            return self._step(lowers[0][2], "L", feature, binding, extras[1:1 + _EXTRAS])
        return None

    def _step(self, base: tuple[str, str, int], op: str, feature: str, index: int,
              extras: list[tuple[int, tuple[str, str, int]]]) -> tuple[str, str, int]:
        """``base`` and a step feature ``index`` (named ``feature``) took, its further
        sources as atoms, folded where long."""
        text = f"{base[0]};{op}:{feature}" + "".join(f"+{_LETTER[kind]}:{self.atom(rendered)}"
                                                    for kind, rendered in extras)
        held = base[2] | 1 << index
        for _kind, rendered in extras:
            held |= rendered[2]
        return (self.folded(text, feature) if len(text) > FOLD_LENGTH else text), feature, held

    def atom(self, rendered: tuple[str, str, int]) -> str:
        """A rendered derivation as an atom: itself where it is one, else folded."""
        text, feature, _held = rendered
        return text if ";" not in text else self.folded(text, feature)

    def folded(self, text: str, feature: str) -> str:
        """``text`` as an atom: ``feature`` and a digest of it, the table spelling it."""
        atom = f"{feature}~{hashlib.sha256(text.encode()).hexdigest()[:12]}"
        self.table[atom] = text
        return atom

    def distinct(self, texts: list[str | None], elements: Any) -> list[str | None]:
        """One kind's names of a component (``elements``, its map of that kind), each named
        alike after the first given the next ``;D<n>``, in the order of where their elements
        are (``_place``), then of their ordinals: the B-rep's order is OCCT's, which a
        boolean's heap can change, and where an element is is the geometry's."""
        alike: dict[str, list[int]] = {}
        for at, text in enumerate(texts):
            if text is not None:
                alike.setdefault(text, []).append(at)
        found: list[str | None] = list(texts)
        for text, places in alike.items():
            if len(places) < 2:
                continue
            ordered = sorted(places, key=lambda at: (_place(elements.FindKey(at + 1)), at))
            for number, at in enumerate(ordered[1:], 2):
                marked = f"{text};D{number}"
                if len(marked) > FOLD_LENGTH:
                    marked = self.folded(marked, _features(text)[-1])
                found[at] = marked
        return found

    def closed(self, names: list[str]) -> dict[str, str]:
        """The table entries element ``names`` reach: every folded atom they or the entries
        name."""
        # Borrow each source table once per account, not once per copied element
        # (which would repeatedly copy a growing table for a large part).
        stack = [(self, False)]
        merged: set[_Renderer] = set()
        while stack:
            renderer, ready = stack.pop()
            if renderer in merged:
                continue
            if not ready:
                stack.append((renderer, True))
                stack.extend((source, False) for source in renderer._copied if source not in merged)
                continue
            for source in renderer._copied:
                renderer.table.update(source.table)
                renderer.namings.update(source.namings)
            merged.add(renderer)
        closed: dict[str, str] = {}
        pending = folded_atoms("\n".join(names))
        while pending:
            reached = pending.pop()
            if reached not in closed and reached in self.table:
                # (An atom a read file's name folded is spelled in that file's own table.)
                closed[reached] = self.table[reached]
                if "~" in closed[reached]:
                    pending.extend(folded_atoms(closed[reached]))
        return dict(sorted(closed.items()))


def _features(text: str) -> list[str]:
    """The features a derivation this module wrote names, in order, its last step's last:
    its atoms' and its steps'."""
    atom, *steps = text.split(";")
    found = [atom.split("~", 1)[0] if "~" in atom else atom.rsplit(".", 1)[0]]
    for step in steps:
        head, *extras = step.split("+")
        found.extend(extra[2:].split("~", 1)[0] if "~" in extra else extra[2:].rsplit(".", 1)[0] for extra in extras)
        if ":" in head:
            found.append(head.split(":", 1)[1])
    return found


def _read_structure(feature: Feature) -> _Structure:
    """A file read's naming: every element of what it made is its own, named within its
    own product -- the shape of a part of the file, however often the file places it --
    never across the file. An element the file names (``Feature.imported``) is named so:
    as it is, where the name is an element name of its kind (a file this engine wrote),
    else as the name and its number among the product's elements the file names alike
    (``f:TopFace.1``); every other element by its ordinal in the product
    (``f:<feature>.<ordinal>``). An assembly of the file holds its products' elements, by
    their names there. Results come products after the assemblies holding them, so they
    are named from the last."""
    rules: dict[Any, tuple] = {}
    table: list[list[list[tuple]] | None] = [None] * len(feature.results)
    for position in range(len(feature.results) - 1, -1, -1):
        result = feature.results[position]
        if result is None:
            continue
        named = feature.imported.get(position) or {}
        kinds = []
        for kind, topabs in enumerate(_TOPABS):
            elements = _map(result, topabs)
            texts = named.get(kind) or {}
            alike: Counter = Counter()
            held = []
            for ordinal in range(1, elements.Extent() + 1):
                tshape = elements.FindKey(ordinal).TShape()
                rule = rules.get((kind, tshape))
                if rule is None:
                    text = texts.get(ordinal)
                    if text is None or text.strip().upper() in _UNNAMED:
                        rule = ("m", ordinal)
                    elif ELEMENT_NAME.fullmatch(text) and text[0] == _LETTER[kind]:
                        rule = ("n", text[2:])
                    else:
                        word = identifier(text)
                        alike[word] += 1
                        rule = ("n", f"{word}.{alike[word]}")
                    rules[(kind, tshape)] = rule
                held.append(rule)
            kinds.append(held)
        table[position] = kinds
    return _Structure(table)


def _groups(results: list[Any], returned: list[Any], count: int) -> tuple[int, ...] | None:
    """Per result position, which of the ``count`` shapes a call returned it is or holds,
    when it returned that many: each target of a tuple assignment names its own; None
    otherwise."""
    if len(returned) != count:
        return None
    starts = {_object_key(shape): k for k, shape in enumerate(returned)}
    found = []
    current = 0
    for shape in results:
        k = starts.get(_object_key(shape))
        if k is not None and returned[k] is shape:
            current = k
        found.append(current)
    return tuple(found)


def _ranked(rules: list[tuple | None]) -> None:
    """Tell apart, in one result's elements of one kind, those history made alike -- the
    same sources, taken the same way: a ruled loft reports each piece of a long edge as
    generated from every vertex on it -- by their place among what was reported of their
    first source, FreeCAD's index: the second and later are numbered in their step
    (``;Gv2:``), where a later operation leaves the number alone."""
    alike: dict[tuple, list[int]] = {}
    for at, rule in enumerate(rules):
        if rule is not None and rule[0] == "h":
            alike.setdefault(rule[1], []).append(at)
    for members in alike.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda at: (rules[at][3], at))
        for rank, at in enumerate(members, 1):
            _tag, sources, _rank, place = rules[at]
            rules[at] = ("h", sources, rank, place)


def _distinct(named: list[tuple[int, tuple[str, str, int]]]) -> list[tuple[int, tuple[str, str, int]]]:
    """Sources or lower elements, each kind and name once, in order: a name twice adds
    nothing to a name made of it."""
    seen: set[tuple[int, str]] = set()
    found = []
    for kind, rendered in named:
        if (kind, rendered[0]) not in seen:
            seen.add((kind, rendered[0]))
            found.append((kind, rendered))
    return found


def _passes(result: Any, maps: list[Any], table: list[list[tuple | None]]) -> None:
    """The reverse and forward passes over one result's elements (``maps``, by kind),
    naming in ``table`` what identity and history left unnamed (None): an edge of a named
    face, then a vertex of a named edge, from its parents (``u``), each with its number
    among that parent's unnamed elements of its kind; then an edge whose vertices are all
    named, and a face whose outer wire's edges are, from those (``l``). Only the unnamed
    are visited: a parent is found from its child, through the result's map of ancestors."""
    if all(None not in rules for rules in table):
        return
    if not any(rule is not None and rule[0] != "x" for rules in table for rule in rules):
        return  # nothing named: each pass names only from what is

    def named(kind: int, ordinal: int) -> bool:
        rule = table[kind][ordinal - 1]
        return rule is not None and rule[0] != "x"

    for parent_kind, child_kind in ((FACE, EDGE), (EDGE, VERTEX)):
        children = [ordinal for ordinal, rule in enumerate(table[child_kind], 1) if rule is None]
        if not children:
            continue
        ancestors = IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher()
        TopExp.MapShapesAndAncestors_s(result, _TOPABS[child_kind], _TOPABS[parent_kind], ancestors)
        # Per parent, each of its unnamed children's number among them, in its own order.
        numbers: dict[int, dict[int, int]] = {}
        candidates: dict[int, list[tuple[int, int, int]]] = {}
        for child in children:
            at = ancestors.FindIndex(maps[child_kind].FindKey(child))
            if not at:
                continue
            parents = sorted({maps[parent_kind].FindIndex(shape) for shape in listed(ancestors.FindFromIndex(at))}
                             - {0})
            for parent in parents:
                if not named(parent_kind, parent):
                    continue
                counted = numbers.get(parent)
                if counted is None:
                    counted = numbers[parent] = {}
                    subs = _map(maps[parent_kind].FindKey(parent), _TOPABS[child_kind])
                    for index in range(1, subs.Extent() + 1):
                        sub = maps[child_kind].FindIndex(subs.FindKey(index))
                        if sub and table[child_kind][sub - 1] is None:
                            counted[sub] = len(counted) + 1
                if child in counted:
                    candidates.setdefault(child, []).append((parent_kind, parent, counted[child]))
        for child, found in candidates.items():
            table[child_kind][child - 1] = ("u", tuple(found))
    for ordinal in range(1, maps[EDGE].Extent() + 1):
        if table[EDGE][ordinal - 1] is None:
            lowers = _lowers(TopExp_Explorer(maps[EDGE].FindKey(ordinal), TopAbs_VERTEX), maps[VERTEX], named, VERTEX)
            if lowers:
                table[EDGE][ordinal - 1] = ("l", tuple((VERTEX, lower) for lower in lowers))
    for ordinal in range(1, maps[FACE].Extent() + 1):
        if table[FACE][ordinal - 1] is None:
            wire = BRepTools.OuterWire_s(TopoDS.Face(maps[FACE].FindKey(ordinal)))
            if wire.IsNull():
                continue
            lowers = _lowers(TopExp_Explorer(wire, TopAbs_EDGE), maps[EDGE], named, EDGE)
            if lowers:
                table[FACE][ordinal - 1] = ("l", tuple((EDGE, lower) for lower in lowers))


def _lowers(explorer: Any, elements: Any, named: Callable[[int, int], bool], kind: int) -> list[int] | None:
    """The ordinals of what ``explorer`` visits, each once, when all of them are named."""
    found: list[int] = []
    while explorer.More():
        ordinal = elements.FindIndex(explorer.Current())
        if not ordinal or not named(kind, ordinal):
            return None
        if ordinal not in found:
            found.append(ordinal)
        explorer.Next()
    return found or None


# --- helpers ----------------------------------------------------------------------------


def _classify(filename: str) -> str:
    """``"model"`` for first-party source, ``"own"`` for cadgen's internal
    frames, ``"other"`` for everything skipped (build123d, cadgen's public
    helpers, the memo itself, the standard library)."""
    if not filename or filename.startswith("<"):
        return "other"
    try:
        path = Path(filename).resolve()
    except (OSError, RuntimeError):
        return "other"
    if path.parent == _HERE or path in _API:
        return "other"
    if any(root in path.parents for root in _OWN):
        return "own"
    return "model" if _first_party(path) else "other"


@functools.lru_cache(maxsize=65536)
def _first_party(path: Path) -> bool:
    """A ``.py`` file of the model's own: not the standard library, not an installed
    package, not cadgen (a library a model calls counts as build123d does)."""
    return path.suffix == ".py" and not any(root == path or root in path.parents for root in _library_roots())


@functools.lru_cache(maxsize=65536)
def first_party_file(filename: str) -> bool:
    """:func:`_first_party` of a module's or a frame's file name, resolved once per name."""
    if not filename or filename.startswith("<"):
        return False
    try:
        return _first_party(Path(filename).resolve())
    except (OSError, RuntimeError):
        return False


@functools.cache
def _library_roots() -> tuple[Path, ...]:
    import site
    import sysconfig

    found: set[Path] = {_ENGINE.parent}
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            found.add(Path(value).resolve())
    # And every installed-packages folder on the module search path, whoever put it there: a
    # ``.pth`` line or PYTHONPATH reaching another environment's packages (numpy, build123d)
    # makes them no less a library than this interpreter's own.
    entries = [entry for entry in sys.path if entry and Path(entry).name in ("site-packages", "dist-packages")]
    for value in (sys.prefix, sys.base_prefix, sys.exec_prefix, *site.getsitepackages(), site.getusersitepackages(),
                  *entries):
        if value:
            try:
                found.add(Path(value).resolve())
            except OSError:
                pass
    return tuple(found)


def folded_atoms(text: str) -> list[str]:
    """The folded atoms of names one per line, or of a derivation: read off each '~',
    which only a folded atom holds -- the feature before it, back to the ':' or the
    start, and the twelve hex digits of the digest after it."""
    pieces = text.split("~")
    return [f"{piece.rsplit(':', 1)[-1]}~{after[:12]}" for piece, after in zip(pieces, pieces[1:])]


def shape_entities(shape: Any) -> tuple:
    """A body's solids, else its shells, else the body: the shapes of it a feature may
    have made one by one."""
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID

    for kind in (TopAbs_SOLID, TopAbs_SHELL):
        found = []
        explorer = TopExp_Explorer(shape, kind)
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
        if found:
            return tuple(found)
    return (shape,)


def handle_of(shape: Any) -> Any:
    """A handle copy of the shape's ``TopoDS`` from its own state, or None: an
    empty shape, or a child model's promise or a reference assembly, whose
    property would force what the body only placed."""
    state = getattr(shape, "__dict__", None)
    wrapped = None if state is None else state.get("_wrapped")
    return None if wrapped is None else wrapped.Located(wrapped.Location())


def _input_index(given: list[tuple[int, list[Any]]], kind: int) -> tuple[Any, Any]:
    """An element's first input and ordinal, under the input maps' ``IsSame`` equality.
    A first input with no name still owns the element; later inputs never replace it.
    Kept with the feature's inputs (``Trace._identity_inputs``) until every result it
    names, or its whole structure, is done.
    ``index.FindIndex(element)`` is the element's place among the inputs' elements, in
    input order (0 where none holds it), and ``owners[place - 1]`` its input and its
    ordinal there. A few inputs (a boolean's) are asked in turn (``_FirstOwners``), which
    costs a result's element a lookup or two; more (a compound of many) are made one map
    of every element of every input, which costs each of them one step."""
    if len(given) <= _SCANNED_INPUTS:
        owners = _FirstOwners([(j, held[kind]) for j, held in given])
        return owners, owners
    elements = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    union: list[tuple[int, int]] = []
    for j, held in given:
        source = held[kind]
        for ordinal in range(1, source.Extent() + 1):
            at = elements.Add(source.FindKey(ordinal))
            if at > len(union):
                union.append((j, ordinal))
    return elements, union


# Up to this many inputs, an element's owner is asked of each input in turn.
_SCANNED_INPUTS = 3


class _FirstOwners:
    """The first input whose map holds an element, asked of each map in turn: a result's
    element costs a lookup or two, where a union of the inputs' maps would cost every
    element of every input a step to build (``_input_index``)."""

    __slots__ = ("maps", "starts")

    def __init__(self, maps: list[tuple[int, Any]]) -> None:
        self.maps = maps
        self.starts: list[int] = []
        offset = 0
        for _j, elements in maps:
            self.starts.append(offset)
            offset += elements.Extent()

    def FindIndex(self, element: Any) -> int:  # noqa: N802 - the map interface it stands in for
        for (_j, elements), start in zip(self.maps, self.starts):
            ordinal = elements.FindIndex(element)
            if ordinal:
                return start + ordinal
        return 0

    def __getitem__(self, place: int) -> tuple[int, int]:
        at = bisect.bisect_right(self.starts, place) - 1
        return self.maps[at][0], place - self.starts[at] + 1


def _relative(element: Any, shape: Any) -> Any:
    """``element`` (of a shape ``shape`` is part of, in that shape's frame) in
    ``shape``'s own frame."""
    location = shape.Location()
    return element if location.IsIdentity() else element.Moved(location.Inverted())


def _place(shape: Any) -> tuple:
    """Where a shape is, from its geometry alone: its type, and the size and centre of its
    faces (area), else its edges (length), else its first vertex, rounded as positions are.
    Tolerances, the heap and the order of its sub-shapes play no part. Measured once per
    TShape in its own frame (``_PLACES``) and carried to the shape's placement."""
    tshape = shape.TShape()
    found = _PLACES.get(tshape)
    if found is None:
        found = _PLACES[tshape] = _own_place(shape.Located(TopLoc_Location()))
        while len(_PLACES) > _PLACES_HELD:
            _PLACES.popitem(last=False)
    else:
        _PLACES.move_to_end(tshape)
    dimension, size, centre = found
    if centre is None:
        return (int(shape.ShapeType()),)
    location = shape.Location()
    if not location.IsIdentity():
        transform = location.Transformation()
        centre = centre.Transformed(transform)
        size *= abs(transform.ScaleFactor()) ** dimension
    return (int(shape.ShapeType()), int(round(size / _POSITION_QUANTUM)),
            *(int(round(value / _POSITION_QUANTUM)) for value in centre.Coord()))


# Where each TShape is in its own frame (``_place``): the dimension its size is measured
# in, the size and the centre, unrounded. A TShape's geometry never changes once built,
# and placed prototypes and a warm build's replayed shapes hand naming the same TShapes
# again, so the integral over its faces is taken once per process, the least recently
# asked dropped past the bound.
_PLACES: "OrderedDict[Any, tuple]" = OrderedDict()
_PLACES_HELD = 1 << 16


def _own_place(shape: Any) -> tuple:
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    if TopExp_Explorer(shape, TopAbs_FACE).More():
        BRepGProp.SurfaceProperties_s(shape, props)
        dimension = 2
    elif TopExp_Explorer(shape, TopAbs_EDGE).More():
        BRepGProp.LinearProperties_s(shape, props)
        dimension = 1
    else:
        explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
        if not explorer.More():
            return 0, 0.0, None
        return 0, 0.0, BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current()))
    return dimension, props.Mass(), props.CentreOfMass()


def _leaves(shape: Any) -> tuple | None:
    """The shapes a compound holds, through the compounds it holds, as a tree -- a leaf, or
    ``(compound, children)`` --; None for a shape that holds fewer than two. Ordered by
    where they are only as far as a kind's made elements ask (``_in_place_order``)."""
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopoDS import TopoDS_Iterator

    count = 0

    def tree(current: Any) -> Any:
        nonlocal count
        if current.ShapeType() != TopAbs_COMPOUND:
            count += 1
            return current
        children = []
        iterator = TopoDS_Iterator(current)
        while iterator.More():
            children.append(tree(iterator.Value()))
            iterator.Next()
        return current, children

    found = tree(shape)
    return found if count > 1 else None


def _in_place_order(leaves: tuple | None, elements: Any, topabs: Any, held: list) -> Any:
    """The ordinals of ``elements`` (a result's map of one kind) not yet named (None in
    ``held``) in the order the result's pieces (``leaves``) hold them, each piece's in its
    own order, the pieces of each compound in the order of where they are (``_place``),
    then as held; the result's order where it is one piece. OCCT hands some makers' pieces
    back in an order that depends on the heap (a text's glyph faces), so a compound's order
    is no function of the code; where its pieces are is. Only the pieces holding such an
    element are placed, and only where a compound holds two of them."""
    if leaves is None:
        return range(1, elements.Extent() + 1)
    find = elements.FindIndex
    # Per piece holding an element not yet named, those elements' ordinals in its order;
    # each node holding such a piece.
    holds: dict[int, list[int]] = {}
    relevant: set[int] = set()

    def gather(node: Any) -> bool:
        if isinstance(node, tuple):
            found = False
            for child in node[1]:
                found = gather(child) or found
        else:
            mapped = _map(node, topabs)
            ordinals = [ordinal for ordinal in (find(mapped.FindKey(at)) for at in range(1, mapped.Extent() + 1))
                        if ordinal and held[ordinal - 1] is None]
            if ordinals:
                holds[id(node)] = ordinals
            found = bool(ordinals)
        if found:
            relevant.add(id(node))
        return found

    order: list[int] = []
    seen: set[int] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, tuple):
            for ordinal in holds[id(node)]:
                if ordinal not in seen:
                    seen.add(ordinal)
                    order.append(ordinal)
            return
        children = [(at, child) for at, child in enumerate(node[1]) if id(child) in relevant]
        if len(children) > 1:
            children.sort(key=lambda pair: (_place(pair[1][0] if isinstance(pair[1], tuple) else pair[1]), pair[0]))
        for _at, child in children:
            walk(child)

    if gather(leaves):
        walk(leaves)
    order.extend(ordinal for ordinal in range(1, elements.Extent() + 1)
                 if ordinal not in seen and held[ordinal - 1] is None)
    return order


def _transform(location: Any) -> tuple[int, ...]:
    """A placement rounded as positions and directions are: only to tell places apart."""
    transform = location.Transformation()
    return tuple(int(round(transform.Value(row, column) / (_POSITION_QUANTUM if column == 4 else _DIRECTION_QUANTUM)))
                 for row in (1, 2, 3) for column in (1, 2, 3, 4))
