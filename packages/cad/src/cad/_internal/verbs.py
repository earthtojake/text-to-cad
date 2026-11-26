"""The library's verbs: ``cad.export``, ``cad.inspect``, ``cad.snapshot``, ``cad.dfm`` and ``cad.fea``, one to one
with the ``cad`` command's (``cad export SRC DST``, ``cad inspect FILE``, ...), and ``cad.save``, a shape a program
holds saved as a model's document, its ``.xbf``.

Each takes any source -- a file, its type by its suffix (``cad.registry.type_of``); the handle a model's call
returns, an ``xbf``'s (and its document id, as the engine names it); and, for ``export``, a shape -- and does what that type does for it
(``cad.registry.VERBS``, ``operation_for``): a source whose type lacks the verb is refused in one line naming the
types that have it, before anything runs. ``cad.inspect`` is a robot description's conformance check too, and with
``interference=True`` or ``ranges=True`` a B-rep's interference check or its joint stops (``cad.registry.MODES``).

The document types' operations (``cad.xbf.export``, ``cad.step.dfm``, ``cad.urdf.validate``, ...) are aliases of
these (``per_type``): the same work, for a source of that type alone, each saying once that it is deprecated and
which verb does it now (``cad._internal.aliases.spelled``: the one switch). Each keeps its type's signature and
words, which the ``cad`` command's parsers are made from. KiCad's own checks are the kicad integration's,
``cad.kicad.drc`` and ``cad.kicad.erc``; ``cad.kicad_pcb.drc`` and ``cad.kicad_sch.erc`` are their aliases, built
here too.

Kernel-free: a verb imports what it runs when it runs.
"""

from __future__ import annotations

import functools
import inspect as _inspect
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["dfm", "export", "fea", "inspect", "operation", "per_type", "save", "snapshot", "source_type"]

#: The operations a type had that are another's now, by type: KiCad's checks are the kicad integration's.
FORMER: dict[str, dict[str, tuple[str, str]]] = {"kicad_pcb": {"drc": ("cad.kicad", "drc")},
                                                  "kicad_sch": {"erc": ("cad.kicad", "erc")}}
# KiCad's checks, by the type whose file each takes: what ``cad.dfm`` of a KiCad file sends a caller to.
_KICAD_CHECKS = {"kicad_pcb": "cad.kicad.drc", "kicad_sch": "cad.kicad.erc"}
# A shape's files, by suffix: what ``cad.export`` of a shape writes (an .xbf hands it over as a model).
_SHAPE_KINDS = {".step": "step", ".stp": "step", ".glb": "glb", ".stl": "stl", ".3mf": "threemf", ".dxf": "dxf"}
_MESHED = ("glb", "stl", "threemf")

_MADE: dict[tuple[str, str], Callable[..., Any]] = {}


# --- what a source is --------------------------------------------------------------------------------------

def _held(source: Any) -> bool:
    """Whether ``source`` is a model the engine holds by its handle: the handle a model's call returns
    (``cad.engine.api.Document``) or a model itself (``cad.engine.model.Model``), told without importing either."""
    kind = type(source)
    return (kind.__module__, kind.__name__) in (("cad.engine.api", "Document"), ("cad.engine.model", "Model"))


def _named(source: Any) -> str:
    if isinstance(source, (str, os.PathLike)):
        return os.fspath(source)
    name = getattr(source, "name", None) or getattr(source, "id", None)
    return f"{type(source).__name__} {name!r}" if name else type(source).__name__


def _takes(verb: str, mode: str | None = None) -> str:
    """What ``cad.<verb>`` takes, in words: the types that have it, each by its files."""
    from cad.registry import DOCUMENT_TYPES, types_for

    found = types_for(verb, mode)
    files = [suffix for name in found for suffix in DOCUMENT_TYPES[name].extensions]
    held = "a model's handle, or " if "xbf" in found else ""
    return f"{held}a {', '.join(files[:-1])} or {files[-1]} file" if len(files) > 1 else f"{held}a {files[0]} file"


