"""``DocumentType``: what ``cad.<document_type>`` is.

Each document type's package (``cad/step/``, ``cad/urdf/``, ...) is an instance of this class, bound to
its entry in the registry (``cad.registry``) as its last line runs (``bind``). So ``from cad import
step`` is one object that is

* the type's decorator, where it has one: ``@step("out.step")`` declares a model's file;
* its reader, where it has one: ``step.read(path)``;
* its operations, one to one with the ``cad`` command's (``cad step export``): ``.export``,
  ``.snapshot``, ``.inspect`` and ``.check``, each where the type implements it;
* the vocabulary its own standard defines, where that takes no third-party objects.

Everything loads on first use: ``import cad`` imports no CAD kernel. A file of another type is
refused by name (``cad.stl.export("part.glb", ...)``: that's a glb).
"""

from __future__ import annotations

import os
import sys
import types
from typing import Any

__all__ = ["DocumentType", "bind"]

# A type's reader, by id: the function that reads a file of it into a model.
_READERS = {"step": "cad.engine.model.read_step", "xbf": "cad.engine.model.read_xbf",
            "stl": "cad.engine.reader.read_mesh"}


def _resolve(path: str) -> Any:
    import importlib

    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


class DocumentType(types.ModuleType):
    """A document type: its decorator, its reader and its operations, from its registry entry."""

    @property
    def entry(self) -> Any:
        """The type's row of the registry (``cad.registry.DOCUMENT_TYPES``)."""
        from cad.registry import DOCUMENT_TYPES

        return DOCUMENT_TYPES[self.__name__.rpartition(".")[2]]

    def __call__(self, out: Any = None, /, *, name: str | None = None) -> Any:
        """``@<type>("out.<ext>", name=...)``: declare the file a model writes, of this type."""
        entry = self.entry
        if not entry.decorator:
            raise TypeError(f"cad.{entry.id} has no decorator: a {entry.title} is authored, not made by a model "
                            f"(its operations: {', '.join(entry.operation_names)})")
        from cad.engine import model

        return getattr(model, entry.id)(out, name=name)

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
