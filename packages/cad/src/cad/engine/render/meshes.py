"""Where the prototype's meshes come from: the engine's, never OCCT's.

- ``from_daemon``: the daemon serves the document and meshes every part in its warm pool
  (``POST /api/v1/documents/<kind>/<id>/mesh``), then hands each part's XBM buffer
  (``GET .../parts/<key>``) --
  the bytes the viewer draws. Each request carries the user's token, as the engine's own
  clients send it (``Authorization: Bearer``), and the POST the page's guard header.
- ``save``/``load``: those buffers kept in a folder, a cold run's pre-built cache (prototype
  only: the engine itself writes no mesh to disk).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _get(url: str, token: str, method: str = "GET") -> bytes:
    headers = {"Authorization": f"Bearer {token}", **({"x-cadgen-viewer": "1"} if method == "POST" else {})}
    request = Request(url, data=b"" if method == "POST" else None, method=method, headers=headers)
    with urlopen(request, timeout=900) as answer:  # noqa: S310 - loopback engine
        return answer.read()


def _fetch(url: str, token: str) -> tuple[dict[str, Any], dict[str, bytes], dict[str, float]]:
    timings = {}
    started = time.perf_counter()
    meshed = json.loads(_get(f"{url}/mesh", token, "POST"))
    timings["mesh"] = time.perf_counter() - started
    structure = json.loads(_get(f"{url}/structure", token))
    started = time.perf_counter()
    buffers = {p["key"]: _get(f"{url}/parts/{p['key']}", token) for p in structure["prototypes"]}
    timings["fetch"] = time.perf_counter() - started
    timings["pool_seconds"] = meshed.get("seconds", 0.0)
    return structure, buffers, timings


def from_daemon(path: Path) -> tuple[dict[str, Any], dict[str, bytes], dict[str, float]]:
    """The document's structure and every part's XBM buffer, from the daemon's mesh cache."""
    from cad.engine.client import request

    answer = request({"op": "serve", "path": str(Path(path).resolve())})
    if not answer or "failed" in answer:
        raise RuntimeError(f"the engine would not serve {path}: {(answer or {}).get('failed', 'no daemon')}")
    parsed = urlparse(answer["url"])
    # The engine's API names a document under its kind: a STEP's ``step``, an ``.xbf``'s ``xbf``.
    kind = {".stp": "step", ".step": "step"}.get(Path(path).suffix.lower(), "xbf")
    return _fetch(f"{parsed.scheme}://{parsed.netloc}/api/v1/documents/{kind}/{answer['doc']}", answer["token"])


def save(folder: Path, buffers: dict[str, bytes]) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for key, data in buffers.items():
        (folder / f"{key}.xbm").write_bytes(data)


def load(folder: Path, keys: list[str]) -> dict[str, bytes]:
    folder = Path(folder)
    return {key: (folder / f"{key}.xbm").read_bytes() for key in keys}
