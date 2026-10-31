"""The documents the engine holds by id (a model's), as catalog rows, without kernel imports."""
from __future__ import annotations

from cad.engine.client import request
from cad.engine.ids import is_id


def held(ident: str) -> tuple[dict | None, str, str]:
    """The model the engine holds of id ``ident``, why it holds none (``""`` when it does) -- the
    engine's own words, naming the command that builds it again -- and the state the engine names
    for one it does not hold (``unsaved``, ``detached``; ``""`` when it names none). Nothing is built."""
    answer = request({"op": "model_info", "id": ident}, start=False)
    if not answer:
        return None, f"no document {ident} is held: no engine is running", ""
    if "failed" in answer:
        return None, str(answer["failed"]), str(answer.get("state") or "")
    return answer["model"], "", ""


def entry(value: str) -> dict | None:
    """The catalog row of the model document ``value`` (its id) while the engine holds it; None for
    anything else. The row's ``file`` is the id: a model has no file to browse (``sourcePath``), and
    its name menu's Files opens where the explorer was last, else the person's home folder; nothing
    reads the script. Its ``hash`` is the build the engine holds (its ``version``), so a page that
    shows the model hears a rebuild as it hears a file written again: its picture is taken again."""
    if not is_id(value):
        return None
    model, _why, _state = held(value)
    if model is None:
        return None
    built = model.get("version") or model.get("builtAt")
    return {"id": value, "file": value, "name": model["source"]["name"], "sourcePath": None,
            "kind": "xbf", "sourceFormat": "model", "url": "",
            "hash": f"model:{built}" if built is not None else "model", "bytes": 0}
