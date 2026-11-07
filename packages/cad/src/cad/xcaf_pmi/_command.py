"""``xcaf-pmi`` as ``cad run xcaf-pmi ARGS`` runs it: Paul Fremantle's command line, the environment's.

The xcaf_pmi integration declares the command (``cad.registry.INTEGRATIONS["xcaf_pmi"].commands``), so the
server's ``cad run`` makes the environment of ``cad[xcaf_pmi]`` for it and runs this module with that
environment's Python (``python -P -m cad.xcaf_pmi._command xcaf-pmi ARGS``). The program is the environment's
own ``xcaf-pmi``, the console script beside this Python, never one on PATH. An environment with no script has
none to run: the run says so and exits 2. Its arguments, stdin, stdout, stderr and exit code are xcaf-pmi's;
relative paths are the caller's folder's.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = ["main", "program"]

_INSTALL_HINT = "xcaf-pmi comes with cad's xcaf_pmi integration, cad[xcaf_pmi], which cad run installs on first need"


def program(name: str = "xcaf-pmi") -> Path | None:
    """The ``xcaf-pmi`` to run: the environment's own console script beside this Python; None where this
    environment has none."""
    folder = Path(sys.executable).parent
    return next((folder / item for item in (name, f"{name}.exe") if (folder / item).is_file()), None)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    name, rest = (args[0], args[1:]) if args else ("xcaf-pmi", [])
    found = program(name)
    if found is None:
        print(f"cad run: {name} is not in this environment: {_INSTALL_HINT}", file=sys.stderr)
        return 2
    sys.stdout.flush()
    try:
        return subprocess.run([str(found), *rest], check=False).returncode
    except OSError as error:
        print(f"cad run: cannot run {found}: {error.strerror or error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
