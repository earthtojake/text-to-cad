"""What the server attaches to the library's engine, as a module of it is imported and never sooner: the
engine imports nothing of the server's (its law 3), and a server process that uses no engine imports none
of it -- ``import cad_server.cli`` loads no ``cad.engine`` module (``engine_telemetry``'s law).

``when(name, then)`` calls ``then`` with the module ``name`` once it has run: now, where it is imported
already, else as it is -- by a ``sys.meta_path`` finder for those modules alone (``_Attach``), which finds
them where Python finds them, by the path finder (asked itself, never the rest of ``sys.meta_path``, so no
two finders hand one lookup back and forth), and runs each one's own loader, then what is attached to it
(``_Then``) -- a reload's too. Every other import passes it by at one lookup. What the server attaches: the
engine telemetry's observer to the engine's verbs (``engine_telemetry.install``), and its words where no
installation is registered to the engine's (``cad_server``: ``cad.engine.said.UNREGISTERED``).
"""

from __future__ import annotations

import sys
from typing import Any, Callable

# What is attached to a module as it runs, by its name (``when``).
_THEN: dict[str, list[Callable[[Any], None]]] = {}


def when(name: str, then: Callable[[Any], None]) -> None:
    """``then`` called with the module ``name``: now, where it is imported already, else once it has run
    (``_Attach``). Idempotent."""
    module = sys.modules.get(name)
    if module is not None:
        then(module)
        return
    waiting = _THEN.setdefault(name, [])
    if then not in waiting:
        waiting.append(then)
    if not any(isinstance(finder, _Attach) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Attach())


class _Attach:
    """A ``sys.meta_path`` finder for the modules something is attached to (``_THEN``) alone."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname not in _THEN:
            return None
        from importlib.machinery import PathFinder

        spec = PathFinder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
            spec.loader = _Then(spec.loader, fullname)
        return spec


class _Then:
    """A module's own loader, then what is attached to the module it ran."""

    def __init__(self, loader: Any, name: str) -> None:
        self._loader = loader
        self._name = name

    def __getattr__(self, name: str) -> Any:
        return getattr(self._loader, name)

    def create_module(self, spec: Any) -> Any:
        return self._loader.create_module(spec)

    def exec_module(self, module: Any) -> None:
        self._loader.exec_module(module)
        for then in list(_THEN.get(self._name, ())):
            then(module)
