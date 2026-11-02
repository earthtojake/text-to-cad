"""A library verb that needs the CAD kernel, run where the kernel is, for the server command that wraps it.

The server's own process runs in the core, where the CAD kernel is not installed (``base``), and some verbs read a
part's exact faces with OCCT. :func:`in_kernel` is such a verb with its own signature and docstring, so a command's
parser is still generated from the verb (``cli_from_function`` reads them through ``functools.wraps``). Called, it
runs the verb in this process when this installation carries the kernel itself, else in the installation's base,
the environment ``cad run`` runs a program in: the library's runner (``cad._internal.kernel_run``) in the base's
Python, the verb's arguments in on stdin and its outcome out on stdout, one JSON line each way. The outcome comes
back as the verb's own result type or its own error, so the command prints and reports it as it would a call in
its own process. What the verb says on stderr (``verbose``'s stages) is the command's.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import json
import subprocess
import sys
import typing
from typing import Any, Callable

RUNNER = "cad._internal.kernel_run"


def in_kernel(target: tuple[str, str], *, prog: str) -> Callable[..., Any]:
    """The verb ``target`` (``(module, name)``), run where the CAD kernel is (see the module)."""
    module_name, attribute = target
    verb = getattr(importlib.import_module(module_name), attribute)

    @functools.wraps(verb)
    def call(*args: Any, **kwargs: Any) -> Any:
        from cad._internal.kernel_run import decode, encode
        from cad_server._internal import base

        env = base.ensure(told=lambda line: print(f"{prog}: {line}", file=sys.stderr, flush=True), engine=True)
        assert env is not None  # made, or refused
        if env.own:
            return verb(*args, **kwargs)
        keywords = inspect.signature(verb).bind(*args, **kwargs).arguments
        sys.stdout.flush()
        done = subprocess.run([env.python, "-P", "-m", RUNNER, module_name, attribute],
                              input=json.dumps(encode(keywords), default=str),
                              stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        lines = (done.stdout or "").strip().splitlines()
        try:
            answer = json.loads(lines[-1]) if done.returncode == 0 and lines else None
        except ValueError:
            answer = None
        if not isinstance(answer, dict) or not ("returned" in answer or isinstance(answer.get("raised"), dict)):
            raise RuntimeError(f"the CAD kernel's environment ({env.python}) did not run {module_name}.{attribute} "
                               f"(exit code {done.returncode})")
        if "raised" in answer:
            raise raised(answer["raised"])
        return decode(typing.get_type_hints(verb).get("return"), answer["returned"])

    return call


def raised(error: dict[str, Any]) -> Exception:
    """The verb's error, from the runner's account of it: its own type when that is an exception this process can
    import and make from its message, else a ``RuntimeError`` naming it."""
    module_name, qualname, message = (str(error.get(key, "")) for key in ("module", "type", "message"))
    try:
        kind: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            kind = getattr(kind, part)
        if isinstance(kind, type) and issubclass(kind, Exception):
            return kind(message)
    except Exception:  # noqa: BLE001 -- a type this process lacks or cannot make: named in the RuntimeError
        pass
    return RuntimeError(f"{qualname or 'error'}: {message}" if message else qualname or "error")
