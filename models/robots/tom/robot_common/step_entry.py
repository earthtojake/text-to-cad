"""Load a `<name>.step.py` entry generator as a module, by name.

Entry generators are named `<name>.step.py`, which Python's `import <name>` cannot resolve (the
dotted stem reads as a package path, not a file). When one generator needs another entry's
module-level constants or helpers, it loads the entry here instead of importing it: this searches
``sys.path`` for ``<name>.step.py`` (the same directories that made the legacy ``import <name>``
work) and execs it once, cached by name so repeated loads return the same module.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache(maxsize=None)
def load_step_entry(stem: str) -> ModuleType:
    for directory in sys.path:
        candidate = Path(directory) / f"{stem}.step.py"
        if candidate.is_file():
            module_name = f"_tom_step_entry_{stem}"
            spec = importlib.util.spec_from_file_location(module_name, candidate)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
    raise ImportError(f"{stem}.step.py not found on sys.path")
