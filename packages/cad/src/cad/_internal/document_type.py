"""``DocumentType``: what ``cad.<document_type>`` is.

Each document type's package (``cad/step/``, ``cad/urdf/``, ...) is an instance of this class, bound to
its entry in the registry (``cad.registry``) as its last line runs (``bind``). So ``from cad import
step`` is one object that is

* the type's decorator, where it has one: ``@step("out.step")`` declares a model's file (bare ``@step``,
  ``<name>.step`` beside the script), and ``@model`` the model's ``.xbf``;
* its reader, where it has one: ``step.read(path)``;
* its operations, one to one with the ``cad`` command's (``cad step export``): ``.export`` and
  ``.snapshot``, shared by every type that has them, ``.inspect``, and those named for what they do
  (a 3D type's ``.dfm``, the manufacturing check, ``cad._internal.manufacturing``; a B-rep type's ``.solve``,
  the stress study, ``cad._internal.fea.operation``, and ``.ranges``, its mechanism's joint stops,
  ``cad._internal.ranges``; a board's ``.drc``, a
  schematic's ``.erc``, a robot description's ``.validate``, each the type's own function), each where
  the type implements it;
* the vocabulary its own standard defines, where that takes no third-party objects.

Everything loads on first use: ``import cad`` imports no CAD kernel. A source of another type is
refused by name before anything runs: a file of another type (``cad.stl.export("part.glb", ...)``: that's
a glb's), a model's handle or document id given to a file's type (that's ``cad.model``'s), and a file
given to ``cad.model`` but the one a model is saved as, its ``.xbf``: ``cad.model`` is a model the engine
holds or that file, and its operations run on the file as the file it is. ``cad.xbf``, its earlier
spelling, is an alias of ``cad.model`` (``cad._internal.aliases``).
"""

from __future__ import annotations

import os
import sys
import types
from pkgutil import resolve_name as _resolve
from typing import Any

__all__ = ["DocumentType", "ModelType", "bind", "is_file", "refuse_other"]

# An operation a type does not implement, read as one that needs no integration.
_NONE = types.SimpleNamespace(integration=None, family=None)
# A type's reader: the function that reads a file of it into a model. ``model``'s reads the .xbf a model is
# saved as.
_READERS = {"step": "cad.engine.model.read_step", "model": "cad.engine.model.read_xbf",
            "stl": "cad.engine.reader.read_mesh"}


