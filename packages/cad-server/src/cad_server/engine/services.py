"""Every kind of process the daemon starts, declared (``supervisor.Service``); the supervisor runs
each by its declaration, and the daemon binds its hooks to them by name (``drain``, ``watched``,
``on_progress``, the ``saved`` event).

``WORKER``: a model script's warm worker, one per script and Python (and one for the documents no
worker built, keyed ``documents``), in the installation's base -- or in the Python the script was run
with, which its build names (``contract.interpreter``) when its environment is not the base: one of the
caller's own, with its packages (``interpreter="lease"``) -- with the caller's
environment adopted at each request (``worker.adopt``) but for what binds it to its interpreter
(``places.RESTARTS``), the daemon's bytecode and ``CAD_ENGINE_WORKER``; started in its script's folder,
its stderr the model's log. It counts toward the count cap, and is drained of its documents before it
stops (``models.Models.drain``). It starts with a build, never before: its first build loads the kernel
(``worker.kernel``, which says so when the load is long).

``RENDER``: a served document's render process (``cad.engine.render.service``), one per document by
its id on the server (and per file no document, ``file:`` and its path: ``renders``), in the base,
with the daemon's environment and no bytecode written, standing where the daemon does; its stderr
kept, its last lines said when it is gone. It does not count toward the count cap, is retired for
memory before any worker, and its retirements are listed in ``status`` by its document.

Their ranks give the order memory is shed in: render processes (1), then the workers no page watches
(2), and a watched worker (3) only when no other is left.
"""

from __future__ import annotations

from cad.engine.places import RESTARTS

from cad_server.engine.supervisor import Service, Words

__all__ = ["RENDER", "SERVICES", "WORKER"]

WORKER = Service(
    name="worker",
    command=("{python}", "-X", "faulthandler", "-P", "-m", "cad.engine.worker"),
    environment="kernel",
    interpreter="lease",  # a build in its caller's own Python: that Python's worker (``Daemon.caller``)
    env="lease",
    set_env=(("CAD_ENGINE_WORKER", "1"),),
    bytecode="daemon",
    cwd="lease",
    key="path",
    binding=RESTARTS,
    stderr="relay",
    events=("saved", "collected"),
    words=Words(unstarted="the worker for {label} did not start",
                exited="the worker for {name} exited ({code}) during the build",  # read by api._DIED
                broken="{error}"),
    counted=True,
    rank=2,
    watched_rank=3,
    noted=("script", "builds"),
    drain=True,
    ready_seconds=300.0,  # a worker says it is ready before it loads the kernel, at its first build
)

RENDER = Service(
    name="render",
    command=("{python}", "-P", "-m", "cad.engine.render.service"),
    environment="kernel",
    env="daemon",
    bytecode="read-only",
    cwd="inherit",
    key="id",
    stderr="keep",
    words=Words(unstarted="the renderer for {name} did not start",
                exited="the renderer for {name} exited ({code})",
                broken="the renderer for {name} is gone ({error})"),
    counted=False,
    rank=1,
    noted=("document", "requests"),
    ready_seconds=120.0,
)

SERVICES = (WORKER, RENDER)
