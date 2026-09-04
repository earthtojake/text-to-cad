"""Where a model's imports resolve: exactly what ``python script.py`` would answer.

The script's own folder comes first, as the interpreter puts it; then every entry of the
CALLER's ``PYTHONPATH``, absolute and existing, in order. Nothing else. cadgen adds no root
of its own and infers none from directory names: a project that wants an import root
other than the script's folder declares it the standard Python way (``PYTHONPATH=src``,
an editable install), and project layout stays a convention of the skills, never a fact
cadgen knows.

One helper, one rule: the runner seeds these onto ``sys.path`` for the whole build, the
closure's static scan resolves imports against them, and the module eviction that keeps
one project's ``lib`` from shadowing another's treats them as the model's own roots.
"""

from __future__ import annotations

import os
from pathlib import Path


def pythonpath_entries(environ: dict[str, str] | None = None) -> list[str]:
    """The caller's ``PYTHONPATH`` as absolute, existing, de-duplicated directories."""
    env = os.environ if environ is None else environ
    entries: list[str] = []
    for raw in (env.get("PYTHONPATH") or "").split(os.pathsep):
        if not raw:
            continue
        entry = str(Path(raw).resolve())
        if entry not in entries and os.path.isdir(entry):
            entries.append(entry)
    return entries


def import_roots(script: Path | str) -> list[str]:
    """``python script.py``'s import roots for ``script``: its folder, then ``PYTHONPATH``."""
    folder = str(Path(script).resolve().parent)
    roots = [folder]
    for entry in pythonpath_entries():
        if entry not in roots:
            roots.append(entry)
    return roots
