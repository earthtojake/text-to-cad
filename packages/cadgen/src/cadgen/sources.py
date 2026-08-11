"""Public helpers for loading generator source modules.

Entry generator files use dotted extensions (``<name>.step.py``, ``<name>.dxf.py``)
so they cannot be imported by module name. A drawing generator that reuses geometry
from its sibling ``.step.py`` loads it by path instead:

    from pathlib import Path
    from cadgen.sources import load_source_module

    _step = load_source_module(Path(__file__).with_name("bracket.step.py"))

    def gen_dxf():
        return {"document": _step.build_dxf()}

The loaded module is registered in ``sys.modules``, so the runtime source-closure
capture records the sibling file (and its own imports) as freshness inputs for the
drawing package — editing the ``.step.py`` invalidates the cached DXF artifact.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.generation import _load_generator_module

__all__ = ["load_source_module"]


def load_source_module(script_path: Path | str) -> object:
    """Path-load a generator source file and return the module object."""
    resolved = Path(script_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Generator source does not exist: {resolved}")
    return _load_generator_module(resolved)
