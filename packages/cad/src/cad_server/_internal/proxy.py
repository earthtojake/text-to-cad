"""BRIDGE-ONLY: the module the ``cad`` command of 0.10.0 to 0.11.11 runs: the current installation, run.

That command (``~/.local/bin/cad``, revisions 9 to 11, which no release writes any more) runs this module with the current installation's
interpreter (``installations/current``), or with no current one the interpreter registered last, and it runs one
installation's ``cad`` console script with the arguments:

a. the current installation, while its interpreter and console script are there;
b. else the installation registered last (no installation is current yet: one from before there was
   a current one).

This release's copy runs only where that command is still on the computer (the install command replaces it with
the uv tool's ``cad``) while ``installations/current`` names an installation of this release (``cad_server.cli.setup``):
it runs that installation's ``cad``. Released commands run it by this name, which stays.

There is one installation a command runs, and nothing here compares versions: the arguments go to it as
they are. With no installation at all it says so, in the ``cad`` command's own words (``NONE_INSTALLED``).

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

# The ``cad`` command's own words when no installation is on record.
NONE_INSTALLED = "cad: cad is not installed on this computer."


class Refused(Exception):
    """What the proxy says instead of running anything: one line."""


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
    """What runs: the installation's console script (its record's ``cad``)."""
    return [record["cad"], *args]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
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
