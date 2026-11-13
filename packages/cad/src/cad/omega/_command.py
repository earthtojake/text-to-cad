"""``gsl`` as ``cad run gsl ARGS`` runs it: omega-core's own command line, as it is.

The omega integration declares the command (``cad.registry.INTEGRATIONS["omega"].commands``), so the server's
``cad run`` makes the environment of ``cad[omega]`` for it and runs this module with that environment's Python
(``python -P -m cad.omega._command gsl ARGS``). The program is the one ``cad.omega._program`` finds: ``CAD_GSL``'s,
else the omega-core wheel's, never one on PATH. Its arguments, stdin, stdout, stderr and exit code are ``gsl``'s;
relative paths are the caller's folder's. It runs with no display to reach (``gsl render`` draws on the CPU).
"""

from __future__ import annotations

import os
import subprocess
import sys

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from cad._internal.programs import DISPLAY
    from cad.omega._program import OmegaMissingError, find_gsl

    args = list(sys.argv[1:] if argv is None else argv)
    rest = args[1:] if args else []
    try:
        found = find_gsl()
    except OmegaMissingError as error:
        print(f"cad run: {error}", file=sys.stderr)
        return 2
    env = {key: value for key, value in os.environ.items() if key not in DISPLAY}
    sys.stdout.flush()
    try:
        child = subprocess.Popen([str(found), *rest], env=env)
    except OSError as error:
        print(f"cad run: cannot run {found}: {error.strerror or error}", file=sys.stderr)
        return 1
    while True:
        try:
            return child.wait()
        except KeyboardInterrupt:  # gsl was interrupted too: its exit code is the run's
            continue


if __name__ == "__main__":
    raise SystemExit(main())
