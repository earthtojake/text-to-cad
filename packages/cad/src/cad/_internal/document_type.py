"""``DocumentType``: what ``cad.<document_type>`` is.

Each document type's package (``cad/step/``, ``cad/urdf/``, ...) is an instance of this class, bound to
its entry in the registry (``cad.registry``) as its last line runs (``bind``). So ``from cad import
step`` is one object that is

* the type's decorator, where it has one: ``@step("out.step")`` declares a model's file (bare ``@step``,
  ``<name>.step`` beside the script), and ``@xbf`` the model's ``.xbf``;
* its reader, where it has one: ``step.read(path)``;
* the vocabulary its own standard defines, where that takes no third-party objects.

What is done to a document is a verb's, the library's and the command's alike: ``cad.export``, ``cad.inspect``,
``cad.snapshot``, ``cad.dfm`` and ``cad.fea`` (``cad._internal.verbs``), ``cad.save`` a shape's ``.xbf``. A
type's operations under its own name (``cad.step.export``, ``cad.stl.dfm``, ``cad.urdf.validate``,
``cad.kicad_pcb.drc``) are their earlier spellings, aliases of the verbs (``verbs.per_type``), as is a file
type's call given a shape (``step(shape, "crate.step")`` is ``cad.export``'s, ``xbf(shape, "crate.xbf")``
``cad.save``'s): each answers as before and says once that it is deprecated (``cad._internal.aliases``).

Everything loads on first use: ``import cad`` imports no CAD kernel. A source of another type is
refused by name before anything runs: a file of another type (``cad.stl.export("part.glb", ...)``: that's
a glb's), a model's handle or document id given to a file's type (that's ``cad.xbf``'s), and a file
given to ``cad.xbf`` but the one a model is saved as, its ``.xbf``: ``cad.xbf`` is a document the engine
holds or that file, and its operations run on the file as the file it is. ``cad.model``, its earlier spelling,
is an alias of ``cad.xbf`` (``cad._internal.aliases``).
"""

from __future__ import annotations

import os
import sys
import types
from pkgutil import resolve_name as _resolve
from typing import Any

__all__ = ["DocumentType", "XbfType", "bind", "is_file", "refuse_other"]

# A type's reader: the function that reads a file of it into a model. ``xbf``'s reads the .xbf a model is
# saved as.
_READERS = {"step": "cad.engine.model.read_step", "xbf": "cad.engine.model.read_xbf",
            "stl": "cad.engine.reader.read_mesh"}


class DocumentType(types.ModuleType):
    """A document type: its decorator, its reader and its operations, from its registry entry."""

    @property
    def entry(self) -> Any:
        """The type's row of the registry (``cad.registry.DOCUMENT_TYPES``)."""
        from cad.registry import DOCUMENT_TYPES

        return DOCUMENT_TYPES[self.__name__.rpartition(".")[2]]

    def __call__(self, target: Any = None, file: Any = None, /, *, out: Any = None, name: str | None = None,
                 tolerance: float | None = None, angle: float | None = None) -> Any:
        """``@<type>("out.<ext>", name=...)`` (or ``@<type>(out="out.<ext>")``, the decorator's 0.10 signature):
        declare the file a model writes, of this type, and nothing else; with no path (``@<type>``, ``@<type>()``),
        ``<name>.<ext>`` beside the script, the model's ``name=`` or its function's. Given a shape first
        (``<type>(shape, "out.<ext>")``), write that file of it now (``cad.engine.api.write_shape``)."""
        entry = self.entry
        if not entry.decorator:
            how = (f"; a file of it is changed in place with `with cad.{entry.id}.edit(path) as {entry.edit.noun}:`"
                   if entry.edit is not None else "")
            raise TypeError(f"cad.{entry.id} has no decorator: a {entry.title} is authored, not made by a model{how}")
        from cad.engine import model

        if model._given(target, file, out)[2] is not None:
            from cad._internal.aliases import spelled

            spelled(f"cad.{entry.id}(shape, ...)", f"cad.export(shape, 'part{entry.suffix}')")

        # A GLB's, an STL's or a 3MF's own mesh tolerance and angle go to the engine's decorator, which alone
        # takes them.
        return getattr(model, entry.id)(target, file, out=out, name=name,
                                        **({} if tolerance is None else {"tolerance": tolerance}),
                                        **({} if angle is None else {"angle": angle}))

    def __getattr__(self, name: str) -> Any:
        entry = self.entry
        if name == "read" and entry.id in _READERS:
            value = _resolve(_READERS[entry.id])
            self.__dict__[name] = value  # one object, every lookup: cad.read_step is cad.step.read
            return value
        from cad._internal.verbs import FORMER, per_type

        if name in entry.operation_names or name in FORMER.get(entry.id, {}):
            # An operation under the type's name: an alias of the verb that does it now, which says so once.
            value = per_type(entry.id, name)
            self.__dict__[name] = value
            return value
        if name.startswith("__"):
            raise AttributeError(name)
        from cad._internal.aliases import lookup

        try:
            return lookup(self.__name__, name)
        except AttributeError:
            pass
        has = [*([entry.id] if entry.decorator else []), *(["read"] if entry.reader else []),
               *(["edit"] if entry.edit is not None else []), *self._declarations]
        raise AttributeError(f"cad.{entry.id} has no {name!r}; it has {', '.join(has) or 'no names of its own'}, and "
                             f"cad.export, cad.inspect, cad.snapshot, cad.dfm and cad.fea take its files")

    #: What a script declares with the type beside its decorator, by name: none but the model's (``ModelType``).
    _declarations: tuple[str, ...] = ()

    def __dir__(self) -> list[str]:
        entry = self.entry
        names = {*super().__dir__(), *(["read"] if entry.reader else []), *self._declarations}
        return sorted(name for name in names if not name.startswith("_") or name.startswith("__"))

    def __repr__(self) -> str:
        entry = self.entry
        return f"<document type {entry.id!r}: {'held in memory, or ' if entry.held else ''}{', '.join(entry.extensions)}>"

