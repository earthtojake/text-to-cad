"""Where the prototype's meshes come from: the engine's, never OCCT's.

- ``from_daemon``: the daemon serves the document and meshes every part in its warm pool
  (``POST /api/doc/<id>/mesh``), then hands each part's XBM buffer (``GET .../part/<key>``) --
  the bytes the viewer draws.
- ``from_server``: the same from a server of this process (``serve.Server``), as
  ``snapshot(..., daemon=False)`` meshes.
- ``save``/``load``: those buffers kept in a folder, a cold run's pre-built cache (prototype
  only: the engine itself writes no mesh to disk).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


def _get(url: str, method: str = "GET") -> bytes:
    with urlopen(Request(url, method=method), timeout=900) as answer:  # noqa: S310 - loopback engine
        return answer.read()


def _fetch(url: str) -> tuple[dict[str, Any], dict[str, bytes], dict[str, float]]:
    timings = {}
    started = time.perf_counter()
    meshed = json.loads(_get(f"{url}/mesh", "POST"))
    timings["mesh"] = time.perf_counter() - started
    structure = json.loads(_get(url))
    started = time.perf_counter()
    buffers = {p["key"]: _get(f"{url}/part/{p['key']}") for p in structure["prototypes"]}
    timings["fetch"] = time.perf_counter() - started
    timings["pool_seconds"] = meshed.get("seconds", 0.0)
    return structure, buffers, timings


def from_daemon(path: Path) -> tuple[dict[str, Any], dict[str, bytes], dict[str, float]]:
    """The document's structure and every part's XBM buffer, from the daemon's mesh cache."""
    from cadgen.engine.client import request

    answer = request({"op": "serve", "path": str(Path(path).resolve())})
    if not answer or "failed" in answer:
        raise RuntimeError(f"the engine would not serve {path}: {(answer or {}).get('failed', 'no daemon')}")
    parsed = urlparse(answer["url"])
    url = f"{parsed.scheme}://{parsed.netloc}/api/doc/{parse_qs(parsed.query)['doc'][0]}"
    return _fetch(url)


def from_server(path: Path) -> tuple[dict[str, Any], dict[str, bytes], dict[str, float]]:
    from cadgen.engine.serve import Server

    server = Server(port=0)
    server.start()
    try:
        ident = server.add(Path(path).resolve())
        return _fetch(f"{server.url}/api/doc/{ident}")
    finally:
        server.stop()


def save(folder: Path, buffers: dict[str, bytes]) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for key, data in buffers.items():
        (folder / f"{key}.xbm").write_bytes(data)


def load(folder: Path, keys: list[str]) -> dict[str, bytes]:
    folder = Path(folder)
    return {key: (folder / f"{key}.xbm").read_bytes() for key in keys}
