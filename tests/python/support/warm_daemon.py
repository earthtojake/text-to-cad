"""Route a test's model-run subprocesses through ONE warm daemon per test module.

A cold ``python <model>.py`` spends about 2.6 s importing build123d and OCP before it
draws anything, and this suite runs roughly 250 of them. The import is not what those
tests are about: they are about what the run WRITES -- bytes, records, freshness
verdicts, result lines. Sending them through a daemon pays that import once for the
module instead of once per run.

The daemon is private to the module and dies with it. ``unittest_files.py`` already
gives every test FILE its own store, daemon state directory and endpoint, and retires
whatever bound that endpoint when the module finishes; this helper simply stops
opting out of it, and creates the same private endpoint itself when a file is run
directly (``python -m unittest tests/...``) so a direct run can never reach -- or
retire -- the developer's own daemon.

Where it pays: the pool binds a worker per SCRIPT PATH and never rebinds an idle
one, so a module whose tests each write a fresh script into a fresh directory pays
one kernel import per test either way -- and on Windows the spawn is dearer than
the cold run it replaces. Route a module through the daemon when its tests run the
SAME script several times (rerun / --force / `store why` / an edit-and-rebuild),
which is where measured CI time halved on both platforms.

What must NOT use this:

* anything whose subject is the daemon, the pool or the broker;
* anything asserting COLD semantics -- a fresh interpreter's import hints, bytecode,
  ``__main__`` handling, hash-seed independence across processes, or the cold half of
  a cold/warm comparison.

Those keep ``CADGEN_DAEMON=0`` and say why where they set it.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

_OWNED: dict[str, str] = {}


def _private_endpoint() -> tuple[str, str]:
    """This process's daemon endpoint and state directory, created once.

    AF_UNIX paths are length-limited (~104 bytes on macOS), so the socket gets a short
    directory of its own rather than the repo tmp root. A Windows pipe name is not a
    path and is simply made unique.
    """
    if "address" in _OWNED:
        return _OWNED["address"], _OWNED["state"]
    state = tempfile.mkdtemp(prefix="cgw-", dir=None if os.name == "nt" else "/tmp")
    address = (rf"\\.\pipe\cadgen-warm-{os.getpid()}" if os.name == "nt"
               else str(Path(state) / "d.sock"))
    _OWNED.update(address=address, state=state)
    atexit.register(_retire)
    return address, state


def _retire() -> None:
    """Stop the daemon this process started, if it started one."""
    address, state = _OWNED.get("address"), _OWNED.get("state")
    if not address or not state or not os.path.isdir(state):
        return
    if not any(name.endswith(".key") for name in os.listdir(state)):
        return  # no key means nothing ever bound this endpoint
    environment = dict(os.environ)
    environment["CADGEN_DAEMON_SOCKET"] = address
    environment["CADGEN_DAEMON_STATE_DIR"] = state
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO_ROOT), str(REPO_ROOT / "packages" / "cadgen" / "src"),
                      os.environ.get("PYTHONPATH", "")])
    )
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "python" / "support" / "daemon_cleanup.py"), address],
        env=environment, capture_output=True, text=True, timeout=30, check=False,
    )


def warm_entries() -> dict[str, str]:
    """The entries that route a model run through this module's private warm daemon.

    For the ``env.update({...})`` and ``{**os.environ, ...}`` shapes the tests already
    use: splat it where ``"CADGEN_DAEMON": "0"`` used to be. The endpoint is the one
    ``unittest_files.py`` gave this process, or a private one created here for a
    direct run.
    """
    entries: dict[str, str] = {}
    address = os.environ.get("CADGEN_DAEMON_SOCKET")
    if not address:
        address, state = _private_endpoint()
        entries["CADGEN_DAEMON_SOCKET"] = address
        entries["CADGEN_DAEMON_STATE_DIR"] = state
    entries["CADGEN_DAEMON"] = "1"
    # Long enough to outlive one module, short enough that an abandoned one goes away.
    entries["CADGEN_DAEMON_IDLE_TIMEOUT"] = os.environ.get("CADGEN_DAEMON_IDLE_TIMEOUT", "300")
    # Spares stay at the production default. Measured with them off, every warm
    # file got slower on CI (a new script's first build then imports the kernel on
    # the test's critical path instead of in the background) and nothing else got
    # faster: the runner had the headroom the spares were using.
    return entries


def warm_env(base: dict | None = None, **overrides: str) -> dict:
    """``base`` (default ``os.environ``) with model runs routed through the warm daemon.

    The caller's own keys win, so a test can still pin ``CADGEN_JOBS`` or a store root.
    """
    environment = dict(os.environ if base is None else base)
    environment.update(warm_entries())
    # A worker sets this on the children it spawns; inheriting it would send the
    # subprocess straight back to the inline path this helper exists to avoid.
    environment.pop("CADGEN_DAEMON_CHILD", None)
    environment.update(overrides)
    return environment


def warm_environ(testcase: unittest.TestCase, **overrides: str) -> None:
    """Put :func:`warm_env` on ``os.environ`` for the duration of ``testcase``.

    For tests that build IN PROCESS through cadgen's own API and would otherwise read
    ``CADGEN_DAEMON=0`` off the environment.
    """
    from unittest import mock

    patch = mock.patch.dict(os.environ, warm_env(**overrides))
    patch.start()
    testcase.addCleanup(patch.stop)
