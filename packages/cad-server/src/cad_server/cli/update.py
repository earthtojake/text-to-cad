"""``cad update``: text-to-cad brought up to the newest release, in every agent app here.

The same path as the update button and the install command run again: the newest release the version
feed names (read now; ``cad_server/updates.py``) is installed in its own folder, ``<state>/releases/<release>``
(``cad_server._internal.releases``), and that release's own ``cad setup`` runs from there with these
arguments (``cad_server.cli.setup``): its base, every agent app's plugin, and the switch of the engine to it.
With the feed out of reach, or this the newest, it is this release's ``cad setup``. ``--dry-run`` reads the
feed too, kept nowhere, and says what an update would do -- the release it would install, or this one set up
again and why -- before this release's setup plan, and changes nothing.

``cad update --switch <release>`` is the switch's helper (``cad_server._internal.switch``), which the
engine starts detached as it drains for the update button: not a command to run by hand.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad update"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    """``cad setup``'s options (``cad_server.cli.setup.build_parser``), and the switch helper's own."""
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
        return setup.main(given, prog, update=_would(prog, args))
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
        print(f"Once that is fixed, run `cad update` again, or the install command: {updates.command()}",
              file=sys.stderr, flush=True)
        if not args.json:
            return 1
        from cad_server._internal.cli_errors import Failure, write

        return write(Failure(f"text-to-cad {newest}'s release folder was not made: {refused}"), prog=prog, as_json=True)
    run = [made["cad"], "setup", *given]
    if os.name == "nt":
        return subprocess.call(run)
    os.execv(run[0], run)
    return 1  # not reached


def _would(prog: str, args: argparse.Namespace) -> dict:
    """What ``cad update`` would do, for its dry run: the version feed read now -- a read the person asked
    for, bounded, kept nowhere (``updates.newest_now``) -- said in a line before this release's setup plan
    (stdout, or stderr under ``--json``, whose document carries it as ``update``): the release it would
    install, or that it would set this one up again, and why."""
    from cad_server import __version__, updates

    state, newer = updates.newest_now()
    why = {"newer": f"would install text-to-cad {newer} (this is {__version__}), then set it up in every agent app "
                    "here, as its own setup plans it; this release's plan of it",
           "newest": f"text-to-cad {__version__} is the newest release: it would set this one up again",
           "unreachable": f"could not reach the version feed ({updates.feed_url()}): it would set up this release, "
                          f"{__version__}, again",
           "off": f"the version feed is not read here (CAD_UPDATE_CHECK=0, or CI): it would set up this release, "
                  f"{__version__}, again"}[state]
    print(f"{prog}: {why}:", file=sys.stderr if args.json else sys.stdout, flush=True)
    return {"current": __version__, "feed": {"newer": "read", "newest": "read"}.get(state, state), "release": newer}


if __name__ == "__main__":
    raise SystemExit(main())
