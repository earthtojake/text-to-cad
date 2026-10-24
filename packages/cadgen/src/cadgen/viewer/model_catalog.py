"""The documents the engine holds by id (a model's), as catalog rows, without kernel imports."""
from __future__ import annotations

from cadgen.engine.client import request
from cadgen.engine.ids import is_id


def held(ident: str) -> tuple[dict | None, str]:
    """The model the engine holds of id ``ident``, and why it holds none (``""`` when it does):
    the engine's own words, naming the command that builds it again. Nothing is built."""
    answer = request({"op": "model_info", "id": ident}, start=False)
    if not answer:
        return None, f"no document {ident} is held: no engine is running"
    if "failed" in answer:
        return None, str(answer["failed"])
    return answer["model"], ""


def entry(value: str) -> dict | None:
    """The catalog row of the model document ``value`` (its id) while the engine holds it; None for
    anything else. The row's ``file`` is the id: a model has no file to browse (``sourcePath``)."""
    if not is_id(value):
        return None
    model, _why = held(value)
    if model is None:
        return None
    return {"id": value, "file": value, "name": model["source"]["name"], "sourcePath": None,
            "kind": "xbf", "sourceFormat": "model", "url": "", "hash": "model", "bytes": 0}
