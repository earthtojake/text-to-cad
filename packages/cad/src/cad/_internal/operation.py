"""``python -m cad._internal.operation``: one operation of a document type, run for the server's command in
an environment of the library that holds the integration the operation needs.

The ``cad`` command runs in the server's environment, which holds no integration but the ones it was
installed with; an operation that needs another (a 3D type's ``dfm``: a mesh's the trimesh integration's,
a STEP's, an xbf's, a model's and a DXF's build123d's; a board's ``drc``, the kicad integration's) runs
here instead, in the environment the server made for that integration (``cad[<integration>]`` at its own
release). It reads one request on stdin -- ``{"type", "operation", "args", "kwargs"}``, plain JSON -- calls
``cad.<type>.<operation>(*args, **kwargs)`` and writes one line on stdout: ``{"result": ...}``, the result
dataclass as data (a ``Path`` as text), or ``{"error": ...}``, the exception's words, with ``"reason"``
where the exception is the caller's mistake rather than the work's (``REASONS``: an argument refused by name
``invalid_argument``, a document the engine does not hold ``not_found``), so the server's command says it
as its own call would (exit 2), not as a failure. Anything else the operation says goes to stderr, untouched.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["REASONS", "main"]

#: The exceptions that are the caller's mistake, by ``(module, class)``, and the reason the server's command
#: says each by (``cad_server._internal.cli_errors.REASONS``): told by name, nothing of the engine imported.
REASONS: dict[tuple[str, str], str] = {
    ("cad._internal.refused", "ArgumentRefused"): "invalid_argument",
    ("cad.engine.serve", "NotHeld"): "not_found",
    ("cad.engine.snapshot", "NoSuchFile"): "not_found",
}


def _reason(error: BaseException) -> str | None:
    return next((REASONS[(kind.__module__, kind.__name__)] for kind in type(error).__mro__
                 if (kind.__module__, kind.__name__) in REASONS), None)


def _plain(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _answer(request: dict[str, Any]) -> dict[str, Any]:
    import importlib

    from cad.registry import DOCUMENT_TYPES

    document_type, operation = request.get("type"), request.get("operation")
    entry = DOCUMENT_TYPES.get(str(document_type))
    if entry is None or operation not in entry.operation_names:
        return {"error": f"no operation {operation!r} of a document type {document_type!r}"}
    function = getattr(importlib.import_module(f"cad.{entry.id}"), str(operation))
    try:
        result = function(*request.get("args") or [], **request.get("kwargs") or {})
    except Exception as error:  # noqa: BLE001 - the server's command reports it, as its own call would
        reason = _reason(error)
        return {"error": str(error).strip() or type(error).__name__, **({"reason": reason} if reason else {})}
    return {"result": _plain(dataclasses.asdict(result))}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except ValueError as error:
        request = {"error": f"no request: {error}"}
    answer = {"error": request["error"]} if "error" in request else _answer(request)
    try:
        line = json.dumps(answer, separators=(",", ":"), allow_nan=False)
    except ValueError as error:  # a figure that is no finite number is no JSON
        line = json.dumps({"error": f"the result is not JSON: {error}"})
    sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
