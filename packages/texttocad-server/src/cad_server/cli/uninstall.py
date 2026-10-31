"""``cadgen uninstall``: text-to-cad taken out of every agent app on this machine.

One implementation with ``cadgen setup``: this is ``cad_server.cli.setup``'s uninstall path, with a parser
of its own (``--dry-run``, ``--only``, ``--purge``, ``--json``). What it takes back and what it
leaves are said in that module's docstring.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen uninstall"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server.cli import setup

    return setup.build_parser(prog, uninstall=True)


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    from cad_server.cli import setup

    return setup.main(argv, prog, uninstall=True)


if __name__ == "__main__":
    raise SystemExit(main())
