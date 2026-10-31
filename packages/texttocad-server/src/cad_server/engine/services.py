"""Every kind of process the daemon starts, declared (``supervisor.Service``); the supervisor runs
each by its declaration, and the daemon binds its hooks to them by name (``drain``, ``watched``,
``on_progress``, the ``saved`` event).

``WORKER``: a model script's warm worker, one per script (and one for the documents no worker built,
keyed ``documents``), in the installation's base, with the caller's environment adopted at each
request (``worker.adopt``) but for what binds it to its interpreter (``places.RESTARTS``), the
daemon's bytecode and ``CAD_ENGINE_WORKER``; started in its script's folder, its stderr the model's
log. It counts toward the count cap, is drained of its documents before it stops
(``models.Models.drain``), and keeps a standby with the kernel loaded (``worker.load_kernel``).
"""

from __future__ import annotations

from cad.engine.places import RESTARTS
from cad.engine.worker import KERNEL_NOTICE, KERNEL_PATIENCE

from cad_server.engine.supervisor import Service, Standby, Words

__all__ = ["SERVICES", "WORKER"]

WORKER = Service(
    name="worker",
    command=("{python}", "-X", "faulthandler", "-P", "-m", "cad.engine.worker"),
    environment="kernel",
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
    standby=Standby(args=("--standby",), adopt="adopt", rank=0, notice=KERNEL_NOTICE, patience=KERNEL_PATIENCE),
)

SERVICES = (WORKER,)
