"""Every analysis ``cadgen fea`` knows, by name: built, or registered as planned.

The registry is written once, here, in the order the skill and the viewer list
them: the Tier 1 solvers, the Tier 2 estimate, the Tier 3 lite solvers, then
the types planned next. Each entry names the module and class that implement
it; a module that is not in this cadgen yet makes :func:`get_analysis` say so
in a sentence, never an ImportError. Stdlib only: the modules import lazily.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cadgen._internal.fea.analyses.base import Tier

if TYPE_CHECKING:
    from cadgen._internal.fea.analyses.base import Analysis

__all__ = ["ANALYSIS_NAMES", "DEFAULT_ANALYSIS", "Entry", "REGISTRY", "available", "get_analysis"]

DEFAULT_ANALYSIS = "static"
_PACKAGE = "cadgen._internal.fea.analyses"


@dataclass(frozen=True)
class Entry:
    name: str
    tier: Tier
    module: str            # "cadgen._internal.fea.analyses.modal"
    cls: str               # "ModalAnalysis"
    word: str
    #: Registered now, built after Tier 3 (spec section 2.1).
    planned: bool = False


def _entry(name: str, tier: Tier, cls: str, word: str, *, planned: bool = False) -> Entry:
    return Entry(name, tier, f"{_PACKAGE}.{name}", cls, word, planned)


REGISTRY: dict[str, Entry] = {entry.name: entry for entry in (
    # Tier 1: full solvers.
    _entry("static", 1, "StaticAnalysis", "Strength"),
    _entry("modal", 1, "ModalAnalysis", "Vibration"),
    _entry("buckling", 1, "BucklingAnalysis", "Buckling"),
    _entry("thermal", 1, "ThermalAnalysis", "Heat"),
    _entry("thermal_transient", 1, "ThermalTransientAnalysis", "Heat over time"),
    _entry("thermal_stress", 1, "ThermalStressAnalysis", "Heat stress"),
    _entry("harmonic", 1, "HarmonicAnalysis", "Shaking"),
    _entry("random_vibration", 1, "RandomVibrationAnalysis", "Random vibration"),
    _entry("shock", 1, "ShockAnalysis", "Shock"),
    _entry("transient", 1, "TransientAnalysis", "Over time"),
    _entry("fatigue", 1, "FatigueAnalysis", "Fatigue life"),
    # Tier 2: an engineering estimate.
    _entry("drop", 2, "DropAnalysis", "Drop (estimate)"),
    # Tier 3: in-house lite solvers.
    _entry("cfd", 3, "CfdAnalysis", "Flow"),
    _entry("impact", 3, "ImpactAnalysis", "Drop impact"),
    _entry("nonlinear", 3, "NonlinearAnalysis", "Permanent bend / Stretch"),
    _entry("contact", 3, "ContactAnalysis", "Contact"),
    # Planned next (spec 2.1): registered so they answer plainly; built after Tier 3.
    _entry("cfd_turbulent", 3, "CfdTurbulentAnalysis", "Turbulent flow"),
    _entry("cfd_compressible", 3, "CfdCompressibleAnalysis", "Fast gas flow"),
    _entry("creep", 3, "CreepAnalysis", "Creep"),
    _entry("composite", 3, "CompositeAnalysis", "Composite"),
    _entry("bolt", 3, "BoltAnalysis", "Bolted joint"),
    _entry("electromagnetic", 3, "ElectromagneticAnalysis", "Magnetic / electric"),
)}
ANALYSIS_NAMES: tuple[str, ...] = tuple(REGISTRY)

_INSTANCES: dict[str, "Analysis"] = {}


def _module(entry: Entry):
    """The entry's module, or ``None`` when it is not in this cadgen yet."""
    try:
        return importlib.import_module(entry.module)
    except ModuleNotFoundError as exc:
        if exc.name == entry.module:
            return None
        raise


def available() -> tuple[str, ...]:
    """The registered names whose module is in this cadgen, in registry order."""
    return tuple(name for name, entry in REGISTRY.items() if importlib.util.find_spec(entry.module) is not None)


def get_analysis(name: str) -> "Analysis":
    """The analysis class's instance. An unknown name: ValueError listing ANALYSIS_NAMES.
    A registered name whose module is not built yet: ValueError
    "'<name>' is planned but not in this cadgen yet; available: ...". Never ImportError."""
    if name in _INSTANCES:
        return _INSTANCES[name]
    entry = REGISTRY.get(name) if isinstance(name, str) else None
    if entry is None:
        raise ValueError(f"analysis: {name!r} is not an analysis cadgen knows; use one of {', '.join(ANALYSIS_NAMES)}")
    module = _module(entry)
    if module is None or not hasattr(module, entry.cls):
        raise ValueError(f"analysis: {name!r} is planned but not in this cadgen yet; available: {', '.join(available())}")
    instance = getattr(module, entry.cls)()
    _INSTANCES[name] = instance
    return instance
