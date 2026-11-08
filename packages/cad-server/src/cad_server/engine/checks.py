"""The manufacturing checks' results the daemon keeps, so the same check of an unchanged document
measures nothing (``Daemon.check``).

A result is kept under its document and the version of it that was measured: a model document by its
id and its generation (``models.Models``' ``version``: a token of its build's own, kept by a run that
changed nothing in the worker that holds it, new for anything else), a file by its path and the digest of
its bytes. Beside that, the check itself: the document type, the process, the resolved options, the
candidates flag and, with no process, the options given, and the release of the library that measured
it (the server's own, or the release of the caller's Python a model was built in). A document holds the
results of one version alone: a result of another version is dropped the moment one of the new version
is kept or asked for, so none outlives the document it describes. Nothing is persisted: the store is
process memory, bounded by ``LIMIT`` results and ``BYTES`` of them (their JSON), the least recently used
going first. A part of an assembly left untouched by an edit is measured again with the rest: a check
measures the document whole (its findings, build volume and rules are the document's), so per-part reuse
would be a second, finer key, not this one.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

__all__ = ["BYTES", "LIMIT", "Checks", "digest"]

# At most this many results kept, and this many bytes of them (their JSON).
LIMIT = 128
BYTES = 64 * 2**20


def digest(path: Path) -> str | None:
    """A file's version as a check's key holds it: the digest of its bytes; None when it does not read."""
    found = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                found.update(block)
    except OSError:
        return None
    return found.hexdigest()


class Checks:
    def __init__(self, limit: int = LIMIT, budget: int = BYTES) -> None:
        self.limit, self.budget = limit, budget
        self.lock = threading.Lock()
        # (document, check) -> (version, the result's JSON), least recently used first.
        self.kept: "OrderedDict[tuple[str, str], tuple[str, str]]" = OrderedDict()
        self.bytes = 0
        self.measured = 0
        self.reused = 0

    @staticmethod
    def key(check: dict[str, Any], release: str) -> str:
        """The check's half of a key: what it asks and which library answers it (never its token)."""
        asked = {name: value for name, value in check.items() if name != "token"}
        return json.dumps({"check": asked, "release": release}, sort_keys=True, separators=(",", ":"))

    def _drop(self, document: str, version: str | None = None) -> None:
        for held in [held for held, (kept, _text) in self.kept.items()
                     if held[0] == document and (version is None or kept != version)]:
            self.bytes -= len(self.kept.pop(held)[1])

    def get(self, document: str, version: str, check: str) -> dict[str, Any] | None:
        """The result kept of ``check`` of ``document`` at ``version``, or None; results of any other
        version of it dropped."""
        with self.lock:
            self._drop(document, version)
            found = self.kept.get((document, check))
            if found is None:
                return None
            self.kept.move_to_end((document, check))
            self.reused += 1
            return json.loads(found[1])

    def keep(self, document: str, version: str, check: str, result: dict[str, Any]) -> None:
        """``result`` kept as ``check``'s of ``document`` at ``version``, the store held to its bounds."""
        text = json.dumps(result, separators=(",", ":"))
        with self.lock:
            if len(text) > self.budget:
                return
            self._drop(document, version)
            old = self.kept.pop((document, check), None)
            if old is not None:
                self.bytes -= len(old[1])
            self.kept[(document, check)] = (version, text)
            self.bytes += len(text)
            while self.kept and (len(self.kept) > self.limit or self.bytes > self.budget):
                self.bytes -= len(self.kept.popitem(last=False)[1][1])

    def counted(self) -> None:
        """One check measured in a worker, kept or not."""
        with self.lock:
            self.measured += 1

    def forget(self, document: str) -> None:
        """Every result of ``document`` dropped (it was deleted)."""
        with self.lock:
            self._drop(document)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {"held": len(self.kept), "bytes": self.bytes, "measured": self.measured, "reused": self.reused}
