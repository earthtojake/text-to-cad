"""``cadgen run ARGS`` -- ``python ARGS`` in the CAD kernel environment: a model script
(``cadgen run model.py``), ``-m`` or ``-c``.

The environment is the installation's base (``cadgen._internal.base``): cadgen with the CAD kernel, on
the engine's Python -- made once, by uv, the first time it is asked for, and said in a line while it
is made; an installation that carries the kernel itself is its own. Its Python runs the arguments, in
the caller's folder and environment: from there the script is any program that calls its models, a
client of its installation's engine, and the engine's worker for it runs in the same environment.

The ``cadgen`` command (``cadgen._internal.proxy``) runs this verb with the installation it picks.
"""

from __future__ import annotations

import os
import sys

PROG = "cadgen run"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["-h"], ["--help"]):
        sys.stdout.write("usage: cadgen run SCRIPT.py [ARGS...] | -m MODULE [ARGS...] | -c CODE\n\n"
                         "Run python with the arguments in the CAD kernel environment (a model script builds by "
                         "running it).\n")
        return 0
    from cadgen._internal import base

    try:
        env = base.ensure(told=lambda line: print(f"{PROG}: {line}", file=sys.stderr, flush=True))
    except base.Refused as refused:
        print(f"{PROG}: {refused}", file=sys.stderr, flush=True)
        return 1
    assert env is not None  # made, or refused
    command = [env.python, *args]
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