def refuse_other(document_type: str, source: Any) -> str:
    """``document_type``, for an operation of it given ``source``, after refusing a source of any other type by
    name before anything runs: a file of another type (``cad.stl.export("part.glb")`` is a glb's: use cad.glb), a
    model's handle or document id given to a file's type (use cad.xbf), any other file given to ``cad.xbf``
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
                raise ValueError(f"{text} is a model's document id, not a {entry.suffix} file: the verbs (cad.export, "
                                 "cad.inspect, ...) take it as it is")
            return entry.id
        found = type_of(named)
        if found is not None and found.id != entry.id:
            raise ValueError(f"{text} is a {found.id}, not a {entry.id}: the verbs (cad.export, cad.inspect, ...) take "
                             "a file of any type")
        if found is None and entry.held:
            raise ValueError(f"cad.xbf takes a model's handle or the {entry.suffix} file a model is saved as, not "
                             f"{text!r}")
        return entry.id
    if not entry.held:
        raise ValueError(f"cad.{entry.id} takes a {entry.suffix} file; {_what(source)} is a model's: the verbs "
                         "(cad.export, cad.inspect, ...) take it as it is")
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


class XbfType(DocumentType):
    """``cad.xbf``: the document type of the ``.xbf`` a model is saved as, which the engine also holds by its id. Its
    decorator is the engine's model declaration itself, and its script declares its parameters with it (``xbf.param``,
    ``cad.engine.parameters.param``: the standard library alone, so ``import cad`` stays kernel-free). ``cad.model``,
    its earlier spelling, is a module alias of it (``cad._internal.aliases``)."""

    _declarations = ("param",)

    def __getattr__(self, name: str) -> Any:
        if name == "param":
            # The function itself, never a wrapper: it reads the frame that calls it (a module's top level).
            from cad.engine.parameters import param

            self.__dict__[name] = param
            return param
        return super().__getattr__(name)

    def __call__(self, target: Any = None, file: Any = None, /, *, out: Any = None,  # type: ignore[override]
                 name: str | None = None, animations: Any = None) -> Any:
        """``@xbf``, ``@xbf(name=...)`` or ``@xbf("XBF/arm.xbf")``: declare a model and the ``.xbf`` each
        run saves it as, at its path relative to the script, else ``<name>.xbf`` beside it
        (``cad.engine.model.model``). A shape a program holds is saved as a model by ``cad.save(shape,
        "plate.xbf")``."""
        from cad.engine import model

        if model._given(target, file, out)[2] is not None:
            from cad._internal.aliases import spelled

            spelled("cad.xbf(shape, ...)", "cad.save(shape, 'part.xbf')")
        return model.model(target, file, out=out, name=name, animations=animations)


def bind(module_name: str) -> None:
    """Make the module ``module_name`` (a type's package) a ``DocumentType`` (``cad.xbf`` an ``XbfType``)."""
    sys.modules[module_name].__class__ = XbfType if module_name.rpartition(".")[2] == "xbf" else DocumentType
