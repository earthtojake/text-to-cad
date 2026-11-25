"""Identity beyond the id's formula (``ids``): how a run re-attaches a moved script's document, how a
record from before a model's id was its ``.xbf``'s is carried to that id, and the one startup pass that
brings older records to this shape. Records and file names only: nothing here imports the kernel, and
nothing reads, parses or writes an XBF.

A model's document is its ``.xbf``, and its id that file's (``ids.file_id``). Before, its id was the formula
over its script and its function, or its folder and an explicit name (``former``): a record of that id is
carried to the file's id (``carry``) -- its creation, its opening, its pin and its picture -- and dropped, the
old id kept on the new record (``aliases``), which an id the engine does not know is looked up in
(``registry.Registry.resolve``). A run's model with nothing to take up -- no document in its worker, no record of
its own at its id -- re-attaches (``reattach``) the record of a script that is gone, or is this very script under
another spelling, with the same name, function and bytes (``fingerprint``): the record is re-pointed under the
new id with its history and its picture (``repoint``). ``migrate`` fills ``namespace``, ``name`` and
``fingerprint`` on records from before them, moves a ``key::`` record to its folder/name id, and carries a model's
record that names its ``.xbf`` to that file's id.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from cad.engine.ids import canonical, derived_id, file_id, is_id
from cad.engine.records import DOCUMENTS, RECORD, home, relative, xbf

__all__ = ["carry", "fingerprint", "former", "migrate", "reattach", "relocated", "repoint"]


def fingerprint(script: str | os.PathLike) -> str | None:
    """SHA-256 of a script's bytes; None for one that cannot be read."""
    try:
        return hashlib.sha256(Path(script).read_bytes()).hexdigest()
    except OSError:
        return None


def former(source: dict[str, Any]) -> str:
    """The id a model's document had before its id was its ``.xbf``'s (``source``: its script, its function and its
    explicit name; a shape's, its scope and its name, ``kind: "shape"``): ``ids.derived_id`` of its script and its
    function, or of its script's folder and its explicit name, or of a shape's scope and its name."""
    if source.get("kind") == "shape":
        return derived_id(source["script"], source["name"])
    script = canonical(source["script"])
    explicit = source.get("explicit_name")
    return derived_id(os.path.dirname(script), explicit) if explicit is not None else derived_id(script, source["name"])


# What a record carried to another id brings with it: what a person did with its card.
CARRIED = ("created", "opened", "pinned", "preview")


def carry(found: dict[str, Any], *others: dict[str, Any] | None) -> dict[str, Any]:
    """``found`` (a record at its id now) with what ``others`` (records of the same document under another id, or
    the record its id had before) hold of a person's use of its card: the first ``created``, the last ``opened``, a
    pin, a picture where ``found`` has none; and every id of theirs as its ``aliases``."""
    found = dict(found)
    aliases = [alias for alias in found.get("aliases") or [] if is_id(alias)]
    for other in others:
        if not other:
            continue
        created = [value for value in (found.get("created"), other.get("created")) if isinstance(value, (int, float))]
        if created:
            found["created"] = min(created)
        opened = [value for value in (found.get("opened"), other.get("opened")) if isinstance(value, (int, float))]
        if opened:
            found["opened"] = max(opened)
        if other.get("pinned"):
            found["pinned"] = True
        if "preview" not in found and isinstance(other.get("preview"), dict):
            found["preview"] = other["preview"]
        for alias in [*(other.get("aliases") or []), other.get("id")]:
            if is_id(alias) and alias != found["id"] and alias not in aliases:
                aliases.append(alias)
    if aliases:
        found["aliases"] = aliases
    return found


def repoint(held: Any, record: dict[str, Any], found: dict[str, Any]) -> None:
    """Move ``record`` to ``found`` (its new id): the new record first, with what a record at that id already holds
    of a person's use of its card and the old id among its ``aliases`` (``carry``), and only then the old one
    forgotten (``Registry.delete``), so a stop at any step leaves the old identity whole. Never parses an XBF."""
    old, new = record["id"], found["id"]
    if old == new:
        held.put(found)
        return
    there = held.get(new)
    held.put(carry(found, there if there is not None and _fields(there) != _fields(found) else None, record))
    held.delete(old)


def _fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "schema"}


