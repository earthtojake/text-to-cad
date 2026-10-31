"""Identity beyond the id's formula (``ids``): what claims a name in a namespace, how a run
re-attaches a moved script's document, and the one startup pass that brings older records to
this shape. Records and file names only: nothing here imports the kernel, and nothing reads,
parses or writes an XBF.

A model's namespace is its script's folder; its name is its function's, or the one ``name=``
gives it. An explicit name is claimed (``claimed``): refused while the registry's record of it
says another file of the folder declared it at that file's last run, naming both ``file:line``;
a run of that file that declares it no more gives it up (``released``). What a script declares
is what its last run said (law 23): no script but the run's own is read. A run's model with
nothing to take up -- no document in its worker, no cache file at its id -- re-attaches
(``reattach``) the record of a script that is gone, or is this very script under another
spelling, with the same name, function and bytes (``fingerprint``): the record is re-pointed
under the new id with its history, its picture and its cache file (``repoint``). ``migrate``
fills ``namespace``, ``name`` and ``fingerprint`` on records from before them and moves a
``key::`` record to its folder/name id.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from cad.engine.ids import canonical, derived_id, is_id, model_id
from cad.engine.records import DOCUMENTS, RECORD, home, relative

__all__ = ["claimed", "claims", "fingerprint", "handed", "migrate", "reattach", "released", "relocated", "repoint"]


def fingerprint(script: str | os.PathLike) -> str | None:
    """SHA-256 of a script's bytes; None for one that cannot be read."""
    try:
        return hashlib.sha256(Path(script).read_bytes()).hexdigest()
    except OSError:
        return None


def _parsed(script: str | os.PathLike) -> Any:
    """A script's syntax tree; None for one that does not read or parse. The migration's alone (a
    record moved from its key finds its line), never a run's: what a script declares is its run's."""
    import ast

    try:
        return ast.parse(Path(script).read_bytes())
    except (OSError, SyntaxError, ValueError, RecursionError):
        return None


def _functions(tree: Any) -> Iterable[Any]:
    import ast

    return (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))


def _first(node: Any) -> int:
    """A function's first line as its code object has it: its first decorator's."""
    return min([node.lineno, *(found.lineno for found in node.decorator_list)])


def claimed(held: Any, source: dict[str, Any], name: str) -> None:
    """Refuse the explicit name ``name`` to ``source`` (its script, function and line) while the
    registry's record of it says another file of the same folder declared it at that file's last run
    (its ``line``), naming both ``file:line``. The record's own script is this declaration's (a
    function renamed, a line moved: two declarations in one file meet in one process,
    ``model.claim``); a file gone, or whose last run declared it no more (``released``), holds
    nothing."""
    script = canonical(source["script"])
    namespace = os.path.dirname(script)
    record = held.get(derived_id(namespace, name))
    if record is None or record.get("kind") != "model" or "line" not in record:
        return
    other = home(held, record)
    if not other.is_file() or canonical(other) == script:
        return
    raise ValueError(f"name {name!r} in namespace {namespace} is claimed by {other}:{record['line']} and "
                     f"{script}:{source.get('line', '?')}; give one declaration another name, or once "
                     f"{other.name} no longer declares it, run `cad run {other.name}` so the engine knows")


def released(held: Any, script: str | os.PathLike, names: Iterable[str]) -> list[str]:
    """The explicit names a run of ``script`` declared before and declares no more, given up: each
    one's record, while it is this script's, keeps its document and loses its claim (``line``), so
    another file of the folder may declare it. The ids given up."""
    script = canonical(script)
    folder = os.path.dirname(script)
    given: list[str] = []

    def release(record: dict[str, Any] | None) -> dict[str, Any] | None:
        if record is None or record.get("kind") != "model" or "line" not in record:
            return None
        if canonical(home(held, record)) != script:
            return None
        given.append(record["id"])
        return {key: value for key, value in record.items() if key != "line"}

    for name in sorted(set(names)):
        held.update(derived_id(folder, name), release)
    return given


def claims(held: Any, script: str | os.PathLike) -> set[str]:
    """The explicit names the registry's records say ``script`` declared: one pass, a record parsed
    only when its text holds a claim (``line``) and the script's folder. What a run of a script none
    of whose models' records says what it declared (``declares``) gives up from."""
    import json

    script = canonical(script)
    folder = json.dumps(os.path.dirname(script), ensure_ascii=False)[1:-1].encode("utf-8")
    found: set[str] = set()
    for ident in held.state.names(DOCUMENTS):
        if not is_id(ident):
            continue
        data = held.state.read(f"{DOCUMENTS}/{ident}/{RECORD}")
        if data is None or b'"line"' not in data or folder not in data:
            continue
        record = held.get(ident)
        if (record is not None and record.get("kind") == "model" and "line" in record
                and isinstance(record.get("name"), str) and canonical(home(held, record)) == script):
            found.add(record["name"])
    return found