def article(word: str) -> str:
    """``word`` (a type's id) with its article as it is said: an xbf, an stl, an srdf; a step."""
    return f"{'an' if word in ('xbf', 'stl', 'srdf') else 'a'} {word}"


def _lacks(verb: str, document_type: str, source: Any, mode: str | None = None) -> ValueError:
    """The one line that refuses a source whose type has no ``verb`` (with ``mode``, ``inspect``'s check of that
    name): naming the types that have it."""
    from cad.registry import types_for

    if verb == "dfm" and document_type in _KICAD_CHECKS:
        return ValueError(f"{_named(source)} is {article(document_type)}: cad.dfm checks that a part can be made; "
                          f"KiCad's own check of it is {_KICAD_CHECKS[document_type]}")
    said = f"inspect with {mode}=True" if mode else verb
    return ValueError(f"{_named(source)} is {article(document_type)}, which has no {said}: cad.{verb}"
                      f"{f'({mode}=True)' if mode else ''} takes {', '.join(types_for(verb, mode))}")


def source_type(source: Any, verb: str) -> str | None:
    """The document type of ``source`` as ``cad.<verb>`` reads it: a file's by its suffix (a ``FILE#REF``'s file),
    a model's document id or handle ``xbf``; None for anything else -- a shape, which ``export`` alone takes. A
    model's script, and a file of no type, are refused by name (``ValueError``)."""
    if isinstance(source, (str, os.PathLike)):
        from cad.engine.addresses import parts
        from cad.engine.ids import is_id
        from cad.registry import type_of

        text = os.fspath(source)
        named = parts(text)[0]  # a FILE#REF's file, a path that holds a '#' itself whole
        if is_id(named):
            return "xbf"
        script = named.partition("::")[0]
        if script.lower().endswith(".py"):
            raise ValueError(f"{text} is a model's script, not a document: running it builds its models (cad run "
                             f"{script}), and cad.{verb} takes the handle a model's call returns or the .xbf it writes")
        found = type_of(named)
        if found is None:
            raise ValueError(f"cad.{verb} takes {_takes(verb)}, not {text!r}")
        return found.id
    if _held(source):
        return "xbf"
    return None


def _typed(source: Any, verb: str, mode: str | None = None) -> tuple[str, str]:
    """``(document_type, operation)``: what ``cad.<verb>`` (with ``mode``) runs of ``source``, after refusing a
    source of a type that has none, by name."""
    from cad.registry import operation_for

    document_type = source_type(source, verb)
    if document_type is None:
        raise TypeError(f"cad.{verb} takes {_takes(verb, mode)}, not {_named(source)}"
                        + ("; a shape is written to a file by cad.export(shape, 'part.xbf')" if verb != "export" else ""))
    name = operation_for(verb, document_type, mode)
    if name is None:
        raise _lacks(verb, document_type, source, mode)
    return document_type, name


def _given(function: Callable[..., Any], options: dict[str, Any], said: str) -> None:
    """``options`` refused by name where ``function`` takes none of that name: the closed set it takes said."""
    parameters = _inspect.signature(function).parameters
    if any(parameter.kind is parameter.VAR_KEYWORD for parameter in parameters.values()):
        return
    takes = [name for name, parameter in parameters.items() if parameter.kind is parameter.KEYWORD_ONLY
             and not name.startswith("_")]
    unknown = sorted(set(options) - set(takes))
    if unknown:
        raise TypeError(f"{said} takes {', '.join(takes) or 'no option'}; not {', '.join(unknown)}")


# --- the operation each type does, and its alias ------------------------------------------------------------

def operation(document_type: str, name: str) -> Callable[..., Any]:
    """The function that does operation ``name`` for a source of ``document_type``, its signature and words that
    type's (what ``cad <type> <operation>`` and the verbs' command lines are made from), a source of another type
    refused by name before anything runs. Made once a pair; it says nothing of being deprecated (``per_type``
    does)."""
    key = (document_type, name)
    if key not in _MADE:
        _MADE[key] = _make(document_type, name)
    return _MADE[key]


