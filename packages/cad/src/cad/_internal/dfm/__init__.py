"""The manufacturing check's processes, type side: their options, their rules and what their findings say.

A manufacturing check (``cad.<type>.dfm(source, process=...)``, ``cad._internal.manufacturing``) is two
layers. The **measurement** is an integration's: exact geometry -- a STEP, an xbf, a document the engine
holds -- is measured on its B-rep by the build123d integration (``cad.build123d._dfm_*``), a mesh -- an STL,
a 3MF, a GLB -- by the trimesh integration (``cad.trimesh``); each answers a report of plain data, facts
alone. The **verdicts** are here: each process's module (``cnc``, ``sheet``, ``molding``, ``printing``)
names its options, its rules (``rules``: general practice, each rule cited), the findings its facts call
for, and its summary line, the standard library alone, so the command resolves every option before it
starts an environment that holds an integration. The checks are general, no shop's: a shop's own limits
are compared with the measurements every result carries.

Every process module has:

- ``OPTIONS``: its own options and their defaults (``None``: not given, measured or the rules' default);
- ``RULES``: its one table of rules, a ``rules.RuleSet``;
- ``MEASURED_FROM``: ``("brep", "mesh")``, the sources it measures (a mesh-only figure says so);
- ``validate(resolved, document_type)``: ``ArgumentRefused`` naming the fix for a value out of range (its
  kind -- a count an ``int``, a flag a ``bool``, a length finite -- already held by ``manufacturing.options``:
  ``_common.require_*``);
- ``context(report, resolved)``: what its rules read beside the report (the material's class, the
  measured thickness, the technology);
- ``findings(report, resolved, candidates)``: the findings its facts call for, verdicts apart;
- ``summary(report, resolved, candidates)``: one line of what was measured.

**Stopping a check.** A check the engine runs can be asked to stop (its worker's ``cancel``): the request
only sets a flag (``stop``), and the measurement stops at its next ``checkpoint`` -- between parts, families,
faces and ray batches, each in the integration's own Python loops -- raising ``Cancelled`` from its own
frame, so nothing is interrupted halfway through a kernel call or while it holds a lock. A stop asked
during one kernel call (an exact intersection, a face's mesh) takes effect when that call returns. A check
in a process no one stops (the caller's own) never stops.
"""

from __future__ import annotations

import importlib
import threading
from types import ModuleType
from typing import Any

from cad._internal.refused import ArgumentRefused

__all__ = ["COMMON", "PROCESSES", "Cancelled", "Unmeasured", "checkpoint", "module", "stop"]

#: The processes a check measures for, in the order the help lists them.
PROCESSES = ("cnc", "sheet", "molding", "printing")
#: The options every process takes, and their defaults. ``units`` is an STL's alone (the others declare
#: theirs).
COMMON: dict[str, Any] = {"material": None, "units": "mm"}


class Unmeasured(Exception):
    """A source the check could not measure at all: its finding's code and words."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Cancelled(BaseException):
    """A check asked to stop (``stop``), raised at its next ``checkpoint``: a ``BaseException``, so no
    family's ``except Exception`` takes it for a measurement that failed."""


_STOPPING = threading.Event()


def stop(asked: bool = True) -> None:
    """The check running in this process asked to stop at its next ``checkpoint`` (``asked``), or let run
    (``False``: a check starting clears what an earlier one was asked)."""
    if asked:
        _STOPPING.set()
    else:
        _STOPPING.clear()


def checkpoint() -> None:
    """``Cancelled`` when the check running here was asked to stop (``stop``); else nothing, at once."""
    if _STOPPING.is_set():
        raise Cancelled


def module(process: str) -> ModuleType:
    """The process's module (``cad._internal.dfm.<process>``)."""
    if process not in PROCESSES:
        raise ArgumentRefused(f"--process is {', '.join(PROCESSES[:-1])} or {PROCESSES[-1]}, not {process!r}")
    return importlib.import_module(f"{__name__}.{process}")
