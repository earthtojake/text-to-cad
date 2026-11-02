"""A library verb that needs the CAD kernel, called by a server command: ``cad fea``'s.

``cad.fea`` reads a document's B-rep with OCP, which the server's own environment carries only when its
installation does (a checkout's development environment, an install with the ``build123d`` extra). So
:func:`in_kernel` wraps the verb in a function of the same signature, from which the generated parser is
derived as from the verb itself: called, it runs the verb here when this installation carries the kernel,
else in the installation's base (``base.ensure``, made first as ``cad run`` makes it), through the library's
runner (``cad._internal.fea.call``). The outcome comes back as the verb's own value or its own error, so the
command prints and reports it as it would a call in its own process.
"""

from __future__ import annotations

import functools
import importlib
import pickle
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The library's runner of one ``cad.fea`` verb in the base.
RUNNER = "cad._internal.fea.call"


def in_kernel(target: tuple[str, str], *, prog: str) -> Callable[..., Any]:
    """``target``'s verb (``("cad.fea", "solve")``), run where the kernel is."""
    module_name, name = target
    verb = getattr(importlib.import_module(module_name), name)

    @functools.wraps(verb)
    def call(*args: Any, **kwargs: Any) -> Any:
        from cad_server._internal import base

        env = base.ensure(told=lambda line: print(f"{prog}: {line}", file=sys.stderr, flush=True), engine=True)
        assert env is not None  # made, or refused
        if env.own:
            return verb(*args, **kwargs)
        return _in_base(env.python, name, args, kwargs)

    return call


def _in_base(python: str, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """The verb ``name`` called in the base whose Python is ``python``: its value, or its error raised."""
    with tempfile.TemporaryDirectory(prefix="cad-fea-") as folder:
        request, answer = Path(folder) / "request.pickle", Path(folder) / "answer.pickle"
        request.write_bytes(pickle.dumps((args, kwargs)))
        sys.stdout.flush()
        done = subprocess.run([python, "-P", "-m", RUNNER, name, str(request), str(answer)],
                              stdout=2, check=False)  # its stdout to this stderr: stdout is the result
        if not answer.is_file():
            raise RuntimeError(f"the CAD kernel environment's {python} stopped before it answered "
                               f"(exit {done.returncode})")
        kind, value = pickle.loads(answer.read_bytes())
    if kind == "raised":
        raise value
    return value