def _make(document_type: str, name: str) -> Callable[..., Any]:
    from cad.registry import DOCUMENT_TYPES

    entry = DOCUMENT_TYPES[document_type]
    if name in FORMER.get(document_type, {}):
        return _kicad_check(document_type, name)
    if name not in entry.operation_names:
        raise AttributeError(f"cad.{document_type} has no operation {name!r}")
    if document_type in ("kicad_pcb", "kicad_sch") and name in ("export", "inspect"):
        return _kicad(document_type, name)
    if name in ("export", "snapshot", "inspect"):
        return _engine(document_type, name)
    if name == "dfm":
        from cad._internal.manufacturing import dfm_for

        return dfm_for(document_type)
    if name == "interference":
        from cad._internal.interference import interference_for

        return interference_for(document_type)
    if name == "solve":
        from cad._internal.fea.operation import solve_for

        return solve_for(document_type)
    if name == "ranges":
        from cad._internal.ranges import ranges_for

        return ranges_for(document_type)
    if name == "validate":
        import importlib

        return importlib.import_module(f"cad.{document_type}._check").validate
    raise AttributeError(f"cad.{document_type} has no operation {name!r}")  # pragma: no cover - the closed set


def per_type(document_type: str, name: str) -> Callable[..., Any]:
    """``cad.<document_type>.<name>``: the alias of the verb that does it now (``aliases.OPERATION_VERBS``) -- its
    type's operation (``operation``), with its signature and words, saying once a process that it is deprecated
    where a program calls it (``aliases.spelled``)."""
    from cad._internal.aliases import ASSIGNED, OPERATION_VERBS, spelled

    done = operation(document_type, name)
    old, new = f"cad.{document_type}.{name}", OPERATION_VERBS[name]

    @functools.wraps(done, assigned=ASSIGNED)
    def alias(*args: Any, **kwargs: Any) -> Any:
        spelled(old, new)
        return done(*args, **kwargs)

    alias.__module__ = f"cad.{document_type}"
    return alias


def _engine(document_type: str, name: str) -> Callable[..., Any]:
    """The engine's operation of that name (``cad.engine.api``), which takes any source, for a source of this type
    alone (``refuse_other``). An export of a mesh to the other mesh kinds takes no ``tolerance``, ``angle`` or
    ``zero``: only a document is meshed or described as a robot."""
    from cad._internal.document_type import refuse_other
    from cad.engine import api
    from cad.registry import DOCUMENT_TYPES

    entry = DOCUMENT_TYPES[document_type]
    verb = getattr(api, name)
    meshed = name == "export" and entry.view == "document"

    if name == "export" and not meshed:
        def done(source: Any, *destinations: Any, **options: Any) -> Any:
            for option in ("tolerance", "angle", "zero"):  # a document's alone: a mesh is meshed by none, nor described
                if option in options:
                    raise TypeError(f"cad.export of {article(document_type)} takes no {option}: only a document's export is "
                                    "meshed or described as a robot")
            refuse_other(document_type, source)
            return verb(source, *destinations, **options)
    else:
        def done(source: Any = None, *args: Any, **options: Any) -> Any:
            refuse_other(document_type, source)
            return verb(source, *args, **options)

    done.__name__ = done.__qualname__ = name
    done.__module__ = f"cad.{document_type}"
    # Its signature is the verb's, as ``help()`` says it: a mesh's export without the options it refuses.
    signature = _inspect.signature(verb)
    if name == "export" and not meshed:
        signature = signature.replace(parameters=[parameter for parameter in signature.parameters.values()
                                                  if parameter.name not in ("tolerance", "angle", "zero")])
    done.__signature__ = signature  # type: ignore[attr-defined]
    # The verb's docstring without its indentation, which Python strips by itself only from 3.13: the same words on
    # every Python the library runs on.
    described = _inspect.cleandoc(verb.__doc__ or "")
    done.__doc__ = f"cad.{document_type}.{name}: {entry.operation(name).summary}.\n\n{described}"
    return done


