"""``DocumentType``: what ``cad.<document_type>`` is.

Each document type's package (``cad/step/``, ``cad/urdf/``, ...) is an instance of this class, bound to
its entry in the registry (``cad.registry``) as its last line runs (``bind``). So ``from cad import
step`` is one object that is

* the type's decorator, where it has one: ``@step("out.step")`` declares a model's file;
* its reader, where it has one: ``step.read(path)``;
* its operations, one to one with the ``cad`` command's (``cad step export``): ``.export``,
  ``.snapshot``, ``.inspect`` and ``.check``, each where the type implements it (a 3D type's ``check``
  is the manufacturing check, ``cad._internal.manufacturing``);
* the vocabulary its own standard defines, where that takes no third-party objects.

Everything loads on first use: ``import cad`` imports no CAD kernel. A file of another type is
refused by name (``cad.stl.export("part.glb", ...)``: that's a glb).
"""

from __future__ import annotations

import os
import sys
import types
from pkgutil import resolve_name as _resolve
from typing import Any

__all__ = ["DocumentType", "bind"]

# An operation a type does not implement, read as one that needs no integration.
_NONE = types.SimpleNamespace(integration=None)
# A type's reader, by id: the function that reads a file of it into a model.
_READERS = {"step": "cad.engine.model.read_step", "xbf": "cad.engine.model.read_xbf",
            "stl": "cad.engine.reader.read_mesh"}


class DocumentType(types.ModuleType):
    """A document type: its decorator, its reader and its operations, from its registry entry."""

    @property
    def entry(self) -> Any:
        """The type's row of the registry (``cad.registry.DOCUMENT_TYPES``)."""
        from cad.registry import DOCUMENT_TYPES

        return DOCUMENT_TYPES[self.__name__.rpartition(".")[2]]

    def __call__(self, out: Any, *, name: str | None = None) -> Any:
        """``@<type>("out.<ext>", name=...)`` (or ``@<type>(out="out.<ext>")``, the decorator's 0.10 signature):
        declare the file a model writes, of this type."""
        entry = self.entry
        if not entry.decorator:
            raise TypeError(f"cad.{entry.id} has no decorator: a {entry.title} is authored, not made by a model "
                            f"(its operations: {', '.join(entry.operation_names)})")
        # The engine's decorator, its path checked now, where a model is what the function is; else the
        # producer that declares what the decorator does (``cad.registry.declarer_for``), by its target.
        engine = None
        if any(not producer.declare for producer in _producers(entry.id)):
            from cad.engine import model

            engine = getattr(model, entry.id)(out, name=name)

        # A type whose own producer declares every target (``decorates`` None) checks its path now too.
        own = next((producer for producer in _producers(entry.id) if producer.declare and producer.decorates is None),
                   None)
        prepared = _resolve(own.declare)(entry.id, out, name) if own is not None else None

        def apply(target: Any) -> Any:
            from cad.registry import declarer_for, decorators_taking

            declarer = declarer_for(entry.id, target)
            if declarer is own and prepared is not None:
                return prepared(target)
            if declarer is not None:
                return _resolve(declarer.declare)(entry.id, out, name)(target)
            taking = decorators_taking(target)
            if taking:
                # A target only some producers declare for (a @kicad_pcb board script): never the engine's model.
                raise TypeError(f"@{entry.id} takes no {type(target).__name__}: one takes "
                                f"{', '.join('@' + document_type for document_type in taking)}")
            if engine is None:
                raise TypeError(f"@{entry.id} takes no {type(target).__name__}")
            scripts = _script_types()
            if scripts and _parameters(target):
                # A function of the open board under @<type>: the board script's decorator is missing, or below.
                raise TypeError(f"@{entry.id} over a function of parameters: a model takes none; a function of "
                                f"the open board is a board script, declared by "
                                f"{' or '.join('@' + kind + '(...)' for kind in scripts)} directly on it, "
                                f"with @{entry.id} above that")
            return engine(target)

        return apply

    def __getattr__(self, name: str) -> Any:
        entry = self.entry
        if name == "read" and entry.id in _READERS:
            value = _resolve(_READERS[entry.id])
            self.__dict__[name] = value  # one object, every lookup: cad.read_step is cad.step.read
            return value
        if name in ("export", "snapshot", "inspect") and name in entry.operation_names:
            value = _operation(self, name)
            self.__dict__[name] = value
            return value
        if name == "check" and (entry.operation("check") or _NONE).integration == "trimesh":
            # The manufacturing check every 3D type shares (``cad._internal.manufacturing``).
            from cad._internal.manufacturing import check_for

            value = check_for(entry.id)
            self.__dict__[name] = value
            return value
        if name.startswith("__"):
            raise AttributeError(name)
        from cad._internal.aliases import lookup

        try:
            return lookup(self.__name__, name)
        except AttributeError:
            pass
        has = [*(["read"] if entry.id in _READERS else []), *entry.operation_names]
        raise AttributeError(f"cad.{entry.id} has no {name!r}; it has {', '.join(has)}")

    def __dir__(self) -> list[str]:
        entry = self.entry
        names = {*super().__dir__(), *entry.operation_names, *(["read"] if entry.id in _READERS else [])}
        return sorted(name for name in names if not name.startswith("_") or name.startswith("__"))

    def __repr__(self) -> str:
        entry = self.entry
        return f"<document type {entry.id!r}: {', '.join(entry.extensions)}>"

    def _own(self, source: Any) -> None:
        """Refuse a file of another type, naming it: ``cad.stl.export("part.glb")`` is a glb's."""
        if not isinstance(source, (str, os.PathLike)):
            return  # a model, a handle or a document's id: the engine says what it holds
        from cad.registry import type_of

        found = type_of(source)
        entry = self.entry
        if found is not None and found.id != entry.id:
            raise ValueError(f"{os.fspath(source)} is a {found.id}, not a {entry.id}: use cad.{found.id}")


def _script_types() -> tuple[str, ...]:
    """The types whose own producer declares a function itself (a board script's ``kicad_pcb``)."""
    from cad.registry import _producers as every

    return tuple(dict.fromkeys(producer.document_type for producer in every()
                               if producer.declare and producer.decorates is None))


def _parameters(target: Any) -> bool:
    """Whether ``target`` is a function some of whose parameters have no default."""
    import inspect

    if not inspect.isfunction(target):
        return False
    return any(parameter.default is inspect.Parameter.empty
               and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
               for parameter in inspect.signature(target).parameters.values())


def _producers(document_type: str) -> tuple[Any, ...]:
    from cad.registry import producers_for

    return producers_for(document_type)


def _operation(owner: DocumentType, name: str) -> Any:
    """``owner.<name>``: the engine's operation of that name (``cad.engine.api``), for a source of this type."""
    from cad.engine import api

    verb = getattr(api, name)

    def operation(source: Any, *args: Any, **options: Any) -> Any:
        owner._own(source)
        return verb(source, *args, **options)

    operation.__name__ = operation.__qualname__ = name
    operation.__module__ = owner.__name__
    operation.__doc__ = f"cad.{owner.entry.id}.{name}: {owner.entry.operation(name).summary}.\n\n{verb.__doc__ or ''}"
    return operation


def bind(module_name: str) -> None:
    """Make the module ``module_name`` (a type's package) a ``DocumentType``."""
    sys.modules[module_name].__class__ = DocumentType
