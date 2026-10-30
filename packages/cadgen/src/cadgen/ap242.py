"""The document's AP242 vocabulary: the mechanism and the semantic PMI that ISO 10303-242 names,
and the model-based definition around that PMI -- notes, named views and their presentation, which
the xbf keeps and a STEP does not.

A function that writes an entity is named after it (the engine's **Kinematics**, **Configuration
sequences** and **PMI**)::

    from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state

``mechanism_state(assembly, name, **values)`` names a state of the assembly's mechanism
(``mechanism_state_representation``); ``gear_pair``, ``rack_and_pinion_pair`` and
``screw_pair(assembly, name, **joints)`` constrain joints to move together by ratio;
``configuration_sequence(assembly, name, ...)`` names a sequence of states over time
(``interpolated_configuration_sequence``); ``posed(assembly, state)`` is a copy of the assembly
with its parts where a state puts them: a posed file is a model returning it, never an option.

Product and manufacturing information (PMI) is a part's, ``annotate(part, ...)`` giving it::

    from cadgen.ap242 import annotate, datum, dimensional_size, plus_minus_tolerance, position_tolerance

``datum(letter, ref)`` (``datum`` and its ``datum_feature``); ``dimensional_size(id, ref,
tolerance=)`` a cylinder's diameter and ``dimensional_location(id, from, to, tolerance=)`` a
distance, theoretically exact with ``basic=True``; ``plus_minus_tolerance(upper, lower=None)`` a
dimension's tolerance; ``flatness_tolerance(id, ref, value)``, ``position_tolerance(id, ref, value,
datums=)`` and ``surface_profile_tolerance(id, refs, value, datums=)``. The rest write no entity of
their own and keep plain names: ``limits(lower, upper)`` (a dimension's 'lower limit' and 'upper
limit' values), ``general_profile(id, value, datums=)`` (ASME's "unless otherwise noted", its faces
computed), ``general_tolerance(id, standard)`` (ISO 2768's general tolerances, a general note a STEP
states as its part's 'default tolerances'), ``note`` and ``view`` (with ``camera`` and ``section``: XCAF's, in the xbf, in no STEP)
and ``place(anchor, offset)`` (presentation: a STEP's callout of the annotation, never its
meaning). A STEP carries the datums, dimensions (their limits too) and tolerances, the general
profile among them, each placed annotation drawn where it was placed; the notes and views stay in
the xbf.

Every name loads on first use: ``import cadgen.ap242`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# PMI's names (``cadgen.engine.pmi``), each the call a model makes.
_PMI = ("annotate", "camera", "datum", "dimensional_location", "dimensional_size", "flatness_tolerance",
        "general_profile", "general_tolerance", "limits", "note", "place", "plus_minus_tolerance", "position_tolerance", "section",
        "surface_profile_tolerance", "view")

__all__ = ["configuration_sequence", "gear_pair", "mechanism_state", "posed", "rack_and_pinion_pair", "screw_pair",
           *_PMI]


def __getattr__(name: str) -> Any:
    if name in ("mechanism_state", "configuration_sequence"):
        from cadgen.engine import model

        return getattr(model, name)
    if name in ("gear_pair", "posed", "rack_and_pinion_pair", "screw_pair"):
        from cadgen.engine import mechanism

        return getattr(mechanism, name)
    if name in _PMI:
        from cadgen.engine import pmi

        return getattr(pmi, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far: what ``dir()`` and
    completion offer, without loading any of them, nor the kernel."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if TYPE_CHECKING:
    from cadgen.engine.mechanism import gear_pair, posed, rack_and_pinion_pair, screw_pair
    from cadgen.engine.model import configuration_sequence, mechanism_state
    from cadgen.engine.pmi import (
        annotate,
        camera,
        datum,
        dimensional_location,
        dimensional_size,
        flatness_tolerance,
        general_profile,
        general_tolerance,
        limits,
        note,
        place,
        plus_minus_tolerance,
        position_tolerance,
        section,
        surface_profile_tolerance,
        view,
    )