def _kicad(document_type: str, name: str) -> Callable[..., Any]:
    """A KiCad file's export (KiCad's outputs of it, into a folder) or its inspection (the library's own reader)."""
    from cad.results import ExportResult

    board = document_type == "kicad_pcb"
    noun = "board" if board else "schematic"

    def refused(path: Any) -> Path:
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, path)
        return Path(path).expanduser()

    if name == "export":
        def export(path: Path | str, to: str, out: Path | str) -> ExportResult:
            source = refused(path)
            said: list[str] = []
            if board:
                from cad.kicad._export import export as run

                written = run(source, str(to), Path(out).expanduser(), warn=said.append)
            else:
                from cad.kicad._schematic import export as run

                written = run(source, str(to), Path(out).expanduser())
            return ExportResult(path=source.resolve(), to=str(to), written=tuple(written), warnings=tuple(said))

        export.__doc__ = (f"KiCad's ``to`` export of the saved {noun} into the folder ``out`` (``cad export "
                          f"{noun.upper()} DIR --to KIND``): ``to`` is one of "
                          + ("``gerbers``, ``drill``, ``pos``, ``bom``, ``step``, ``glb``, ``odb``, ``ipc2581``, "
                             "``pdf`` and ``dxf`` (``cad.kicad._export``'s table says what each writes)" if board else
                             "``pdf`` (every sheet), ``svg`` (one a sheet), ``netlist`` (the one a board imports) and "
                             "``bom``")
                          + ". The result says the files written and any warning. ``RuntimeError`` in KiCad's words "
                            "when it fails.")
        done: Callable[..., Any] = export
    elif board:
        def inspect(path: Path | str) -> dict:
            """What the board at ``path`` holds, as plain data: ``file``, ``format``, ``thickness``, ``size``,
            ``layers``, ``parts``, ``nets`` and ``counts`` (``cad inspect BOARD``)."""
            from cad.engine.formats.kicad.summary import inspect_board

            return inspect_board(refused(path))

        done = inspect
    else:
        def inspect(path: Path | str, ref: str | None = None) -> dict:  # type: ignore[misc]
            """What the schematic at ``path`` holds, as plain data: ``file``, ``root``, ``format``, ``sheets``,
            ``parts``, ``nets`` and ``counts``; with ``ref``, ``resolved``: what that reference names (``cad inspect
            SCHEMATIC [REF]``)."""
            from cad.engine.formats.kicad.schematic_summary import inspect_schematic

            return inspect_schematic(refused(path), ref)

        done = inspect
    done.__module__ = f"cad.{document_type}"
    return done


def _kicad_check(document_type: str, name: str) -> Callable[..., Any]:
    """``cad.kicad_pcb.drc``, ``cad.kicad_sch.erc``: KiCad's check of a file of this type, the kicad integration's
    (``cad.kicad.drc``, ``cad.kicad.erc``), for a file of this type alone."""
    import importlib

    from cad._internal.aliases import ASSIGNED

    module, attribute = FORMER[document_type][name]
    check = getattr(importlib.import_module(module), attribute)

    @functools.wraps(check, assigned=ASSIGNED)
    def done(path: Any) -> Any:
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, path)
        return check(path)

    done.__module__ = f"cad.{document_type}"
    return done


# --- the verbs ------------------------------------------------------------------------------------------------

