"""The manufacturing checks' measurements the daemon keeps (``Measurements``), by what was measured and not by
which document it was measured of: the same parts measured the same way are one measurement, whatever file,
path, model or version they came from. A check's life is ``checks_runner.Runner``'s, which asks this store.

Two kinds of entry, each in memory and in the engine's cache folder:

- **An alias** says what a measurement reads of one version of a document: its content record
  (``cad.build123d._dfm_brep.content``, made in a checks process and keyed by ``kept.content_key``), under a
  token of that version -- ``model_token``: a model's id and its revision; ``build_token``: for a build whose
  revision does not outlive the engine, its id and its generation, kept in memory alone; ``file_token``: the
  digest of a file's bytes with its name's stem and suffix, which are all of its path a read takes (an unnamed
  root is named by the stem), so the same bytes under the same name anywhere are one alias. With it is kept what
  described it
  (``by``: the describing process's code and libraries), and it is served to a caller that process would
  describe for (``serves``), so a record read by other code, or other libraries, is read again. A version whose
  alias is held needs no process to be told what it holds.
- **A result** is one measurement's report (``{"report"}``), under the key of the record it was measured of and
  the measurement's own key (``kept.measure_key``: the type, the process, the options its measurement reads and
  the digest of the code that measures that process). With it is kept what measured it (``by``: that digest and
  the libraries), and it is served to a caller ``serves`` says it stands for. It holds no process, no resolved
  options and no rule's verdict: those are each asking check's.

**In memory**: ``ALIASES`` aliases and ``ALIAS_BYTES`` of them, ``RESULTS`` results and ``RESULT_BYTES`` of
them (their JSON), the least recently used going first.

**On disk**, under ``checks/`` in the cache folder (``folder()``: the engine's registry, or a ``Folder``
alone; None keeps nothing there), each file written whole:

    checks/models/<document id>/<digest of the revision>.json   {"format", "token", "content", "by"}
    checks/files/<xx>/<digest of the token>.json                the same
    checks/results/<xx>/<content key>-<digest of the measure>.json
                                                                {"format", "content", "measure", "by", "result"}

A model keeps its ``REVISIONS`` most recently used aliases; the files' aliases are held to ``FILE_ALIASES`` and
``FILE_ALIAS_BYTES``, the results to ``DISK_RESULTS`` and ``DISK_RESULT_BYTES``, the least recently used (by
its time on disk, set again by each read) going first. A file that does not read as what its name says -- not
JSON, another format, another token's, record's or measurement's, a record whose key is not its own -- is
removed, never served. The files' aliases and the results are listed once each, at their first use (the
half-written files a stopped engine left swept then); one gone since leaves the list as it is asked for. A
folder that cannot be written keeps nothing there, each entry trying its own write.

**A deleted document** (``deleted``, told by ``Registry.delete`` under the document's lock) takes its own
aliases with it, in memory and ``checks/models/<id>/``, and a check of it that began before names none
(``epoch``, ``name``'s ``since``: asked under that lock). The results are no document's: they outlive every
document they were measured of, and go by their bounds or with the cache.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

__all__ = ["ALIASES", "ALIAS_BYTES", "DISK_RESULTS", "DISK_RESULT_BYTES", "FILE_ALIASES", "FILE_ALIAS_BYTES",
           "FORMAT", "RESULTS", "RESULT_BYTES", "REVISIONS", "ROOT", "Measurements", "build_token", "file_token",
           "is_record", "model_token"]

# At most this many aliases kept in memory, and this many bytes of them (their JSON).
ALIASES = 1024
ALIAS_BYTES = 32 * 2**20
# At most this many results kept in memory, and this many bytes of them.
RESULTS = 128
RESULT_BYTES = 64 * 2**20
# On disk: a model's aliases at most; the files' aliases and their bytes; the results and theirs.
REVISIONS = 8
FILE_ALIASES = 4096
FILE_ALIAS_BYTES = 32 * 2**20
DISK_RESULTS = 1024
DISK_RESULT_BYTES = 256 * 2**20
# The format of an entry's file: another is a file that does not read.
FORMAT = 1
# The store's folder in the cache folder, and its three inside it.
ROOT = "checks"
MODELS, FILES, KEPT = f"{ROOT}/models", f"{ROOT}/files", f"{ROOT}/results"

_KEY = re.compile(r"[0-9a-f]{32}")


def model_token(ident: str, revision: str) -> tuple[str, ...]:
    """A model document's version as an alias names it: its id and its revision, its build closure's key, the
    same in any process."""
    return ("model", str(ident), str(revision))


def build_token(ident: str, generation: str) -> tuple[str, ...]:
    """A version of a model document whose revision does not outlive the engine (a build with no key), as an
    alias names it: its id and its generation, a token of this engine's own. Such an alias is kept in memory
    alone."""
    return ("build", str(ident), str(generation))


def file_token(digest: str, path: str | os.PathLike[str]) -> tuple[str, ...]:
    """A file's bytes as an alias names them: their digest, and of the path they were read at the stem and the
    suffix of the file it resolves to -- what a read takes of a path (the reader by the suffix, an unnamed
    root's name from the stem), and nothing of where the file is."""
    resolved = Path(path).resolve()
    return ("file", str(digest), resolved.stem, resolved.suffix.lower())


def is_record(content: Any) -> bool:
    """Whether ``content`` is a content record as ``kept`` reads one: its parts each with a name, an owner and a
    declared material that is a table or none, and its ``key`` the key of the record itself
    (``kept.content_key``), so a record changed since it was keyed is none."""
    from cad._internal.dfm import kept

    if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
        return False
    for part in content["parts"]:
        if not isinstance(part, dict) or not all(
                isinstance(part.get(name), (str, type(None))) and name in part for name in ("name", "owner")):
            return False
        material = part.get("material", False)
        if material is not None and not (
                isinstance(material, dict) and isinstance(material.get("material"), (dict, type(None)))
                and isinstance(material.get("process"), (dict, type(None)))):
            return False
    try:
        return isinstance(content.get("key"), str) and content["key"] == kept.content_key(content)
    except (TypeError, ValueError):
        return False


def _digest(text: str, size: int = 10) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=size).hexdigest()


