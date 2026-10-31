"""``cad``, the command (``~/.local/bin/cad``): the current installation, run.

The proxy's ``sh`` runs this module with the current installation's interpreter
(``cad_server._internal.installations``: ``current``), or with no current one the interpreter registered
last; it runs one installation's ``cad`` console script with the arguments:

a. the current installation, while its interpreter and console script are there;
b. else the installation registered last (no installation is current yet: one from before there was
   a current one).

There is one installation a command runs, and nothing here compares versions: a ``+<version>`` as the
first argument -- what the skills stamp -- is taken off and runs the current installation like any
other command. With no installation at all it says, in one line, the command that installs one.

The console script runs by ``exec``, so the proxy adds no process and no output of its own -- or,
when the installation chosen is the one this interpreter is (the usual case), as its console script
would, in this process. A development or source registration cannot know the version it is
registered as (it reports its release's), so it runs with ``CAD_INSTALLATION_VERSION`` set to its
record's (``installations.named``): its ``doctor``, its records and its engine name it rightly, and
the processes it starts, the same installation, inherit it.
"""

from __future__ import annotations

import os
import sys

from cad_server._internal.launch import LAUNCHER

# The ``cad`` command's own words (``installations._SH``) when no installation is registered.
NONE_INSTALLED = ("text-to-cad is not installed: run `" + " ".join(LAUNCHER) + " texttocad-server "
                  "cad doctor` once, outside any sandbox or with its permission")


class Refused(Exception):
    """What the proxy says instead of running anything: one line."""


def arguments(args: list[str]) -> list[str]:
    """The arguments to run: a first ``+<version>`` (a skill's stamp) taken off."""
    return args[1:] if args and args[0].startswith("+") else args


def _same(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def choose(found: dict | None, records: list[dict]) -> dict:
    """The record to run: the current installation's (``found``), else the one registered last."""
    from cad_server._internal.installations import alive

    if found is not None:
        return found
    live = [record for record in records if alive(record)]
    if not live:
        raise Refused(NONE_INSTALLED)
    return max(live, key=lambda record: str(record.get("registered") or ""))


def command(record: dict, args: list[str]) -> list[str]:
    """What runs: the installation's console script (its record's ``cadgen``, the key every release's
    records name it by)."""
    return [record["cadgen"], *args]


def main(argv: list[str] | None = None) -> int:
    args = arguments(list(sys.argv[1:] if argv is None else argv))
    try:
        from cad_server._internal.installations import current, records

        record = choose(current(), records())
    except Refused as refusal:
        print(refusal, file=sys.stderr)
        return 1
    run = command(record, args)
    from cad_server._internal.installations import NAME_ENV, named as told

    if told(record):  # an installation that cannot know its own name: told it
        os.environ[NAME_ENV] = told(record)
    else:  # a release knows its own, whatever another installation's process that ran this was told
        os.environ.pop(NAME_ENV, None)
    if _same(sys.prefix, record["prefix"]):
        # The installation this interpreter is: its console script's work, here, without a second start.
        sys.argv = run
        from cad_server.cli import main as cad

        return cad(args)
    if os.name == "nt":  # no exec on Windows: a child, and its exit code
        import subprocess

        return subprocess.call(run, env=os.environ)
    try:
        os.execve(run[0], run, os.environ)
    except OSError as error:
        print(f"cad: cannot run {run[0]}: {error.strerror or error}", file=sys.stderr)
        return 1
    return 1  # not reached


if __name__ == "__main__":
    sys.exit(main())
