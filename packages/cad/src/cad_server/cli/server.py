"""``cad server``: the cad server's commands -- ``start`` (``cad.engine.client.start``: detached; with ``--foreground``
in this process), ``stop`` and ``status`` (the engine's verbs, ``cad_server.engine.cli``) -- and ``--rotate-token``,
which replaces the page token, asking first (``cad_server._internal.consent``).

Bare ``cad server`` runs the server in this process, as ``cad server start --foreground`` does: releases 0.10.0 to
0.11.11 tell an agent in a sandbox to run `cad server` outside it, so it stays, unlisted, until the bridge goes.

A start that fails asks for cad's own update before it gives up (``auto_update.after_failed_start``): a release whose
server cannot start still updates.

On Windows a start that ran then names each uv folder in an app's private copy of AppData, a copy of cad that app
runs instead of this one or uv's leftovers, to delete (``doctor.private_folders``): a line each, on stderr. It never
deletes one.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad server"
COMMANDS = ("start", "stop", "status")


def _port(parser: argparse.ArgumentParser, help: str = argparse.SUPPRESS) -> None:  # noqa: A002 - argparse's word
    parser.add_argument("--port", type=int, default=None, help=help)


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server._internal.consent import add_yes
    from cad_server.engine.cli import VERBS

    parser = command_parser(prog, description="The cad server, which builds, keeps and serves your documents: "
                                              "start it, stop it, or say what it runs.")
    _port(parser)  # bare ``cad server --port N``'s (see the module)
    parser.add_argument("--rotate-token", action="store_true",
                        help="replace the page token: every link and browser session made before stops working, in "
                             "the server running too; asked first")
    add_yes(parser, "with --rotate-token, replace the token")
    commands = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}")
    start = commands.add_parser("start", help="start the cad server where it is not running",
                                description="Start the cad server, detached, where it is not running: one of an "
                                            "older release is replaced (stopped first, its work cut short), and one "
                                            "of a newer release is joined, left running. Pages open on the server "
                                            "replaced are served on the same port by the one that starts.")
    _port(start, "the HTTP port the server takes, refused when another process holds it (else CAD_ENGINE_PORT, else "
                 "3245 or the port it rolled to); 0 takes any free port")
    start.add_argument("--foreground", action="store_true",
                       help="run it in this process, its log on this terminal, until it is stopped")
    for verb in ("stop", "status"):
        help_text, arguments, _runner = VERBS[verb]
        arguments(commands.add_parser(verb, help=help_text, description=help_text))
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.engine.cli import VERBS, answered

    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command in ("stop", "status"):
        return answered(VERBS[args.command][2], args, f"{prog} {args.command}")
    return answered(_start, args, f"{prog} start" if args.command else prog)


def _start(args: argparse.Namespace, prog: str) -> int:
    """``cad server start``: this release's server started, detached (``client.start``), and that said; with
    ``--foreground``, or bare ``cad server``, run here until it stops, once room is made for it (``client.make_way``).
    ``--rotate-token`` first."""
    from cad.engine import client
    from cad_server.engine.cli import Failed

    if args.port is not None and not 0 <= args.port <= 65535:
        raise Failed("--port must be between 0 and 65535", 2)
    if args.rotate_token:
        _rotate(args, prog.removesuffix(" start"))
    if args.command == "start" and not args.foreground:
        # Imported before the server is spawned: an update it begins changes this cad's files under this process, and a
        # start that fails still says its one line.
        from cad_server._internal import auto_update
        from cad_server.cli.doctor import private_folders

        try:
            print(client.start(args.port), flush=True)
        except Exception:
            target = auto_update.after_failed_start()
            if target is not None:
                print(f"cad: updating cad to {target}, which then starts the server", file=sys.stderr, flush=True)
            raise
        for line in private_folders():  # Windows: uv's folder in an app's private copy, named, never deleted
            print(f"cad: {line}", file=sys.stderr, flush=True)
        return 0
    running = client.make_way()
    if running is not None:
        print(running)
        return 0
    from cad_server.engine.daemon import main as serve

    return serve([], port=args.port, foreground=True, rotated=bool(args.rotate_token))


def _rotate(args: argparse.Namespace, prog: str) -> None:
    """``--rotate-token``: the page token replaced (``daemon.rotate_token``), which retires every link and session
    made before, for good: asked first (``cad_server._internal.consent``)."""
    from cad_server._internal.consent import confirm, retry
    from cad_server.engine.cli import Failed
    from cad_server.engine.daemon import rotate_token

    confirm("replacing the page token", "Replace the page token?", yes=bool(args.yes), as_json=False,
            command=retry(prog, ["--rotate-token", *(["--port", str(args.port)] if args.port is not None else [])]),
            preview=[f"{prog} --rotate-token replaces the page token: every viewer link and browser session made "
                     "with the one it has now stops working at once, in the server running too, and each page needs a "
                     "new link (cad viewer prints one). This cannot be undone."])
    try:
        rotated = rotate_token(told=lambda line: print(f"cad: {line}", file=sys.stderr, flush=True))
    except (OSError, ValueError) as error:
        raise Failed(f"cannot replace the page token: {getattr(error, 'strerror', None) or error}") from None
    if rotated is None:
        raise Failed("cannot replace the page token: there is no state folder to keep it in")
    print("cad: a new page token: every link and browser session made before no longer works", file=sys.stderr,
          flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