def _text(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


class _Kept:
    """Entries in memory, by their key: each its JSON and what it was made by, the least recently used first,
    held to ``limit`` entries and ``budget`` bytes of their JSON (call with the store's lock held)."""

    def __init__(self, limit: int, budget: int) -> None:
        self.limit, self.budget = limit, budget
        self.held: "OrderedDict[Any, tuple[str, Any]]" = OrderedDict()
        self.bytes = 0

    def get(self, key: Any) -> tuple[Any, Any] | None:
        found = self.held.get(key)
        if found is None:
            return None
        self.held.move_to_end(key)
        return json.loads(found[0]), found[1]

    def put(self, key: Any, value: Any, by: Any) -> None:
        text = _text(value)
        self.drop(key)
        if len(text) > self.budget:
            return
        self.held[key] = (text, by)
        self.bytes += len(text)
        while self.held and (len(self.held) > self.limit or self.bytes > self.budget):
            self.bytes -= len(self.held.popitem(last=False)[1][0])

    def drop(self, key: Any) -> None:
        old = self.held.pop(key, None)
        if old is not None:
            self.bytes -= len(old[0])


class _Shelf:
    """One bounded folder of the store on disk (``inside``): its entries at ``<inside>/<xx>/<name>.json``,
    ``xx`` the name's first two characters, listed and stated once per cache folder (nothing read, the
    half-written files there swept), held to ``limit`` files and ``budget`` bytes, the least recently used --
    by its time on disk, which a read sets again -- going first (call with the store's disk lock held)."""

    def __init__(self, inside: str, limit: int, budget: int) -> None:
        self.inside, self.limit, self.budget = inside, limit, budget
        self.index: dict[str, tuple[int, float]] | None = None
        self.root: Any = None
        self.bytes = 0

    def place(self, name: str) -> str:
        return f"{self.inside}/{name[:2]}/{name}.json"

    def listed(self, held: Any) -> dict[str, tuple[int, float]]:
        root = getattr(held, "root", held)
        if self.index is not None and root == self.root:
            return self.index
        self.index, self.bytes, self.root = {}, 0, root
        for folder in held.names(self.inside):
            for name in held.names(f"{self.inside}/{folder}"):
                inside = f"{self.inside}/{folder}/{name}"
                if not name.endswith(".json"):
                    if ".json." in name and name.endswith(".tmp"):
                        _removed(held, inside)  # a write a stopped engine left half done
                    continue
                try:
                    stat = held.path(inside).stat()
                except OSError:
                    continue
                self.index[inside] = (stat.st_size, stat.st_mtime)
                self.bytes += stat.st_size
        return self.index

    def forget(self, inside: str) -> None:
        found = (self.index or {}).pop(inside, None)
        if found is not None:
            self.bytes -= found[0]

    def remove(self, held: Any, inside: str) -> None:
        _removed(held, inside)
        self.forget(inside)
        try:
            os.rmdir(held.path(inside.rsplit("/", 1)[0]))  # its ``<xx>/``, gone with its last entry
        except (OSError, ValueError):
            pass  # not empty, or gone already

    def read(self, held: Any, name: str, good: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
        """The entry ``name`` as written, where ``good`` says it is what its name says; else None, one that
        does not read removed and one gone dropped from the list."""
        inside = self.place(name)
        found, there = _read(held, inside, good)
        if found is None:
            if there:
                self.listed(held)
                self.remove(held, inside)  # never served: the next check makes and writes it again
            else:
                self.forget(inside)  # gone with its folder since it was listed
            return None
        index = self.listed(held)
        if inside in index:
            index[inside] = (index[inside][0], _stamped(held, inside))
        return found

    def write(self, held: Any, name: str, entry: dict[str, Any]) -> None:
        """``entry`` written whole as ``name``, the shelf held to its bounds; one over the budget alone, or a
        folder that takes no write, keeps nothing."""
        data = _text(entry).encode("utf-8")
        if len(data) > self.budget:
            return
        inside = self.place(name)
        index = self.listed(held)
        try:
            held.write(inside, data)
        except OSError:
            return
        self.forget(inside)
        index[inside] = (len(data), time.time())
        self.bytes += len(data)
        while len(index) > 1 and (len(index) > self.limit or self.bytes > self.budget):
            self.remove(held, min((place for place in index if place != inside), key=lambda place: index[place][1]))

    def status(self) -> tuple[int | None, int]:
        return (None if self.index is None else len(self.index)), self.bytes


def _removed(held: Any, inside: str) -> None:
    try:
        held.remove(inside)
    except OSError:
        pass


def _stamped(held: Any, inside: str) -> float:
    """``inside`` read now: the most recently used, by its time on disk."""
    now = time.time()
    try:
        os.utime(held.path(inside), (now, now))
    except OSError:
        pass
    return now


def _read(held: Any, inside: str, good: Callable[[dict[str, Any]], bool]) -> tuple[dict[str, Any] | None, bool]:
    """The JSON object at ``inside`` where it is of this format and ``good`` says it is the entry asked for, and
    whether a file is there at all."""
    data = held.read(inside)
    if data is None:
        return None, False
    try:
        found = json.loads(data.decode("utf-8"))
        return (found if isinstance(found, dict) and found.get("format") == FORMAT and good(found) else None), True
    except (AttributeError, KeyError, TypeError, UnicodeDecodeError, ValueError):
        return None, True


class Measurements:
    """The kept aliases and results (the module): ``content`` and ``name`` an alias, ``get`` and ``keep`` a
    result, ``forget`` an alias found wrong, ``deleted`` a document's own, ``status`` the counts. ``folder()``:
    the engine's registry, whose cache folder holds the store and whose lock of a document a model's alias is
    written under (``Registry.lock``), or a ``registry.Folder`` alone (a test's); None: nothing is kept on
    disk."""

    def __init__(self, folder: Callable[[], Any] | None = None, *, results: int = RESULTS,
                 budget: int = RESULT_BYTES, aliases: int = ALIASES, disk_results: int = DISK_RESULTS,
                 disk_budget: int = DISK_RESULT_BYTES, file_aliases: int = FILE_ALIASES,
                 revisions: int = REVISIONS) -> None:
        self.folder, self.revisions = folder, revisions
        self.lock = threading.Lock()  # what memory holds, and the counts
        self.disk = threading.Lock()  # the files and their lists: never taken with ``lock`` held, nor it with this
        self.aliases = _Kept(aliases, ALIAS_BYTES)
        self.results = _Kept(results, budget)
        self.files = _Shelf(FILES, file_aliases, FILE_ALIAS_BYTES)
        self.kept = _Shelf(KEPT, disk_results, disk_budget)
        self.described = 0
        self.read = 0
        self.reused = 0
        self.restored = 0
        # How many times each document id was deleted (``deleted``): a check that began before one names nothing.
        self.deletions: dict[str, int] = {}

    def _held(self) -> tuple[Any, Any]:
        """The cache folder and the lock of a document's writes there (``Registry.lock``; none for a folder
        alone), or ``(None, None)``."""
        found = self.folder() if self.folder is not None else None
        if found is None:
            return None, None
        if hasattr(found, "lock") and hasattr(found, "cache"):
            return found.cache, found.lock
        return found, None

    # --- aliases ------------------------------------------------------------------------------------

    @staticmethod
    def _alias(token: tuple[str, ...]) -> tuple[str, str] | None:
        """Where a token's alias is on disk: a model's folder and its file there, or None and its name on the
        files' shelf. ``ValueError`` for a model token whose id is none."""
        if token[0] != "model":
            return None
        from cad.engine.ids import is_id

        if not is_id(token[1]):
            raise ValueError(f"{token[1]!r} is not a document id")
        return f"{MODELS}/{token[1]}", f"{_digest(token[2])}.json"

    def content(self, token: tuple[str, ...], serves: Callable[[Any], bool] = lambda _by: True
                ) -> dict[str, Any] | None:
        """The content record ``token``'s version holds, where what described it describes for the caller
        (``serves(by)``); None for none kept, or one of another's describing, which the next ``name`` replaces.
        Looked for in memory, then, but for a build's own token, on disk, and taken into memory from there."""
        token = tuple(token)
        with self.lock:
            found = self.aliases.get(token)
        if found is None and token[0] != "build":
            found = self._alias_on_disk(token)
            if found is not None:
                with self.lock:
                    self.aliases.put(token, *found)
        if found is None or not serves(found[1]):
            return None
        return found[0]

    def _alias_on_disk(self, token: tuple[str, ...]) -> tuple[dict[str, Any], Any] | None:
        held, _locks = self._held()
        if held is None:
            return None

        def good(found: dict[str, Any]) -> bool:
            return (found.get("token") == list(token) and isinstance(found.get("by"), dict)
                    and is_record(found.get("content")))

        model = self._alias(token)
        with self.disk:
            if model is None:
                found = self.files.read(held, _digest(_text(list(token)), 16), good)
            else:
                inside = f"{model[0]}/{model[1]}"
                found, there = _read(held, inside, good)
                if found is not None:
                    _stamped(held, inside)
                elif there:
                    _removed(held, inside)  # one that does not read: never served
        return None if found is None else (found["content"], found["by"])

    def epoch(self, ident: str | None) -> int:
        """How many times document ``ident`` was deleted so far: what ``name``'s ``since`` names."""
        with self.lock:
            return self.deletions.get(ident or "", 0)

    def name(self, token: tuple[str, ...], content: dict[str, Any], by: Any = None, *,
             since: int | None = None) -> None:
        """``content`` kept as the record ``token``'s version holds, described ``by`` (the describing process's
        code and libraries); on disk too, but for a build's own token. A model's is kept under the registry's
        lock of its document, and not at all where the document was deleted since ``since``, its ``epoch`` as
        the check began."""
        token = tuple(token)
        by = by if isinstance(by, dict) else {}
        held, locks = self._held()
        model = self._alias(token)
        ident = token[1] if token[0] in ("model", "build") else None
        entry = {"format": FORMAT, "token": list(token), "content": content, "by": by}
        with (locks(ident) if locks is not None and ident is not None else contextlib.nullcontext()):
            if ident is not None and since is not None and self.epoch(ident) != since:
                return  # deleted since the check began: its aliases are gone, and stay gone
            with self.lock:
                self.aliases.put(token, content, by)
            if held is None or token[0] == "build":
                return
            with self.disk:
                if model is None:
                    self.files.write(held, _digest(_text(list(token)), 16), entry)
                    return
                try:
                    held.write(f"{model[0]}/{model[1]}", _text(entry).encode("utf-8"))
                except OSError:
                    return
                self._trimmed(held, *model)

    def _trimmed(self, held: Any, folder: str, written: str) -> None:
        """A model's aliases held to ``revisions`` -- the one just ``written`` and the most recently used of the
        others (by their time on disk) -- and a half-written file a stopped engine left there swept."""
        stated: list[tuple[float, str]] = []
        for name in held.names(folder):
            inside = f"{folder}/{name}"
            if not name.endswith(".json"):
                if ".json." in name and name.endswith(".tmp"):
                    _removed(held, inside)
                continue
            if name == written:
                continue
            try:
                stated.append((held.path(inside).stat().st_mtime, inside))
            except OSError:
                continue
        for _changed, inside in sorted(stated)[:max(0, len(stated) + 1 - self.revisions)]:
            _removed(held, inside)

    def forget(self, token: tuple[str, ...]) -> None:
        """``token``'s alias dropped, from memory and from disk: a measurement of that version read another
        record than it says."""
        token = tuple(token)
        with self.lock:
            self.aliases.drop(token)
        held, _locks = self._held()
        if held is None or token[0] == "build":
            return
        model = self._alias(token)
        with self.disk:
            if model is None:
                self.files.remove(held, self.files.place(_digest(_text(list(token)), 16)))
            else:
                _removed(held, f"{model[0]}/{model[1]}")

    def deleted(self, ident: str) -> None:
        """Document id ``ident`` deleted (``Registry.delete``, told under its lock): its aliases dropped from
        memory and its folder of them removed, and a check of it that began before names none (``epoch``)."""
        from cad.engine.ids import is_id

        with self.lock:
            self.deletions[ident] = self.deletions.get(ident, 0) + 1
            for token in [token for token in self.aliases.held
                          if token[0] in ("model", "build") and token[1] == ident]:
                self.aliases.drop(token)
        held, _locks = self._held()
        if held is not None and is_id(ident):
            with self.disk:
                _removed(held, f"{MODELS}/{ident}")

    # --- results ------------------------------------------------------------------------------------

    @staticmethod
    def _result(content_key: str, measure: str) -> str:
        if not (isinstance(content_key, str) and _KEY.fullmatch(content_key)):
            raise ValueError(f"{content_key!r} is not a content record's key")
        return f"{content_key}-{_digest(measure)}"

    def get(self, content_key: str, measure: str, serves: Callable[[Any], bool] = lambda _by: True
            ) -> dict[str, Any] | None:
        """The result kept of measurement ``measure`` (``kept.measure_key``) of the record ``content_key``,
        where what measured it stands for the caller (``serves(by)``); None for none kept, or one another's
        measuring made, which the next ``keep`` replaces. Looked for in memory, then on disk, and taken into
        memory from there."""
        name = self._result(content_key, measure)
        with self.lock:
            found = self.results.get((content_key, measure))
            if found is not None:
                if not serves(found[1]):
                    return None  # measured with other code or libraries than the caller's: measured again
                self.reused += 1
                return found[0]
        held, _locks = self._held()
        if held is None:
            return None

        def good(entry: dict[str, Any]) -> bool:
            return (entry.get("content") == content_key and entry.get("measure") == measure
                    and isinstance(entry.get("by"), dict) and isinstance(entry.get("result"), dict)
                    and isinstance(entry["result"].get("report"), dict))

        with self.disk:
            entry = self.kept.read(held, name, good)
        if entry is None:
            return None
        with self.lock:
            self.results.put((content_key, measure), entry["result"], entry["by"])
            if not serves(entry["by"]):
                return None
            self.reused += 1
            self.restored += 1
        return entry["result"]

    def keep(self, content_key: str, measure: str, result: dict[str, Any], by: Any = None) -> None:
        """``result`` (``{"report"}``) kept as measurement ``measure``'s of the record ``content_key``, measured
        ``by`` (the digest of the code that measured its process, and the libraries), in memory and on disk,
        each held to its bounds; one kept under the same keys before is replaced."""
        name = self._result(content_key, measure)
        by = by if isinstance(by, dict) else {}
        with self.lock:
            self.results.put((content_key, measure), result, by)
        held, _locks = self._held()
        if held is None:
            return
        with self.disk:
            self.kept.write(held, name, {"format": FORMAT, "content": content_key, "measure": measure, "by": by,
                                         "result": result})

    # --- what it holds ------------------------------------------------------------------------------

    def counted(self, read: bool = False) -> None:
        """One document described in a process for a check; ``read``: it read the document, none held."""
        with self.lock:
            self.described += 1
            self.read += int(read)

    def status(self) -> dict[str, Any]:
        """The results and the aliases held in memory (``held`` and ``bytes``, ``aliases``), the documents
        described and those read for it, the results reused and, of them, those restored from disk, and what
        the disk holds of each, once listed (``disk``; None with no cache folder)."""
        with self.lock:
            found: dict[str, Any] = {
                "held": len(self.results.held), "bytes": self.results.bytes, "aliases": len(self.aliases.held),
                "described": self.described, "read": self.read, "reused": self.reused, "restored": self.restored}
        if self.folder is None:
            found["disk"] = None
            return found
        with self.disk:
            (held, size), (aliases, _alias_bytes) = self.kept.status(), self.files.status()
        found["disk"] = {"held": held, "bytes": size, "aliases": aliases}
        return found