def export(source: Any, destination: Any = None, *, to: str | None = None, tolerance: float | None = None,
           angle: float | None = None, zero: str | None = None, **options: Any) -> Any:
    """Write ``source`` to the one file ``destination``, its format by its suffix, as ``cad export SRC DST`` does.

    ``source`` is a file (an ``.xbf``, a STEP, a mesh: ``.glb``, ``.stl``, ``.3mf``; a KiCad board or schematic), the
    handle a model's call returns (the document the engine holds, never built), or a shape a program holds (a
    build123d shape). A document writes a ``.step``, ``.glb``, ``.stl``, ``.3mf``, ``.dxf`` (of a
    planar one), ``.xml`` (an MJCF, its meshes in ``assets/`` beside it), ``.urdf`` (its meshes in ``meshes/``
    beside it) or a copy of itself, an ``.xbf``, relative to the working folder; a mesh writes the other mesh kinds;
    a KiCad file writes KiCad's outputs into the folder ``destination``, ``to`` naming which (a board's
    ``gerbers``, ``drill``, ``pos``, ``bom``, ``step``, ``glb``, ``odb``, ``ipc2581``, ``pdf`` or ``dxf``; a
    schematic's ``pdf``, ``svg``, ``netlist`` or ``bom``). A shape writes a ``.step``, ``.glb``, ``.stl``, ``.3mf``
    or ``.dxf`` now, in this process, relative to the calling script's folder; its model's document, an ``.xbf``,
    is ``cad.save``'s.

    ``tolerance`` (mm) and ``angle`` (degrees) mesh a document's or a shape's ``.glb``, ``.stl`` or ``.3mf`` finer;
    ``zero`` takes a document's MJCF or URDF at a mechanism state. The engine's own options (``log``,
    ``progress``, ``daemon``) pass on to it. Returns what was written: a document's or a mesh's rows
    (``cad.engine.api.Written``), a KiCad file's ``ExportResult``, a shape's file's path. A source with no
    destination, and an option the source does not take, are refused by name.
    """
    if destination is None:
        raise TypeError("cad.export(source, destination): give the one file to write, its format by its suffix "
                        "(part.step, part.glb, ...)")
    if isinstance(destination, (list, tuple, set)):
        raise TypeError("cad.export writes one file: call it once for each destination")
    if source_type(source, "export") is None:
        given = [name for name, value in (("to", to), ("zero", zero)) if value is not None] + sorted(options)
        if given:
            raise TypeError(f"cad.export of a shape takes tolerance and angle; not {', '.join(given)}")
        return _shape(source, destination, tolerance=tolerance, angle=angle, frame=sys._getframe(1))
    document_type, _ = _typed(source, "export")
    if document_type in ("kicad_pcb", "kicad_sch"):
        if tolerance is not None or angle is not None or zero is not None or options:
            raise TypeError(f"cad.export of a {document_type} takes to= alone: KiCad writes its outputs")
        if to is None:
            from cad.kicad._export import EXPORTS as BOARD
            from cad.kicad._schematic import EXPORTS as SCHEMATIC

            kinds = BOARD if document_type == "kicad_pcb" else SCHEMATIC
            raise TypeError(f"cad.export of a {document_type} writes KiCad's outputs into the folder destination: give "
                            f"to=, one of {', '.join(kinds)}")
        return operation(document_type, "export")(source, to, destination)
    if to is not None:
        raise TypeError("cad.export takes to= of a KiCad board or schematic alone; another source's format is its "
                        "destination's suffix")
    given = {name: value for name, value in (("tolerance", tolerance), ("angle", angle), ("zero", zero))
             if value is not None}
    return operation(document_type, "export")(source, destination, **given, **options)


