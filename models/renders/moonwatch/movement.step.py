"""Complete movement: base (plate/train/escapement/balance) + keyless and
motion works + chronograph works, all authored in the shared MOVEMENT local
frame (see _spec.py), so composition is identity — no re-posing here.
"""

import importlib.util
from functools import lru_cache
from pathlib import Path

from build123d import Compound

_HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _load_entry(name: str):
    path = _HERE / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Loaded at import time — the CLI restores sys.path after module load, so the
# children's sibling-helper imports only resolve during this module's import.
_BASE = _load_entry("movement_base.step.py")
_KEYLESS = _load_entry("keyless_works.step.py")
_CHRONO = (
    _load_entry("chrono_works.step.py")
    if (_HERE / "chrono_works.step.py").exists()
    else None
)


def gen_step():
    children = []

    base = _BASE.gen_step()
    base.label = "movement_base"
    children.append(base)

    keyless = _KEYLESS.gen_step()
    keyless.label = "keyless_works"
    children.append(keyless)

    if _CHRONO is not None:
        chrono = _CHRONO.gen_step()
        chrono.label = "chronograph_works"
        children.append(chrono)

    return Compound(children=children, label="movement")
