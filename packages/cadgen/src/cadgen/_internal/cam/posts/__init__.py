"""Every controller ``cadgen cam`` posts for, by name: built, or registered as planned (spec section 7).

Each entry names its module (``posts/<name>.py``) and class, the machine kinds it serves and the posted file's
extension. The job's ``machine.post`` is checked against this table before anything is planned (a post that does not
serve the machine's kind is a teaching error), and :func:`get_post` refuses a registered post whose module is not in
this cadgen in one sentence. Stdlib only: the modules import lazily.
"""

from __future__ import annotations

import difflib
import importlib
import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cadgen._internal.cam.job_errors import CamJobError, shown

if TYPE_CHECKING:
    from cadgen._internal.cam.posts.base import Post

__all__ = ["DEFAULT_POST", "Entry", "POST_NAMES", "REGISTRY", "available", "built", "entry_for", "get_post", "option_default",
           "option_keys", "parse_options"]

_PACKAGE = "cadgen._internal.cam.posts"


@dataclass(frozen=True)
class Entry:
    name: str
    module: str
    cls: str
    kinds: tuple[str, ...]
    extension: str       # ".nc", with the dot
    plain: str


def _entry(name: str, cls: str, kinds: tuple[str, ...], extension: str, plain: str) -> Entry:
    return Entry(name, f"{_PACKAGE}.{name}", cls, kinds, extension, plain)


REGISTRY: dict[str, Entry] = {entry.name: entry for entry in (
    _entry("grbl", "GrblPost", ("mill", "router", "laser"), ".nc", "GRBL 1.1"),
    _entry("linuxcnc", "LinuxCncPost", ("mill", "mill4", "mill5", "lathe"), ".ngc", "LinuxCNC"),
    _entry("fanuc", "FanucPost", ("mill", "mill4", "mill5", "lathe"), ".nc", "Fanuc"),
    _entry("haas", "HaasPost", ("mill", "mill4", "mill5", "lathe"), ".nc", "Haas"),
    _entry("mach3", "Mach3Post", ("mill", "mill4", "router", "plasma"), ".tap", "Mach3/Mach4"),
    _entry("marlin", "MarlinPost", ("laser",), ".gcode", "Marlin laser"),
    _entry("plasma", "PlasmaPost", ("plasma",), ".nc", "Plasma (THC)"),
    _entry("waterjet", "WaterjetPost", ("waterjet",), ".nc", "Waterjet"),
    _entry("wire_edm", "WireEdmPost", ("wire_edm",), ".nc", "Wire EDM (Fanuc-style)"),
)}

POST_NAMES = tuple(REGISTRY)

#: The post a job gets when neither its machine nor its machine's model names one: the dialect most machines of the
#: kind read (``machines.GENERIC`` says why for each, and the plan lists it as assumed).
DEFAULT_POST = {"mill": "fanuc", "mill4": "fanuc", "mill5": "fanuc", "lathe": "fanuc", "router": "grbl",
                "laser": "grbl", "plasma": "plasma", "waterjet": "waterjet", "wire_edm": "wire_edm"}


def available(name: str) -> bool:
    entry = REGISTRY.get(name)
    return entry is not None and importlib.util.find_spec(entry.module) is not None


def built() -> tuple[str, ...]:
    return tuple(name for name in POST_NAMES if available(name))


def entry_for(name: object, kind: str, where: str = "machine.post") -> Entry:
    """The entry for ``name`` when it serves machine ``kind``, else the teaching error."""
    if not isinstance(name, str) or name not in REGISTRY:
        close = difflib.get_close_matches(name, POST_NAMES, n=1) if isinstance(name, str) else []
        hint = f" (did you mean '{close[0]}'?)" if close else ""
        raise CamJobError(f"{where}: unknown post {shown(name)}{hint}; the posts are {', '.join(POST_NAMES)}")
    entry = REGISTRY[name]
    if kind not in entry.kinds:
        serving = [post for post, e in REGISTRY.items() if kind in e.kinds]
        raise CamJobError(f"{where}: the {name} post does not serve a {kind}; it serves {', '.join(entry.kinds)}. "
                          f"For a {kind} use {', '.join(serving)}")
    return entry


def _post_class(name: object):
    entry = REGISTRY.get(name) if isinstance(name, str) else None
    if entry is None or not available(name):
        return None
    return getattr(importlib.import_module(entry.module), entry.cls)


def option_default(name: str, key: str):
    """Post ``name``'s own default for its machine key ``key`` (grbl's ``spindle_spinup_s``), or None."""
    cls = _post_class(name)
    spec = cls.options.get(key) if cls is not None else None
    return spec.get("default") if isinstance(spec, dict) else None


def option_keys(machine: dict) -> tuple[str, ...]:
    """The machine keys the job's post takes beyond the shared ones (``machine.cycles``, ``machine.laser_scale``...):
    its ``options``. None while the kind or post is not one yet (the shared checks then teach)."""
    kind = machine.get("kind")
    name = machine.get("post", DEFAULT_POST.get(kind) if isinstance(kind, str) else None)
    cls = _post_class(name)
    return tuple(cls.options) if cls is not None else ()


def parse_options(name: str, machine: dict) -> dict:
    """The post's own machine keys from the job's machine object, checked (absent keys are left out)."""
    cls = _post_class(name)
    return cls.parse_options(machine) if cls is not None else {}


def get_post(name: str, kind: str, where: str = "machine.post") -> "Post":
    entry = entry_for(name, kind, where)
    if not available(name):
        raise CamJobError(f"{where}: the '{name}' post is planned but not in this cadgen yet; the posts built are "
                          f"{', '.join(built()) or 'none'}")
    return getattr(importlib.import_module(entry.module), entry.cls)()
