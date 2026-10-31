"""Every Python process a watched test command starts records itself in the test's journal.

``tests.python.support.engine_daemon`` puts this folder first on ``PYTHONPATH`` and names a
journal folder in ``CADGEN_TEST_JOURNAL``; the command, the engine daemon it starts and the
daemon's workers all inherit both, so each one, at its start, writes ``<role>-<pid>.txt``
there: when it started, when it listened (a daemon that made its door, or on Windows listened on
its port), when it left and with what, an uncaught error's traceback, and every thread's stack
each ``DUMP_SECONDS`` it is alive -- where a process that hangs is waiting -- and, in the same
``<role>-<pid>.stacks.txt``, the stack of a process that dies in native code. The test reads the
folder when a command does not finish, and prints the stacks when one fails. Nothing here may fail
the process it is in.

``DUMP_SECONDS`` is long, under the commands' 300 s timeout so a hung one still leaves a dump: the
dump's watchdog thread walks the other threads' frames without the GIL, and in a process still
importing at that moment (a cold first build on a loaded Windows runner) that walk can itself fault."""

from __future__ import annotations

import os

DUMP_SECONDS = 240


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
    # Each by its module; the distribution starts the daemon as ``cad_server._internal.engine_daemon``
    # (``engine_host``), its engine's own entry point being ``cad_server.engine.daemon``.
    roles = {"cad_server.engine.daemon": "daemon", "cad_server._internal.engine_daemon": "daemon",
             "cad.engine.worker": "worker", "cad.engine.reader": "reader",
             "cad.engine.render.service": "render"}
    role = next((role for module, role in roles.items() if module in argv), "process")
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

    if hasattr(os, "mkfifo"):
        mkfifo = os.mkfifo

        def door(path: object, *args: object, **kwargs: object) -> None:
            mkfifo(path, *args, **kwargs)  # type: ignore[arg-type]
            if str(path).endswith(".door"):  # a POSIX daemon listens on its door, a named pipe
                write(f"listening {path}")

        os.mkfifo = door  # type: ignore[assignment]

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
