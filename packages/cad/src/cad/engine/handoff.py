"""The go-between of a start outside a Windows app package (``places.outside_package``): Task Scheduler runs it, as
``pythonw -I handoff.py <request>`` by the environment's own interpreter, and it starts the command it is handed,
which no package then holds, since a task's process is the scheduler's, never the app's child.

``request`` is a JSON file in cad's state folder: ``argv``, ``env``, ``cwd``, ``flags`` (Windows' process creation
flags), ``reply`` (the file the go-between answers in) and ``wait``. It is taken first (renamed), so a start that gave
up on it and started the command itself never has it started twice, and removed once read. The command is started
detached as ``places.detached`` starts one: its standard streams the null device, a process group and a console of
its own with no window, and out of the task's job where the job allows it (``CREATE_BREAKAWAY_FROM_JOB``), so the
task's end never ends it. The answer, written whole: ``{"pid", "between"}`` (the process started, and this one), or
``{"error"}``; then the go-between waits for its starter to remove the answer (it has opened the process by then,
``wait`` seconds at most) and ends.

Run by its file, isolated, it imports the standard library alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

# Windows' flag for a process started out of its starter's job (``subprocess`` names it on Windows alone).
CREATE_BREAKAWAY_FROM_JOB = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)


def main(arguments: list[str]) -> int:
    """The request named by ``arguments[0]`` carried out (see the module); 0 once the command started, else 1."""
    request = arguments[0]
    taken = f"{request}.taken"
    try:
        os.rename(request, taken)
    except OSError:
        return 1  # given up on: its starter started the command itself
    try:
        with open(taken, encoding="utf-8") as handle:
            told = json.load(handle)
    finally:
        try:
            os.remove(taken)
        except OSError:
            pass
    reply = told["reply"]
    try:
        child = start(told)
    except Exception as error:  # noqa: BLE001 - said to the starter, which starts it as it would elsewhere
        answer(reply, {"error": f"{type(error).__name__}: {error}"})
        return 1
    answer(reply, {"pid": child.pid, "between": os.getpid()})
    deadline = time.monotonic() + float(told.get("wait", 5))
    while os.path.exists(reply) and time.monotonic() < deadline:
        time.sleep(0.01)
    return 0


def start(told: dict[str, Any], popen: Callable[..., Any] | None = None) -> Any:
    """``told``'s command started, detached, out of the task's job where the job allows it, else in it."""
    popen = popen or subprocess.Popen
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
               "env": told["env"], "cwd": told["cwd"], "close_fds": True}
    try:
        return popen(told["argv"], creationflags=told["flags"] | CREATE_BREAKAWAY_FROM_JOB, **options)
    except OSError:  # a job that allows no breakaway refuses the flag
        return popen(told["argv"], creationflags=told["flags"], **options)


def answer(path: str, value: dict[str, Any]) -> None:
    """``value`` written to ``path`` whole: a starter reading it never reads half of it."""
    part = f"{path}.part"
    with open(part, "w", encoding="utf-8") as handle:
        json.dump(value, handle)
    os.replace(part, path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
