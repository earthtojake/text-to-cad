"""Build a model's TREE from its returned geometry.

Walks the compound a model returned. Every leaf becomes a content-addressed
**component** (exact ``.brep`` + render ``.surf``, each an object); every
subtree that is a child model's materialized geometry, found intact, becomes a
**link** to that child's tree. The decision is mechanical (§Tree in STORE.md):

- a compound carrying a materialize tag whose geometry is still the tagged
  TShape (``IsPartner``: same shape, only the location differs) → link, placed
  at its world location; relabelled or recolored is still intact;
- anything else — geometry the model made, an extracted sub-shape, a modified
  child (``housing() - holes``: a new TShape), a mirrored child (a new TShape)
  → the model's own components. No error path.

Component extraction is the existing surface extractor; missing components are
extracted in a process pool from their BREP payloads, exactly as before, into a
scratch directory that is then ingested into ``objects/``. Reuse is by cid
through ``index/component/<cid>`` (cid → the pair of object hashes): a cid seen
before costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cadgen.coordination import PHASE_COMPONENTS, PHASE_FINALIZE, PHASE_PACKAGE
from cadgen.coordination import resolve as resolve_progress
from cadgen.store.index import read_entry, write_entry
from cadgen.store.materialize import PARTNER_TAG, TREE_TAG
from cadgen.store.objects import has_object, put_object_from_file
from cadgen.store.trees import put_tree


def _component_index(cid: str) -> tuple[str, str] | None:
    entry = read_entry("component", cid)
    if not entry:
        return None
    surf, brep = str(entry.get("surf") or ""), str(entry.get("brep") or "")
    if surf and brep and has_object(surf) and has_object(brep):
        return surf, brep
    return None


def _tagged_intact(node: Any) -> str | None:
    """The tree hash when ``node`` is a materialized child still carrying the
    geometry it was materialized with (placement may differ), else None."""
    tag = getattr(node, TREE_TAG, None)
    if not tag:
        return None
    partner = getattr(getattr(node, PARTNER_TAG, None), "shape", None)
    wrapped = getattr(node, "wrapped", None)
    if partner is None or wrapped is None:
        return str(tag)
    try:
        return str(tag) if wrapped.IsPartner(partner) else None
    except Exception:  # noqa: BLE001 - an odd wrapper is not intact
        return None


def build_tree_from_compound(
    compound: Any,
    *,
    root_name: str,
    entry_kind: str,
    single_component: bool = False,
    force: bool = False,
    progress: Any | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return ``(tree_hash, tree, stats)``. ``extra`` are content-pure fields
    recorded on the tree (capabilities, edgeRendering) — never paths or times."""
    from build123d import Location

    from cadgen._internal.component_package import (
        PAYLOAD_UNREADABLE,
        _build_component_surf_worker,
        _component_build_worker_count,
        _component_id,
        _content_hash_and_bytes,
        _bbox_from_shape,
        _occurrence_color,
        _occurrence_material,
        _shape_brep_bytes,
        _transform_from_location,
        _write_component_artifacts_atomic,
    )

    progress = resolve_progress(progress)
    occurrences: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    components: dict[str, dict[str, Any]] = {}
    shapes: dict[str, Any] = {}
    hash_memo: dict[Any, str] = {}
    brep_bytes_by_cid: dict[str, bytes] = {}

    def _add_leaf(node: Any, world_loc: Any, occ_id: str, name: str | None = None) -> dict[str, Any]:
        try:
            memo_key = node.wrapped.TShape()
            content_hash = hash_memo.get(memo_key)
            if content_hash is None:
                content_hash, brep = _content_hash_and_bytes(node)
                hash_memo[memo_key] = content_hash
                brep_bytes_by_cid.setdefault(_component_id(content_hash), brep)
        except TypeError:
            content_hash, brep = _content_hash_and_bytes(node)
            brep_bytes_by_cid.setdefault(_component_id(content_hash), brep)
        cid = _component_id(content_hash)
        shapes.setdefault(cid, node)
        entry_meta: dict[str, Any] = {"contentHash": content_hash}
        node_color = getattr(node, "color", None)
        if node_color is not None:
            try:
                entry_meta["color"] = [float(c) for c in node_color.to_tuple()]
            except Exception:  # noqa: BLE001
                pass
        components.setdefault(cid, entry_meta)
        if name is None:
            name = str(getattr(node, "label", "") or f"part_{occ_id}")
        occurrence: dict[str, Any] = {
            "id": occ_id,
            "name": name,
            "component": cid,
            "transform": _transform_from_location(world_loc),
        }
        color = _occurrence_color(node)
        if color is not None:
            occurrence["color"] = color
        material = _occurrence_material(node)
        if material is not None:
            occurrence["material"] = material
        occurrences.append(occurrence)
        progress.advance(detail=name)
        return {"id": occ_id, "name": name, "nodeType": "part", "leafPartIds": [occ_id], "children": []}

    def _add_link(node: Any, world_loc: Any, occ_id: str, tree_hash: str) -> dict[str, Any]:
        name = str(getattr(node, "label", "") or occ_id)
        link: dict[str, Any] = {
            "id": occ_id,
            "name": name,
            "tree": tree_hash,
            "transform": _transform_from_location(world_loc),
        }
        color = _occurrence_color(node)
        if color is not None:
            link["color"] = color
        links.append(link)
        progress.advance(detail=name)
        return {"id": occ_id, "name": name, "nodeType": "link", "tree": tree_hash, "children": []}

    def _consume_spliced(node: dict[str, Any], parent_world_loc: Any, path: str) -> dict[str, Any]:
        if node.get("leaf"):
            return _add_leaf(node["shape"], parent_world_loc * node["world_loc"], path, name=node["name"])
        child_nodes = [
            _consume_spliced(child, parent_world_loc, f"{path}.{index}")
            for index, child in enumerate(node["children"], start=1)
        ]
        return {
            "id": path,
            "name": node["name"],
            "nodeType": "subassembly",
            "leafPartIds": [leaf for cn in child_nodes for leaf in cn.get("leafPartIds", [cn["id"]])],
            "children": child_nodes,
        }

    def _walk(node: Any, parent_world_loc: Any, path: str) -> dict[str, Any]:
        node_loc = getattr(node, "location", None)
        world_loc = (parent_world_loc * node_loc) if node_loc is not None else parent_world_loc
        if path != "o1":
            tagged = _tagged_intact(node)
            if tagged is not None:
                return _add_link(node, world_loc, path, tagged)
        nested_tree = getattr(node, "_occurrence_tree", None)
        if nested_tree is not None:
            spliced = _consume_spliced(dict(nested_tree, leaf=False), world_loc, path)
            spliced["name"] = str(getattr(node, "label", "") or nested_tree.get("name") or path)
            return spliced
        child_shapes = list(getattr(node, "children", []) or [])
        if not child_shapes:
            return _add_leaf(node, world_loc, path)
        child_nodes = [_walk(child, world_loc, f"{path}.{index}") for index, child in enumerate(child_shapes, start=1)]
        return {
            "id": path,
            "name": str(getattr(node, "label", "") or path),
            "nodeType": "subassembly",
            "leafPartIds": [leaf for cn in child_nodes for leaf in cn.get("leafPartIds", [cn["id"]])],
            "children": child_nodes,
        }

    progress.phase(PHASE_PACKAGE)
    if single_component:
        root = _add_leaf(compound, getattr(compound, "location", None) or Location(), "o1")
        root["nodeType"] = "part"
    else:
        occurrence_tree = getattr(compound, "_occurrence_tree", None)
        if occurrence_tree is not None:
            root = _consume_spliced(dict(occurrence_tree, leaf=False), Location(), "o1")
        else:
            root = _walk(compound, Location(), "o1")
        root["nodeType"] = "assembly"
    if not occurrences and not links:
        raise RuntimeError(f"model {root_name!r} has no geometry")

    # --- components: reuse by cid, extract the rest, ingest as objects -------------
    built: list[str] = []
    reused: list[str] = []
    missing: list[tuple[str, Any]] = []
    resolved: dict[str, tuple[str, str]] = {}
    for cid, shape in shapes.items():
        indexed = None if force else _component_index(cid)
        if indexed is not None:
            resolved[cid] = indexed
            reused.append(cid)
        else:
            missing.append((cid, shape))

    with tempfile.TemporaryDirectory(prefix="cadgen-components-") as scratch_str:
        scratch = Path(scratch_str)
        payloads = [
            (
                brep_bytes_by_cid.get(cid) or _shape_brep_bytes(shape),
                cid,
                str(scratch / f"{cid}.surf"),
                getattr(shape, "cad_face_ordinal_colors", None),
            )
            for cid, shape in missing
        ]
        workers = _component_build_worker_count(len(payloads))
        progress.phase(PHASE_COMPONENTS, total=len(payloads))
        if workers > 1 and payloads:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor, as_completed

            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                futures = {pool.submit(_build_component_surf_worker, args): args[1] for args in payloads}
                errors_by_cid: dict[str, str | None] = {}
                for future in as_completed(futures):
                    built_cid, error = future.result()
                    errors_by_cid[built_cid] = error
                    progress.advance(detail=built_cid)
            results = [(cid, errors_by_cid[cid]) for _p, cid, *_r in payloads]
        else:
            results = []
            for args in payloads:
                results.append(_build_component_surf_worker(args))
                progress.advance(detail=args[1])
        shapes_by_cid = dict(missing)
        for cid, error in results:
            if error is not None and error.startswith(PAYLOAD_UNREADABLE):
                _write_component_artifacts_atomic(shapes_by_cid[cid], scratch / f"{cid}.surf", cad_ref=cid)
            elif error is not None:
                raise RuntimeError(f"component {cid} build failed: {error}")
            surf_obj = put_object_from_file(scratch / f"{cid}.surf")
            brep_obj = put_object_from_file(scratch / f"{cid}.brep")
            write_entry("component", cid, {"surf": surf_obj, "brep": brep_obj})
            resolved[cid] = (surf_obj, brep_obj)
            built.append(cid)

    for cid, (surf_obj, brep_obj) in resolved.items():
        components[cid]["surf"] = surf_obj
        components[cid]["brep"] = brep_obj

    progress.phase(PHASE_FINALIZE)
    tree: dict[str, Any] = dict(extra or {})
    tree.update(
        {
            "label": root_name,
            "entryKind": entry_kind,
            "units": "mm",
            "components": components,
            "occurrences": occurrences,
            "links": links,
            "assembly": {"root": root},
        }
    )
    bbox = _bbox_from_shape(compound)
    if bbox is not None:
        tree["bbox"] = bbox
    tree["stats"] = {"occurrenceCount": len(occurrences), "linkCount": len(links)}
    tree_hash = put_tree(tree)
    stats = {
        "occurrences": len(occurrences),
        "links": len(links),
        "unique_components": len(components),
        "components_built": len(built),
        "components_reused": len(reused),
    }
    return tree_hash, tree, stats
