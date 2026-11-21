"""The manufacturing checks' measurements the daemon keeps (``Measurements``), by what was measured and not by
which document it was measured of: the same parts measured the same way are one measurement, whatever file,
path, model or version they came from. A check's life is ``checks_runner.Runner``'s, which asks this store.

Two kinds of entry, each in memory and in the engine's cache folder:

- **An alias** says what a measurement reads of one version of a document: its content record
  (``cad.build123d._dfm_brep.content``, made in a checks process and keyed by ``kept.content_key``), under a
  token of that version -- ``model_token``: a model's id and what names its version beyond the engine's life
  (its revision with a digest of what the engine knows the build made: ``Daemon._check_built``);
  ``build_token``: for a build that has no such name, its id and its generation, kept in memory alone;
  ``file_token``: the
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

A model keeps its ``REVISIONS`` most recently used aliases, and the models' together are held to
``MODEL_ALIASES`` and ``MODEL_ALIAS_BYTES``; the files' aliases to ``FILE_ALIASES`` and ``FILE_ALIAS_BYTES``,
the results to ``DISK_RESULTS`` and ``DISK_RESULT_BYTES``, the least recently used (by its time on disk, set
again by each read) going first. A file that does not read as what its name says -- not JSON, another format,
another token's, record's or measurement's, a record whose key is not its own -- is removed, never served.
Each of the three is listed once, at its first use (the half-written files a stopped engine left swept
then); one gone since leaves the list as it is asked for. A folder that cannot be written keeps nothing
there, each entry trying its own write.

**A deleted document** takes its own aliases with it. Its folder of them, ``checks/models/<id>/``, is the
registry's to remove with the document's others (``Registry.delete``, ``registry.CHECKED``), whether an engine
runs or not: a model built again under the id may hold other parts at a revision it had before, which an
alias left behind would answer for. A running engine is told (``deleted``, under the document's lock) and
drops what it holds of them in memory; and a check of the document that began before neither names an alias
nor takes one from disk into memory (``epoch``: asked under that lock). The results are no document's: they
outlive every document they were measured of, and go by their bounds or with the cache.

**What a model's alias takes for granted.** A build is not always a function of its closure: it can read the
environment, an argument, a clock, so a model built again at a revision it had before -- after an edit undone,
or after it was deleted -- may hold other parts. A check answered from what was kept asks no process, and so
would catch nothing; hence a model's version is named by its revision *and* the build's facts as the engine
holds them (its parts' geometry keys and counts, their looks and materials, its bounds and joints), and a
deleted document's aliases go with it. What the facts do not hold -- a part's name, where it stands inside the
same bounds -- is taken for granted of two builds at one revision that agree in all the facts; where a process
is asked, a measurement of other parts than the alias says is caught and the alias forgotten (``forget``).
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

from cad_server.engine.registry import CHECKED

__all__ = ["ALIASES", "ALIAS_BYTES", "DISK_RESULTS", "DISK_RESULT_BYTES", "FILE_ALIASES", "FILE_ALIAS_BYTES",
           "FORMAT", "MODEL_ALIASES", "MODEL_ALIAS_BYTES", "RESULTS", "RESULT_BYTES", "REVISIONS", "ROOT",
           "Measurements", "build_token", "file_token", "is_key", "is_record", "model_token"]

# At most this many aliases kept in memory, and this many bytes of them (their JSON).
ALIASES = 1024
ALIAS_BYTES = 32 * 2**20
# At most this many results kept in memory, and this many bytes of them.
RESULTS = 128
RESULT_BYTES = 64 * 2**20
# On disk: a model's aliases at most, and the models' together and their bytes; the files' aliases and their
# bytes; the results and theirs.
REVISIONS = 8
MODEL_ALIASES = 4096
MODEL_ALIAS_BYTES = 32 * 2**20
FILE_ALIASES = 4096
FILE_ALIAS_BYTES = 32 * 2**20
DISK_RESULTS = 1024
DISK_RESULT_BYTES = 256 * 2**20
# The format of an entry's file: another is a file that does not read.
FORMAT = 1
# The store's folder in the cache folder, and its three inside it: the models' aliases where the registry
# removes a deleted document's (``registry.CHECKED``).
ROOT = "checks"
MODELS, FILES, KEPT = CHECKED, f"{ROOT}/files", f"{ROOT}/results"

_KEY = re.compile(r"[0-9a-f]{32}")


def is_key(text: Any) -> bool:
    """Whether ``text`` is a content record's key, as ``kept.content_key`` makes one."""
    return isinstance(text, str) and _KEY.fullmatch(text) is not None


