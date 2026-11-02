"""cad's integrations as ``cad run`` reads them: what tells a program needs one, worked out from the registry.

The registry (``cad.registry.INTEGRATIONS``) is the one place each integration's modules, distributions and
extra are listed, and its document types say which decorators need which integration. This module is the
view of it the server's ``cad run`` reads to work out a script's integrations from its imports (a static
scan, no code run), to add one a resolution pulled in through another package, and to give a requirement
its indexes; a program run with one missing says, in one line, which extra brings it (``missing``).

The standard library alone: the server's command and a model's process both read it, and neither loads
any integration to do so.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["INTEGRATIONS", "Integration", "decorated", "for_distribution", "for_module", "missing"]


@dataclass(frozen=True)
class Integration:
    """One integration, as ``cad run`` reads it: its extra's name (``cad[<extra>]``), the top-level modules a
    program imports of it (``modules``), the distributions that are it, which a resolution may pull in
    through another package (``distributions``, as PEP 503 normalizes their names), the names of cad's
    decorators that need it (``decorators``: ``@cad.<name>`` or a ``<name>`` imported from cad), and the
    package indexes and folders of wheels its packages come from beside the default index (``indexes``,
    ``find_links``: none today, a hook for packaged binaries)."""

    extra: str
    modules: tuple[str, ...]
    distributions: tuple[str, ...]
    decorators: tuple[str, ...] = ()
    indexes: tuple[str, ...] = ()
    find_links: tuple[str, ...] = ()


def _normal(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


def _from_registry() -> dict[str, Integration]:
    """Every integration with an extra, from the registry: its modules; the distributions that are it
    (``identity``: its own and the other builds of its modules, not every package its extra installs); the decorators its own
    producers declare for every target (``Producer.declare``, ``decorates`` None: ``@kicad_pcb``) -- a
    decorator the engine makes a model of is no sign of an integration a program chose."""
    from cad.registry import DOCUMENT_TYPES, INTEGRATIONS as REGISTERED, producers_for

    found: dict[str, Integration] = {}
    for name, integration in REGISTERED.items():
        if not integration.extra:
            continue
        decorators = tuple(entry.id for entry in DOCUMENT_TYPES.values() if entry.decorator_integration == name
                           and any(producer.integration == name and producer.declare and producer.decorates is None
                                   for producer in producers_for(entry.id)))
        distributions = tuple(dict.fromkeys(_normal(item) for item in integration.identity))
        found[integration.extra] = Integration(integration.extra, integration.modules, distributions, decorators,
                                               integration.indexes, integration.find_links)
    return found


# Every integration, by its extra's name.
INTEGRATIONS: dict[str, Integration] = _from_registry()


def for_module(name: str) -> str | None:
    """The integration whose modules hold ``name`` (a module's dotted name: its top level decides), or None."""
    top = name.split(".", 1)[0]
    return next((key for key, found in INTEGRATIONS.items() if top in found.modules), None)


def for_distribution(name: str) -> str | None:
    """The integration a distribution (any spelling of its name) is part of, or None."""
    normal = _normal(name)
    return next((key for key, found in INTEGRATIONS.items() if normal in found.distributions), None)


def decorated(name: str) -> str | None:
    """The integration one of cad's decorators, by its name, needs, or None."""
    return next((key for key, found in INTEGRATIONS.items() if name in found.decorators), None)


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
