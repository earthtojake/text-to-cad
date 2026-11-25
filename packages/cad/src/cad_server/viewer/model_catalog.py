"""The documents the engine holds by id (a model's), as catalog rows, without kernel imports."""
from __future__ import annotations

from cad.engine.client import request


def held(ident: str) -> dict | None:
    """The model a live worker holds of id ``ident``, asked of the engine; None where none does, or no engine
    runs. Nothing is built."""
    answer = request({"op": "model_info", "id": ident}, start=False) or {}
    return answer.get("model")


def row(value: str, model: dict) -> dict:
    """The catalog row of the model document ``value`` the engine holds as ``model`` (``held``)."""
    built = model.get("version") or model.get("builtAt")
    return {"id": value, "file": value, "name": model["source"]["name"], "sourcePath": None,
            "kind": "xbf", "sourceFormat": "model", "url": "",
            "hash": f"model:{built}" if built is not None else "model", "bytes": 0}
