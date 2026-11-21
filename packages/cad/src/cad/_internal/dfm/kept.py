"""What a manufacturing check's measurement depends on, said apart from the check that asked it: the options it
reads.

**The options it reads.** A process's options are of two kinds: those its measurement reads, which change the
report (CNC's tools decide which corners a tool reaches, sheet's K-factor where a bend's flat pattern ends), and
those its rules alone read, which change only the verdict (a material's limits, a sheet's size, a mold's
cavities). Each process's module declares the first beside its ``OPTIONS`` (``MEASURES``), and the integration's
``measure(document, options, candidates)`` is handed those alone (``measuring``), as a ``Measuring``: a dict of
the declared names that refuses any other (``KeyError``) and keeps each such name (``undeclared``), so a read the
module does not declare fails the check that made it even where the family that read it caught the refusal
(``cad.build123d._dfm_check``). So the report of one document is a function of these options alone, and the same
report stands for every check that resolves them alike. The standard library alone.
"""

from __future__ import annotations

from typing import Any

from cad._internal import dfm

__all__ = ["Measuring", "measuring"]


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
