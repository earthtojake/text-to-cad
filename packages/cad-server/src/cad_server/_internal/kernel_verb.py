"""A library verb that needs the CAD kernel, run where the kernel is: what ``cad cam features|plan`` call.

The server's own process runs in the core, where the CAD kernel is not installed (``base``), and a CAM
verb reads a part's exact faces with OCCT. :func:`in_kernel` is such a verb with its own signature and
docstring, so a command's parser is still generated from the verb (``cli_from_function`` reads them
through ``functools.wraps``). Called, it runs the verb in this process when this installation carries the
kernel itself, else in the installation's base, the environment ``cad run`` runs a program in: the
library's runner of the verb (:data:`RUNNERS`) in the base's Python, the verb's arguments in on stdin as one
JSON object and its result out on stdout as one JSON line, made the verb's own result type again. What the
verb says on stderr (``verbose``'s stages) is the command's.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import inspect
import json
import subprocess
import sys
import typing
from pathlib import Path
from typing import Any, Callable

#: A library namespace whose verbs run in the kernel's environment -> the library module that runs one there.
RUNNERS = {"cad.cam": "cad._internal.cam"}


def in_kernel(target: tuple[str, str], *, prog: str) -> Callable[..., Any]:
    """The verb ``target`` (``(module, name)``), run where the CAD kernel is (see the module)."""
    module_name, attribute = target
    verb = getattr(importlib.import_module(module_name), attribute)
    runner = RUNNERS[module_name]

    @functools.wraps(verb)
    def call(*args: Any, **kwargs: Any) -> Any:
        from cad_server._internal import base

        env = base.ensure(told=lambda line: print(f"{prog}: {line}", file=sys.stderr, flush=True), engine=True)
        assert env is not None  # made, or refused
        if env.own:
            return verb(*args, **kwargs)
        keywords = inspect.signature(verb).bind(*args, **kwargs).arguments
        sys.stdout.flush()
        done = subprocess.run([env.python, "-P", "-m", runner, attribute], input=json.dumps(keywords, default=str),
                              stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        lines = (done.stdout or "").strip().splitlines()
        try:
            answer = json.loads(lines[-1]) if done.returncode == 0 and lines else None
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise RuntimeError(f"the CAD kernel's environment ({env.python}) did not run {module_name}.{attribute} "
                               f"(exit code {done.returncode})")
        return result(answer)

    return call


def result(answer: dict[str, Any]) -> Any:
    """The runner's answer as the verb's own result type (``cad.results``): its paths ``Path`` again, its lists
    tuples where the type's fields are."""
    import cad.results

    kind = getattr(cad.results, str(answer.get("result")))
    hints = typing.get_type_hints(kind)
    fields = answer.get("fields") or {}
    values = {}
    for field in dataclasses.fields(kind):
        if field.name not in fields:
            continue
        value, hint = fields[field.name], hints[field.name]
        if value is not None and Path in (hint, *typing.get_args(hint)):
            value = Path(value)
        elif isinstance(value, list) and typing.get_origin(hint) is tuple:
            value = tuple(value)
        values[field.name] = value
    return kind(**values)
