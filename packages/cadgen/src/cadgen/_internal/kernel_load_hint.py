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

``kernel_load_hint`` is deliberately narrow: a Windows ``ImportError`` whose
message is the loader's ``DLL load failed`` naming OCP. ``ModuleNotFoundError``
is a missing install and already has its own hint; a failure on any other
platform is not this. A command can fail on any import, and it says nothing
about a module it cannot name the cause for.

``native_load_hint`` is the wider one, for a caller that knows the failed
import was a native module cadgen itself needed. The engine's kernel processes
are one such case (``engine.serve.KernelProcessesUnavailable``): on Windows a
pool needs ``_multiprocessing.pyd``, and a refused load of it once failed
``cad_show`` on a machine where every other module loaded. The cause has the
same shape as OCP's: the loader names the module and not who refused it, and
the record is the same Event ID 3077. So that hint names the refused module and
the blockers that refuse one file and not its neighbours (Smart App Control's
per-file verdict, another application control policy, antivirus). For OCP it
stays the hint above, word for word.
"""

from __future__ import annotations

import re
import sys

_LOADER_REFUSED = "DLL load failed"
_KERNEL_MODULE = "OCP"
_REFUSED_MODULE = re.compile(r"DLL load failed while importing ([A-Za-z_][\w.]*)")

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


NATIVE_MODULE_HINT = (
    "hint: Windows refused to load {module}, a native module (.pyd) CAD needs. Smart App",
    "Control, another application control policy or antivirus software blocks native",
    "code it does not trust, one file at a time. Event Viewer > Applications and",
    "Services Logs > Microsoft > Windows > CodeIntegrity > Operational records a Smart",
    "App Control or application control refusal as Event ID 3077, naming the .pyd;",
    "antivirus keeps its own log. Allow that file there, or turn Smart App Control off",
    "(Settings > Privacy & security > Windows Security > App & browser control > Smart",
    "App Control settings; once off it can only be turned back on by reinstalling",
    "Windows), or run the CAD tools under WSL, where none of these apply.",
)


def native_load_hint(
    failure: BaseException | str, *, platform: str | None = None
) -> tuple[str, ...] | None:
    """The hint lines for a native module Windows refused to load, whichever
    module the loader names. OCP gets ``SMART_APP_CONTROL_HINT``; any other module
    gets ``NATIVE_MODULE_HINT``, naming that module. None off Windows, for a
    missing module (``ModuleNotFoundError``), or for any error that is not the
    loader's ``DLL load failed while importing <module>``. ``failure`` and
    ``platform`` are read as ``kernel_load_hint`` reads them.
    """
    if (platform or sys.platform) != "win32":
        return None
    if isinstance(failure, BaseException):
        if not isinstance(failure, ImportError) or isinstance(failure, ModuleNotFoundError):
            return None
        text = str(failure)
    else:
        text = failure
    found = _REFUSED_MODULE.search(text)
    if found is None:
        return None
    module = found.group(1)
    if module == _KERNEL_MODULE:
        return SMART_APP_CONTROL_HINT
    return tuple(line.format(module=module) for line in NATIVE_MODULE_HINT)
