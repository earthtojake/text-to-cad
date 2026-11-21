"""What a manufacturing check's measurement depends on, said apart from the check that asked it: the options it
reads, what it reads of the document, and the code that measures.

**The options it reads.** A process's options are of two kinds: those its measurement reads, which change the
report (CNC's tools decide which corners a tool reaches, sheet's K-factor where a bend's flat pattern ends), and
those its rules alone read, which change only the verdict (a material's limits, a sheet's size, a mold's
cavities). Each process's module declares the first beside its ``OPTIONS`` (``MEASURES``), and the integration's
``measure(document, options, candidates)`` is handed those alone (``measuring``), as a ``Measuring``: a dict of
the declared names that refuses any other (``KeyError``) and keeps each such name (``undeclared``), so a read the
module does not declare fails the check that made it even where the family that read it caught the refusal
(``cad.build123d._dfm_check``). So the report of one document is a function of these options alone, and the same
report stands for every check that resolves them alike.

**What it reads of the document.** A measurement reads the parts as the engine's reader made them, and not the
document's bytes: its content record (``cad.build123d._dfm_brep.content``, made in a checks process from the parts
a measurement would be handed) is that, as plain data -- each part's geometry key, names, placements, the token of
the mesh it was read with and its declared material's physics and process -- keyed by its canonical JSON
(``content_key``). So a document rebuilt with only a colour changed, the same file's bytes at another path, a
model edited and edited back are each one record. The record says what its parts declare (``declares``), so the
process a check given none is for is resolved from it with no kernel (``asked``), as from the parts themselves.

**The measurement's key.** What one measurement of one record is (``measure_key``): the document's type (a
report says it), the process, whether it ranks candidates, the options its measurement reads as they resolve
(``measuring``) and the digest of the code that measures that process (``cad.engine._measuring``'s ``dfm``).
``MEASURE_VERSION`` stands in it for what none of these says: it goes up by hand when a report's shape changes
by what no digest holds. The standard library alone.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

from cad._internal import dfm

__all__ = ["MEASURE_VERSION", "Measuring", "asked", "content_key", "declares", "measure_key", "measuring"]

#: The measurement key's own version (``measure_key``).
MEASURE_VERSION = 1


def measuring(process: str, resolved: dict[str, Any]) -> dict[str, Any]:
    """The options ``process``'s measurement reads (its ``MEASURES``), as ``resolved`` holds them: a name it does
    not hold is left out, as the measurement's ``get`` reads it."""
    return {name: resolved[name] for name in dfm.module(process).MEASURES if name in resolved}


class Measuring(dict):
    """The options a process's measurement is handed (``measuring``): a dict whose lookups -- ``[]``, ``get``,
    ``in``, ``setdefault``, ``pop`` -- of a name its process does not declare (``MEASURES``) raise ``KeyError``
    and keep the name in ``undeclared``, which the caller reads once the measurement is done. A declared name it
    does not hold reads as any dict's does."""

    def __init__(self, process: str, resolved: dict[str, Any]) -> None:
        super().__init__(measuring(process, resolved))
        self.process = process
        self.declared = frozenset(dfm.module(process).MEASURES)
        self.undeclared: set[str] = set()

    def _held(self, name: Any) -> None:
        if name not in self.declared:
            self.undeclared.add(str(name))
            raise KeyError(f"{name!r} is not read by a {self.process} measurement: "
                           f"cad._internal.dfm.{self.process}.MEASURES does not declare it")

    def __getitem__(self, name: Any) -> Any:
        self._held(name)
        return super().__getitem__(name)

    def __contains__(self, name: object) -> bool:
        self._held(name)
        return super().__contains__(name)

    def get(self, name: Any, default: Any = None) -> Any:
        self._held(name)
        return super().get(name, default)

    def setdefault(self, name: Any, default: Any = None) -> Any:
        self._held(name)
        return super().setdefault(name, default)

    def pop(self, name: Any, *default: Any) -> Any:
        self._held(name)
        return super().pop(name, *default)


def _canonical(value: Any) -> str:
    """``value`` as one JSON text: its keys sorted, no space."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_key(content: dict[str, Any]) -> str:
    """The key of a content record (``_dfm_brep.content``): a digest of its canonical JSON (blake2b, 16 bytes), its
    own ``key`` left out."""
    record = {name: value for name, value in content.items() if name != "key"}
    return hashlib.blake2b(_canonical(record).encode("utf-8"), digest_size=16).hexdigest()


def _declared(material: dict[str, Any] | None) -> Any:
    """A part's declared material as ``manufacturing.declared`` reads one, from its record (``material``): its
    ``name`` (the physics', as a ``bd_materials`` material's is) and its ``process`` (the route, ``skin`` and
    ``pitch_mm`` as ``processes.declared`` reads them); None for none."""
    if material is None:
        return None
    process = material.get("process")
    return SimpleNamespace(name=(material.get("material") or {}).get("name"),
                           process=None if process is None else SimpleNamespace(**process))


def declares(content: dict[str, Any]) -> list[tuple[str, Any]]:
    """What the parts of a content record declare, as ``manufacturing.declared`` takes the parts: each part's
    owner (else its name) and its declared material, read from the record alone (``_declared``)."""
    return [(part["owner"] or part["name"], _declared(part["material"])) for part in content["parts"]]


def asked(content: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    """What ``check`` (``{"type", "process", "resolved", "candidates", "given", "printer_settings"}``, as a checks
    process is handed it) asks of the document a content record says, its process named: ``{"process",
    "resolved", "declared"}`` -- the process and options given, ``declared`` None; or, given none, the process
    the parts declare and the options resolved for it (``manufacturing.declared`` over ``declares``), with the
    finding that says so (``declared``, which a report's findings end with, as ``_dfm_check`` ends them). A
    document of no part is ``{"unmeasured": {"code": "document_empty", "message"}}``, as its measurement says,
    and what ``manufacturing.declared`` refuses ``{"refused": words}``, as ``_dfm_check.held`` answers them."""
    from cad._internal import manufacturing
    from cad._internal.refused import ArgumentRefused

    if not content["parts"]:
        return {"unmeasured": {"code": "document_empty",
                               "message": "the document holds no part with a face to measure"}}
    if check.get("process") is not None:
        return {"process": check["process"], "resolved": dict(check["resolved"]), "declared": None}
    try:
        process, resolved, said = manufacturing.declared(
            check["type"], declares(content), dict(check.get("given") or {}),
            candidates=bool(check.get("candidates")), printer_snapshot=check.get("printer_settings"))
    except ArgumentRefused as refused:
        return {"refused": str(refused)}
    return {"process": process, "resolved": resolved, "declared": said}


def measure_key(document_type: str, process: str, candidates: bool, resolved: dict[str, Any], code: str) -> str:
    """The key of one measurement of a content record, as canonical JSON: ``{"v": MEASURE_VERSION, "type",
    "process", "candidates", "options": the options it reads as resolved (``measuring``), "code": the digest of
    the code that measures the process}``. Options its rules alone read, and the release, are not in it."""
    return _canonical({"v": MEASURE_VERSION, "type": document_type, "process": process,
                       "candidates": bool(candidates), "options": measuring(process, resolved), "code": code})
