"""``cad update`` -- cad, and only cad, updated to the newest release now, by the server that runs (``{"op": "update"}``,
``Daemon.update``): it asks PyPI which release is newest and, where a newer one is out, begins cad's own update as soon
as nothing is in flight (``cad_server._internal.auto_update``: ``asked``, ``begin``), even with automatic updates off.
Where PyPI cannot be reached, the update runs all the same, and says what it got. It never runs the install command.
The server does the work where one runs: an agent's shell may not reach the network or change cad's folders, and the
server, outside that sandbox, may; so the command asks no permission.

Where no server runs, the command judges and begins the update itself, in this process, the same way. Its helper then
starts no server: an update typed with none running leaves none running. In a shell whose sandbox cannot start a server
(``client._sandboxed``) it does not try, and says so in the one line ``client.SANDBOXED``. It never starts a server
first to update through it: a start may begin an automatic update, which can run the install command.

Then it waits for the update to end and says how it ended, as the server that answers afterwards tells it
(``{"op": "update", "begin": false}``), else as the attempt's record in the state folder does; ``WAIT_SECONDS`` at
most. On Windows too: this command is a running ``cad.exe`` of the tool, which the update renames aside before the
installer runs (``cad_server._internal.auto_update_helper``). Everything the wait uses is imported before the update
begins: from then on the files of this cad's environment change under it.

A cad that is no global install does not update itself, and is refused.

``cad update auto [status|on|off]`` shows or changes whether cad updates itself (``cad_server.cli.auto_update``).
"""

from __future__ import annotations

import argparse
import threading  # noqa: F401 - the client's bounded request (``client._within``) imports it: before the update begins
import time
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_PROG = "cad update"
# How long the server may take to judge it: PyPI asked now (5 s at most) and the rest.
ASK_SECONDS = 30.0
# How long the command waits for the update to end, and how often it looks.
WAIT_SECONDS = 600.0
LOOK_SECONDS = 0.5
NOT_A_TOOL = ("refused: this cad is not a global install, so it does not update itself: update it the way it was "
              "installed (for pip, `pip install --upgrade cad`), or install it globally with `uv tool install cad`")
OLD_SERVER = ("the cad server running cannot update cad: run `cad server stop`, then `cad server start`, then "
              "`cad update` again")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server.cli import auto_update

    parser = command_parser(prog=prog, usage="%(prog)s [-h] [auto [{status,on,off}]]", description=(
        "Update cad to the newest release now, even with automatic updates off. cad asks PyPI which release is "
        "newest and, once nothing is running, installs it. A cad server that was running starts again; with none "
        "running, none is started. `cad update auto` shows or changes whether cad updates itself."))
    commands = parser.add_subparsers(dest="command", metavar="{auto}")
    auto_update.arguments(commands.add_parser("auto", prog=f"{prog} auto",
                                              help="show or change whether cad updates itself: status, on, off",
                                              description=auto_update.DESCRIPTION))
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    if args.command == "auto":
        from cad_server.cli import auto_update as switch

        return switch.switch(args.action, prog=f"{prog} auto")
    from cad.engine import client
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, classify, write

    if auto_update.global_install() is None:  # this command's own cad
        return write(Failure(NOT_A_TOOL), prog=prog, as_json=False)
    try:
        answer = client.request({"op": "update"}, timeout=ASK_SECONDS)  # never starts one
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
    if isinstance(answer.get("newest"), str):
        print(f"cad {answer['newest']} is the newest release")
        return 0
    target, was, since = answer.get("updating"), answer.get("from"), answer.get("since")
    if not (isinstance(target, (str, type(None))) and "updating" in answer and isinstance(was, str)
            and isinstance(since, (int, float))):
        return write(Failure(f"the cad server's answer was not understood: {answer}"), prog=prog, as_json=False)
    return wait(lambda: look(client, auto_update), was, float(since),
                said=lambda words: write(Failure(words), prog=prog, as_json=False))


def here(auto_update: Any) -> dict[str, Any]:
    """The update judged and begun in this process, where no server runs: the server's answer to ``{"op": "update"}``
    in shape (``Daemon.update``), ``since`` the attempt's own ``at``. The helper is told to start no server."""
    judged = auto_update.asked()
    if "updating" not in judged:
        return judged
    found = auto_update.begin(judged["updating"], start=False)
    if found is None:
        return {"failed": f"the update could not begin, so cad {judged['from']} stays as it is"}
    return {**judged, "updating": found["release"], "since": found["at"]}


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
         clock: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None) -> int:
    """The update that began at ``since`` (by the server's clock: an attempt begun then or later serves it) waited for
    until its record says it ended, and that said in one line: its exit status."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + seconds
    while True:
        running, record, waiting, told = looked()
        attempt = record if isinstance(record, dict) and isinstance(record.get("at"), (int, float)) \
            and record["at"] >= since else None
        if attempt is not None and attempt.get("outcome") not in (None, "underway"):
            return ended(attempt, was, running, said)
        if told and attempt is None and not waiting:
            return said(f"the update could not begin, so cad {was} stays as it is")
        if clock() >= deadline:
            return said(f"the update of cad {was} is still underway after {seconds / 60:.0f} minutes: run "
                        "`cad --version` later to see where it ended")
        sleep(every)


def ended(attempt: dict[str, Any], was: str, running: str | None, said: Callable[[str], int]) -> int:
    """An attempt that ended, said in one line: its exit status. The release it names is the one installed, where it
    ended well (an update begun without PyPI's answer finds out only then). Of an attempt that was to start no server
    (``"start": false``: none ran when it began), nothing is said of the server."""
    target = attempt.get("release")
    if attempt.get("outcome") in ("installed", "current"):
        done = f"cad {target} is the newest release" if target == was else f"cad {was} updated to {target}"
        if str(attempt.get("started", "")).startswith("not started"):
            return said(f"{done}, but the cad server did not start again: run `cad server start`")
        print(done)
        return 0
    if running:
        serving = f"; cad {running} is running"
    else:
        serving = "" if attempt.get("start") is False else "; no cad server is running: run `cad server start`"
    newest = "the newest release" if target == "latest" else target
    return said(f"could not update cad {was} to {newest}: {attempt.get('detail') or 'no reason given'}{serving}")


if __name__ == "__main__":
    raise SystemExit(main())
