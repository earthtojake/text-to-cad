"""Saved STEP readers and exact, revision-scoped scene selection.

``read_step`` returns native build123d geometry. ``read_scene`` retains the
occurrence hierarchy and canonical selector IDs; geometry is acquired only
when requested. Neither reader discovers or executes source scripts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Literal

if TYPE_CHECKING:
    from build123d import Shape
    from cadgen._internal.step_scene_types import LoadedStepScene

__all__ = ["read_step", "read_scene", "StepScene", "Occurrence", "Selection"]

EntityKind = Literal["shape", "face", "edge", "vertex"]

def __getattr__(name: str):
    if name in {"load_step_scene", "located_shape", "occurrence_selector_id", "scene_occurrence_shape"}:
        raise ImportError(f"{name} has been removed; use read_scene(path), scene.resolve(ref) and selection.shape()")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _record_input(step_path: Path | str, *, reader: str) -> Path:
    """Resolve a STEP a model asked for, and declare it a build input.

    Both public readers go through here, because "which cadgen function records
    what it reads" must not be a thing anyone has to remember: they all do. The
    engine's own internal loads go straight to
    :mod:`cadgen._internal.step_scene` and are unaffected — a build must not
    record its own output as its input.
    """
    resolved = Path(step_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{reader}: no STEP file at {resolved}. Check the path — it resolves "
            "relative to the process's working directory, so anchor a model's own "
            "inputs on its file: Path(__file__).parent / '../STEP/part.step'."
        )
    from cadgen._internal.self_input import refuse_own_output
    from cadgen._internal.source_hash import note_discovered_input

    refuse_own_output(resolved, reader=reader)
    note_discovered_input(resolved)
    return resolved


def read_scene(step_path: Path | str) -> StepScene:
    """Open one saved STEP revision, using its canonical native cache.

    A cache miss compiles the document, never its source. No tessellation or
    display-surface extraction is required. STEP coordinates are in mm.
    Keep this scene open for repeated queries; calling again reads/hashes the
    document again so a replacement cannot masquerade as the old revision.
    """
    from cadgen._internal.doors import document_target

    path = _record_input(step_path, reader="read_scene")
    document_target(path, suffixes=(".step", ".stp"))
    from cadgen._internal.step_scene_package import load_step_scene_cached

    return StepScene(load_step_scene_cached(path, lazy=True))


@dataclass(frozen=True)
class Selection:
    """An exact reference within one scene; ``shape()`` returns an owned copy."""

    _scene: StepScene = field(repr=False)
    occurrence_ref: str
    kind: Literal["occurrence", "shape", "face", "edge", "vertex"]
    _ordinal: int | None = None

    @property
    def ref(self) -> str:
        if self.kind == "occurrence":
            return self.occurrence_ref
        prefix = {"shape": "s", "face": "f", "edge": "e", "vertex": "v"}[self.kind]
        return f"{self.occurrence_ref}.{prefix}{self._ordinal}"

    def shape(self) -> Shape:
        """Native geometry in world coordinates, privately owned by the caller.

        An occurrence group is an unfused compound of its descendants.
        Modifying the result cannot change this scene or another result.
        """
        from cadgen.geometry import _cast, _copy

        result = _cast(_copy(self._scene._placed(self)))
        occurrence = self._scene._occurrences[self.occurrence_ref]
        result.label = occurrence.label or ""
        color = occurrence._node.color
        if color is not None:
            result.color = color
        return result

    def entities(self, kind: EntityKind) -> Iterator[Selection]:
        """Enumerate canonical entities inside this selection.

        IDs stay occurrence-scoped, including coincident repeated parts.
        Asking a face for edges retains the leaf's edge ordinals.
        """
        if kind not in {"shape", "face", "edge", "vertex"}:
            raise ValueError(f"unknown entity kind: {kind!r}")
        yield from self._scene._entities(self, kind)


@dataclass(frozen=True)
class Occurrence(Selection):
    _node: Any = field(default=None, repr=False, compare=False)

    @property
    def label(self) -> str | None:
        return self._node.name or self._node.source_name

    @property
    def prototype_id(self) -> str | None:
        """Shared geometry identity within this scene; None for a group."""
        return self._scene._prototype_ids.get(self._node.prototype_key)

    @property
    def children(self) -> tuple[Occurrence, ...]:
        return tuple(self._scene._occurrences[_node_ref(node)] for node in self._node.children)


def _node_ref(node) -> str:
    return "#o" + ".".join(str(n) for n in node.path)


class StepScene:
    """A saved document revision with immutable occurrence and selector views.

    References are canonical for these document bytes, not persistent feature
    names across edits. The scene does not apply kinematics/animation poses.
    """

    def __init__(self, scene: LoadedStepScene):
        from cadgen.label_refs import build_label_aliases

        self._loaded = scene
        self._occurrences: dict[str, Occurrence] = {}
        self._maps: dict[tuple[Any, str], Any] = {}
        self._prototype_ids = {key: f"p{i}" for i, key in enumerate(scene.prototype_shapes, 1)}
        stack = list(reversed(scene.roots))
        while stack:
            node = stack.pop()
            ref = _node_ref(node)
            self._occurrences[ref] = Occurrence(self, ref, "occurrence", _node=node)
            stack.extend(reversed(node.children))
        self._leaves = tuple(o for o in self._occurrences.values() if o._node.prototype_key is not None)
        self._aliases = build_label_aliases(
            {"id": o.ref[1:], "name": o.label} for o in self._occurrences.values()
        )

    @property
    def document_hash(self) -> str:
        return self._loaded.step_hash

    @property
    def roots(self) -> tuple[Occurrence, ...]:
        return tuple(self._occurrences[_node_ref(node)] for node in self._loaded.roots)

    def leaves(self) -> Iterator[Occurrence]:
        """Placed geometry occurrences; a leaf may contain several solids."""
        return iter(self._leaves)

    def resolve(self, ref: str) -> Selection:
        """Resolve one numeric ref, exact label alias, or file-prefixed ref.

        Ambiguous labels raise with numbered candidates. A bare entity ID
        (e.g. #f1) requires exactly one leaf. No fuzzy matching or first match.
        """
        from cadgen.cad_ref_syntax import parse_selector, path_has_suffix
        from cadgen.label_refs import resolve_label_selectors

        text = ref.strip()
        if "#" in text:
            prefix, text = text.split("#", 1)
            if prefix and not path_has_suffix(str(self._loaded.step_path), prefix):
                raise ValueError(f"reference names {prefix!r}, but this scene is {str(self._loaded.step_path)!r}")
        parsed = parse_selector(text)
        if parsed is None or parsed.selector_type == "opaque":
            raise ValueError(f"invalid reference: {ref!r}; pass one occurrence or entity ref")
        if parsed.label:
            text = resolve_label_selectors([text], self._aliases)[0]
            parsed = parse_selector(text)
        oid = "#" + parsed.occurrence_id if parsed.occurrence_id else ""
        if not oid:
            if len(self._leaves) != 1:
                raise ValueError(f"{ref!r} needs an occurrence prefix in an assembly")
            oid = self._leaves[0].ref
        occurrence = self._occurrences.get(oid)
        if occurrence is None:
            raise ValueError(f"unknown occurrence: {oid}")
        if parsed.selector_type == "occurrence":
            return occurrence
        kind = parsed.selector_type
        ordinal = parsed.ordinal
        if occurrence._node.prototype_key is None:
            raise ValueError(f"{oid} is a group; enumerate its entities or specify a leaf occurrence")
        entities = self._table(occurrence, kind)
        size = len(entities) if kind == "shape" else entities.Extent()
        if ordinal is None or not 1 <= ordinal <= size:
            raise ValueError(f"unknown {kind} reference: {ref!r} (available: 1..{size})")
        return Selection(self, oid, kind, ordinal)

    def _table(self, occurrence, kind):
        from cadgen._internal.entity_ordinals import entity_map, shape_entities

        key = (occurrence._node.prototype_key, kind)
        if key not in self._maps:
            prototype = self._loaded.prototype_shapes[key[0]]
            self._maps[key] = shape_entities(prototype) if kind == "shape" else entity_map(prototype, kind)
        return self._maps[key]

    def _local(self, selection):
        occurrence = self._occurrences[selection.occurrence_ref]
        if selection.kind == "occurrence":
            return self._loaded.prototype_shapes[occurrence._node.prototype_key]
        table = self._table(occurrence, selection.kind)
        return table[selection._ordinal - 1] if selection.kind == "shape" else table.FindKey(selection._ordinal)

    def _placed(self, selection):
        occurrence = self._occurrences[selection.occurrence_ref]
        if occurrence._node.prototype_key is None:
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Compound

            compound, builder = TopoDS_Compound(), BRep_Builder()
            builder.MakeCompound(compound)
            for child in occurrence.children:
                builder.Add(compound, self._placed(child))
            return compound
        local = self._local(selection)
        location = occurrence._node.location
        return local.Moved(location) if location is not None else local

    def _entities(self, selection, kind):
        from cadgen._internal.entity_ordinals import entity_map

        occurrence = self._occurrences[selection.occurrence_ref]
        if occurrence._node.prototype_key is None:
            for child in occurrence.children:
                yield from self._entities(child, kind)
            return
        table = self._table(occurrence, kind)
        if selection.kind == "occurrence":
            size = len(table) if kind == "shape" else table.Extent()
            ordinals = range(1, size + 1)
        elif selection.kind == kind:
            ordinals = [selection._ordinal]
        else:
            local = self._local(selection)
            if kind == "shape":
                # Usually a face/edge cannot contain a solid/shell. A leaf
                # containing only that face/edge also gives it a fallback s1.
                ordinals = [i for i, entity in enumerate(table, 1) if entity.IsSame(local)]
            else:
                subset = entity_map(local, kind)
                ordinals = [table.FindIndex(subset.FindKey(i)) for i in range(1, subset.Extent() + 1)]
        for ordinal in ordinals:
            yield Selection(self, occurrence.ref, kind, ordinal)


def read_step(step_path: Path | str, *, label: str | None = None) -> Any:
    """Read a STEP file as build123d geometry, AND record it as a build input.

    Usable in a ``@step`` body (composing a vendor part into an assembly) and in
    a ``@dxf`` body (deriving a cut profile from one) alike. The returned shape
    is the file's geometry, as ``build123d.import_step`` would read it — the
    root itself, not a wrapper — with per-occurrence and prototype STEP colors
    applied. When the store holds a tree for the file's bytes the read is warm
    (tens of milliseconds instead of a full text-STEP parse), and it is the
    SAME geometry: a model's tree is built from the STEP it wrote, re-read, so a
    warm read, a cold parse and ``import_step`` agree by construction
    (``cadgen.store.build.build_tree_through_step``).

    **The recording is the point.** Freshness used to follow a model's Python
    import reach only, which is observable: modules announce themselves. A file
    read as data announces nothing, so a model built from a vendor STEP went on
    reporting itself current after that STEP was replaced, and the only way to
    get the truth back was ``--force``. Reading through this function declares
    the file: its path and content hash join the model's closure, and the next
    run's gate re-hashes it (design/dxf-build123d.md).

    A missing file raises here rather than deep inside the importer, because
    "the vendor STEP is not where the model thinks it is" is the whole message.
    """
    from cadgen._internal.step_scene import import_step

    return import_step(_record_input(step_path, reader="read_step"), label=label)
