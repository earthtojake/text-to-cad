"""``ccx`` as ``cad run ccx ARGS`` runs it: CalculiX's own solver, the ``ccx`` package's, headless.

The calculix integration declares the command (``cad.registry.INTEGRATIONS["calculix"].commands``), so the server's
``cad run`` makes the environment of ``cad[calculix]`` for it and runs this module with that environment's Python
(``python -P -m cad.calculix._command ccx ARGS``). The program is the environment's own: the ``ccx`` package's
(``ccx.executable()``), never one on PATH, a FreeCAD's or one ``CAD_CCX`` names, which picks the ccx of cad's own
studies: this runs the pinned one. An environment with no ``ccx`` package has no ccx to run: the run says so, with
the extra's install hint, and exits 2.

It runs with no display, homes of its own (``cad._internal.programs.private_run``) and the caller's working folder,
since CalculiX reads ``-i JOB`` there and writes ``JOB.dat`` and ``JOB.frd`` beside it. Its thread count is the
caller's (``OMP_NUM_THREADS`` and CalculiX's own variables), unlike a study's, which solves on one. Its arguments,
stdin, stdout, stderr and exit code are ccx's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cad.calculix import _program

__all__ = ["main", "program"]


def program() -> Path | None:
    """The ``ccx`` to run: the ``ccx`` package's, where this environment holds one; else None."""
    found = _program._installed()
    return found[0] if found else None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    name, rest = (args[0], args[1:]) if args else ("ccx", [])
    found = program() if name == "ccx" else None
    if found is None:
        print(f"cad run: {name} is not in this environment: {_program.install_hint()}", file=sys.stderr)
        return 2
    sys.stdout.flush()
    with _program.programs.private_run("cad-ccx-") as (_folder, env):
        # The run's homes are private; its threads and its folder are the caller's.
        env = {**env, **{name: os.environ[name] for name in _program.THREAD_VARIABLES if name in os.environ}}
        try:
            child = subprocess.Popen([str(found), *rest], env=env, cwd=os.getcwd())
        except OSError as error:
            print(f"cad run: cannot run {found}: {error.strerror or error}", file=sys.stderr)
            return 1
        while True:
            try:
                return child.wait()
            except KeyboardInterrupt:  # ccx was interrupted too: its exit code is the run's
                continue


if __name__ == "__main__":
    raise SystemExit(main())
