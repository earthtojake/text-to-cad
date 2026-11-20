"""uv's cache filled with what an offline install of this installation's kernel environment reads. The base
environment is installed from uv's cache first (``cad_server._internal.base``: ``--offline``, then the network
for what it lacks), so a test that counts what uv is asked, or that runs uv offline, needs the cache to hold it.
An environment synced from a lock (``uv sync``: the checkout's, and CI's) leaves the cache without the index
pages an unlocked resolution reads and without any wheel but the lock's; pip and ``uv pip install`` filled it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def warm(folder: Path) -> None:
    """This installation's library with its kernel, as uv resolves it now, installed once into a throwaway
    environment in ``folder`` with the network, so uv's cache holds it: the index pages an unlocked resolution
    reads and the wheels it picks. Where the cache holds them already this downloads nothing; with no network it
    does nothing, and what runs after reads what the cache holds."""
    from cad_server._internal import base

    uv, own = base.find_uv(), base._own()
    env = Path(folder) / "warm"
    made = subprocess.run([uv, "venv", "--no-project", "--python", sys.executable, str(env)], capture_output=True)
    if made.returncode == 0:
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([uv, "pip", "install", "--python", str(python), *own.requirement(), "numpy"],
                       capture_output=True, cwd=folder)
    shutil.rmtree(env, ignore_errors=True)
