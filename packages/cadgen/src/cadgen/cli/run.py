"""``cadgen run SCRIPT.py [ARGS...]``: a model script run in its project's environment, on the selected
engine.

The selected engine (``--port``, else ``CADGEN_PORT``, else 3245) is started when none answers, as the
MCP bootstrap starts it (``client.connect(start=True)``: an older release's idle engine retired first),
and asked what it runs as (its hello: its release, installation, Python line and cadgen's source). The
script's project environment -- its declared dependencies and that engine's own cadgen, made by uv in
the cache folder's ``envs/`` -- is made when it is missing or out of date (``cadgen._internal.projects``),
and the script runs there as ``python SCRIPT.py ARGS...``, in the caller's folder and environment with
``CADGEN_PORT`` set: from there it is any model run, a client of the engine, whose worker runs in that
environment. ``--refresh`` makes the environment again; ``--show-env`` prints its folder instead of
running the script.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PROG = "cadgen run"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog, description="Build a model: run SCRIPT.py in its project's environment (the project's dependencies "
                               "and the engine's cadgen, made by uv once), on the selected engine, started when none runs.")
    parser.add_argument("--port", type=int, default=None, help="select the engine port (else CADGEN_PORT, else 3245)")
    parser.add_argument("--refresh", action="store_true", help="make the project's environment again first")
    parser.add_argument("--show-env", action="store_true",
                        help="print the project environment's folder (made first when it is missing) and run nothing")
    parser.add_argument("script", metavar="SCRIPT.py", help="the model script, run as `python SCRIPT.py` runs it")
    parser.add_argument("args", nargs=argparse.REMAINDER, metavar="ARGS", help="the script's own arguments")
    return parser


def _say(prog: str, line: object) -> None:
    print(f"{prog}: {line}", file=sys.stderr, flush=True)


def _split(argv: list[str]) -> tuple[list[str], list[str]]:
    """``argv`` as the command's own arguments, up to and with the script, and the script's: every one
    after it, as written (argparse would take a ``--`` of the script's as its own)."""
    value = False
    for index, token in enumerate(argv):
        if value:
            value = False
        elif token == "--port":
            value = True
        elif token == "--":
            return argv[:index + 2], argv[index + 2:]
        elif token == "-" or not token.startswith("-"):
            return argv[:index + 1], argv[index + 1:]
    return argv, []


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    own, rest = _split(list(sys.argv[1:] if argv is None else argv))
    args = build_parser(prog).parse_args(own)
    args.args = rest
    script = Path(args.script)
    if not script.is_file():
        _say(prog, f"no script {args.script}" if not script.exists() else f"{args.script} is not a file")
        return 2
    if script.suffix.lower() != ".py":
        _say(prog, f"{args.script} is not a Python script (.py)")
        return 2
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            _say(prog, "--port must be between 1 and 65535")
            return 2
        os.environ["CADGEN_PORT"] = str(args.port)
    from cadgen._internal import projects
    from cadgen.engine import client, daemon

    try:
        port = daemon.selected_port()
    except ValueError as error:
        _say(prog, error)
        return 2
    try:
        connection = client.connect(start=True)
    except (ConnectionError, OSError) as error:  # none could start (a sandbox's, the daemon's own line), or none meets
        _say(prog, error)
        return 1
    said = dict(connection.engine)
    connection.close()
    try:
        engine = projects.Engine.said(said)
        project = projects.find(script)
        python = projects.python_for(project, engine)
        if args.refresh:
            _free(projects.environment(project, engine, python), port, args.script)
        env = projects.ensure(project, engine, python, refresh=args.refresh)
    except projects.Refused as refused:
        _say(prog, refused)
        return 1
    if args.show_env:
        print(env)
        return 0
    python_path = str(projects.interpreter(env))
    command = [python_path, args.script, *args.args]
    environment = {**os.environ, "CADGEN_PORT": str(port)}
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":  # no exec on Windows: a child, and its exit code
        return subprocess.call(command, env=environment)
    try:
        os.execve(python_path, command, environment)
    except OSError as error:
        _say(prog, f"cannot run {python_path}: {error.strerror or error}")
        return 1
    return 1  # not reached


def _free(env: Path, port: int, script: str) -> None:
    """Refuse to make ``env`` again while the engine runs a worker in it: a worker reads its installed
    packages once, as it starts, so it would go on with what it loaded beside what the new environment
    installs (and on Windows the files it holds cannot be removed)."""
    from cadgen._internal.projects import Refused
    from cadgen.engine import client

    try:
        status = client.request({"op": "status"}, start=False) or {}
    except (ConnectionError, OSError, ValueError):
        return
    held = [Path(str(row.get("script"))).name for row in status.get("workers") or []
            if isinstance(row, dict) and row.get("alive", True) and _inside(row, env)]
    if isinstance(status.get("standby"), dict) and _inside(status["standby"], env):
        held.append("its standby")
    if held:
        raise Refused(f"the engine on port {port} runs {' and '.join(held)} in this project's environment: run "
                      f"`{client.stop_command(port)}`, then `cadgen run --refresh {script}`")


def _inside(row: dict, env: Path) -> bool:
    """Whether the worker ``row`` of the engine's status runs in ``env`` (its Python's prefix)."""
    prefix = row.get("prefix")
    return isinstance(prefix, str) and bool(prefix) and \
        os.path.normcase(os.path.realpath(prefix)) == os.path.normcase(os.path.realpath(env))


if __name__ == "__main__":
    raise SystemExit(main())