def _moved(held: Any, record: dict[str, Any], script: Path, name: str, entry: str, digest: str) -> bool:
    """Whether ``record`` is the document of ``script``'s model, moved: the same name, function and
    bytes, its script gone -- or there still as this very file under another spelling (a link, a
    case). Its script there as another file is the original of a copy."""
    if (record.get("kind") != "model" or record.get("name") != name or record.get("entry") != entry
            or record.get("fingerprint") != digest):
        return False
    try:
        was = home(held, record)
    except (KeyError, TypeError, ValueError):
        return False
    return not was.exists() or canonical(was) == str(script)


def _holding(held: Any, digests: Iterable[str]) -> list[dict[str, Any]]:
    """Every record whose text holds one of ``digests``: one pass over the registry, a record parsed
    only when its bytes hold one (``Registry.get`` reads it then)."""
    needles = [digest.encode("ascii") for digest in digests]
    found = []
    for ident in held.state.names(DOCUMENTS):
        if not is_id(ident):
            continue
        data = held.state.read(f"{DOCUMENTS}/{ident}/{RECORD}")
        if data is None or not any(needle in data for needle in needles):
            continue
        record = held.get(ident)
        if record is not None:
            found.append(record)
    return found


def reattach(held: Any, sources: list[dict[str, Any]], *,
             log: Callable[[str], None] = lambda _line: None) -> list[tuple[str, str]]:
    """Re-attach each of a run's models that has nothing to take up (``sources``: each a model's
    ``source``: its script, function, explicit name, fingerprint and ``.xbf``) to the record of its script
    moved, or of its id before its id was its ``.xbf``'s (``_moved``): the record of its own id when it has one
    (a named model whose file moved in its folder), else one the registry holds, read in one pass for all of
    them (``_holding``). One candidate is adopted; of several, the most recently built (the id breaks a tie),
    the choice logged; none, and the model is a new document. The record is re-pointed (``repoint``) at its
    ``.xbf`` now, with ``relocated``, the script its ``.xbf`` was built from where that is another, kept from
    the first move. The ``(old id, new id)`` pairs re-pointed."""
    wanted = [source for source in sources if isinstance(source.get("fingerprint"), str)]
    adopted: list[tuple[str, str]] = []
    pool: list[dict[str, Any]] | None = None
    for source in wanted:
        script = Path(canonical(source["script"]))
        entry, explicit = source["name"], source.get("explicit_name")
        name = explicit or entry
        ident = file_id(source["xbf"]) if isinstance(source.get("xbf"), str) else former(source)
        existing = held.get(ident)
        if existing is not None and existing.get("kind") == "model":
            if home(held, existing) == script:
                continue  # its own record: nothing moved
            records = [existing]
        else:
            if pool is None:
                pool = _holding(held, {row["fingerprint"] for row in wanted})
            records = pool
        candidates = [record for record in records if _moved(held, record, script, name, entry, source["fingerprint"])]
        if not candidates:
            continue
        candidates.sort(key=lambda row: (row.get("built") or 0, row["id"]), reverse=True)
        old = candidates[0]
        origin = home(held, old)
        found = {**old, "id": ident, "root": str(script.parent), "namespace": str(script.parent),
                 "home": relative(script, script.parent), "name": name}
        if isinstance(source.get("xbf"), str):
            found["saved"] = relative(canonical(source["xbf"]), script.parent)
        if old.get("relocated") or canonical(origin) != str(script):
            found["relocated"] = old.get("relocated") or {"script": str(origin), "module": old.get("module") or origin.stem}
        repoint(held, old, found)
        if pool is not None:
            pool = [record for record in pool if record["id"] != old["id"]]
        adopted.append((old["id"], ident))
        choice = f"; chose the most recently built of {len(candidates)} candidates" if len(candidates) > 1 else ""
        log(f"identity: reattached {old['id']} to {ident} ({script}::{name}){choice}")
    return adopted


def relocated(closure: dict[str, Any], origin: str | os.PathLike, script: Path, folder: Path) -> dict[str, Any]:
    """A closure written for ``origin`` (the script a moved document's ``.xbf`` was built from), its
    paths renamed as the same files are named from ``script``: what the document's closure is
    compared as when it is taken. The digests, its bytes and its key stay as they are, so a file
    whose bytes differ still differs."""
    old_script = Path(origin)
    old_folder = old_script.parent / os.path.relpath(folder, script.parent)

    def moved(path: str | None) -> str | None:
        if path is None:
            return None
        absolute = Path(os.path.normpath(old_folder / path))
        if absolute == old_script:
            target = script
        elif absolute.is_relative_to(old_script.parent):
            target = script.parent / absolute.relative_to(old_script.parent)
        else:
            target = absolute
        return relative(target, folder)

    inputs = []
    for row in closure.get("inputs") or []:
        row = list(row)
        at = 1 if row[0] in ("file", "read") else 2
        row[at] = moved(row[at])
        inputs.append(row)
    return {**closure, "source": {**closure["source"], "path": relative(script, folder)},
            "modules": sorted([moved(path), digest] for path, digest in closure["modules"]),
            "symbols": {moved(path): value for path, value in closure.get("symbols", {}).items()},
            "inputs": inputs if closure.get("inputs") is not None else None}


