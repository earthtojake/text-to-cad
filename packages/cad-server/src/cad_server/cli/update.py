"""``cad update``: the default channel brought up to the newest release, in every agent app here.

The same path as the update button and the install command run again (``cad_server._internal.update``, whose
docstring is the contract between releases): the newest release the version feed names (read now;
``cad_server/updates.py``) is installed by its own release (``cad setup --add``, through uvx), and that release's
own ``cad setup`` runs with these arguments (``cad_server.cli.setup``): the default channel moved to it, its server
on the same port, and every agent app given its text. With the feed out of reach, or this the newest, it is this
release's ``cad setup``. ``--dry-run`` reads the feed too, kept nowhere, and says what an update would do -- the
release it would install, or this one set up again and why -- before this release's setup plan, and changes
nothing.

Only the default channel has an updater, and only where the install command has run (its receipt): with no
receipt, it says there is no install to update and names the install command; run with a channel's pin (``cad
+<version>@<channel> update``), it says that copy is updated by whoever delivers it. Neither changes anything.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad update"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    """``cad setup``'s options (``cad_server.cli.setup.build_parser``)."""
    from cad_server.cli.setup import build_parser as setup_parser

    return setup_parser(prog, update=True)


def refusal(channel: str | None = None) -> str | None:
    """Why ``cad update`` does nothing here, in one line, or None: a named channel's command (``channel``; by default
    this command's, ``places.channel``), whose copy whoever delivers it updates; a device where the install command
    never ran (no receipt), which has no install to update."""
    from cad.engine import places
    from cad_server._internal.update import installed_here
    from cad_server.updates import command

    channel = places.channel() if channel is None else channel
    if channel != places.DEFAULT_CHANNEL:
        return (f"the {channel} channel's copy of text-to-cad is updated by whoever delivers it (its store or app), "
                "not by cad update")
    if not installed_here():
        return f"there is no install of text-to-cad here to update: the install command installs one, {command()}"
    return None


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    given = list(sys.argv[1:] if argv is None else argv)
    args = build_parser(prog).parse_args(given)
    from cad_server.cli import setup

    why = refusal()
    if why is not None:
        from cad_server._internal.cli_errors import Failure, write

        return write(Failure(why), prog=prog, as_json=bool(args.json))
    if args.dry_run:
        return setup.main(given, prog, update=_would(prog, args))
    from cad_server import __version__, updates

    newest = updates.newest() if updates.checking(asked=True) else None
    if newest is None:
        return setup.main(given, prog)
    from cad_server._internal import base, update

    print(f"text-to-cad {newest} is out (this is {__version__}): installing it", file=sys.stderr, flush=True)
    try:
        record = update.install(newest)
    except base.Refused as refused:
        print(f"version  {refused}", file=sys.stderr, flush=True)
        print(f"Once that is fixed, run `cad update` again, or the install command: {updates.command()}",
              file=sys.stderr, flush=True)
        if not args.json:
            return 1
        from cad_server._internal.cli_errors import Failure, write

        return write(Failure(f"text-to-cad {newest} could not be installed: {refused}"), prog=prog, as_json=True)
    # Its own setup, with this command's arguments: the contract's second step, at a terminal.
    run = [record["cad"], "setup", *given]
    if os.name == "nt":
        return subprocess.call(run, env=update.environment())
    sys.stdout.flush()
    sys.stderr.flush()
    os.execve(run[0], run, update.environment())
    return 1  # not reached


def _would(prog: str, args: argparse.Namespace) -> dict:
    """What ``cad update`` would do, for its dry run: the version feed read now -- a read the person asked
    for, bounded, kept nowhere (``updates.newest_now``) -- said in a line before this release's setup plan
    (stdout, or stderr under ``--json``, whose document carries it as ``update``): the release it would
    install, or that it would set this one up again, and why."""
    from cad_server import __version__, updates

    state, newer = updates.newest_now()
    why = {"newer": f"would install text-to-cad {newer} (this is {__version__}), then run its setup, which moves the "
                    "default channel to it and sets it up in every agent app here; this release's plan of it",
           "newest": f"text-to-cad {__version__} is the newest release: it would set this one up again",
           "unreachable": f"could not reach the version feed ({updates.feed_url()}): it would set up this release, "
                          f"{__version__}, again",
           "off": f"the version feed is not read here (CAD_UPDATE_CHECK=0, or CI): it would set up this release, "
                  f"{__version__}, again"}[state]
    print(f"{prog}: {why}:", file=sys.stderr if args.json else sys.stdout, flush=True)
    return {"current": __version__, "feed": {"newer": "read", "newest": "read"}.get(state, state), "release": newer}


if __name__ == "__main__":
    raise SystemExit(main())