class DocumentType(types.ModuleType):
    """A document type: its decorator, its reader and its operations, from its registry entry."""

    @property
    def entry(self) -> Any:
        """The type's row of the registry (``cad.registry.DOCUMENT_TYPES``)."""
        from cad.registry import DOCUMENT_TYPES

        return DOCUMENT_TYPES[self.__name__.rpartition(".")[2]]

    def __call__(self, out: Any = None, *, name: str | None = None, tolerance: float | None = None,
                 angle: float | None = None) -> Any:
        """``@<type>("out.<ext>", name=...)`` (or ``@<type>(out="out.<ext>")``, the decorator's 0.10 signature):
        declare the file a model writes, of this type; with no path (``@<type>``, ``@<type>()``), ``<name>.<ext>``
        beside the script, the model's ``name=`` or its function's."""
        entry = self.entry
        if not entry.decorator:
            how = (f"; a file of it is changed in place with `with cad.{entry.id}.edit(path) as {entry.edit.noun}:`"
                   if entry.edit is not None else "")
            raise TypeError(f"cad.{entry.id} has no decorator: a {entry.title} is authored, not made by a model"
                            f"{how} (its operations: {', '.join(entry.operation_names)})")
        from cad.engine import model

        # A GLB's, an STL's or a 3MF's own mesh tolerance and angle go to the engine's decorator, which alone
        # takes them.
        return getattr(model, entry.id)(out, name=name, **({} if tolerance is None else {"tolerance": tolerance}),
                                        **({} if angle is None else {"angle": angle}))

    def __getattr__(self, name: str) -> Any:
        entry = self.entry
        if name == "read" and entry.id in _READERS:
            value = _resolve(_READERS[entry.id])
            self.__dict__[name] = value  # one object, every lookup: cad.read_step is cad.step.read
            return value
        if name in ("export", "snapshot", "inspect") and name in entry.operation_names:
            value = _operation(entry.id, name)
            self.__dict__[name] = value
            return value
        if name == "dfm" and (entry.operation("dfm") or _NONE).family == "manufacturing":
            # The manufacturing check every 3D type shares (``cad._internal.manufacturing``).
            from cad._internal.manufacturing import dfm_for

            value = dfm_for(entry.id)
            self.__dict__[name] = value
            return value
        if name == "interference" and name in entry.operation_names:
            # The interference check every B-rep type shares (``cad._internal.interference``).
            from cad._internal.interference import interference_for

            value = interference_for(entry.id)
            self.__dict__[name] = value
            return value
        if name == "solve" and (entry.operation("solve") or _NONE).integration == "calculix":
            # The stress study every B-rep type shares (``cad._internal.fea.operation``).
            from cad._internal.fea.operation import solve_for

            value = solve_for(entry.id)
            self.__dict__[name] = value
            return value
        if name == "ranges" and "ranges" in entry.operation_names:
            # The joint stops every type with a mechanism shares (``cad._internal.ranges``).
            from cad._internal.ranges import ranges_for

            value = ranges_for(entry.id)
            self.__dict__[name] = value
            return value
        if name.startswith("__"):
            raise AttributeError(name)
        from cad._internal.aliases import lookup

        try:
            return lookup(self.__name__, name)
        except AttributeError:
            pass
        has = [*(["read"] if entry.reader else []), *entry.operation_names, *self._declarations]
        raise AttributeError(f"cad.{entry.id} has no {name!r}; it has {', '.join(has)}")

    #: What a script declares with the type beside its decorator, by name: none but the model's (``ModelType``).
    _declarations: tuple[str, ...] = ()

    def __dir__(self) -> list[str]:
        entry = self.entry
        names = {*super().__dir__(), *entry.operation_names, *(["read"] if entry.reader else []), *self._declarations}
        return sorted(name for name in names if not name.startswith("_") or name.startswith("__"))

    def __repr__(self) -> str:
        entry = self.entry
        return f"<document type {entry.id!r}: {'held in memory, or ' if entry.held else ''}{', '.join(entry.extensions)}>"

def refuse_other(document_type: str, source: Any) -> str:
    """``document_type``, for an operation of it given ``source``, after refusing a source of any other type by
    name before anything runs: a file of another type (``cad.stl.export("part.glb")`` is a glb's: use cad.glb), a
    model's handle or document id given to a file's type (use cad.model), any other file given to ``cad.model``
    than its ``.xbf``. None (no source: a snapshot's job names its own) passes."""
    if source is None:
        return document_type
    from cad.registry import DOCUMENT_TYPES, type_of

    entry = DOCUMENT_TYPES[document_type]
    if isinstance(source, (str, os.PathLike)):
        text = os.fspath(source)
        from cad.engine.addresses import parts
        from cad.engine.ids import is_id

        named = parts(text)[0]  # a FILE#REF's file, a path that holds a '#' itself whole
        if is_id(named):
            if not entry.held:
                raise ValueError(f"{text} is a model's document id, not a {entry.suffix} file: use cad.model")
            return entry.id
        found = type_of(named)
        if found is not None and found.id != entry.id:
            raise ValueError(f"{text} is a {found.id}, not a {entry.id}: use cad.{found.id}")
        if found is None and entry.held:
            raise ValueError(f"cad.model takes a model's handle, its document id (cad run SCRIPT.py prints it) or "
                             f"an {entry.suffix} file, not {text!r}")
        return entry.id
    if not entry.held:
        raise ValueError(f"cad.{entry.id} takes a {entry.suffix} file; {_what(source)} is a model's: use cad.model")
    return entry.id


