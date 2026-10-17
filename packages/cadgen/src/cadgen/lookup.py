"""The selector index: every row a ref can resolve to, keyed by the ref that names it.

An occurrence row is keyed by its token (``o:…``); a face, edge or vertex row by
``<occurrence token>/<element name>``, the one composition rule
(``cad_ref_syntax.element_ref``). The rows come from the tree and the parts'
selector tables (``assembly_lookup``); nothing here mints a name. A ref is resolved
against the index by the one resolver (``cadgen.refs``), over :func:`index_space`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cadgen import cad_ref_syntax as syntax


def _table_rows(manifest: dict[str, Any], table_name: str, columns_name: str) -> list[dict[str, Any]]:
    """Materialize one manifest table into dicts keyed by its declared column names."""
    columns = manifest.get("tables", {}).get(columns_name)
    rows = manifest.get(table_name)
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        materialized.append({str(columns[index]): row[index] for index in range(min(len(columns), len(row)))})
    return materialized


@dataclass(frozen=True)
class SelectorIndex:
    occurrences: list[dict[str, Any]]
    shapes: list[dict[str, Any]]
    faces: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    vertices: list[dict[str, Any]]
    occurrence_by_id: dict[str, dict[str, Any]]
    face_by_id: dict[str, dict[str, Any]]
    edge_by_id: dict[str, dict[str, Any]]
    vertex_by_id: dict[str, dict[str, Any]]
    # The instance tree's INTERIOR nodes -- subassemblies -- keyed by token, as the tree
    # records them (name, nodeType, child count). Rows above are leaves, because only a leaf
    # owns geometry; this is the rest of the tree, and it is what lets a command answer a group
    # ref with the node's own identity instead of an anonymous id. Filled in by
    # cadgen.assembly_lookup.merge_assembly_occurrences; empty for part entries, which
    # have no interior nodes to describe.
    group_nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Every tree node's leaf occurrences (a leaf's: itself), by token: a group ref's members.
    # A token holds no hierarchy, so the tree is the one source of it (``occurrence_groups``).
    members: dict[str, list[str]] = field(default_factory=dict)
    # Every name of the tree's nodes, groups and leaves alike, with the nodes it names in
    # tree order (``refs.descriptor_nodes``): what a ``#name`` resolves in.
    names: dict[str, list[str]] = field(default_factory=dict)
    # The components the element rows were composed from, as a tree lists them, by cid:
    # what a ref by geometry is matched against (``index_space``).
    components: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_selector_index(manifest: dict[str, Any]) -> SelectorIndex:
    """An index over one table's rows: an occurrence row keyed by its ``id``, each element
    row by ``id`` where the table carries one (a composed index's do; a component's own
    table carries element names alone, which :mod:`cadgen.assembly_lookup` composes with the
    occurrence that places it)."""
    occurrences = _table_rows(manifest, "occurrences", "occurrenceColumns")
    shapes = _table_rows(manifest, "shapes", "shapeColumns")
    faces = _table_rows(manifest, "faces", "faceColumns")
    edges = _table_rows(manifest, "edges", "edgeColumns")
    vertices = _table_rows(manifest, "vertices", "vertexColumns")

    def by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(row["id"]): row for row in rows if row.get("id")}

    return SelectorIndex(
        occurrences=occurrences,
        shapes=shapes,
        faces=faces,
        edges=edges,
        vertices=vertices,
        occurrence_by_id=by_id(occurrences),
        face_by_id=by_id(faces),
        edge_by_id=by_id(edges),
        vertex_by_id=by_id(vertices),
    )


def index_space(index: SelectorIndex, *, document: str | None = None):
    """The refs space (``cadgen.refs.Space``) of a selector index: its tree's nodes and
    their names, and each leaf's elements as its rows name them, matched by geometry
    against the component that leaf places when a ref by geometric token names none of
    them."""
    from cadgen.cad_ref_syntax import OCCURRENCE_SELECTOR_RE
    from cadgen.refs import Space

    members = {token: list(leaves) for token, leaves in index.members.items()}
    # A leaf occurrence's row, or any element row, names a leaf.
    for row in [*index.occurrences, *index.faces, *index.edges, *index.vertices]:
        token = str(row.get("occurrenceId") or row.get("id") or "").split("/", 1)[0]
        if OCCURRENCE_SELECTOR_RE.match(token):
            members.setdefault(token, [token])
    rows: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}

    def by_ordinal(token: str, kind: str) -> dict[int, dict[str, Any]]:
        if not rows:
            for row_kind, table in (("face", index.faces), ("edge", index.edges), ("vertex", index.vertices)):
                for row in table:
                    owner = str(row.get("occurrenceId") or "")
                    if owner and isinstance(row.get("ordinal"), int):
                        rows.setdefault((owner, row_kind), {})[row["ordinal"]] = row
        return rows.get((token, kind), {})

    def elements(token: str, kind: str) -> list[str | None]:
        found = by_ordinal(token, kind)
        return [str(found[ordinal].get("name") or "") or None if ordinal in found else None
                for ordinal in range(1, max(found, default=0) + 1)]

    def tokens(token: str, kind: str) -> list[str]:
        row = index.occurrence_by_id.get(token) or {}
        entry = index.components.get(str(row.get("component") or ""))
        if entry is None:
            return []
        from cadgen.store.parts import element_tokens

        return element_tokens(entry)[{"face": "faces", "edge": "edges", "vertex": "vertices"}[kind]]

    return Space(members, index.names, elements=elements, tokens=tokens, document=document)


def find(ref: str, index: SelectorIndex) -> tuple[str, dict[str, Any] | None]:
    """What ``ref`` names in ``index``, resolved by the one resolver (``cadgen.refs``): its
    kind (``occurrence``, ``face``, ``edge`` or ``vertex``) and its row, None for a group,
    which has none. ``ValueError`` says why it names nothing there."""
    from cadgen.refs import resolve

    found = resolve(ref, index_space(index))
    if found.kind == "occurrence":
        return found.kind, index.occurrence_by_id.get(found.occurrence)
    named = getattr(index, f"{found.kind}_by_id").get(syntax.element_ref(found.occurrence, found.element or ""))
    if named is not None and named.get("ordinal") == found.ordinal:
        return found.kind, named
    table = getattr(index, {"face": "faces", "edge": "edges", "vertex": "vertices"}[found.kind])
    row = next((row for row in table if row.get("occurrenceId") == found.occurrence
                and row.get("ordinal") == found.ordinal), None)
    if row is None:
        raise ValueError(f"{ref!r} names {found.kind} {found.ordinal} of #{found.occurrence}, which has no row here")
    return found.kind, row
