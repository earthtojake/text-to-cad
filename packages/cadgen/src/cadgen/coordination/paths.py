"""The daemon's state directory: ONE derivation, imported by the daemon and the viewer.

There is no advisory progress record any more: a build's position is the daemon's
job ledger (``cadgen.daemon.jobs``), read over the socket. What lives here is the
address, the auth key and the log — process state, never store content.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def state_dir() -> Path:
    """The daemon's state directory: the address, the auth key, the log.

    Same derivation as ``cadgen.daemon.transport.state_dir`` (which imports this one).
    ``CADGEN_DAEMON_STATE_DIR`` overrides it (tests isolate their daemons that way);
    otherwise ``tempfile.gettempdir()``, which answers correctly on every platform.
    """
    override = os.environ.get("CADGEN_DAEMON_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "cadgen-daemon"
