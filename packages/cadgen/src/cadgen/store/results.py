"""Results by key: ``index/result/<key>``, a model's stored result under the identity
of the model and everything it was built from (STORE.md §3, §4).

A model's **key** is a hash of the model (its script and function) and its inputs as
its record keeps them: its closure's hash, its constants by value, the keys of the
children its body called, the producer (this cadgen's and the kernel's versions) and
its arguments (none: a model is parameterless, and the key reserves their digest).
The model is in it because two models of one file share a closure and are two
results. A parent records each child by its key, so a parent depends on a child by
everything the child was built from, and the gate's clause 3 compares keys
(``store.gate``). ``write_record`` keys every record it writes from what the record
holds and stores the record under that key, and ``write_provenance`` keeps the
provenance it writes beside the record with that result, so the result at a key is
the record as last written under it with its provenance; the gate recomputes the key
only to ask whether a stored result already answers for the source as it is now
(``Verdict.candidate``).

The result entry is that snapshot of the record and provenance, with its tree beside
them. It is derived (``paths.DERIVED_KINDS``): evicted under the cap, least recently
written first, retired a week after it was written by another cadgen (its producer
names it), and dropped with the model's record by ``store forget``. While it stands it
protects the tree it names, as a record does (``gc``), so a source reverted to an
earlier state is a hit on that result -- the record is restored from the snapshot --
not a rebuild.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from cadgen.store.index import iter_entries, read_entry, resolve_model_ref, write_entry

#: The shape of a result entry. The key names the producer, so a cadgen of another
#: version never reads this one's entries; the field refuses another shape at the
#: same version.
RESULT_SCHEMA_VERSION = 1
RESULT_KIND = "result"


def producer_versions() -> dict[str, str]:
    """Who builds: this cadgen and the kernel distributions it runs on, from their
    installed metadata -- no kernel import, so the gate stays kernel-free."""
    return dict(_producer_versions())


@functools.lru_cache(maxsize=1)
def _producer_versions() -> tuple[tuple[str, str], ...]:
    from importlib.metadata import PackageNotFoundError, version

    from cadgen import __version__

    versions = [("cadgen", str(__version__))]
    for name, distribution in (("build123d", "build123d"), ("cadqueryOcp", "cadquery-ocp-novtk")):
        try:
            versions.append((name, version(distribution)))
        except PackageNotFoundError:
            versions.append((name, ""))
    return tuple(versions)


def result_key(*, model: Path | str, closure_hash: str, constants: Mapping[str, Mapping[str, str]],
               children: Iterable[str], producer: Mapping[str, str], arguments: str = "") -> str:
    """The key of ``model``'s result built from these inputs (the module docstring)."""
    payload = {
        "model": resolve_model_ref(model),
        "closure": str(closure_hash),
        "constants": {str(rel): {str(name): str(digest) for name, digest in sorted(names.items())}
                      for rel, names in sorted(constants.items())},
        "children": sorted({str(key) for key in children}),
        "producer": {str(name): str(value) for name, value in sorted(producer.items())},
        "arguments": str(arguments),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def key_for(record: Mapping[str, Any], model: Path | str) -> str:
    """The key of ``model``'s result as ``record`` keeps it: its closure's hash, its
    constants, its children's keys and its producer."""
    return result_key(
        model=model,
        closure_hash=str((record.get("closure") or {}).get("hash") or ""),
        constants=record.get("constants") or {},
        children=[str((child or {}).get("key") or "") for child in record.get("children") or []],
        producer=record.get("producer") or {},
    )


def write_result(key: str, model: Path | str, record: Mapping[str, Any]) -> None:
    """Store ``record`` as the result at ``key`` -- ``write_record`` does, for every
    record it writes -- keeping the provenance already stored there."""
    existing = read_entry(RESULT_KIND, key) or {}
    kept = existing.get("provenance")
    write_entry(RESULT_KIND, key, {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "key": str(key),
        "model": resolve_model_ref(model),
        "tree": record.get("tree"),
        "producer": dict(record.get("producer") or {}),
        "record": dict(record),
        "provenance": dict(kept) if isinstance(kept, Mapping) else None,
    })


def write_result_provenance(key: str, provenance: Mapping[str, Any]) -> None:
    """Keep ``provenance`` -- the entry ``write_provenance`` wrote beside the record --
    with the result at ``key``; nothing when no result stands there."""
    entry = read_entry(RESULT_KIND, key)
    if entry:
        write_entry(RESULT_KIND, key, {**entry, "provenance": dict(provenance)})


def read_result(key: str) -> dict[str, Any] | None:
    """The result stored at ``key``, or None."""
    if not isinstance(key, str) or not key:
        return None
    entry = read_entry(RESULT_KIND, key)
    if not entry or entry.get("schemaVersion") != RESULT_SCHEMA_VERSION or not isinstance(entry.get("record"), dict):
        return None
    return entry


def results_of(model: Path | str) -> list[str]:
    """The keys of every result stored for ``model`` (``store forget`` drops them)."""
    ref = resolve_model_ref(model)
    keys: list[str] = []
    for key, _path in iter_entries(RESULT_KIND):
        entry = read_entry(RESULT_KIND, key)
        if entry and entry.get("model") == ref:
            keys.append(key)
    return keys


def obsolete_result(entry: Mapping[str, Any] | None) -> bool:
    """Whether a result entry was written by another cadgen: no build of this one asks
    for it again (its key names its producer), so the sweeper retires it (``gc``)."""
    from cadgen import __version__

    producer = (entry or {}).get("producer")
    return not isinstance(producer, Mapping) or str(producer.get("cadgen") or "") != str(__version__)
