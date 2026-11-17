"""``cad update`` -- cad updated to the newest release now, by the server that runs (``{"op": "update"}``,
``Daemon.update``): it reads the version feed at once and, where a newer release is out, begins cad's own update as soon
as nothing is in flight (``cad_server._internal.auto_update``: ``asked``, ``begin``), even with automatic updates off.
The server does the work, not this command: an agent's shell may not reach the network or change cad's folders, and the
server, outside that sandbox, may; so the command asks no permission.

Then it waits for the update to end (``waits``) and says how it ended, as the server that answers afterwards tells it
(``{"op": "update", "begin": false}``), else as the attempt's record in the state folder does; ``WAIT_SECONDS`` at
most. Not on Windows: there a running ``cad.exe`` of the tool makes uv's install fail halfway, and this command is one,
so it says the update began and ends. Everything the wait uses is imported before the update begins: from then on the
files of this cad's environment change under it.

It never starts a server: with none running, the one line every command says. A cad that is no uv tool does not update
itself, and is refused.
"""

from __future__ import annotations

import argparse
import os
import threading  # noqa: F401 - the client's bounded request (``client._within``) imports it: before the update begins
import time
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_PROG = "cad update"
# How long the server may take to judge it: the feed read now (5 s at most) and the rest.
ASK_SECONDS = 30.0
# How long the command waits for the update to end, and how often it looks.
WAIT_SECONDS = 600.0
LOOK_SECONDS = 0.5
NOT_A_TOOL = ("refused: this cad is not a uv tool, so it does not update itself: update it the way it was installed "
              "(for pip, `pip install --upgrade cad`), or install it as a uv tool with `uv tool install cad`")
OLD_SERVER = ("the cad server running cannot update cad: run `cad server stop`, then `cad server start`, then "
              "`cad update` again")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    return command_parser(prog=prog, description=(
        "Update cad to the newest release now, even with automatic updates off. The cad server reads which release "
        "is newest and, once nothing is running, installs it with uv and starts again. Needs the server running."))


def waits(windows: bool = os.name == "nt") -> bool:
    """Whether ``cad update`` waits for the update to end. Not on Windows: while any ``cad.exe`` of the tool runs,
    ``uv tool install`` fails halfway and leaves the tool broken until it runs again with none running, and a command
    that waits is one."""
    return not windows


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG, windows: bool = os.name == "nt") -> int:
    build_parser(prog).parse_args(argv)
    from cad.engine import client
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, classify, write

    if auto_update.uv_tool() is None:  # this command's own cad
        return write(Failure(NOT_A_TOOL), prog=prog, as_json=False)
    try:
        answer = client.request({"op": "update"}, timeout=ASK_SECONDS)  # never starts one: none running, said
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
    if not (isinstance(target, str) and isinstance(was, str) and isinstance(since, (int, float))):
        return write(Failure(f"the cad server's answer was not understood: {answer}"), prog=prog, as_json=False)
    if not waits(windows):
        print(f"updating cad {was} to {target}: it takes about a minute")
        return 0
    return wait(lambda: look(client, auto_update), was, float(since),
                said=lambda words: write(Failure(words), prog=prog, as_json=False))


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
    """An attempt that ended, said in one line: its exit status."""
    target = attempt.get("release")
    if attempt.get("outcome") in ("installed", "current"):
        if str(attempt.get("started", "")).startswith("not started"):
            return said(f"cad {was} updated to {target}, but the cad server did not start again: run "
                        "`cad server start`")
        print(f"cad {was} updated to {target}")
        return 0
    serving = f"cad {running} is running" if running else "no cad server is running: run `cad server start`"
    return said(f"could not update cad {was} to {target}: {attempt.get('detail') or 'no reason given'}; {serving}")


if __name__ == "__main__":
    raise SystemExit(main())
