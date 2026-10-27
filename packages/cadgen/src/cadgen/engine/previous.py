"""A model's build closure, on its xbf's main label: what made the document, as pointers and
digests, and the key a restart compares.

When a build writes a model's xbf, the document's main label carries its closure
(``manifest``, schema ``cadgen.engine closure/2``):

- ``engine``: the keyed xbf format (``FORMAT``); as information only, the release that wrote it
  (``cadgen <VERSION>``, the version declared beside this very code: ``version``) and a digest of
  the engine's own code;
- ``libs``: the versions of build123d and OCP (the kernel: OCCT's release leads its version),
  which decide the geometry;
- ``platform``: the keyed system and architecture (``platform.system()``, ``platform.machine()``):
  an arm64 kernel and an x86-64 one write other bytes of one model; the Python version is recorded
  as information only;
- ``source``: ``{"kind": "script", "path", "function"}`` -- the script relative to the
  document's folder and the model's function;
- ``modules``: ``[path, digest]`` per first-party module the script's load imported or the
  model reaches, each a digest of what the model reaches in it (its functions' code objects
  with no line tables, its classes, the values its bindings hold: ``sources.Symbols.modules``);
  a comment or a blank line changes none;
- ``symbols``: per module of ``modules``, a short digest of each binding and each function and
  class the model reaches in it, by name (``sources.Symbols.symbols``): not in the key, what a
  build names when that module changed (``lib/geometry.py: _CACHE changed``);
- ``inputs``: ``[kind, path, digest]`` per file a body read -- through the engine
  (``file``: ``read_step``, ``read_xbf``, the importers) or itself (``read``) -- by its path
  relative to the document's folder (``null`` digest: a file it found missing), and a text's
  font (``font``);
- ``bodies``: how many bodies the model is;
- ``key``: one digest over the format, the libraries, the system and the architecture, and the
  code: the source, the modules and the inputs; ``null`` where the closure
  cannot say all the model is made of (a body read a pipe, or reaches what cannot be keyed).
  Not the engine's code digest: an engine edit that leaves the document alone keeps every xbf
  current. ``FORMAT`` is what moves when the written document, or what the key covers, changes
  (``xbf/1`` to ``xbf/2``), and every xbf then builds once, cleanly. A cadgen release or Python
  version change alone leaves the key current.

No source text, no line, no input's contents (**the file is the document**, **names are the
durable tie to code**).

A build asks the document before it runs a model's body (``build._previous``): the closure
made again now -- the script loaded, its modules digested, each input hashed again -- against
the one the document holds. The same key, in a document this engine wrote that reads whole, and
the body is not run: the document on disk is what it would make, and it is not written.
Otherwise the build runs, and its report names what changed (``changes``): ``../src/lib/arm.py
changed``, ``../STEP/gripper.step is missing``, ``arm64 became x86_64``.

Only the whole document is taken, never a part of it. OCCT's BinXCAF reader does not
give back the doubles it was given: it builds each direction and placement anew, and a
direction made again is normalized again, a rotation orthogonalized again, a unit in the
last place apart (a document read and saved is other bytes, and read and saved again,
other bytes again). A document holding a body's result read back would so drift from the
cold build's bytes, build after build. So what is written is always made from what bodies
made in this process, and a document read is never written: an edit after a restart runs
the model.

An explicit build with an older format in its closure is rebuilt from source. Reading a saved
snapshot is independent: ``document_migrations`` converts supported metadata in memory while
preserving this original closure. Migration never makes old geometry a current build-cache hit.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "cadgen.engine closure/2"
# Bumped deliberately, never by a release: when the document an engine writes, or what the
# key covers, changes. A document of another format is built again once (``build._previous``).
# xbf/2: the key covers the format alone of the engine, and no numpy; the closure holds no commit.
# xbf/3: the kinematics are AP242's alone: couplings as its couplers, motions' interpolation, no
# cadgen-only attribute, no gear pair.
# xbf/4: a function motion's samples are checked at every eighth of a step and held to half the tolerance there.
# xbf/5: files read by motion functions join the closure.
# xbf/6: the closure counts the build's animations, and a document with any is not taken.
# xbf/7: the build's animations are a record on the main label (``animations.record``); the closure counts none.
# xbf/8: the closure names the toolchain that built it (closure/2): the system and architecture join the key.
# xbf/9: native bd_materials physics and PbrProperties replace the cadgen material schema.
FORMAT = "xbf/9"
# The libraries a key covers: what decides the geometry and native material payload.
KEYED_LIBRARIES = ("build123d", "OCP", "bd_materials", "threejs_materials")
# The keyed platform fields; the closure also records Python as information only.
KEYED_PLATFORM = ("system", "arch")
# The start of a closure's text: the schema first, so a head scan finds it.
_PREFIX = f'{{"schema":"{SCHEMA}",'.encode()
# How far into a document its main label's attributes are: right after the header.
_HEAD_BYTES = 1 << 20


@functools.cache
def version() -> str:
    """The cadgen release declared beside this very code -- its source tree's
    ``pyproject.toml`` (stamped from ``VERSION`` by the release), else the ``.dist-info``
    installed beside the package -- never the first ``cadgen`` metadata on the path, which
    can be another install's. ``0+unknown`` with neither."""
    import tomllib

    package = Path(__file__).resolve().parent.parent
    try:
        with (package.parent.parent / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle).get("project") or {}
        if project.get("name") == "cadgen" and project.get("version"):
            return str(project["version"])
    except (OSError, ValueError):
        pass
    found = []
    for metadata in package.parent.glob("cadgen-*.dist-info"):
        try:
            found.append((metadata.stat().st_mtime_ns, metadata.name))
        except OSError:
            continue
    return max(found)[1][len("cadgen-"):-len(".dist-info")] if found else "0+unknown"


