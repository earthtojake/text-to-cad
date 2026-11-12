"""omega-core's ``gsl``, the program every check runs: found and checked, as the library's one helper for the
external programs our code runs finds every one (``cad._internal.programs``).

The ``omega`` integration's probe (``cad.registry.INTEGRATIONS["omega"]``: the program, its minimum, its install
hint and ``CAD_GSL``). ``gsl`` is the integration's extra's, ``cad[omega]``: the ``omega-core`` wheel carries omega's
own ``gsl`` for each platform it builds and says where it is (``omega_core.executable()``). ``CAD_GSL`` names another
(a build of the person's own from an omega-core checkout); a ``gsl`` on PATH is never run, so every check on every
device meshes with the pinned release. Stdlib only: ``omega_core`` is read when a check looks for the program, never
at import.
"""

from __future__ import annotations

from pathlib import Path

from cad._internal import programs
from cad.registry import INTEGRATIONS

__all__ = ["EXTRA", "GSL", "OmegaMissingError", "find_gsl", "installed"]

_PROBE = INTEGRATIONS["omega"].probe
assert _PROBE is not None
EXTRA = "cad[omega]"


class OmegaMissingError(programs.ProgramMissing):
    """No ``gsl`` cad can run."""


def installed() -> bool:
    """Whether this process can run ``gsl`` itself: ``CAD_GSL`` names one, or omega-core is installed here."""
    import importlib.util
    import os

    return bool(os.environ.get(_PROBE.override, "").strip()) or importlib.util.find_spec("omega_core") is not None


def _carried() -> list[Path]:
    """The ``gsl`` the integration's extra installed: the omega-core wheel's, where this environment holds it."""
    try:
        import omega_core
    except ModuleNotFoundError:
        return []
    try:
        return [Path(omega_core.executable())]
    except FileNotFoundError:  # an omega-core with no program for this platform
        return []


#: ``gsl`` as the helper finds it, asked ``gsl --version`` (``gsl 0.1.1``). ``search_path`` is off: the program is
#: the extra's, never one on PATH.
GSL = programs.Program.from_probe(_PROBE, names=("gsl",), installed=_carried, version_args=("--version",),
                                  title=f"omega-core {_PROBE.minimum}", search_path=False)


def find_gsl() -> Path:
    """The ``gsl`` to run, its version checked: the file ``CAD_GSL`` names, else omega-core's. Raises
    :class:`OmegaMissingError` naming why and how to install it."""
    try:
        path = programs.find(GSL).absolute()
        programs.check_version(GSL, path, programs.version(GSL, path))
        return path
    except programs.ProgramMissing as error:
        raise OmegaMissingError(str(error)) from None
