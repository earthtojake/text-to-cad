"""An operation the ``cad`` command runs where the integration it needs is installed.

A 3D type's ``check`` is the trimesh integration's (``cad.registry``): the library measures the mesh
with trimesh; a KiCad board's and a schematic's ``check`` and ``export`` are the kicad integration's, run by
kicode's kicad-cli. The command's own environment -- the server's installation -- holds the library without
it, so the operation runs in the environment of that integration instead: ``cad[<integration>]`` at
the installation's release, made once by the device's engine outside any sandbox and used again, as
``cad run`` makes a program's (``cad_server._internal.extras``: offline first, from uv's cache). Its
Python runs the library's runner of one operation (``cad._internal.operation``), handed the call on
stdin and answering it on stdout; what the operation says beside goes to stderr as it comes.

An installation whose own environment carries the integration (a checkout's development environment,
``requirements-dev.txt``; one installed with the extra) runs the operation itself, in this process, as
an installation that carries the kernel is its own base (``base``).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

__all__ = ["Failed", "call", "carries", "environment"]

# The library's runner of one operation (``cad._internal.operation``).
RUNNER = "cad._internal.operation"


class Failed(RuntimeError):
    """The operation's environment could not be made, or its runner gave no answer: said in one line."""


def carries(integration: str) -> bool:
    """Whether this process's environment holds ``integration``'s modules (found, none loaded)."""
    import importlib.util

    from cad.registry import INTEGRATIONS

    modules = INTEGRATIONS[integration].modules
    try:
        return bool(modules) and all(importlib.util.find_spec(name) is not None for name in modules)
    except (ImportError, ValueError):
        return False


def environment(integration: str, told: Callable[[str], None], *, engine: bool = True) -> str:
    """The Python of the environment that holds ``integration``, made first when it is not complete (by
    the device's engine when one runs, its lines said to ``told``; here, with ``engine`` false: the engine
    itself, a viewer export). ``Failed`` in uv's or the engine's words."""
    from cad_server._internal import base, extras

    try:
        found = extras.ensure(base.Installation.here(), extras.Spec(integrations=(integration,)), told=told,
                              engine=engine)
    except (base.Refused, OSError) as error:
        raise Failed(str(error) if isinstance(error, base.Refused) else f"{error.strerror or error}") from None
    return found.python


def call(python: str, document_type: str, operation: str, args: list[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    """``cad.<document_type>.<operation>(*args, **kwargs)`` run by ``python`` (``RUNNER``): its result as
    data. The operation's own failure is raised as a ``Failed`` in its words."""
    request = json.dumps({"type": document_type, "operation": operation, "args": args, "kwargs": kwargs})
    try:
        done = subprocess.run([python, "-P", "-m", RUNNER], input=request, stdout=subprocess.PIPE, stderr=None,
                              text=True, encoding="utf-8", errors="replace", check=False)
    except OSError as error:
        raise Failed(f"cannot run {python}: {error.strerror or error}") from None
    lines = done.stdout.strip().splitlines()
    try:
        answer = json.loads(lines[-1]) if lines else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or not ({"result", "error"} & set(answer)):
        raise Failed(f"the {document_type} {operation} gave no answer (its Python exited {done.returncode})")
    if "error" in answer:
        raise Failed(str(answer["error"]))
    return answer["result"]