def model_token(ident: str, revision: str) -> tuple[str, ...]:
    """A model document's version as an alias names it: its id and what names the version in any engine
    (``revision``: its build closure's key, with what the engine knows the build made where it says so)."""
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
    """One bounded folder of the store on disk (``inside``): its entries two folders down,
    ``<inside>/<folder>/<name>.json``, listed and stated once per cache folder (nothing read, the half-written
    files there swept), held to ``limit`` files and ``budget`` bytes -- and each folder of it to ``within``
    files, where one is given -- the least recently used, by its time on disk, which a read sets again, going
    first (call with the store's disk lock held)."""

    def __init__(self, inside: str, limit: int, budget: int, within: int | None = None) -> None:
        self.inside, self.limit, self.budget, self.within = inside, limit, budget, within
        self.index: dict[str, tuple[int, float]] | None = None
        self.root: Any = None
        self.bytes = 0

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

    def dropped(self, folder: str) -> None:
        """Every entry of ``<inside>/<folder>/`` out of the list: the folder went, with what it was of."""
        mine = f"{self.inside}/{folder}/"
        for inside in [inside for inside in self.index or {} if inside.startswith(mine)]:
            self.forget(inside)

    def remove(self, held: Any, inside: str) -> None:
        _removed(held, inside)
        self.forget(inside)
        try:
            os.rmdir(held.path(inside.rsplit("/", 1)[0]))  # its folder, gone with its last entry
        except (OSError, ValueError):
            pass  # not empty, or gone already

    def read(self, held: Any, inside: str, good: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
        """The entry at ``inside`` as written, where ``good`` says it is what its name says; else None, one
        that does not read removed and one gone dropped from the list."""
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

    def write(self, held: Any, inside: str, entry: dict[str, Any]) -> None:
        """``entry`` written whole at ``inside``, its folder and the shelf held to their bounds, the one just
        written never the one to go; one over the budget alone, or a folder that takes no write, keeps
        nothing."""
        data = _text(entry).encode("utf-8")
        if len(data) > self.budget:
            return
        index = self.listed(held)
        try:
            held.write(inside, data)
        except OSError:
            return
        self.forget(inside)
        index[inside] = (len(data), time.time())
        self.bytes += len(data)

        def oldest(places: Any) -> str:
            return min((place for place in places if place != inside), key=lambda place: index[place][1])

        if self.within is not None:
            mine = inside.rsplit("/", 1)[0] + "/"
            beside = [place for place in index if place.startswith(mine)]
            while len(beside) > max(1, self.within):
                gone = oldest(beside)
                beside.remove(gone)
                self.remove(held, gone)
        while len(index) > 1 and (len(index) > self.limit or self.bytes > self.budget):
            self.remove(held, oldest(index))

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
    result, ``forget`` an alias found wrong, ``deleted`` what memory holds of a deleted document, ``status`` the
    counts. ``folder()``: the engine's registry, whose cache folder holds the store and whose lock of a document
    a model's alias is read and written under (``Registry.lock``), or a ``registry.Folder`` alone (a test's);
    None: nothing is kept on disk."""

    def __init__(self, folder: Callable[[], Any] | None = None, *, results: int = RESULTS,
                 budget: int = RESULT_BYTES, aliases: int = ALIASES, disk_results: int = DISK_RESULTS,
                 disk_budget: int = DISK_RESULT_BYTES, file_aliases: int = FILE_ALIASES,
                 model_aliases: int = MODEL_ALIASES, revisions: int = REVISIONS) -> None:
        self.folder = folder
        self.lock = threading.Lock()  # what memory holds, and the counts
        self.disk = threading.Lock()  # the files and their lists: never taken with ``lock`` held, nor it with this
        self.aliases = _Kept(aliases, ALIAS_BYTES)
        self.results = _Kept(results, budget)
        self.models = _Shelf(MODELS, model_aliases, MODEL_ALIAS_BYTES, within=revisions)
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

    def _place(self, token: tuple[str, ...]) -> tuple[_Shelf, str]:
        """Where a token's alias is on disk: its shelf and its place there -- a model's in its document's own
        folder, a file's by its token's digest. ``ValueError`` for a model token whose id is none."""
        if token[0] == "model":
            from cad.engine.ids import is_id

            if not is_id(token[1]):
                raise ValueError(f"{token[1]!r} is not a document id")
            return self.models, f"{MODELS}/{token[1]}/{_digest(token[2])}.json"
        name = _digest(_text(list(token)), 16)
        return self.files, f"{FILES}/{name[:2]}/{name}.json"

    @staticmethod
    def _document(token: tuple[str, ...]) -> str | None:
        """The document a token's alias is the own of (a model's, by either token), or None: a file's bytes are
        no document's."""
        return token[1] if token[0] in ("model", "build") else None

    def content(self, token: tuple[str, ...], serves: Callable[[Any], bool] = lambda _by: True
                ) -> dict[str, Any] | None:
        """The content record ``token``'s version holds, where what described it describes for the caller
        (``serves(by)``); None for none kept, or one of another's describing, which the next ``name`` replaces.
        Looked for in memory, then, but for a build's own token, on disk, and taken into memory from there."""
        token = tuple(token)
        with self.lock:
            found = self.aliases.get(token)
        if found is None and token[0] != "build":
            found = self._restored(token)
        if found is None or not serves(found[1]):
            return None
        return found[0]

    def _restored(self, token: tuple[str, ...]) -> tuple[dict[str, Any], Any] | None:
        """``token``'s alias read from disk and taken into memory -- a model's under the registry's lock of its
        document, as ``name`` writes one, and neither answered nor taken where the document was deleted while
        it was read (``epoch``): its aliases are gone, and stay gone."""
        held, locks = self._held()
        if held is None:
            return None
        shelf, inside = self._place(token)
        ident = self._document(token)

        def good(found: dict[str, Any]) -> bool:
            return (found.get("token") == list(token) and isinstance(found.get("by"), dict)
                    and is_record(found.get("content")))

        with (locks(ident) if locks is not None and ident is not None else contextlib.nullcontext()):
            since = self.epoch(ident)
            with self.disk:
                found = shelf.read(held, inside, good)
            if found is None:
                return None
            with self.lock:
                if ident is not None and self.deletions.get(ident, 0) != since:
                    return None
                self.aliases.put(token, found["content"], found["by"])
        return found["content"], found["by"]

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
        ident = self._document(token)
        with (locks(ident) if locks is not None and ident is not None else contextlib.nullcontext()):
            if ident is not None and since is not None and self.epoch(ident) != since:
                return  # deleted since the check began: its aliases are gone, and stay gone
            with self.lock:
                self.aliases.put(token, content, by)
            if held is None or token[0] == "build":
                return
            shelf, inside = self._place(token)
            with self.disk:
                shelf.write(held, inside, {"format": FORMAT, "token": list(token), "content": content, "by": by})

    def forget(self, token: tuple[str, ...]) -> None:
        """``token``'s alias dropped, from memory and from disk: a measurement of that version read another
        record than it says."""
        token = tuple(token)
        with self.lock:
            self.aliases.drop(token)
        held, _locks = self._held()
        if held is None or token[0] == "build":
            return
        shelf, inside = self._place(token)
        with self.disk:
            shelf.remove(held, inside)

    def deleted(self, ident: str) -> None:
        """Document id ``ident`` deleted (``Registry.delete``, told under its lock, its folder of aliases
        removed with its others): what memory holds of them dropped, the folder's entries out of the list, and
        a check of it that began before neither names an alias nor takes one into memory (``epoch``)."""
        with self.lock:
            self.deletions[ident] = self.deletions.get(ident, 0) + 1
            for token in [token for token in self.aliases.held if self._document(token) == ident]:
                self.aliases.drop(token)
        with self.disk:
            self.models.dropped(ident)

    # --- results ------------------------------------------------------------------------------------

    @staticmethod
    def _result(content_key: str, measure: str) -> str:
        if not is_key(content_key):
            raise ValueError(f"{content_key!r} is not a content record's key")
        name = f"{content_key}-{_digest(measure)}"
        return f"{KEPT}/{name[:2]}/{name}.json"

    def get(self, content_key: str, measure: str, serves: Callable[[Any], bool] = lambda _by: True
            ) -> dict[str, Any] | None:
        """The result kept of measurement ``measure`` (``kept.measure_key``) of the record ``content_key``,
        where what measured it stands for the caller (``serves(by)``); None for none kept, or one another's
        measuring made, which the next ``keep`` replaces. Looked for in memory, then on disk, and taken into
        memory from there."""
        inside = self._result(content_key, measure)
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
            entry = self.kept.read(held, inside, good)
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
        inside = self._result(content_key, measure)
        by = by if isinstance(by, dict) else {}
        with self.lock:
            self.results.put((content_key, measure), result, by)
        held, _locks = self._held()
        if held is None:
            return
        with self.disk:
            self.kept.write(held, inside, {"format": FORMAT, "content": content_key, "measure": measure, "by": by,
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
        the disk holds, once listed (``disk``: the results and their bytes, and the aliases of the files and
        of the models that were listed; None with no cache folder)."""
        with self.lock:
            found: dict[str, Any] = {
                "held": len(self.results.held), "bytes": self.results.bytes, "aliases": len(self.aliases.held),
                "described": self.described, "read": self.read, "reused": self.reused, "restored": self.restored}
        if self.folder is None:
            found["disk"] = None
            return found
        with self.disk:
            (held, size), aliases = self.kept.status(), [self.files.status()[0], self.models.status()[0]]
        listed = [count for count in aliases if count is not None]
        found["disk"] = {"held": held, "bytes": size, "aliases": sum(listed) if listed else None}
        return found
