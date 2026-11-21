"""``cad config [list] | get KEY | set KEY VALUE | unset KEY``: the settings a person keeps that an environment
variable overrides -- the server's limits and port, and how an integration finds what it reads or runs.

Each is a public variable declared a setting in ``cad._internal.environment``, which says its key (the variable's
name without ``CAD_``, in lower case: ``engine_workers``), the values it takes and whether the server reads it only
as it starts; this command has no list of its own, so a setting declared there is shown and changed here. The value in
effect is the variable's where it is set and not blank, else the saved one, else the default the code has
(``environment.resolved``), and every process reads it the same way, whoever started it.

- ``list`` (the default): every setting on a line, its key, its value in effect, where that came from
  (``environment``, ``saved``, ``default``) and the variable that overrides it; ``--json`` the same as one document,
  ``{"ok": true, "settings": [{"key", "value", "source", "variable"}]}``, a default's value ``""``.
- ``get KEY``: one setting's line; ``--json`` its document, ``{"ok": true, "key", "value", "source", "variable"}``.
  ``KEY`` is its key, or its variable's name.
- ``set KEY VALUE``: the value saved, refused before anything is written where the key names no setting or the
  value is none its kind takes (``environment.check``).
- ``unset KEY``: the saved value removed, so the default holds where the variable is unset.

Saved values are the ``config`` section of ``settings.json`` (``cad_server.settings``), written under its lock with
no server running or started. After a change to one the server reads as it starts, it says that a running server
keeps the value it started with; where the variable is set here, that it overrides the saved value in this shell.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad config"
COMMANDS = ("list", "get", "set", "unset")
RESTART = ("A running cad server keeps the value it started with: `cad server stop`, then `cad server start`, "
           "starts it with this one.")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="Show or change the settings cad keeps for this computer: the "
                                              "server's limits and port, and the programs and folders its "
                                              "integrations use. Each one's environment variable, where it is set, "
                                              "overrides it.")
    parser.add_argument("--json", action="store_true", help="the answer as one JSON document (list, get)")
    commands = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}")
    listed = commands.add_parser("list", help="every setting: its value in effect, where that came from, and its "
                                              "variable",
                                 description="Every setting: its key, its value in effect, where that came from "
                                             "(environment, saved, default), and the variable that overrides it.")
    listed.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="the settings as one JSON document")
    get = commands.add_parser("get", help="one setting's value in effect, and where it came from",
                              description="One setting's value in effect, where it came from, and its variable.")
    get.add_argument("key", metavar="KEY", help="the setting's key, or its variable's name")
    get.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                     help="the setting as one JSON document")
    put = commands.add_parser("set", help="save a setting's value",
                              description="Save a setting's value, checked first: its variable, where it is set, "
                                          "overrides it.")
    put.add_argument("key", metavar="KEY", help="the setting's key, or its variable's name")
    put.add_argument("value", metavar="VALUE", help="the value to save")
    unset = commands.add_parser("unset", help="remove a setting's saved value, so its default holds",
                                description="Remove a setting's saved value, so its default holds where its variable "
                                            "is unset.")
    unset.add_argument("key", metavar="KEY", help="the setting's key, or its variable's name")
    return parser


def _row(word: str):
    """The setting ``word`` names, or the failure naming every key."""
    from cad._internal import environment
    from cad_server._internal.cli_errors import Failure

    row = environment.setting(word)
    if row is None:
        keys = ", ".join(found.key for found in environment.settings())
        raise Failure(f"no setting {word!r}; the settings are {keys}", "invalid_argument")
    return row


def entry(row) -> dict[str, str]:
    """One setting as ``list --json`` gives it."""
    from cad._internal.environment import resolved

    value, source = resolved(row.name)
    return {"key": row.key, "value": value, "source": source, "variable": row.name}


def _lines(rows) -> list[str]:
    found = [entry(row) for row in rows]
    widths = [max(len(item[field] or "-") for item in found) for field in ("key", "value", "source")]
    return [f"{item['key'].ljust(widths[0])}  {(item['value'] or '-').ljust(widths[1])}  "
            f"{item['source'].ljust(widths[2])}  {item['variable']}" for item in found]


def _save(row, value: str | None) -> bool:
    """``value`` saved as ``row``'s (None: its saved value removed), under the settings' lock; whether one was
    saved before."""
    from cad_server.settings import update_section

    had: list[bool] = []

    def change(section: dict) -> dict | None:
        had.append(row.key in section)
        if value is None:
            section.pop(row.key, None)
        else:
            section[row.key] = value
        return section or None

    update_section("config", change)
    return had[0]


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad._internal import environment
    from cad_server._internal.cli_errors import Failure, write

    args = build_parser(prog).parse_args(list(sys.argv[1:] if argv is None else argv))
    command = args.command or "list"
    try:
        if command == "list":
            if args.json:
                sys.stdout.write(json.dumps({"ok": True, "settings": [entry(row) for row in environment.settings()]})
                                 + "\n")
            else:
                sys.stdout.write("".join(line + "\n" for line in _lines(environment.settings())))
            return 0
        row = _row(args.key)
        if command == "get":
            sys.stdout.write((json.dumps({"ok": True, **entry(row)}) if args.json else _lines([row])[0]) + "\n")
            return 0
        if command == "set":
            try:
                environment.check(row, args.value)
            except ValueError as refused:
                raise Failure(str(refused), "invalid_argument") from None
        try:
            had = _save(row, args.value if command == "set" else None)
        except OSError as error:
            from cad_server.settings import settings_path

            # An agent app's shell sandbox may refuse the state folder: said, with what to do, never a traceback.
            outside = (" Where this shell runs in an agent app's sandbox, run the command outside it."
                       if isinstance(error, PermissionError) else "")
            raise Failure(f"could not save the setting: the state folder ({settings_path().parent}) could not be "
                          f"written ({error.strerror or error}).{outside}") from None
    except Failure as failure:
        return write(failure, prog=prog, as_json=args.json)
    if command == "set":
        print(f"{row.key}: {args.value} saved")
    else:
        print(f"{row.key}: the saved value removed" if had else f"{row.key}: no value was saved")
    if row.at_start and (had or command == "set"):
        print(RESTART)
    if environment.resolved(row.name)[1] == environment.ENVIRONMENT:
        print(f"{row.name} is set in this environment and overrides the saved value here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
