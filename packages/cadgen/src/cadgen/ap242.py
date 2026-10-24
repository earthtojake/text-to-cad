"""The document's AP242 vocabulary: what a model says that ISO 10303-242 names.

Each function is named after the entity it writes (the engine's **Kinematics** and
**Configuration sequences**)::

    from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state

``mechanism_state(assembly, name, **values)`` names a state of the assembly's mechanism
(``mechanism_state_representation``); ``gear_pair``, ``rack_and_pinion_pair`` and
``screw_pair(assembly, name, **joints)`` constrain joints to move together by ratio;
``configuration_sequence(assembly, name, ...)`` names a sequence of states over time
(``interpolated_configuration_sequence``); ``posed(assembly, state)`` is a copy of the assembly
with its parts where a state puts them: a posed file is a model returning it, never an option. Product and manufacturing information (PMI) will
join them here.

Every name loads on first use: ``import cadgen.ap242`` imports no CAD kernel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["configuration_sequence", "gear_pair", "mechanism_state", "posed", "rack_and_pinion_pair", "screw_pair"]


def __getattr__(name: str) -> Any:
    if name in ("mechanism_state", "configuration_sequence"):
        from cadgen.engine import model

        return getattr(model, name)
    if name in ("gear_pair", "posed", "rack_and_pinion_pair", "screw_pair"):
        from cadgen.engine import mechanism

        return getattr(mechanism, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from cadgen.engine.mechanism import gear_pair, posed, rack_and_pinion_pair, screw_pair
    from cadgen.engine.model import configuration_sequence, mechanism_state
