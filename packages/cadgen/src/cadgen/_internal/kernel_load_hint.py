"""Name the blocker when Windows refuses to load the CAD kernel.

The kernel cadgen and build123d run on is ``OCP``, a single native extension
module (``OCP.cp3xx-win_amd64.pyd``, ~90 MB) that the cadquery-ocp wheels ship
WITHOUT an Authenticode signature. Windows 11's Smart App Control blocks
unsigned native code, so on a machine where it is on -- which is the default
state of a fresh install -- every command that imports the kernel fails with::

    ImportError: DLL load failed while importing OCP: ...

Nothing in that message says who refused the load, and the only record is
Event ID 3077 in the CodeIntegrity operational log. An agent that sees the
ImportError reinstalls, retries and gives up; a user who does find the event
still has to learn that Smart App Control has no per-app exception. So the
CLI failure reporter and ``cadgen doctor`` say all of that in the place the
failure is read.

The hint is deliberately narrow: a Windows ``ImportError`` whose message is
the loader's ``DLL load failed`` naming OCP. ``ModuleNotFoundError`` is a
missing install and already has its own hint; a failure on any other platform
is not this.
"""

from __future__ import annotations

import sys

_LOADER_REFUSED = "DLL load failed"
_KERNEL_MODULE = "OCP"

SMART_APP_CONTROL_HINT = (
    "hint: Windows refused to load the CAD kernel's native module (OCP). On Windows 11",
    "the usual cause is Smart App Control: it blocks native code that is not",
    "Authenticode-signed, and the OCP wheel is not signed. Event Viewer > Applications",
    "and Services Logs > Microsoft > Windows > CodeIntegrity > Operational records the",
    "refusal as Event ID 3077, naming the .pyd.",
    "Smart App Control has no per-app exception. Either turn it off (Settings > Privacy",
    "& security > Windows Security > App & browser control > Smart App Control settings;",
    "once off it can only be turned back on by reinstalling Windows) or run the CAD",
    "tools under WSL, where it does not apply. `python -c \"import OCP\"` succeeds once",
    "the kernel loads.",
)


def _looks_like_refused_kernel_load(text: str) -> bool:
    return _LOADER_REFUSED in text and _KERNEL_MODULE in text


def kernel_load_hint(
    failure: BaseException | str, *, platform: str | None = None
) -> tuple[str, ...] | None:
    """The Smart App Control hint lines for ``failure``, or None when it is not
    a refused kernel load on Windows.

    ``failure`` is the exception a command caught, or the last line of a
    subprocess's stderr (``cadgen doctor`` probes the kernel in a fresh
    interpreter, so it only has the text). ``platform`` defaults to the running
    one; tests pass ``"win32"`` from any host.
    """
    if (platform or sys.platform) != "win32":
        return None
    if isinstance(failure, BaseException):
        # A missing OCP is a pip problem with its own hint, not a refused load.
        if not isinstance(failure, ImportError) or isinstance(failure, ModuleNotFoundError):
            return None
        text = str(failure)
    else:
        text = failure
    if not _looks_like_refused_kernel_load(text):
        return None
    return SMART_APP_CONTROL_HINT
