"""``python -P -m cad._internal.kernel_run MODULE VERB``: one library verb, run in this process, the CAD kernel's
environment.

A server command whose own environment has no CAD kernel runs its verb here (``cad_server._internal.kernel_verb``).
The verb's keyword arguments come in on stdin as one JSON object; its outcome goes out on stdout as one JSON line,
``{"returned": <the result>}`` or, when the verb raises, ``{"raised": ...}`` (:func:`told`), so the command reports
it as it reports a call in its own process. What the verb prints goes to stderr, with its progress, even from the
kernel's C++: stdout is the answer. :func:`encode` and :func:`decode` are both ends of the JSON: a dataclass as its
fields, and back as the type its annotation names, its paths ``Path`` and its tuples tuples again.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import sys
import traceback
import types
import typing
from pathlib import Path
from typing import Any

USAGE = "usage: python -P -m cad._internal.kernel_run MODULE VERB < KEYWORDS.json"


def encode(value: Any) -> Any:
    """``value`` as JSON can carry it: a dataclass as its fields, a path as its text, an array as its list."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):  # a numpy array or scalar
        return value.tolist()
    return value


def decode(hint: Any, value: Any) -> Any:
    """``value``, from :func:`encode`, as the type ``hint`` names."""
    if value is None:
        return None
    if hint is Path:
        return Path(value)
    if dataclasses.is_dataclass(hint) and isinstance(value, dict):
        hints = typing.get_type_hints(hint)
        return hint(**{field.name: decode(hints[field.name], value[field.name])
                       for field in dataclasses.fields(hint) if field.name in value})
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        # ``Path | None`` is a path; ``str | dict | None`` is whichever came, so it is left as it came.
        kinds = [arg for arg in args if arg is not type(None)]
        return decode(kinds[0], value) if len(kinds) == 1 else value
    if origin is tuple and isinstance(value, list):
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], item) for item in value)
        return tuple(decode(arg, item) for arg, item in zip(args, value)) if len(args) == len(value) else tuple(value)
    return value


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or not args[0].startswith("cad."):
        print(USAGE, file=sys.stderr)
        return 2
    verb = getattr(importlib.import_module(args[0]), args[1])
    hints = typing.get_type_hints(verb)
    keywords = {name: decode(hints.get(name), value) for name, value in json.loads(sys.stdin.read() or "{}").items()}
    # The answer keeps stdout; everything else written to it goes to stderr, at the descriptor, so what the
    # kernel's C++ prints (OCCT's reader messages) and what a child process inherits cannot take its place.
    sys.stdout.flush()
    answer = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    try:
        outcome: dict[str, Any] = {"returned": encode(verb(**keywords))}
    except Exception as error:  # noqa: BLE001 -- handed to the command, which reports it
        outcome = {"raised": told(error)}
    sys.stdout.flush()
    answer.write(json.dumps(outcome, default=str, separators=(",", ":")) + "\n")
    answer.close()
    return 0


def told(error: Exception) -> dict[str, Any]:
    """``error`` as the command remakes and reports it: its type and module, its arguments where JSON carries them
    (an ``OSError``'s errno and file), its message, its frames innermost last (``cad_server.analytics``'s told
    form, ``{file, function, line}``) and its traceback as Python prints it."""
    kind = type(error)
    frames = [{"file": frame.f_code.co_filename, "function": frame.f_code.co_qualname, "line": int(line or 0)}
              for frame, line in traceback.walk_tb(error.__traceback__)]
    found: dict[str, Any] = {"module": kind.__module__, "type": kind.__qualname__, "message": str(error),
                             "frames": frames, "traceback": "".join(traceback.format_exception(error))}
    try:
        found["args"] = json.loads(json.dumps(encode(list(error.args))))
    except (TypeError, ValueError):
        pass
    return found


if __name__ == "__main__":
    raise SystemExit(main())