def _to_file(held: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    """A model's or a shape's record from before its id was its ``.xbf``'s, at that file's id now: what a record of the
    file there holds of a person's use of its card carried (``carry``, the old id an alias), the fields of the cache, of
    the fold and of the name claims gone, and the file's version as the engine wrote it where the file's record said so (its ``of``,
    of this very revision): its next run takes it from the file. None for a record that names no ``.xbf``, or is at
    its id already."""
    if record.get("kind") not in ("model", "shape"):
        return None
    path = xbf(held, record)
    if path is None:
        return None
    new = file_id(path)
    if new == record["id"]:
        return None
    found = {key: value for key, value in record.items() if key not in ("cache", "line", "declares", "of")}
    found["id"] = new
    there = held.get(new)
    of = (there or {}).get("of") if isinstance((there or {}).get("of"), dict) else {}
    if of.get("id") == record["id"] and of.get("revision") == record.get("revision") and isinstance(of.get("version"), str):
        found["version"] = of["version"]
    return found


def migrate(held: Any | None, *, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The one pass at engine start, over the records' JSON: each record from before ``namespace``,
    ``name`` and ``fingerprint`` (a model's script's bytes, null where its script is gone) gets them,
    each record a ``key=`` named (``uuid5(NAMESPACE, "key::" + key)``) moves to its id then
    (``repoint``) -- a model's its folder and the key, a shape's its scope and its name -- and each model's or
    shape's record that names its ``.xbf`` moves to that file's id (``_to_file``). Idempotent: a second pass writes
    nothing. A record that does not read, or cannot move, is skipped, never deleted, and listed; the pass says what
    it did in one line, and nothing when it did nothing."""
    import uuid

    from cad.engine.ids import NAMESPACE

    filled, moved, skipped = 0, 0, []
    for ident in held.state.names(DOCUMENTS) if held is not None else []:
        if not is_id(ident):
            continue  # no record's folder: nothing of the registry's
        location = f"{DOCUMENTS}/{ident}/{RECORD}"
        try:
            record = held.get(ident)
            if record is None:
                if not held.state.path(location).exists():
                    continue  # moved by this pass: the record it was moved to is its
                raise ValueError("unreadable record or unsupported schema/id")
            if record.get("kind") not in ("model", "shape", "file"):
                raise ValueError("unknown document kind")
            if not all(isinstance(record.get(field), str) and record[field] for field in ("root", "home")):
                raise ValueError("missing root/home")
            if record["kind"] != "file" and not isinstance(record.get("entry"), str):
                raise ValueError("missing entry")
            found = dict(record)
            found.setdefault("namespace", record["root"])
            legacy = record.get("key")
            keyed = isinstance(legacy, str) and ident == str(uuid.uuid5(NAMESPACE, "key::" + legacy))
            name = legacy if keyed and record["kind"] == "model" else record.get("entry") or Path(record["home"]).name
            found.setdefault("name", name)
            if "fingerprint" not in found and record["kind"] == "model":
                found["fingerprint"] = fingerprint(home(held, record))
            filed = _to_file(held, found)
            if keyed:
                scope = found["namespace"] if record["kind"] == "model" else home(held, record)
                found["id"] = derived_id(scope, found["name"])
                found.pop("key", None)
                repoint(held, record, found)
                moved += 1
            elif filed is not None:
                repoint(held, record, filed)
                moved += 1
            elif held.put(found):
                filled += 1
        except Exception as error:  # noqa: BLE001 - a record this pass cannot bring over stays as it is
            skipped.append(f"{location}: {error}")
    result = {"filled": filled, "moved": moved, "skipped": skipped}
    if filled or moved or skipped:
        line = f"identity migration: filled {filled}, moved {moved}, skipped {len(skipped)}"
        if skipped:
            line += "; " + "; ".join(skipped)
        (log or (lambda message: print(f"cad: {message}", file=sys.stderr, flush=True)))(line)
    return result
