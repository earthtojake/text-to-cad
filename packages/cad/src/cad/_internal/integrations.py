"""cad's integrations: the third-party technologies the library's extras carry, each named for its
technology as its extra is (``cad[build123d]``), and what tells a program needs one.

This table is the one place each integration's modules, distributions and decorators are listed: the
server's ``cad run`` reads it to work out a script's integrations from its imports (a static scan, no
code run), to add one a resolution pulled in through another package, and to give a requirement its
indexes; a program run with one missing says, in one line, which extra brings it (``missing``). It is a
seam: a registry of integrations may own these lists, and the rest reads them through ``INTEGRATIONS``.

The standard library alone: the server's command and a model's process both read it, and neither loads
any integration to do so.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["INTEGRATIONS", "Integration", "decorated", "for_distribution", "for_module", "missing"]


@dataclass(frozen=True)
class Integration:
    """One integration: its extra's name (``cad[<extra>]``), the top-level modules a program imports of it
    (``modules``), the distributions that are it, which a resolution may pull in through another package
    (``distributions``, as PEP 503 normalizes their names), the names of cad's decorators that need it
    (``decorators``: ``@cad.<name>`` or a ``<name>`` imported from cad), and the package indexes and
    folders of wheels its packages come from beside the default index (``indexes``, ``find_links``: none
    today, a hook for packaged binaries)."""

    extra: str
    modules: tuple[str, ...]
    distributions: tuple[str, ...]
    decorators: tuple[str, ...] = ()
    indexes: tuple[str, ...] = ()
    find_links: tuple[str, ...] = ()


# Every integration, by its extra's name.
INTEGRATIONS: dict[str, Integration] = {
    "build123d": Integration(
        extra="build123d",
        modules=("build123d", "OCP"),
        distributions=("build123d", "cadquery-ocp", "cadquery-ocp-novtk", "cadquery-ocp-proxy"),
    ),
    "kicad": Integration(
        extra="kicad",
        modules=("kipy",),
        distributions=("kicad-python",),
        decorators=("kicad_pcb",),
    ),
}


def for_module(name: str) -> str | None:
    """The integration whose modules hold ``name`` (a module's dotted name: its top level decides), or None."""
    top = name.split(".", 1)[0]
    return next((key for key, found in INTEGRATIONS.items() if top in found.modules), None)


def for_distribution(name: str) -> str | None:
    """The integration a distribution (any spelling of its name) is part of, or None."""
    import re

    normal = re.sub(r"[-_.]+", "-", name).lower()
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
