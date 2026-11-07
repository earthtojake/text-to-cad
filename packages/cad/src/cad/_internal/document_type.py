"""``DocumentType``: what ``cad.<document_type>`` is.

Each document type's package (``cad/step/``, ``cad/urdf/``, ...) is an instance of this class, bound to
its entry in the registry (``cad.registry``) as its last line runs (``bind``). So ``from cad import
step`` is one object that is

* the type's decorator, where it has one: ``@step("out.step")`` declares a model's file, and ``@model``
  the model itself, with no file;
* its reader, where it has one: ``step.read(path)``;
* its operations, one to one with the ``cad`` command's (``cad step export``): ``.export`` and
  ``.snapshot``, shared by every type that has them, ``.inspect``, and those named for what they do
  (a 3D type's ``.dfm``, the manufacturing check, ``cad._internal.manufacturing``; a board's ``.drc``, a
  schematic's ``.erc``, a robot description's ``.validate``, each the type's own function), each where
  the type implements it;
* the vocabulary its own standard defines, where that takes no third-party objects.

Everything loads on first use: ``import cad`` imports no CAD kernel. A source of another type is
refused by name before anything runs: a file of another type (``cad.stl.export("part.glb", ...)``: that's
a glb's), a model's handle or document id given to a file's type (that's ``cad.model``'s), and a file
given to ``cad.model``.
"""

from __future__ import annotations

import os
import sys
import types
from pkgutil import resolve_name as _resolve
from typing import Any

__all__ = ["DocumentType", "ModelType", "bind", "refuse_other"]

# An operation a type does not implement, read as one that needs no integration.
_NONE = types.SimpleNamespace(integration=None, family=None)
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

    def __call__(self, out: Any, *, name: str | None = None, tolerance: float | None = None) -> Any:
        """``@<type>("out.<ext>", name=...)`` (or ``@<type>(out="out.<ext>")``, the decorator's 0.10 signature):
        declare the file a model writes, of this type."""
        entry = self.entry
        if not entry.decorator:
            how = (f"; a file of it is changed in place with `with cad.{entry.id}.edit(path) as {entry.edit.noun}:`"
                   if entry.edit is not None else "")
            raise TypeError(f"cad.{entry.id} has no decorator: a {entry.title} is authored, not made by a model"
                            f"{how} (its operations: {', '.join(entry.operation_names)})")
        from cad.engine import model

        # An STL's or a 3MF's own mesh tolerance goes to the engine's decorator, which alone takes it.
        return getattr(model, entry.id)(out, name=name, **({} if tolerance is None else {"tolerance": tolerance}))

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
        if name == "dfm" and (entry.operation("dfm") or _NONE).family == "manufacturing":
            # The manufacturing check every 3D type shares (``cad._internal.manufacturing``).
            from cad._internal.manufacturing import dfm_for

            value = dfm_for(entry.id)
            self.__dict__[name] = value
            return value
        if name.startswith("__"):
            raise AttributeError(name)
        from cad._internal.aliases import lookup

        try:
            return lookup(self.__name__, name)
        except AttributeError:
            pass
        has = [*(["read"] if entry.reader else []), *entry.operation_names]
        raise AttributeError(f"cad.{entry.id} has no {name!r}; it has {', '.join(has)}")

    def __dir__(self) -> list[str]:
        entry = self.entry
        names = {*super().__dir__(), *entry.operation_names, *(["read"] if entry.reader else [])}
        return sorted(name for name in names if not name.startswith("_") or name.startswith("__"))

    def __repr__(self) -> str:
        entry = self.entry
        return f"<document type {entry.id!r}: {', '.join(entry.extensions) or 'no file, held in memory'}>"

    def _own(self, source: Any) -> None:
        """Refuse a source of another type, naming it (``refuse_other``)."""
        refuse_other(self.entry.id, source)


def refuse_other(document_type: str, source: Any) -> None:
    """A source of another type than ``document_type``, refused by name before anything runs: a file of
    another type (``cad.stl.export("part.glb")`` is a glb's: use cad.glb), a model's handle or document id
    given to a file's type (``cad.model.export(<id>)``: use cad.model), a file given to ``cad.model``. None
    (no source: a snapshot's job names its own) passes."""
    if source is None:
        return
    from cad.registry import DOCUMENT_TYPES, type_of

    entry = DOCUMENT_TYPES[document_type]
    if isinstance(source, (str, os.PathLike)):
        text = os.fspath(source)
        from cad.engine.ids import is_id

        if is_id(str(text).partition("#")[0]):
            if entry.has_file:
                raise ValueError(f"{text} is a model's document id, not a {entry.suffix} file: use cad.model")
            return
        found = type_of(str(text).partition("#")[0])
        if found is not None and found.id != entry.id:
            raise ValueError(f"{text} is a {found.id}, not a {entry.id}: use cad.{found.id}")
        if found is None and not entry.has_file:
            raise ValueError(f"cad.model takes a model's handle or its document id (cad run SCRIPT.py prints it), "
                             f"not {text!r}")
        return
    if entry.has_file:
        raise ValueError(f"cad.{entry.id} takes a {entry.suffix} file; {_what(source)} is a model's: use cad.model")


def _what(source: Any) -> str:
    """A model's source as a person names it: the handle of a document, a model by its name."""
    name = getattr(source, "name", None) or getattr(source, "id", None)
    return f"{type(source).__name__} {name!r}" if name else type(source).__name__


class ModelType(DocumentType):
    """``cad.model``: the one type with no file, whose decorator is the engine's model itself."""

    def __call__(self, target: Any = None, /, *, name: str | None = None, animations: Any = None) -> Any:  # type: ignore[override]
        """``@model`` or ``@model(name=...)``: declare a model; ``model(shape, name=...)``: hand a shape over as
        a named model (``cad.engine.model.model``)."""
        from cad.engine import model

        return model.model(target, name=name, animations=animations)


def _operation(owner: DocumentType, name: str) -> Any:
    """``owner.<name>``: the engine's operation of that name (``cad.engine.api``), for a source of this type.
    An export of a mesh to the other mesh kinds takes no ``tolerance``: only a document is meshed by it."""
    from cad.engine import api

    verb = getattr(api, name)
    meshed = name == "export" and owner.entry.view == "document"

    if name == "export" and not meshed:
        def operation(source: Any, *destinations: Any, **options: Any) -> Any:
            if "tolerance" in options:
                raise TypeError(f"cad.{owner.entry.id}.export() got an unexpected keyword argument 'tolerance'")
            owner._own(source)
            return verb(source, *destinations, **options)
    else:
        def operation(source: Any = None, *args: Any, **options: Any) -> Any:
            owner._own(source)
            return verb(source, *args, **options)

    operation.__name__ = operation.__qualname__ = name
    operation.__module__ = owner.__name__
    operation.__doc__ = f"cad.{owner.entry.id}.{name}: {owner.entry.operation(name).summary}.\n\n{verb.__doc__ or ''}"
    return operation


def bind(module_name: str) -> None:
    """Make the module ``module_name`` (a type's package) a ``DocumentType`` (``cad.model`` a ``ModelType``)."""
    sys.modules[module_name].__class__ = ModelType if module_name.rpartition(".")[2] == "model" else DocumentType
