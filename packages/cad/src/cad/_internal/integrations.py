"""cad's integrations as ``cad run`` reads them: what tells a program needs one, worked out from the registry.

The registry (``cad.registry.INTEGRATIONS``) is the one place each integration's modules, distributions and
extra are listed, and its document types say which of their functions need which integration. This module is the
view of it the server's ``cad run`` reads to work out a script's integrations from its imports (a static
scan, no code run), and a command's from its name (``kicad-cli`` is the kicad integration's), to add one a
resolution pulled in through another package, and to give a requirement its indexes; a program run with one missing says, in one line, which extra brings it (``missing``).

The standard library alone: the server's command and a model's process both read it, and neither loads
any integration to do so.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["INTEGRATIONS", "Integration", "alongside", "for_command", "for_distribution", "for_module", "for_name",
           "for_verb", "missing", "needs", "needs_call"]


@dataclass(frozen=True)
class Integration:
    """One integration, as ``cad run`` reads it: its extra's name (``cad[<extra>]``), the top-level modules a
    program imports of it (``modules``), the distributions that are it, which a resolution may pull in
    through another package (``distributions``, as PEP 503 normalizes their names), and the
    package indexes and folders of wheels its packages come from beside the default index (``indexes``,
    ``find_links``: none today, a hook for packaged binaries), the commands its extra puts in an environment
    (``commands``: ``kicad-cli``) and the library's module that runs one (``runner``: ``cad.kicad._command``)."""

    extra: str
    modules: tuple[str, ...]
    distributions: tuple[str, ...]
    indexes: tuple[str, ...] = ()
    find_links: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    runner: str | None = None


