"""The process a part declares, as the check's: ``--process`` and, for a print, ``--technology`` and
``--layer-height``.

A part's declared material (``part.material = metals.aluminum(process=machined())``, a
``bd_materials.FinishedMaterial`` the document keeps) carries how the part is made: its ``.process``, an
``AppliedProcess`` whose ``.process`` is a route (``fdm``, ``sls``, ``mjf``, ``slm``, ``vat``, ``molded``,
``machined``, ``cast``, ``wrought``) and whose ``.pitch_mm`` is FDM's layer height. A check given no
``--process`` takes the route's (``declared``): machined is cnc, molded is molding, the printed routes are
printing by their technology. Cast and wrought stock have no check, and no route is sheet's. Read by duck
typing, the standard library alone: the type side never imports ``bd_materials``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ROUTES", "declared", "route"]

#: Each declared route the check measures: its process and, for a print, its technology.
ROUTES: dict[str, tuple[str, str | None]] = {
    "machined": ("cnc", None),
    "molded": ("molding", None),
    "fdm": ("printing", "fdm"),
    "sls": ("printing", "sls"),
    "mjf": ("printing", "mjf"),
    "slm": ("printing", "pbf"),  # metal powder bed
    "vat": ("printing", "sla"),  # SLA / DLP resin
}


def route(applied: Any) -> str | None:
    """The route's name (``machined``, ``fdm``, ``cast``) of a declared process -- an ``AppliedProcess``, a bare
    ``Process`` (bd_materials' deprecated spelling) or its value -- None for none."""
    if applied is None:
        return None
    found = getattr(applied, "process", applied)  # an AppliedProcess's route, else the route itself
    value = getattr(found, "value", found)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower()


def declared(applied: Any) -> tuple[str, str | None, float | None] | None:
    """``(process, technology, layer_height)`` of a declared process: the check's process, printing's
    technology (None for another process) and FDM's layer height in mm (its wall pitch; None for another
    route, an FDM skin, whose pitch is the line width, or none given). None for a route no check measures
    (cast, wrought) and for none."""
    name = route(applied)
    if name not in ROUTES:
        return None
    process, technology = ROUTES[name]
    layer = None
    if name == "fdm" and not getattr(applied, "skin", False):
        pitch = getattr(applied, "pitch_mm", None)
        if isinstance(pitch, (int, float)) and not isinstance(pitch, bool) and pitch > 0:
            layer = float(pitch)
    return process, technology, layer
