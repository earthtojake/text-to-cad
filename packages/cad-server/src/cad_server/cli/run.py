"""``cad run [--with REQ]... ARGS`` -- ``python ARGS`` in the CAD kernel environment: a model script
(``cad run model.py``), ``-m`` or ``-c``.

The environment is the installation's base (``cad_server._internal.base``): the library with the CAD
kernel (``cad[build123d]``), on the engine's Python -- made once, by uv, the first time it is asked for, and said in a line
while it is made: by the device's engine when one runs (an agent's sandbox may not let this command write
the cache folder; the engine a host's CAD app started runs outside it), else here; an installation that
carries the kernel itself is its own. A model that needs packages the base lacks names them, in its
script's inline metadata (PEP 723: a ``# /// script`` block's ``dependencies``) or with ``--with REQ``
(repeated, or a comma-separated list, as ``uv run --with`` takes it: a name, a pin, extras, a local path
or wheel); then the environment is the one of those packages beside the base, made the same way
(``cad_server._internal.extras``), and the program it runs is told the ``--with`` it was given
(``places.RUN_WITH``), which a document it builds names to build it again. A header's ``requires-python``
the server's Python does not meet is refused in one line. Its Python runs the
arguments, in the caller's folder and environment, with the program's own folder last on its module
search path, not first (the library's ``cad._internal.program``): a project's ``cad.py`` never stands in
for the library. From there the script is any program that calls its models, a client of its
installation's engine, and the engine's worker for it runs in the same environment.

The ``cad`` command (``cad_server._internal.proxy``) runs this verb with the installation it picks.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

PROG = "cad run"
# The library's runner of a program: ``python ARGS``, the program's folder last on its module search path.
PROGRAM = "cad._internal.program"
USAGE = "usage: cad run [--with REQ]... SCRIPT.py [ARGS...] | -m MODULE [ARGS...] | -c CODE\n"


def requirements(given: list[str], rest: list[str]) -> tuple[list[str], list[str]]:
    """The packages a run names, normalized (``extras.normalized``): ``--with``'s, against the working folder,
    and the script's header's, against its folder; each once, sorted -- and ``--with``'s alone, which a
    document it builds names to build it again. ``extras.Refused`` in one line for a header that does not
    read, or a ``requires-python`` the server's Python does not meet."""
    from cad_server._internal import extras

    named = [extras.normalized(item, os.getcwd()) for item in given]
    script = Path(rest[0]) if rest and not rest[0].startswith("-") else None
    found = extras.header(script) if script is not None else {}
    wanted = found.get("requires-python")
    if wanted:
        admitted = extras.admits(wanted, platform.python_version())
        if admitted is None:
            raise extras.Refused(f"{script.name}'s requires-python, {wanted!r}, is no version specifier")
        if not admitted:
            raise extras.Refused(f"{script.name} requires Python {wanted}, and the server's is "
                                 f"{platform.python_version()}")
    folder = str(script.resolve().parent) if script is not None else os.getcwd()
    every = named + [extras.normalized(item, folder) for item in found.get("dependencies") or []]
    return sorted(set(every)), sorted(set(named))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["-h"], ["--help"]):
        sys.stdout.write(USAGE + "\nRun python with the arguments in the CAD kernel environment (a model script builds "
                                 "by running it). A model that needs packages it lacks names them in its script's "
                                 "`# /// script` header (its dependencies), or with --with REQ: the environment is "
                                 "then the one of those packages beside it, made once.\n")
        return 0
    from cad_server._internal import base, extras

    def said(line: str) -> None:
        print(f"{PROG}: {line}", file=sys.stderr, flush=True)

    try:
        given, rest = extras.arguments(args)
        if not rest:
            sys.stderr.write(f"{PROG}: name a script, -m MODULE or -c CODE\n{USAGE}")
            return 2
        every, named = requirements(given, rest)
        if every:
            env = extras.ensure(base.Installation.here(), every, told=said, engine=True)
        else:
            env = base.ensure(told=said, engine=True)
    except base.Refused as refused:
        said(str(refused))
        return 1
    assert env is not None  # made, or refused
    extras.tell(named)  # what a document the program builds says builds it again
    # The program's folder last on its path (``-P``, then the library's runner), never first.
    command = [env.python, "-P", "-m", PROGRAM, *rest]
    sys.stdout.flush()
    if os.name == "nt":  # no exec on Windows: a child, and its exit code
        import subprocess

        return subprocess.call(command)
    try:
        os.execv(env.python, command)
    except OSError as error:
        print(f"{PROG}: cannot run {env.python}: {error.strerror or error}", file=sys.stderr, flush=True)
        return 1
    return 1  # not reached


if __name__ == "__main__":
    raise SystemExit(main())
