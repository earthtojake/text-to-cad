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

__all__ = ["INTEGRATIONS", "Integration", "for_command", "for_distribution", "for_module", "for_name", "missing"]


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
    (``cad.step.dfm``: trimesh; never one the engine runs, as ``cad.step.export``). None for any other name: a type itself (``cad.step``), the model contract."""
    from cad._internal.aliases import current
    from cad.registry import DOCUMENT_TYPES, INTEGRATIONS as REGISTERED

    parts = current(name).split(".")
    if parts[0] not in _LIBRARY or len(parts) < 2:
        return None
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
