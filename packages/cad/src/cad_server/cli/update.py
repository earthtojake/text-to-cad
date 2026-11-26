"""``cad update`` -- cad, and only cad, updated now to the newest release of its major version, by the server that runs
(``{"op": "update"}``, ``Daemon.update``): it asks PyPI for the newest release of this cad's major that is not yanked
and, where it is newer, begins cad's own update at once (``cad_server._internal.auto_update``: ``asked``, ``begin``),
even with automatic updates off; where nothing in this major is newer, it says so. It never crosses a major: where a
release of a higher major is out, it adds one line naming it and where the migration guides are
(``auto_update.MAJOR_LINE``). Where PyPI cannot be reached, the update runs all the same, and says what it got.
It never runs the install command. The server does the work where one runs: an agent's shell may not reach the network
or change cad's folders, and the server, outside that sandbox, may; so the command asks no permission.

Where no server runs, the command judges and begins the update itself, in this process, the same way. Its worker then
starts no server: an update typed with none running leaves none running. In a shell whose sandbox cannot start a server
(``client._sandboxed``) it does not try, and says so in the one line ``client.SANDBOXED``. It never starts a server
first to update through it.

Then it waits for the update to end, saying once on stderr that cad is updating (``step``), and says how it ended (a
failure: why, what to do and where its log is, ``ended``), as the server that answers afterwards tells it (``{"op":
"update", "begin": false}``), else as the attempt's record in the state folder does; ``WAIT_SECONDS`` at most. cad's
installer (uv, pipx) upgrades cad in place meanwhile, by the worker of the release it updates to, run from uv's
cache; this process, which imported what it needs before, is left running by the update on Windows (it sends its
``pid``: ``auto_update.spared``). Where the update left no cad that runs and cad is being installed again whole, it
says so and ends (``REPAIRING``): the worker waits for it to.

A cad that is no global install does not update itself, and is refused. ``cad update auto [status|on|off]`` shows or
changes whether cad updates itself (``cad_server.cli.auto_update``).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_PROG = "cad update"
# How long the server may take to answer a question, and to judge the update and begin it: PyPI asked now (5 s at
# most), uv's build of the environment the worker runs from (``auto_update.build``: 15 minutes at most) and the rest.
ASK_SECONDS = 30.0
BEGIN_SECONDS = ASK_SECONDS + 900.0
# How long the command waits for the update to end, and how often it looks: past the longest build and the switch.
WAIT_SECONDS = 1800.0
LOOK_SECONDS = 0.5
NOT_A_TOOL = ("refused: this cad is not a global install, so it does not update itself: update it the way it was "
              "installed (for pip, `pip install --upgrade cad`), or install it globally with `uv tool install cad`")
# Where the update left no cad that runs and cad is being installed again whole (``auto_update_helper.reinstall``,
# which waits for this process to leave cad's environment): the command ends, and the person looks later.
REPAIRING = ("the update of cad {was} left cad unable to run, so cad is being installed again: run `cad --version` in "
             "a few minutes to see where it ended{log}")
OLD_SERVER = ("the cad server running cannot update cad: run `cad server stop`, then `cad server start`, then "
              "`cad update` again")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server.cli import auto_update

    parser = command_parser(prog=prog, usage=f"%(prog)s [-h]\n       {prog} auto [{{status,on,off}}]",
                            description=(
        "cad installs every newer release of its major version by itself, and never a new major version. "
        "`cad update` updates cad now to the newest release of its major version, even with "
        "automatic updates off: cad asks PyPI, and the installer that made it (uv, pipx) upgrades cad in place. A cad server that was running restarts "
        "on it at once, stopping what is in flight; with none running, none is started. By itself, cad updates as "
        "the server next starts once a newer release is out. `cad update auto` shows or changes whether cad updates "
        "itself."))
    commands = parser.add_subparsers(dest="command", metavar="{auto}")
    auto_update.arguments(commands.add_parser("auto", prog=f"{prog} auto",
                                              help="show or change whether cad updates itself: status, on, off",
                                              description=auto_update.DESCRIPTION))
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    if args.command == "auto":
        from cad_server.cli import auto_update as switch

        return switch.switch(args.action, prog=f"{prog} auto")
    from cad.engine import client
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, classify, write

    if auto_update.global_install() is None:  # this command's own cad
        return write(Failure(NOT_A_TOOL), prog=prog, as_json=False)
    try:  # never starts one
        answer = client.request({"op": "update", "pid": os.getpid()}, timeout=BEGIN_SECONDS)
    except client.NotRunning:
        if client._sandboxed():  # noqa: SLF001 - nor can it update cad
            return write(classify(client.NotRunning(client.SANDBOXED)), prog=prog, as_json=False)
        answer = here(auto_update)
    except ConnectionError as error:
        return write(classify(error), prog=prog, as_json=False)
    failed = answer.get("failed") if isinstance(answer, dict) else "the cad server gave no answer"
    if failed:
        return write(Failure(OLD_SERVER if str(failed).startswith("unknown request") else str(failed)), prog=prog,
                     as_json=False)
    higher = answer.get("higher") if isinstance(answer.get("higher"), str) else None
    if isinstance(answer.get("newest"), str):
        print(f"cad {answer['newest']} is {newest_of(answer['newest'], higher)}")
        if higher:
            print(auto_update.MAJOR_LINE.format(release=higher))
        return 0
    target, was, since = answer.get("updating"), answer.get("from"), answer.get("since")
    if not (isinstance(target, (str, type(None))) and "updating" in answer and isinstance(was, str)
            and isinstance(since, (int, float))):
        return write(Failure(f"the cad server's answer was not understood: {answer}"), prog=prog, as_json=False)
    code = wait(lambda: look(client, auto_update), was, float(since),
                said=lambda words: write(Failure(words), prog=prog, as_json=False), higher=higher,
                server=not answer.get("here"))
    if code == 0 and higher:
        print(auto_update.MAJOR_LINE.format(release=higher))
    return code


def newest_of(release: str, higher: str | None) -> str:
    """What ``release`` is, said after it: the newest release, or, where a release of a higher major is out
    (``higher``), the newest of its own major."""
    return f"the newest {release.split('.', 1)[0]}.x release" if higher else "the newest release"


def here(auto_update: Any) -> dict[str, Any]:
    """The update judged and begun in this process, where no server runs: the server's answer to ``{"op": "update"}``
    in shape (``Daemon.update``), ``since`` the attempt's own ``at``. The helper is told to start no server."""
    judged = auto_update.asked()
    if "updating" not in judged:
        return judged
    found = auto_update.begin(judged["updating"], start=False)
    if found is None:
        return {"failed": f"the update could not begin, so cad {judged['from']} stays as it is"}
    return {**judged, "updating": found["release"], "since": found["at"], "here": True}