def _shape(shape: Any, destination: Any, *, tolerance: float | None, angle: float | None, frame: Any) -> Any:
    """``cad.export(shape, DST)``: a file of a shape, written now (``api.write_shape``, as ``step(shape, path)``
    wrote one); its model's ``.xbf`` is ``save``'s."""
    from cad.engine import api

    if not isinstance(destination, (str, os.PathLike)) or not os.fspath(destination):
        raise TypeError("cad.export(shape, destination) takes the file's path")
    suffix = Path(os.fspath(destination)).suffix.lower()
    if suffix == ".xbf":
        raise ValueError(f"cad.export writes a shape's other files; its model's document, "
                         f"{os.fspath(destination)!r}, is cad.save(shape, {os.fspath(destination)!r})")
    kind = _SHAPE_KINDS.get(suffix)
    if kind is None:
        raise ValueError(f"cad.export writes a shape to a .step, a .glb, an .stl, a .3mf or a .dxf, not "
                         f"{os.fspath(destination)!r}: save it as a model first (cad.save) for anything else")
    if kind not in _MESHED and (tolerance is not None or angle is not None):
        raise TypeError(f"cad.export of a shape to a {suffix} takes no tolerance or angle: only a .glb, an .stl and a "
                        ".3mf are meshed")
    return api.write_shape(shape, kind, destination, None, frame, tolerance, angle)


def save(shape: Any, path: Any = None, *, animations: Any = None) -> Any:
    """Save a shape a program holds as a model's document, its ``.xbf`` at ``path`` (relative to the calling
    script's folder, or the working folder where there is none): handed to the engine, which names the model for
    the file, records the calling script as its build closure, writes the ``.xbf`` (only where it differs or is
    missing) and serves its page. ``animations``: its clips, ``animation()`` builders on the shape or a part of it.
    Returns the model's handle, which every verb takes. A file of another kind is ``cad.export``'s; a model's handle
    or a file is its document already (``cad.export(handle, "copy.xbf")`` writes a copy)."""
    if path is None:
        raise TypeError("cad.save(shape, path): give the model's .xbf, the file it is saved as (part.xbf)")
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        raise TypeError("cad.save(shape, path) takes the .xbf's path")
    if Path(os.fspath(path)).suffix.lower() != ".xbf":
        raise ValueError(f"cad.save writes a model's .xbf, not {os.fspath(path)!r}: a shape's other files are "
                         f"cad.export(shape, {os.fspath(path)!r})")
    if isinstance(shape, (str, os.PathLike)) or _held(shape):
        raise TypeError(f"cad.save takes a shape a program holds, not {_named(shape)}: a model's document is its .xbf "
                        "already, and cad.export(source, 'copy.xbf') writes a copy")
    from cad.engine import api

    return api.hand_over(shape, None, animations=animations, frame=sys._getframe(1), out=path)


def inspect(source: Any, ref: str | None = None, *, query: str | None = None, interference: bool = False,
            ranges: bool = False, **options: Any) -> Any:
    """What ``source`` holds, as ``cad inspect FILE [REF]`` says it: a model's document (its handle), an
    ``.xbf``, a STEP or a GLB through the engine (``query``: ``summary``, ``structure``, ``closure``, ``geometry``
    or ``build``; with ``ref``, what one element or part is and what made it); a KiCad board's or schematic's
    contents (a schematic's ``ref`` too); a URDF's or an SRDF's conformance check, a ``CheckResult`` (``strict``,
    ``packages`` for a URDF, ``urdf`` for an SRDF, ``verbose``).

    ``interference=True``: a model's, an ``.xbf``'s or a STEP's interference check, which parts share volume
    (``poses``, ``fits``, ``min_volume``). ``ranges=True``: its joint stops, found from its geometry (``step``,
    ``clearance``, ``joint``, ``verbose``). Each a ``CheckResult``. An option the source's inspection does not take is
    refused by name, as is a source whose type has none, naming the types that have it.
    """
    if interference and ranges:
        raise TypeError("cad.inspect() takes interference=True or ranges=True, not both")
    mode = "interference" if interference else "ranges" if ranges else None
    document_type, name = _typed(source, "inspect", mode)
    done = operation(document_type, name)
    said = f"cad.inspect() of {article(document_type)}" + (f" with {mode}=True" if mode else "")
    if name != "inspect":  # a check: interference, ranges, a robot description's conformance
        if ref is not None or query is not None:
            raise TypeError(f"{said} takes no ref or query: it answers a check's findings")
        _given(done, options, said)
        return done(source, **options)
    if document_type in ("kicad_pcb", "kicad_sch"):
        if query is not None or options:
            raise TypeError(f"{said} takes no query or options")
        if document_type == "kicad_pcb":
            if ref is not None:
                raise TypeError(f"{said} takes no ref: its contents are the answer")
            return done(source)
        return done(source, ref)
    _given(done, options, said)
    return done(source, ref, **({"query": query} if query is not None else {}), **options)


