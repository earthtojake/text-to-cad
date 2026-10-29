"""Select an installed cadgen CLI by +VERSION, otherwise the release the device runs
(``installations.current``: the pointer, else the newest live registered release), else the newest
live registration.

Server selection is independent: CADGEN_PORT (or --port) chooses its address, and client and
engine meet by protocol, never by release. The launcher never searches running engines or
chooses a Python interpreter for model scripts.
"""

from __future__ import annotations

import os
import sys

# What the command says when the release it names is not installed, and when none is (``refusal``): first
# the install command, which installs text-to-cad and brings it up to date in every agent app on the
# computer, then the one command that registers a release alone. The ``cadgen`` script says the same
# when no installation is alive (``installations._SH``, ``_CMD``).
NOT_INSTALLED = ("cadgen {version} is not installed: run `{install}`, or, to register exactly this release "
                 "without changing any agent app, `uvx --no-config --managed-python --python 3.13 "
                 "--from cadgen=={version} cadgen doctor`, once, outside any sandbox or with its permission")
NONE_INSTALLED = ("cadgen is not installed: run `{install}`, or, to register the latest release without "
                  "changing any agent app, `uvx --no-config --managed-python --python 3.13 --from cadgen "
                  "cadgen doctor`, once, outside any sandbox or with its permission")


class Refused(Exception):
    """What the proxy says instead of running anything: one line."""


def refusal(version: str | None, system: str | None = None) -> str:
    """That ``version`` (``None``: any release) is not installed, with the install command for this
    computer (or for ``system``, an ``os.name``): ``NOT_INSTALLED`` or ``NONE_INSTALLED``."""
    from cadgen.updates import command  # the install command's one definition, imported only to refuse

    if version is None:
        return NONE_INSTALLED.format(install=command(system))
    return NOT_INSTALLED.format(version=version, install=command(system))


def version_key(version: str) -> tuple:
    """Newest last, using ``cadgen.engine.daemon.rank``'s release ordering: a release above its own pre-releases
    and development builds (``0.8.0-dev.<time>``), which sort by their time; a version that is no
    PEP 440 version below every one that is."""
    from cadgen.engine.daemon import rank

    ranked = rank(version)
    return (ranked is not None, ranked or ())


def named(args: list[str], environ) -> tuple[str | None, list[str]]:
    """The version the command names (a-b), and the arguments left to run. ``Refused`` for one
    that is no version: never echoed into the command the refusal names."""
    if args and args[0].startswith("+") and len(args[0]) > 1:
        return _version(args[0][1:], "its first argument"), args[1:]
    return None, args


def _version(version: str, source: str) -> str:
    """``version`` when it is one (``installations.VERSION``), else ``Refused``, saying where it came from."""
    from cadgen._internal.installations import VERSION

    if not VERSION.fullmatch(version):
        raise Refused(f"cadgen: {source} names no cadgen version: {ascii(version[:64])}")
    return version


def _same(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def choose(version: str | None, records: list[dict], current: dict | None = None) -> dict:
    """The explicitly named installation, else the ``current`` one (``installations.current``), else
    the newest installed release; no server discovery."""
    from cadgen._internal.installations import alive

    live = [record for record in records if alive(record)]
    if version is not None:
        for record in live:
            if record["version"] == version:
                return record
        raise Refused(refusal(version))
    if current is not None:
        for record in live:
            if record["version"] == current["release"] and _same(record["cadgen"], current["cadgen"]):
                return record
    if not live:
        raise Refused(refusal(None))
    return max(live, key=lambda record: version_key(record["version"]))


def command(record: dict, args: list[str]) -> list[str]:
    """Dispatch CLI arguments to the selected installed console script."""
    return [record["cadgen"], *args]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        from cadgen._internal.installations import current, records

        version, args = named(args, os.environ)
        found = records()
        record = choose(version, found, None if version is not None else current())
    except Refused as refusal:
        print(refusal, file=sys.stderr)
        return 1
    run = command(record, args)
    from cadgen._internal.installations import NAME_ENV, named as told

    if told(record):  # an installation that cannot know its own name: told it
        os.environ[NAME_ENV] = told(record)
    else:  # a release knows its own, whatever another installation's process that ran this was told
        os.environ.pop(NAME_ENV, None)
    if run[0] == record["cadgen"] and _same(sys.prefix, record["prefix"]):
        # The installation this interpreter is: its console script's work, here, without a second start.
        sys.argv = run
        from cadgen.cli import main as cadgen

        return cadgen(args)
    if os.name == "nt":  # no exec on Windows: a child, and its exit code
        import subprocess

        return subprocess.call(run, env=os.environ)
    try:
        os.execve(run[0], run, os.environ)
    except OSError as error:
        print(f"cadgen: cannot run {run[0]}: {error.strerror or error}", file=sys.stderr)
        return 1
    return 1  # not reached


if __name__ == "__main__":
    sys.exit(main())