@functools.cache
def _libraries() -> dict[str, str]:
    """The versions of what a model's body runs on beyond its own code and the engine's."""
    from importlib import metadata

    found = {}
    # OCP ships as two distributions, with VTK and without: either is the OCP a body runs on.
    for shown, names in (("build123d", ("build123d",)), ("OCP", ("cadquery-ocp", "cadquery-ocp-novtk")),
                         ("bd_materials", ("bd_materials",)), ("threejs_materials", ("threejs-materials",))):
        for name in names:
            try:
                found[shown] = metadata.version(name)
                break
            except metadata.PackageNotFoundError:
                continue
    return found


@functools.cache
def _engine() -> dict[str, str]:
    from cadgen.engine.model import _engine_version

    return {"release": f"cadgen {version()}", "format": FORMAT,
            "digest": hashlib.sha256(_engine_version().encode()).hexdigest()[:32]}


@functools.cache
def _platform() -> dict[str, str]:
    """The Python a body runs on and the machine it runs on: the system (``Darwin``, ``Linux``,
    ``Windows``) and the architecture (``arm64``, ``x86_64``, ``AMD64``), as ``platform`` names
    them. A worker runs the engine's own interpreter, so the engine and its workers say the same."""
    import platform

    return {"python": platform.python_version(), "system": platform.system(), "arch": platform.machine()}


