"""``kicad-cli`` as ``cad run kicad-cli ARGS`` runs it: KiCad's own command line, kicode's, headless.

The kicad integration declares the command (``cad.registry.INTEGRATIONS["kicad"].commands``), so the server's
``cad run`` makes the environment of ``cad[kicad]`` for it and runs this module with that environment's
Python (``python -P -m cad.kicad._command kicad-cli ARGS``). The program is the environment's own
``kicad-cli``, kicode's console script beside this Python; with a kicode that installs none (those before
the script), ``kicode.executable()`` itself. Never one on PATH, in KiCad's installation
folders or named by ``CAD_KICAD_CLI``, which picks the kicad-cli of cad's typed commands and board scripts:
this runs the pinned one.

It runs in a private folder of its own, the homes the typed commands' runs get (``_program.private_run``:
kicode's ``environment``, no display), removed when it exits, so nothing of the person's KiCad settings is
read or written whatever their environment names. Its arguments, stdin, stdout, stderr and exit code are
kicad-cli's; relative paths are the caller's folder's.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cad.kicad import _program

__all__ = ["main", "program"]


def program(name: str = "kicad-cli") -> Path | None:
    """The ``kicad-cli`` to run: the environment's own (beside this Python), else kicode's executable; None
    where this environment holds neither."""
    folder = Path(sys.executable).parent
    found = next((folder / item for item in (name, f"{name}.exe") if (folder / item).is_file()), None)
    return found or _program.packaged()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    name, rest = (args[0], args[1:]) if args else ("kicad-cli", [])
    found = program(name)
    if found is None:
        print(f"cad run: {name} is not in this environment: {_program.install_hint()}", file=sys.stderr)
        return 2
    sys.stdout.flush()
    with _program.private_run("cad-kicad-cli-") as (_folder, env):
        try:
            child = subprocess.Popen([str(found), *rest], env=env)
        except OSError as error:
            print(f"cad run: cannot run {found}: {error.strerror or error}", file=sys.stderr)
            return 1
        while True:
            try:
                return child.wait()
            except KeyboardInterrupt:  # kicad-cli was interrupted too: its exit code is the run's
                continue


if __name__ == "__main__":
    raise SystemExit(main())