def _normal(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


def _from_registry() -> dict[str, Integration]:
    """Every integration with an extra, from the registry: its modules; the distributions that are it
    (``identity``: its own and the other builds of its modules, not every package its extra installs)."""
    from cad.registry import INTEGRATIONS as REGISTERED

    found: dict[str, Integration] = {}
    for name, integration in REGISTERED.items():
        if not integration.extra:
            continue
        distributions = tuple(dict.fromkeys(_normal(item) for item in integration.identity))
        found[integration.extra] = Integration(integration.extra, integration.modules, distributions, integration.indexes,
                                               integration.find_links, integration.commands,
                                               f"cad.{name}._command" if integration.commands else None)
    return found


# Every integration, by its extra's name.
INTEGRATIONS: dict[str, Integration] = _from_registry()


# The library's own names (``cad``, ``cadgen``): ``cad.<integration>`` is that integration's namespace.
_LIBRARY = ("cad", "cadgen")


def _namespaces() -> dict[str, str]:
    """Each integration's namespace in the library (``cad.build123d``), by its name, to its extra."""
    from cad.registry import INTEGRATIONS as REGISTERED

    return {name: integration.extra for name, integration in REGISTERED.items() if integration.extra}


def for_module(name: str) -> str | None:
    """The integration whose modules hold ``name`` (a module's dotted name: its top level decides), or the one
    a name of the library's needs (``for_name``), or None."""
    parts = name.split(".")
    if parts[0] in _LIBRARY:
        return for_name(name)
    return next((key for key, found in INTEGRATIONS.items() if parts[0] in found.modules), None)


def for_name(name: str) -> str | None:
    """The integration a program that uses the library's name ``name`` needs in its own process, worked out
    from where each is declared: an earlier spelling read as the name it is now (the alias table,
    ``cad._internal.aliases.current``: ``cad.read_step`` is ``cad.step.read``, ``cad.ap242`` is
    ``cad.build123d``); then an integration's namespace (``cad.build123d``, ``cad.kicad._session``: the
    registry's), a document type's reader (``cad.step.read``: its ``reader_integration``), its edit
    (``cad.kicad_pcb.edit``: the edit's integration, kicad) and a type's operation that runs in the caller
    (``cad.step.dfm``: build123d, ``cad.stl.dfm``: trimesh; never one the engine runs, as ``cad.step.export``), and a
    verb's where every type it takes needs one alike (``cad.fea``: calculix; ``for_verb``, which a call's source decides
    otherwise). None for any other name: a type itself (``cad.step``), the model contract."""
    from cad._internal.aliases import current
    from cad.registry import DOCUMENT_TYPES, INTEGRATIONS as REGISTERED, VERBS

    parts = current(name).split(".")
    if parts[0] not in _LIBRARY or len(parts) < 2:
        return None
    if parts[1] in VERBS and len(parts) == 2:  # ``cad.fea``: by its name alone where every type needs one alike
        return for_verb(parts[1])
    namespace = _namespaces().get(parts[1])
    if namespace is not None:
        return namespace
    entry = DOCUMENT_TYPES.get(parts[1])
    if entry is None or len(parts) < 3:
        return None
    if parts[2] == "read":
        needed = entry.reader_integration
    elif parts[2] == "edit":
        needed = entry.edit.integration if entry.edit is not None else None
    else:
        operation = entry.operation(parts[2])
        needed = operation.integration if operation is not None and not operation.engine else None
    return REGISTERED[needed].extra if needed is not None else None


def for_verb(verb: str, suffix: str | None = None, mode: str | None = None) -> str | None:
    """The integration a program that calls the verb ``cad.<verb>`` needs in its own process: of a source whose
    suffix is ``suffix`` (``.stl``), that of the operation the verb runs of its type (``cad.registry.operation_for``,
    ``mode`` one of ``inspect``'s: ``ranges``), none where the engine runs it; with no suffix known, the one every
    type the verb takes needs alike (``cad.fea``: calculix), else None -- a ``cad.dfm`` of a source the scan cannot
    read, which the program's run names in one line where it lacks it."""
    from cad.registry import (DOCUMENT_TYPES, INTEGRATIONS as REGISTERED, MODES, VERBS, by_extension, operation_for,
                              types_for)

    if verb not in VERBS or (mode is not None and (verb != "inspect" or mode not in MODES)):
        return None

    def of(document_type: str) -> str | None:
        operation = DOCUMENT_TYPES[document_type].operation(operation_for(verb, document_type, mode))
        needed = operation.integration if operation is not None and not operation.engine else None
        return REGISTERED[needed].extra if needed is not None else None

    if suffix is not None:
        entry = by_extension(suffix)
        return of(entry.id) if entry is not None and operation_for(verb, entry.id, mode) is not None else None
    found = {of(document_type) for document_type in types_for(verb, mode)}
    return found.pop() if len(found) == 1 else None


def needs_call(verb: str, suffix: str | None = None, mode: str | None = None) -> tuple[str, ...]:
    """Every extra a program that calls ``cad.<verb>`` needs in its own process (``for_verb``), with those its
    integration's operations need beside it (``alongside``: ``cad.fea``'s calculix, the kernel and netgen). Sorted;
    none for a call that needs none."""
    key = for_verb(verb, suffix, mode)
    return tuple(sorted({key, *alongside(key)})) if key is not None else ()


def alongside(extra: str) -> tuple[str, ...]:
    """The extras the operations of the integration whose extra is ``extra`` need in the same process beside it,
    transitively (the registry's ``alongside``: calculix's, the kernel's and netgen's), sorted; none for one that
    names none."""
    from cad.registry import INTEGRATIONS as REGISTERED

    by_extra = {integration.extra: integration for integration in REGISTERED.values() if integration.extra}
    found: set[str] = set()
    pending = [extra]
    while pending:
        current = by_extra.get(pending.pop())
        for name in current.alongside if current is not None else ():
            other = REGISTERED[name].extra
            if other and other != extra and other not in found:
                found.add(other)
                pending.append(other)
    return tuple(sorted(found))


def needs(name: str) -> tuple[str, ...]:
    """Every extra a program that imports or uses ``name`` needs in its own process: ``for_module``'s, and where the
    name is a document type's operation, those that operation's integration needs beside it (``alongside``:
    ``cad.step.solve`` is calculix's, with the kernel that reads the part and netgen that meshes it). A tool's own
    module or namespace (``cad_ccx``, ``cad.calculix``) is its integration alone. Sorted; none for a name that
    needs none."""
    from cad._internal.aliases import current
    from cad.registry import DOCUMENT_TYPES, VERBS

    key = for_module(name)
    if key is None:
        return ()
    parts = current(name).split(".")
    operation = parts[0] in _LIBRARY and ((len(parts) >= 3 and parts[1] in DOCUMENT_TYPES
                                           and parts[2] not in ("read", "edit"))
                                          or (len(parts) == 2 and parts[1] in VERBS))
    return tuple(sorted({key, *(alongside(key) if operation else ())}))


def for_distribution(name: str) -> str | None:
    """The integration a distribution (any spelling of its name) is part of, or None."""
    normal = _normal(name)
    return next((key for key, found in INTEGRATIONS.items() if normal in found.distributions), None)


def for_command(name: str) -> str | None:
    """The integration that declares the command ``name`` (``kicad-cli``, or ``kicad-cli.exe`` as Windows spells
    it), or None: a bare command ``cad run`` runs, no path."""
    if "/" in name or "\\" in name:
        return None
    bare = name[:-4] if name.lower().endswith(".exe") else name
    return next((key for key, found in INTEGRATIONS.items() if bare in found.commands), None)


def missing(error: BaseException) -> str | None:
    """The one line that names the fix for a program that failed importing a module of an integration its
    environment lacks (a ``ModuleNotFoundError`` for one of ``INTEGRATIONS``' modules); None for any other
    error: ``kipy comes with cad's kicad integration: add `cad[kicad]` to the script's header``."""
    if not isinstance(error, ModuleNotFoundError) or not error.name:
        return None
    key = for_module(error.name)
    if key is None:
        return None
    top = error.name.split(".", 1)[0]
    return f"{top} comes with cad's {key} integration: add `cad[{key}]` to the script's header"
