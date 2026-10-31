"""``python -P -m cad._internal.program ARGS``: ``python ARGS`` -- a script, ``-m MODULE`` or ``-c CODE`` --
with the program's own folder (the script's; for a module or code, the working folder) LAST on the module
search path, where Python puts it first.

So a project's module that bears the library's name -- a ``cad.py`` beside a model -- never stands in for
the library, and the program's own modules still import by their names. ``-P`` keeps the working folder
off the path from the interpreter's start. The server's ``run`` verb runs every program so, and the
engine's worker seats a model's folder the same way (``cad.engine.model.seat``).
"""

from __future__ import annotations

import os
import runpy
import sys
import types

USAGE = "usage: python -P -m cad._internal.program SCRIPT [ARGS...] | -m MODULE [ARGS...] | -c CODE [ARGS...]"


def last(folder: str) -> None:
    """``folder`` at the end of the module search path, moved there if the path holds it already."""
    while folder in sys.path:
        sys.path.remove(folder)
    sys.path.append(folder)


def main(argv: list[str]) -> None:
    if not argv or (argv[0] in ("-m", "-c") and len(argv) < 2) or (argv[0].startswith("-") and argv[0] not in ("-m", "-c")):
        raise SystemExit(USAGE)
    if argv[0] == "-m":
        last(os.getcwd())
        sys.argv = [argv[1], *argv[2:]]  # runpy names the module's file in argv[0], as ``python -m`` does
        runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
    elif argv[0] == "-c":
        last(os.getcwd())
        sys.argv = ["-c", *argv[2:]]
        program = types.ModuleType("__main__")
        sys.modules["__main__"] = program
        exec(compile(argv[1], "<string>", "exec"), program.__dict__)  # noqa: S102 -- python -c, as asked
    else:
        last(os.path.dirname(os.path.abspath(argv[0])))
        sys.argv = list(argv)
        runpy.run_path(argv[0], run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
