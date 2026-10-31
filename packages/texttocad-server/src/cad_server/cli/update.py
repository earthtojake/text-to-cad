"""``cadgen update``: text-to-cad brought up to the newest release, in every agent app here.

The same path as the update button and the install command run again: the newest release the version
feed names (read now; ``cad_server/updates.py``) is installed in its own folder, ``<state>/releases/<release>``
(``cad_server._internal.releases``), and that release's own ``cadgen setup`` runs from there with these
arguments (``cad_server.cli.setup``): its base, every agent app's plugin, and the switch of the engine to it.
With the feed out of reach, or this the newest, it is this release's ``cadgen setup``.

``cadgen update --switch <release>`` is the switch's helper (``cad_server._internal.switch``), which the
engine starts detached as it drains for the update button: not a command to run by hand.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cadgen update"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    """``cadgen setup``'s options (``cad_server.cli.setup.build_parser``), and the switch helper's own."""
    from cad_server.cli.setup import build_parser as setup_parser

    return setup_parser(prog, update=True)


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    args = build_parser(prog).parse_args(given)
    if args.switch:
        from cad_server._internal import switch

        return switch.helper(args.switch, port=args.port, previous=args.previous)
    from cad_server.cli import setup

    if args.dry_run:
        return setup.main(given, prog)
    from cad_server import __version__, updates

    newest = updates.newest() if updates.checking(asked=True) else None
    if newest is None:
        return setup.main(given, prog)
    from cad_server._internal import base, releases

    print(f"text-to-cad {newest} is out (this is {__version__}): installing it", file=sys.stderr, flush=True)
    try:
        made = releases.make(newest, told=lambda line: print(f"release  {line}", file=sys.stderr, flush=True))
    except base.Refused as refused:
        print(f"release  {refused}", file=sys.stderr, flush=True)
        print(f"Once that is fixed, run `cadgen update` again, or the install command: {updates.command()}",
              file=sys.stderr, flush=True)
        return 1
    run = [made["cadgen"], "setup", *given]
    if os.name == "nt":
        return subprocess.call(run)
    os.execv(run[0], run)
    return 1  # not reached


if __name__ == "__main__":
    raise SystemExit(main())