def look(client: Any, auto_update: Any) -> tuple[str | None, Any, Any, bool]:
    """What can be seen of the update now: ``(the release of the server that answers, the last attempt, the release
    an update waits to begin for, whether the server said)``. Asked of the server that answers, of any release
    (``{"op": "update", "begin": false}``); where none answers, or one that does not know the request, the attempt as the
    state folder keeps it (a sandbox may refuse that read: then none)."""
    running = None
    try:
        connection = client._connect()  # noqa: SLF001 - any release: the one after the update is another
    except ConnectionError:
        connection = None
    if connection is not None:
        running = connection.release
        try:
            answer = client._within(ASK_SECONDS, lambda: client._exchange(  # noqa: SLF001
                connection, {"op": "update", "begin": False}))
        except (ConnectionError, OSError, ValueError):
            answer = None
        if isinstance(answer, dict) and answer.get("ok") is True:
            return answer.get("version") or running, answer.get("last"), answer.get("waiting"), True
    return running, auto_update.last(), None, False


def wait(looked: Callable[[], tuple[str | None, Any, Any, bool]], was: str, since: float, *,
         said: Callable[[str], int], seconds: float = WAIT_SECONDS, every: float = LOOK_SECONDS,
         clock: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None,
         higher: str | None = None, server: bool = True) -> int:
    """The update that began at ``since`` (by the server's clock: an attempt begun then or later serves it) waited for
    until its record says it ended, each step said once on stderr as it begins (``step``; ``server``: one was running,
    and is restarted), and the end said in one line (``higher``: a release of a higher major is out); or, where it is
    being installed again whole, that (``REPAIRING``), at once: its exit status."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + seconds
    told_of: set[str] = set()
    while True:
        running, record, waiting, told = looked()
        attempt = record if isinstance(record, dict) and isinstance(record.get("at"), (int, float)) \
            and record["at"] >= since else None
        if attempt is not None and attempt.get("outcome") == "underway":
            if attempt.get("phase") == "repairing":  # the worker waits for this process to end (on Windows)
                return said(REPAIRING.format(was=was, log=log_line()))
            step(attempt, was, told_of, server=server)
        if attempt is not None and attempt.get("outcome") not in (None, "underway"):
            return ended(attempt, was, running, said, higher=higher)
        if told and attempt is None and not waiting:
            return said(f"the update could not begin, so cad {was} stays as it is")
        if clock() >= deadline:
            return said(f"the update of cad {was} is still underway after {seconds / 60:.0f} minutes: run "
                        "`cad --version` later to see where it ended")
        sleep(every)


def step(attempt: dict[str, Any], was: str, told_of: set[str], *, server: bool) -> None:
    """The update underway, once its record says it is switching (its ``phase``), said once on stderr (``told_of``: what
    was said), naming the release it is for."""
    if "switching" in told_of or attempt.get("phase") != "switching":
        return
    target = attempt.get("release")
    named = "the newest release" if target in (None, "latest") else f"cad {target}"
    told_of.add("switching")
    print(f"cad: updating cad {was} to {named}" + (", then restarting the cad server" if server else ""),
          file=sys.stderr, flush=True)


def log_line() -> str:
    """``; its log: <the worker's log>`` where there is one, else nothing."""
    from cad.engine.places import state_dir
    from cad_server._internal import auto_update

    log = state_dir() / auto_update.LOG
    return f"; its log: {log}" if log.is_file() else ""


