"""The documents the engine holds by id (a model's), as catalog rows, without kernel imports."""
from __future__ import annotations

import re

from cad.engine.client import request


def held(ident: str) -> dict | None:
    """The model a live worker holds of id ``ident``, asked of the engine; None where none does, or no engine
    runs. Nothing is built."""
    answer = request({"op": "model_info", "id": ident}, start=False) or {}
    return answer.get("model")


def name(model: dict) -> str:
    """A model's document's name: its ``.xbf``'s file name, as every list names that file and its page names it
    whether a worker holds it or it is read from the file; the function's name only for a model with no ``.xbf``.
    The function's own name stays its source's (``source.function`` in its envelope)."""
    source = model.get("source") or {}
    xbf = source.get("xbf")
    return re.split(r"[\\/]", xbf)[-1] if isinstance(xbf, str) and xbf else str(source.get("name") or "")


def row(value: str, model: dict) -> dict:
    """The catalog row of the model document ``value`` the engine holds as ``model`` (``held``)."""
    built = model.get("version") or model.get("builtAt")
    return {"id": value, "file": value, "name": name(model), "sourcePath": None,
            "kind": "xbf", "sourceFormat": "model", "url": "",
            "hash": f"model:{built}" if built is not None else "model", "bytes": 0}
