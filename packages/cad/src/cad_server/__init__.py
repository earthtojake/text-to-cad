"""The CAD server: the device's one daemon that builds, keeps and serves documents, the viewer's and
the CAD app's servers on its listener, every verb of the ``cadgen`` command, the environments its kernel
processes run in, the installations and the one that is current, and telemetry.

It imports the library's (``cad``) kernel-free modules and never the CAD kernel: the kernel lives in the
environment models run in (``_internal/base.py``). Importing it installs what the server attaches to the
library: the engine's verbs a server process runs are counted (``_internal/engine_telemetry.py``), and a
model's build by the daemon that answers it; a model's own process, where the server is not installed,
counts nothing. Each is attached as the engine's
module is imported, never sooner (``_internal/attach.py``): importing the server imports no engine.
"""

import sys as _sys

# uv's cad.exe runs `python cad.exe`, so the launcher (a zip) is sys.path[0]; once anything reads package metadata, this
# process holds it open, and Windows will not let an update rename it. That one entry goes first, before anything reads.
if _sys.path and _sys.path[0].replace("\\", "/").rsplit("/", 1)[-1].lower() == "cad.exe":
    del _sys.path[0]
del _sys

from functools import cache as _cache

from cad_server._internal import engine_telemetry as _engine_telemetry

_engine_telemetry.install()
del _engine_telemetry

__all__ = ["__version__"]


def __getattr__(name: str):
    if name == "__version__":
        return _version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@_cache
def _version() -> str:
    """The version declared beside this very package (``cad._internal.version.declared_version``): the
    source tree's pyproject for a checkout, the dist-info beside it for an install."""
    import pathlib

    from cad._internal.version import declared_version

    return declared_version(pathlib.Path(__file__).resolve().parent)