def _digest(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return hashlib.blake2b(text.encode(), digest_size=16).hexdigest()


def closure(keys: dict[str, tuple], name: str) -> list[str]:
    """The bodies a body is: itself and every body it called, once each, in order."""
    found: list[str] = []
    pending = [name]
    while pending:
        current = pending.pop()
        if current in found or current not in keys:
            continue
        found.append(current)
        pending.extend(reversed(keys[current][3]))
    return found


def _relative(path: str | None, folder: Path) -> str | None:
    if path is None:
        return None
    try:
        return Path(os.path.relpath(path, folder)).as_posix()
    except ValueError:  # another drive
        return Path(path).as_posix()


def absolute(path: str | None, folder: Path) -> str | None:
    """A closure's path as a file: relative to the document's folder."""
    return None if path is None else os.path.normpath(os.path.join(folder, path))


def _source(model: Any, folder: Path) -> dict[str, Any]:
    return {"kind": "script", "path": _relative(str(model.script), folder), "function": model.name}


def _input(recipe: tuple, value: Any, folder: Path) -> list:
    """One input as the closure lists it: its kind, its path, the digest of what it held."""
    kind = recipe[0]
    if kind in ("file", "read"):
        return [kind, _relative(recipe[1], folder), _value(kind, value)]
    return [kind, recipe[1], _relative(recipe[2], folder), recipe[3], _value(kind, value)]


def _value(kind: str, value: Any) -> str | None:
    if value is None:
        return None
    if kind == "file":
        return value[1]
    if kind == "font":
        return f"{value[1]}:{value[2][1]}"
    return value


def _recipe(row: list, folder: Path) -> tuple:
    kind = row[0]
    if kind in ("file", "read"):
        return (kind, absolute(row[1], folder))
    return (kind, row[1], absolute(row[2], folder), row[3])


def manifest(keys: dict[str, tuple], name: str, folder: Path, model: Any, modules: dict[str, str],
             unkeyable: bool, symbols: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """The closure a model's document carries (see the module), its paths relative to
    ``folder``, the document's: ``keys`` the run's bodies (``memo``), ``name`` the model's
    body, ``modules`` and ``unkeyable`` its closure by file (``sources.Symbols.modules``)."""
    from cadgen.engine.kernel import memo

    found = keys.get(name)
    keyed = found is not None and bool(found[2]) and not unkeyable
    inputs: list | None = None
    if found is not None:
        inputs = []
        for check, expected in found[1]:
            recipe = memo.recipe(check)
            if recipe is None:
                keyed = False  # bytes handed to an importer: no path a fresh process reads again
                continue
            row = _input(recipe, expected, folder)
            if row not in inputs:  # a child placed again holds its reads again
                inputs.append(row)
    record: dict[str, Any] = {
        "schema": SCHEMA, "engine": _engine(), "libs": _libraries(), "platform": _platform(),
        "source": _source(model, folder),
        "modules": sorted([_relative(path, folder), digest] for path, digest in modules.items()),
        "symbols": _named(symbols or {}, folder),
        "inputs": inputs, "bodies": len(closure(keys, name)) if found is not None else None}
    record["key"] = key(record) if keyed else None
    return record


def _named(symbols: dict[str, dict[str, str]], folder: Path) -> dict[str, dict[str, str]]:
    """``symbols`` by each module's path relative to ``folder``, in order."""
    return {_relative(path, folder): dict(sorted(found.items()))
            for path, found in sorted(symbols.items(), key=lambda item: _relative(item[0], folder))}


def key(record: dict[str, Any]) -> str:
    """The digest a restart compares: the format, the libraries, the system and the architecture,
    and the code: the source, the modules and the inputs. The release, Python version and engine's
    code digest are recorded but not keyed; the format moves when what an engine writes does."""
    libs = {name: record["libs"].get(name) for name in KEYED_LIBRARIES}
    platform = {name: record["platform"].get(name) for name in KEYED_PLATFORM}
    return _digest([SCHEMA, record["engine"]["format"], libs, platform,
                    record["source"], record["modules"], record["inputs"]])


def text(record: dict[str, Any]) -> str:
    """A closure as the main label holds it: ASCII JSON, the schema first."""
    return json.dumps(record, ensure_ascii=True, separators=(",", ":"))


def again(record: dict[str, Any], model: Any, folder: Path, modules: dict[str, str],
          symbols: dict[str, dict[str, str]] | None = None) -> tuple[str, list[str]]:
    """The closure ``record`` names, made again now: its key, and what differs from the
    record, each said by name (``../src/arm.py: WIDTH, plate changed``, ``../STEP/gripper.step
    is missing``). ``modules`` is the model's closure by file now, ``symbols`` what it reaches in
    each by name (a changed module names what changed in it where the record holds its names)."""
    from cadgen.engine.kernel import memo

    now = {"schema": SCHEMA, "engine": _engine(), "libs": _libraries(), "platform": _platform(),
           "source": _source(model, folder),
           "modules": sorted([_relative(path, folder), digest] for path, digest in modules.items())}
    changes: list[str] = []
    if now["engine"]["format"] != record["engine"].get("format"):
        changes.append(f"the xbf format changed ({record['engine'].get('format')} to {now['engine']['format']})")
    for name in sorted(set(now["libs"]) | set(record["libs"])):
        if now["libs"].get(name) != record["libs"].get(name):
            changes.append(f"{name} {record['libs'].get(name)} became {now['libs'].get(name)}")
    held_platform = record.get("platform") or {}
    for name in KEYED_PLATFORM:
        if now["platform"][name] != held_platform.get(name):
            changes.append(f"{held_platform.get(name)} became {now['platform'][name]}")
    if now["source"] != record["source"]:
        source = now["source"]
        changes.append(f"the model is now {source['path']}::{source['function']}")
    held, current = dict(map(tuple, record["modules"])), dict(map(tuple, now["modules"]))
    named = _named(symbols or {}, folder)
    for path in sorted(set(held) | set(current)):
        if path not in current:
            changes.append(f"{path} is no longer imported")
        elif path not in held:
            changes.append(f"{path} is new")
        elif held[path] != current[path]:
            was, now_named = (record.get("symbols") or {}).get(path), named.get(path, {})
            differ = [] if was is None else sorted(name for name in set(was) | set(now_named)
                                                   if was.get(name) != now_named.get(name))
            changes.append(f"{path}: {', '.join(differ)} changed" if differ else f"{path} changed")
    inputs = []
    for row in record["inputs"] or []:
        recipe = _recipe(row, folder)
        try:
            value = _value(row[0], memo.recheck(recipe))
        except Exception:  # noqa: BLE001 - a file it read that reads no more: missing
            value = None
        shown = row[1] if row[0] != "font" else f"font {row[1]}"
        if value != row[-1]:
            changes.append(f"{shown} is missing" if value is None else f"{shown} changed")
        inputs.append([*row[:-1], value])
    now["inputs"] = inputs if record["inputs"] is not None else None
    return key(now), changes


def located(record: dict[str, Any], folder: Path) -> dict[str, Any]:
    """What a build's report says of its closure (``record``, its paths relative to ``folder``):
    its key, and its modules and inputs by absolute path -- what the engine's registry records."""
    inputs = []
    for row in record.get("inputs") or []:
        row = list(row)
        at = 1 if row[0] in ("file", "read") else 2
        row[at] = absolute(row[at], folder)
        inputs.append(row)
    return {"key": record.get("key"), "modules": [[absolute(path, folder), digest] for path, digest in record.get("modules") or []],
            "inputs": inputs}


def scan(path: Path) -> tuple[str | None, str | None]:
    """What wrote the document at ``path`` and the closure its main label holds, read from
    its head, where the main label's attributes are: ``(writer, closure text)``, each None
    where the head holds none. A first look only: a document is taken once it reads whole. The
    closure of whichever schema it holds -- an earlier engine's is what that document holds -- for
    a build takes only a document of this engine's format (``build._previous``)."""
    with open(path, "rb") as handle:
        return _head(handle.read(_HEAD_BYTES))


def _head(head: bytes, schema: str | None = None) -> tuple[str | None, str | None]:
    """``scan`` of a document's first bytes: its writer, and its closure, of ``schema`` where one
    is named."""
    import re

    writer = re.search(rb"cadgen\.engine xbf/[0-9]+ \(cadgen [ -~]{1,64}?\)", head)
    found = None
    schemas = "cadgen.engine closure/"  # every closure's schema starts so
    at = head.find(f'{{"schema":"{schema}",'.encode() if schema else f'{{"schema":"{schemas}'.encode())
    if at >= 0:
        end = head.find(b"\x00", at)  # an ASCII string's bytes end before the next attribute's
        tail = head[at:end if end >= 0 else len(head)].decode("ascii", "replace")
        try:
            value, length = json.JSONDecoder().raw_decode(tail)
            held = value.get("schema") if isinstance(value, dict) else None
            if held == schema or (schema is None and str(held).startswith(schemas)):
                found = tail[:length]
        except ValueError:
            found = None
    return (writer.group(0).decode() if writer else None, found)


def read_record(doc: Any) -> tuple[str | None, str | None]:
    """The writer and the closure a document read whole holds on its main label."""
    from cadgen.engine.document import CLOSURE_GUID, WRITER_GUID, _label_text

    return _label_text(doc.Main(), WRITER_GUID), _label_text(doc.Main(), CLOSURE_GUID)


def of(path: Path) -> dict[str, Any] | None:
    """The closure the xbf at ``path`` holds, or None."""
    _writer, found = scan(Path(path))
    return None if found is None else json.loads(found)
