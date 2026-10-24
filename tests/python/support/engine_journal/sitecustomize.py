"""Every Python process a watched test command starts records itself in the test's journal.

``tests.python.support.engine_daemon`` puts this folder first on ``PYTHONPATH`` and names a
journal folder in ``CADGEN_TEST_JOURNAL``; the command, the engine daemon it starts and the
daemon's workers all inherit both, so each one, at its start, writes ``<role>-<pid>.txt``
there: when it started, when it listened (a daemon that bound its socket), when it left and
with what, an uncaught error's traceback, and every thread's stack each ``DUMP_SECONDS`` it
is alive -- where a process that hangs is waiting. The test reads the folder when a command
does not finish. Nothing here may fail the process it is in."""

from __future__ import annotations

import os

DUMP_SECONDS = 45


def _record() -> None:
    import atexit
    import faulthandler
    import socket
    import sys
    import threading
    import time
    import traceback

    folder = os.environ.get("CADGEN_TEST_JOURNAL")
    if not folder or not os.path.isdir(folder):
        return
    argv = " ".join(getattr(sys, "orig_argv", sys.argv))
    roles = {"daemon": "daemon", "worker": "worker", "reader": "reader", "render.service": "render"}
    role = next((role for module, role in roles.items() if f"cadgen.engine.{module}" in argv), "process")
    path = os.path.join(folder, f"{role}-{os.getpid()}.txt")
    started = time.time()

    def write(line: str) -> None:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"{time.time():.3f} {line}\n")
        except OSError:
            pass

    write(f"start parent={os.getppid()} argv={argv}")
    # The stacks go to a handle of their own, kept open: faulthandler writes from its own thread.
    stacks = open(os.path.join(folder, f"{role}-{os.getpid()}.stacks.txt"), "a", encoding="utf-8")  # noqa: SIM115
    faulthandler.enable(stacks)
    faulthandler.dump_traceback_later(DUMP_SECONDS, repeat=True, file=stacks)

    listen = socket.socket.listen

    def listening(self: socket.socket, *args: object) -> None:
        listen(self, *args)
        try:
            write(f"listening {self.getsockname()!r}")
        except OSError:
            write("listening")

    socket.socket.listen = listening  # type: ignore[method-assign]

    previous = sys.excepthook

    def uncaught(kind: type[BaseException], error: BaseException, trace: object) -> None:
        write("uncaught " + "".join(traceback.format_exception(kind, error, trace)).replace("\n", "\n    "))
        previous(kind, error, trace)

    sys.excepthook = uncaught

    def thread_uncaught(args: threading.ExceptHookArgs) -> None:
        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        write(f"uncaught in thread {args.thread.name if args.thread else '?'} " + text.replace("\n", "\n    "))

    threading.excepthook = thread_uncaught
    atexit.register(lambda: write(f"exit after {time.time() - started:.1f}s"))


try:
    _record()
except Exception:  # noqa: BLE001, S110 - a journal that cannot be kept is no reason to fail the process
    pass