def snapshot(source: Any = None, out: Any = None, *, job: Any = None, folder: Any = None, display: Any = None,
             camera: Any = None, grid: bool = False, preview: bool = False, pose: Any = None, width: int | None = None,
             height: int | None = None, size_profile: str | None = None, annotation: Any = None,
             measurements: Any = None, **options: Any) -> Any:
    """Draw ``source`` into ``out`` (a ``.png``) as the viewer draws it, as ``cad snapshot SRC OUT.png`` does: any
    document a viewer opens -- a model's handle, an ``.xbf``, a STEP, a mesh, a DXF, a URDF or an SRDF, a KiCad
    board or schematic. ``job`` draws every picture a Quick Edit packet or a job names instead, each that names no
    path into ``folder``, ``source`` then drawn in place of each job's input. ``display``, ``camera``, ``grid``,
    ``preview``, ``pose``, ``width``, ``height``, ``size_profile``, ``annotation`` and ``measurements`` are the
    viewer's, as ``cad.engine.api.snapshot`` takes them; its own options (``progress``, ``daemon``) pass on. A
    ``Drawn``, or a list of them for a job."""
    given = {"job": job, "folder": folder, "display": display, "camera": camera, "grid": grid, "preview": preview,
             "pose": pose, "width": width, "height": height, "size_profile": size_profile, "annotation": annotation,
             "measurements": measurements, **options}
    if source is None:
        from cad.engine import api

        return api.snapshot(None, out, **given)
    document_type, _ = _typed(source, "snapshot")
    return operation(document_type, "snapshot")(source, out, **given)


def dfm(source: Any, **options: Any) -> Any:
    """Check a part can be made, as ``cad dfm FILE`` does: a model's handle, an ``.xbf`` or a STEP measured
    exactly, for ``process`` ``cnc``, ``sheet``, ``molding`` or ``printing`` (a model's or an ``.xbf``'s parts'
    declared one where none is given); a mesh (STL, 3MF, GLB) for ``printing``; a DXF as a sheet's cut file. The
    options are the process's (``material``, ``axes``, ``tools``, ``thickness``, ``technology``, ...: the type's own
    signature, its type's manufacturing check's), and ``strict`` fails a warning too. A ``CheckResult`` whose ``status`` is
    ``ok``, ``failed`` or ``not_checked``. A KiCad file's checks are KiCad's: ``cad.kicad.drc``, ``cad.kicad.erc``."""
    document_type, name = _typed(source, "dfm")
    return operation(document_type, name)(source, **options)


def fea(source: Any, *, study: Any = None, out: Any = None, occurrence: str | None = None, deck: bool = False,
        verbose: bool = False) -> Any:
    """A linear static stress study of a part or a bonded assembly, as ``cad fea FILE`` does: a model's handle,
    an ``.xbf`` or a STEP. With no ``study``, its setup, writing nothing: the parts, the pairs that touch and a part's
    faces by ref (``occurrence``); with ``study`` (a JSON file, inline JSON or a dict) and ``out`` (a folder), the
    solve, meshed by netgen and solved by CalculiX, its results written into ``out`` (``deck``, ``verbose``). A
    ``cad.results.FeaResult``."""
    document_type, name = _typed(source, "fea")
    return operation(document_type, name)(source, study=study, out=out, occurrence=occurrence, deck=deck,
                                          verbose=verbose)
