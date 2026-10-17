"""Views of a tree for consumers that speak the view layout (assembly.json + components/).

The browser cannot read objects by hash directly: the viewer/snapshot client
resolves ``assembly.json`` and ``components/<cid>.<suffix>`` RELATIVE to a package
URL. Nothing gets a directory in the store — the store has no result
directories. A consumer of that layout gets a **view**:

- :func:`export_view` writes the flattened tree (assembly.json) plus every component it
  references -- its BREP and its part's selector table -- into a TEMPORARY directory
  outside the store (copies; the objects are small and the view is short-lived).
  Callers own its lifetime.
- :func:`virtual_path` resolves a view-relative path (``<tree>/assembly.json``,
  ``<tree>/components/<cid>.<suffix>``) to bytes on demand, so an HTTP route can
  present a tree as if it were a view directory without writing anything.

Each component of a view names its part (``part``: ``cadgen.store.parts``), the key
a page reads its display mesh and selector table by. A view a snapshot draws
(:func:`view_dir_for`) goes on without a part no mesh could be made of, as the CAD
Viewer does: that component names why instead (``failure``), and the page leaves it out.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from cadgen.store.objects import is_object_hash, object_path, read_verified_object
from cadgen.store.trees import capture_tree

DESCRIPTOR_NAME = "assembly.json"
COMPONENT_DIRNAME = "components"
# A component's selector table in a view: `components/<cid>.selectors.json`.
SELECTOR_TABLE_SUFFIX = ".selectors.json"


# The producers this process found no worker implements, each with the one that replaced it
# (``materialize_parts``, the CAD Viewer's part requests). A view of a document whose hint names
# one starts under its replacement, and re-attests the document, instead of paying one refused
# job per part again on every open (a kernel upgrade).
_REPLACED: dict[str, dict] = {}
_REPLACED_LOCK = threading.Lock()


def note_replaced_producer(previous: dict, current: dict) -> None:
    """``previous`` cannot be implemented here; ``current`` replaced it."""
    from cadgen.store import parts

    with _REPLACED_LOCK:
        _REPLACED[parts.producer_key(parts.producer_fields(previous))] = parts.producer_fields(current)


def _replacement_for(producer: dict) -> dict | None:
    from cadgen.store import parts

    found, seen = None, set()
    with _REPLACED_LOCK:
        key = parts.producer_key(producer)
        while key in _REPLACED and key not in seen:
            seen.add(key)
            found = _REPLACED[key]
            key = parts.producer_key(found)
    return found


def _attest(document_hash: str, tree_hash: str, producer: dict) -> None:
    """Record ``producer`` as the document's hint while the document still selects
    ``tree_hash``. Best effort: no read needs it, and a store this process cannot write
    keeps the hint it has (README law 2: a read never writes the store)."""
    from cadgen.store.paths import StoreUnwritableError
    from cadgen.store.records import document_entry_for_hash, note_document_tree

    with contextlib.suppress(OSError, StoreUnwritableError):
        current = document_entry_for_hash(document_hash)
        if current is not None and current.get("tree") == tree_hash:
            note_document_tree(document_hash, tree_hash, producer=producer)


def _select_producer(tree_hash: str, producer: dict | None, document_hash: str | None) -> dict:
    from cadgen.store import parts
    from cadgen.store.records import document_entry_for_hash

    selected = producer
    if document_hash:
        entry = document_entry_for_hash(document_hash)
        if entry is None or entry.get("tree") != tree_hash:
            raise FileNotFoundError("the selected document no longer has this geometry tree")
        if selected is None:
            try:
                selected = parts.producer_fields(entry.get("producer"))
            except (ValueError, TypeError):
                selected = None
            replacement = _replacement_for(selected) if selected is not None else None
            if replacement is not None:
                selected = replacement
                _attest(document_hash, tree_hash, selected)
    if selected is None:
        from cadgen.daemon.artifacts import resolve_artifact

        selected = resolve_artifact({"kind": "producer"})
        if document_hash:
            _attest(document_hash, tree_hash, selected)
    return parts.producer_fields(selected)


def descriptor_for_view(
    tree_hash: str, *, producer: dict | None = None, document_hash: str | None = None,
) -> dict[str, Any] | None:
    """An owned runtime view of complete geometry: each component names its part.

    A saved document's one index snapshot supplies its attested producer hint.
    A bare tree without a hint initializes a producer through the build pool;
    this adapter and its HTTP callers never import the kernel.
    """
    from cadgen.store import parts

    try:
        # Reject damaged geometry before starting even a producer-identity job.
        geometry, _ = capture_tree(tree_hash, retain_payloads=False)
        selected = _select_producer(tree_hash, producer, document_hash)
        descriptor = parts.view_from_geometry(tree_hash, geometry, producer=selected)
    except (OSError, ValueError):
        return None
    for cid, entry in descriptor["components"].items():
        entry["brep"] = f"{COMPONENT_DIRNAME}/{cid}.brep"
    if document_hash:
        descriptor["documentHash"] = document_hash
    return descriptor


def stored_parts(descriptor: dict, cids: list[str] | None = None) -> dict:
    """The part records the store holds for ``cids`` (every component when None),
    ``{cid: record}``; a component whose part is missing is absent. A read: nothing is
    derived."""
    from cadgen.store import parts

    selected = list(descriptor["components"]) if cids is None else cids
    if any(cid not in descriptor["components"] for cid in selected):
        raise ValueError("view request names an unpinned component")
    result = {}
    for cid in selected:
        record = parts.probe(descriptor["components"][cid]["part"])
        if record is not None:
            result[cid] = record
    return result


def materialize_parts(descriptor: dict, cids: list[str] | None = None, *,
                      drawable: bool = False) -> tuple[dict, dict]:
    """``(descriptor, {cid: record})``: the part records of ``cids`` (every component when
    None), each stored. The build that made the tree derived them; a part the store lacks
    (a cleared, evicted or older store) is derived by ONE build-pool job for all of them
    (``kind: display``), never in this process. A view whose producer this runtime
    cannot implement is replaced by one under this runtime's: the descriptor returned
    is the one the records belong to.

    A part that job could not derive fails the request, named by the occurrences that place
    it (``#o:3f2a9c1d7e5b ball could not be meshed (...)``) -- unless the view is ``drawable``: then it
    is left out, as the CAD Viewer leaves it out, its component carrying why (``failure``,
    the reason in those parentheses) and the records holding the rest. A drawable view
    none of whose parts is left fails as any other: there is nothing to draw."""
    from cadgen.daemon.artifacts import ArtifactJobError, resolve_artifact
    from cadgen.store import parts

    tree = descriptor["tree"]
    producer = parts.producer_fields(descriptor["producer"])
    wanted = list(descriptor["components"]) if cids is None else list(dict.fromkeys(cids))
    records = stored_parts(descriptor, wanted)
    missing = [cid for cid in wanted if cid not in records]
    if missing:
        try:
            resolve_artifact({"kind": "display", "tree": tree, "cids": missing, "producer": producer})
        # A pooled job's refusal arrives as its text; one run where it was submitted, as itself
        # (``MeshProductionError`` and ``ProducerUnavailable`` are ValueErrors).
        except (ArtifactJobError, ValueError) as error:
            if not parts.producer_unavailable(error):
                return _without_failed_parts(descriptor, wanted, missing, error, drawable=drawable)
            current = resolve_artifact({"kind": "producer"})
            if parts.producer_key(current) == parts.producer_key(producer):
                raise
            note_replaced_producer(producer, current)
            # Static exports have no displayed revision to retain. Prepare a
            # whole new owned view; never mix an old mesh with new selectors.
            replacement = descriptor_for_view(tree, producer=current, document_hash=descriptor.get("documentHash"))
            if replacement is None:
                raise FileNotFoundError("geometry disappeared during producer replacement") from error
            if descriptor.get("documentHash"):
                _attest(descriptor["documentHash"], tree, current)
            return materialize_parts(replacement, cids, drawable=drawable)
        records = stored_parts(descriptor, wanted)
    if any(cid not in records for cid in wanted):
        raise FileNotFoundError("display data disappeared before view publication")
    return descriptor, records


def _without_failed_parts(descriptor: dict, wanted: list[str], missing: list[str], error: Exception, *,
                          drawable: bool) -> tuple[dict, dict]:
    """``materialize_parts`` once its display job failed with ``error``. A ``drawable`` view
    with a part left is returned without the parts the job left missing, each of their
    components carrying why; otherwise those parts' failure is raised as a reader says it
    (:func:`failed_parts_error`). ``error`` itself is raised for any other failure, or when
    every part is stored after all."""
    from cadgen.store.parts import failed_parts

    failed = failed_parts({cid: descriptor["components"][cid]["part"] for cid in missing}, error)
    if not failed:
        raise error
    if not drawable or len(failed) == len(wanted):
        from cadgen.store.meshes import placements

        raise failed_parts_error(failed, placements(descriptor.get("occurrences"))) from error
    for cid, reason in failed.items():
        descriptor["components"][cid]["failure"] = reason
    records = stored_parts(descriptor, wanted)
    if any(cid not in records and cid not in failed for cid in wanted):
        raise FileNotFoundError("display data disappeared before view publication")
    return descriptor, records


def failed_parts_error(failed: dict[str, str], placed: dict[str, list[tuple[str, str]]]) -> Exception:
    """The ``MeshProductionError`` of parts no mesh could be made of, where nothing goes on
    without them: each of ``failed`` (``{cid: reason}``) named by the occurrences that place
    it (``placed``, ``{cid: [(ref, name)]}``), ``#o:3f2a9c1d7e5b ball could not be meshed (...)``, the
    parts joined by "; " in the order ``placed`` places them."""
    from cadgen._internal.tessellate import MeshProductionError
    from cadgen.store.meshes import failed_part

    ordered = [*(cid for cid in placed if cid in failed), *(cid for cid in failed if cid not in placed)]
    return MeshProductionError("; ".join(failed_part(placed.get(cid) or [], failed[cid], component=cid)
                                         for cid in ordered))


def component_object_for_tree(tree_hash: str, ref: str) -> tuple[str, str] | None:
    """Resolve a native component from its verified pinned geometry closure.

    Neither a CID nor a bare object hash can expose bytes unrelated to this
    geometry tree.
    """
    name = str(ref or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name.endswith(".brep"):
        return None
    stem = name[:-5]
    try:
        descriptor, _ = capture_tree(tree_hash, retain_payloads=False)
    except (OSError, ValueError, TypeError):
        return None
    components = descriptor["components"]
    entry = components.get(stem)
    if entry is not None:
        digest = entry["brep"]
    elif is_object_hash(stem) and any(item["brep"] == stem for item in components.values()):
        digest = stem
    else:
        return None
    return digest, "brep"


def views_root() -> Path:
    """Where this process's views live: under the system temp dir, per pid, so
    a served view path is always confined to one known root. A killed
    process's are swept by the next worker that starts
    (``cadgen._internal.temp_leftovers``)."""
    from cadgen._internal.temp_leftovers import VIEWS_DIRNAME

    root = Path(tempfile.gettempdir()) / VIEWS_DIRNAME / str(os.getpid())
    root.mkdir(parents=True, exist_ok=True)
    return root


_VIEW_DIRS: dict[tuple[str, str | None], Path] = {}
_VIEW_LOCK = threading.Lock()
_VIEW_CLEANUP_REGISTERED = False


def _cleanup_views() -> None:
    shutil.rmtree(views_root(), ignore_errors=True)


def _left_out(descriptor: dict) -> set[str]:
    """The components a drawable view left out, no mesh having been made of them
    (``failure``, :func:`materialize_parts`)."""
    components = descriptor.get("components")
    return {cid for cid, entry in (components.items() if isinstance(components, dict) else ())
            if isinstance(entry, dict) and entry.get("failure")}


def _written(view: Path | None) -> dict | None:
    """The descriptor a view directory was written with; None when it has none."""
    try:
        written = json.loads((view / DESCRIPTOR_NAME).read_text(encoding="utf-8")) if view is not None else None
    except (OSError, ValueError):
        return None
    return written if isinstance(written, dict) else None


def view_dir_for(tree_hash: str, *, producer: dict | None = None, document_hash: str | None = None) -> Path:
    """A view (assembly.json + components/) of ``tree_hash``, built once per process and
    removed at exit. The adapter for consumers that need a DIRECTORY (the
    selector-index composer, the snapshot page). It is drawable: a part no mesh could be
    made of is left out of it, its component saying why (``materialize_parts``)."""
    global _VIEW_CLEANUP_REGISTERED
    descriptor = descriptor_for_view(tree_hash, producer=producer, document_hash=document_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    # Byte-distinct saved documents may share geometry and a display producer.
    # Their owned manifests retain the selected document binding separately.
    view_key = (descriptor["viewId"], document_hash)
    with _VIEW_LOCK:
        existing = _VIEW_DIRS.get(view_key)
    # The directory holds copies of the selector tables; its readers take the display
    # meshes from the store, so a part evicted since it was written derives it again. A
    # part it left out is not asked for again while the store still lacks it.
    written = _written(existing)
    if written is not None:
        stored, left_out = stored_parts(descriptor), _left_out(written)
        if all((cid in stored) != (cid in left_out) for cid in descriptor["components"]):
            return existing
    # Never hold a process-wide view lock while waiting for pooled native work.
    descriptor, records = materialize_parts(descriptor, drawable=True)
    view_key = (descriptor["viewId"], document_hash)
    with _VIEW_LOCK:
        existing = _VIEW_DIRS.get(view_key)
        written = _written(existing)
        if written is not None and _left_out(written) == _left_out(descriptor):
            return existing
        if not _VIEW_CLEANUP_REGISTERED:
            atexit.register(_cleanup_views)
            _VIEW_CLEANUP_REGISTERED = True
        target = views_root() / descriptor["viewId"] / (document_hash or "geometry")
        _write_view(descriptor, records, target)
        _VIEW_DIRS[view_key] = target
        return target


def export_view(
    tree_hash: str, dest: Path | None = None, *, producer: dict | None = None, cids: list[str] | None = None,
) -> Path:
    """Write a view directory (assembly.json + components/) for ``tree_hash``; return its path.
    With ``dest`` None a fresh temporary directory is created (caller removes). ``cids`` limits
    ``components/`` to those components, and the display work to theirs; assembly.json still
    describes the whole tree."""
    descriptor = descriptor_for_view(tree_hash, producer=producer)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    if cids is not None and any(cid not in descriptor["components"] for cid in cids):
        raise ValueError("view request names an unpinned component")
    if dest is None:
        from cadgen._internal.temp_leftovers import VIEW_PREFIX, owned_prefix

        # Named after this process, so a sweep can tell whether its owner is gone.
        dest = Path(tempfile.mkdtemp(prefix=owned_prefix(VIEW_PREFIX)))
    descriptor, records = materialize_parts(descriptor, cids)
    return _write_view(descriptor, records, Path(dest))


def _write_view(descriptor: dict, records: dict, root: Path) -> Path:
    """The view's files: each of ``records``' components' BREP and selector table (it
    names ``selectors``), then assembly.json. A component the view left out has none."""
    comp_dir = root / COMPONENT_DIRNAME
    comp_dir.mkdir(parents=True, exist_ok=True)
    components = descriptor.get("components") or {}
    for cid in _left_out(descriptor):
        # Nothing of it stays from an earlier view written to this directory.
        for suffix in (".brep", SELECTOR_TABLE_SUFFIX):
            (comp_dir / f"{cid}{suffix}").unlink(missing_ok=True)
    for cid, record in records.items():
        entry = components[cid]
        entry["selectors"] = f"{COMPONENT_DIRNAME}/{cid}{SELECTOR_TABLE_SUFFIX}"
        for suffix, digest in ((".brep", entry["brepObject"]), (SELECTOR_TABLE_SUFFIX, record["selectors"]["object"])):
            # The file is an owned view, not the CAS object. Always replace
            # it from verified bytes when publishing a new descriptor.
            (comp_dir / f"{cid}{suffix}").write_bytes(read_verified_object(digest))
    (root / DESCRIPTOR_NAME).write_text(json.dumps(descriptor), encoding="utf-8")
    return root


def preview_annotations(object_hash: str) -> bytes | None:
    """The annotations object a build feed names for its preview revision
    (``_internal/preview_revision.py``), as JSON bytes; None when the store holds no such
    object. A read of ``objects/`` alone."""
    from cadgen._internal.preview_revision import read_annotations

    payload = read_annotations(object_hash)
    return None if payload is None else json.dumps(payload).encode("utf-8")


def virtual_path(
    rel: str, *, producer: dict | None = None, document_hash: str | None = None,
) -> tuple[bytes | Path | None, str]:
    """Resolve ``<tree>`` (or ``<tree>/assembly.json``) and ``<tree>/components/<cid>.brep``,
    a component's BREP.

    Returns ``(payload, content_type)``: bytes for the assembly.json, a Path for a BREP
    (streamable), or ``(None, "")`` when nothing matches."""
    segments = [p for p in str(rel or "").replace("\\", "/").split("/") if p]
    if not segments or not is_object_hash(segments[0]):
        return None, ""
    tree_hash = segments[0]
    if segments[1:] in ([], [DESCRIPTOR_NAME]):
        # The tree itself IS the "directory" the client names; its assembly.json
        # answers for both spellings.
        descriptor = descriptor_for_view(tree_hash, producer=producer, document_hash=document_hash)
        if descriptor is None:
            return None, ""
        return json.dumps(descriptor).encode("utf-8"), "application/json"
    if len(segments) == 3 and segments[1] == COMPONENT_DIRNAME:
        resolved = component_object_for_tree(tree_hash, segments[2])
        if resolved is None:
            return None, ""
        path = object_path(resolved[0])
        if not path.is_file():
            return None, ""
        return path, "application/octet-stream"
    return None, ""