def ended(attempt: dict[str, Any], was: str, running: str | None, said: Callable[[str], int], *,
          higher: str | None = None) -> int:
    """An attempt that ended, said in one line: its exit status. The release it names is the one installed, where it
    ended well (an update begun without PyPI's answer finds out only then). One that failed for a cause it names says
    it in plain words (``auto_update.in_words``), then what to do (``auto_update.advice``, by who made the global
    install), then where the worker's log is; one whose new server did not start, that cad went back and runs the
    release before still. One that names no cause says uv's last words (its ``detail``) and the server, of which
    nothing is said for an attempt that was to start none (``"start": false``: none ran when it began)."""
    from cad_server._internal import auto_update

    target = attempt.get("release")
    if attempt.get("outcome") in ("installed", "current"):
        done = (f"cad {target} is {newest_of(str(target), higher)}" if target == was
                else f"cad {was} updated to {target}")
        if str(attempt.get("started", "")).startswith("not started"):
            return said(f"{done}, but the cad server did not start again: run `cad server start`")
        print(done)
        return 0
    newest = "the newest release" if target == "latest" else target
    word = auto_update.cause(attempt)
    if word is not None:
        installer = attempt.get("installer")
        if installer not in auto_update.INSTALLERS:
            found = auto_update.global_install()
            installer = found.installer if found is not None else None
        why, what = auto_update.in_words(word, installer), auto_update.advice(word, installer)
        if word == "start_failed":  # the release before named: it is the one that runs
            why += f" (cad {was})"
            if attempt.get("restored") is False:
                why, what = f"{why}, but its server did not start either", "`cad server start` starts it"
        return said(f"could not update cad {was} to {newest}, as {why}: {what}{log_line()}")
    if running:
        serving = f"; cad {running} is running"
    else:
        serving = "" if attempt.get("start") is False else "; no cad server is running: run `cad server start`"
    return said(f"could not update cad {was} to {newest}: {attempt.get('detail') or 'no reason given'}{serving}")


if __name__ == "__main__":
    raise SystemExit(main())