def handed(held: Any, ident: str, scope: str, name: str) -> None:
    """Refuse a shape handed over (``model(shape, name=...)``) under the id a named model holds --
    from a REPL in a folder one of whose scripts gave a model ``name=`` the same at its last run --
    naming that declaration: one id is one document. A model whose script is gone, or whose last run
    declared the name no more (``released``), holds nothing."""
    record = held.get(ident)
    if record is None or record.get("kind") != "model" or "line" not in record:
        return
    other = home(held, record)
    if not other.is_file():
        return
    raise ValueError(f"the shape {name!r} handed over from {scope} would take the id of the model "
                     f"{record.get('name')!r} declared at {other}:{record['line']}; hand it over under "
                     "another name")


def repoint(held: Any, record: dict[str, Any], found: dict[str, Any]) -> None:
    """Move ``record`` to ``found`` (its new id): the cache file first, then the new record, and only
    then the old one forgotten (``Registry.delete``), so a stop at any step leaves the old identity
    whole. A move stopped part way is finished: a cache file at the new id with no record is no
    one's, and a new record equal to ``found`` is this move's. Refused (``ValueError``) when another
    record holds the new id. Never parses an XBF."""
    old, new = record["id"], found["id"]
    if old == new:
        held.put(found)
        return
    there = held.get(new)
    if there is not None and _fields(there) != _fields(found):
        raise ValueError(f"cannot move {old} to {new}: another record holds that id")
    if held.cache is not None:
        source = held.cache.path(f"{DOCUMENTS}/{old}/document.xbf")
        if source.is_file():
            held.cache._land(f"{DOCUMENTS}/{new}/document.xbf", lambda target: shutil.copyfile(source, target))
    held.put(found)
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
             before: Callable[[dict[str, Any]], None] = lambda _record: None,
             log: Callable[[str], None] = lambda _line: None) -> list[tuple[str, str]]:
    """Re-attach each of a run's models that has nothing to take up (``sources``: each a model's
    ``source``: its script, function, explicit name and fingerprint) to the record of its script
    moved (``_moved``): the record of its own id when it has one (a named model whose file moved in
    its folder), else one the registry holds, read in one pass for all of them (``_holding``). One
    candidate is adopted; of several, the most recently built (the id breaks a tie), the choice
    logged; none, and the model is a new document. ``before(record)`` runs first (the daemon saves a
    live document's bytes to its cache file); the record is re-pointed (``repoint``) with
    ``relocated``, the script its cache file was built from, kept from the first move. The ``(old
    id, new id)`` pairs re-pointed."""
    wanted = [source for source in sources if isinstance(source.get("fingerprint"), str)]
    adopted: list[tuple[str, str]] = []
    pool: list[dict[str, Any]] | None = None
    for source in wanted:
        script = Path(canonical(source["script"]))
        entry, explicit = source["name"], source.get("explicit_name")
        name = explicit or entry
        ident = model_id(script, entry, explicit)
        existing = held.get(ident)
        if existing is not None:
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
        before(candidates[0])
        old = held.get(candidates[0]["id"]) or candidates[0]  # a save may have added its cache field
        origin = home(held, old)
        found = {**old, "id": ident, "root": str(script.parent), "namespace": str(script.parent),
                 "home": relative(script, script.parent), "name": name,
                 "relocated": old.get("relocated") or {"script": str(origin), "module": old.get("module") or origin.stem}}
        repoint(held, old, found)
        if pool is not None:
            pool = [record for record in pool if record["id"] != old["id"]]
        adopted.append((old["id"], ident))
        choice = f"; chose the most recently built of {len(candidates)} candidates" if len(candidates) > 1 else ""
        log(f"identity: reattached {old['id']} to {ident} ({script}::{name}){choice}")
    return adopted


def relocated(closure: dict[str, Any], origin: str | os.PathLike, script: Path, folder: Path) -> dict[str, Any]:
    """A closure written for ``origin`` (the script a moved document's cache file was built from), its
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


def migrate(held: Any | None, *, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The one pass at engine start, over the records' JSON: each record from before ``namespace``,
    ``name`` and ``fingerprint`` (a model's script's bytes, null where its script is gone) gets them,
    and each record a ``key=`` named (``uuid5(NAMESPACE, "key::" + key)``) moves to its id now
    (``repoint``) with its cache file -- a model's its folder and the key, a shape's its scope and its
    name. Idempotent: a second pass writes nothing. A record that does not read, or cannot move, is
    skipped, never deleted, and listed; the pass says what it did in one line, and nothing when it
    did nothing."""
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
            if keyed and record["kind"] == "model" and "line" not in found:
                tree = _parsed(home(held, record))
                line = next((_first(node) for node in _functions(tree) if node.name == record["entry"]), None) \
                    if tree is not None else None
                if line is not None:
                    found["line"] = line
            if keyed:
                scope = found["namespace"] if record["kind"] == "model" else home(held, record)
                found["id"] = derived_id(scope, found["name"])
                found.pop("key", None)
                repoint(held, record, found)
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