def is_file(source: Any) -> bool:
    """Whether ``source`` names a file (a path, a ``FILE#REF``'s file), not a model the engine holds (its handle,
    its document id): a model's operation given its ``.xbf`` reads the file as the file it is."""
    if not isinstance(source, (str, os.PathLike)):
        return False
    from cad.engine.addresses import parts
    from cad.engine.ids import is_id

    return not is_id(parts(os.fspath(source))[0])


def _what(source: Any) -> str:
    """A model's source as a person names it: the handle of a document, a model by its name."""
    name = getattr(source, "name", None) or getattr(source, "id", None)
    return f"{type(source).__name__} {name!r}" if name else type(source).__name__


class ModelType(DocumentType):
    """``cad.model``: the one type a document of which the engine also holds by its id, whose decorator is the
    engine's model itself, and whose script declares its parameters with it (``model.param``, ``cad.engine.parameters.param``: the standard
    library alone, so ``import cad`` stays kernel-free)."""

    _declarations = ("param",)

    def __getattr__(self, name: str) -> Any:
        if name == "param":
            # The function itself, never a wrapper: it reads the frame that calls it (a module's top level).
            from cad.engine.parameters import param

            self.__dict__[name] = param
            return param
        return super().__getattr__(name)

    def __call__(self, target: Any = None, /, *, name: str | None = None, out: Any = None,  # type: ignore[override]
                 animations: Any = None) -> Any:
        """``@model``, ``@model(name=...)`` or ``@model("XBF/arm.xbf")``: declare a model and the ``.xbf`` each
        run saves it as, at its path relative to the script, else ``<name>.xbf`` beside it; ``model(shape,
        name=...)``: hand a shape over as a named model (``cad.engine.model.model``)."""
        from cad.engine import model

        return model.model(target, name=name, out=out, animations=animations)


def _operation(document_type: str, name: str) -> Any:
    """``cad.<document_type>.<name>``: the engine's operation of that name (``cad.engine.api``), which takes any
    source, for a source of this type alone (``refuse_other``). An export of a mesh to the other mesh kinds takes
    no ``tolerance``, ``angle`` or ``zero``: only a document is meshed or described as a robot."""
    from cad.engine import api
    from cad.registry import DOCUMENT_TYPES

    entry = DOCUMENT_TYPES[document_type]
    verb = getattr(api, name)
    meshed = name == "export" and entry.view == "document"

    if name == "export" and not meshed:
        def operation(source: Any, *destinations: Any, **options: Any) -> Any:
            for option in ("tolerance", "angle", "zero"):  # a document's alone: a mesh is meshed by none, nor described
                if option in options:
                    raise TypeError(f"cad.{document_type}.export() got an unexpected keyword argument '{option}'")
            refuse_other(document_type, source)
            return verb(source, *destinations, **options)
    else:
        def operation(source: Any = None, *args: Any, **options: Any) -> Any:
            refuse_other(document_type, source)
            return verb(source, *args, **options)

    operation.__name__ = operation.__qualname__ = name
    operation.__module__ = f"cad.{document_type}"
    # Its signature is the verb's, as ``help()`` and the library's reference say it: a mesh's export without
    # the options it refuses.
    import inspect

    signature = inspect.signature(verb)
    if name == "export" and not meshed:
        signature = signature.replace(parameters=[parameter for parameter in signature.parameters.values()
                                                  if parameter.name not in ("tolerance", "angle", "zero")])
    operation.__signature__ = signature  # type: ignore[attr-defined]
    # The verb's docstring without its indentation, which Python strips by itself only from 3.13: the same words on
    # every Python the library runs on.
    described = inspect.cleandoc(verb.__doc__ or "")
    operation.__doc__ = f"cad.{document_type}.{name}: {entry.operation(name).summary}.\n\n{described}"
    return operation


def bind(module_name: str) -> None:
    """Make the module ``module_name`` (a type's package) a ``DocumentType`` (``cad.model`` a ``ModelType``)."""
    sys.modules[module_name].__class__ = ModelType if module_name.rpartition(".")[2] == "model" else DocumentType
