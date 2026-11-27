"""kernel.py: the harness cad's build runs under on the WebAssembly kernel (prototype).

``build`` is ``cad.engine.build.build``, the function an engine worker calls, in this one process. What had to be
stood in for it to run here is done below, each named in ``SHIMS`` with what in cad needs it: the list is what a
real port has to settle in the library itself.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SHIMS: list[dict[str, str]] = []


def shim(what: str, why: str) -> None:
    SHIMS.append({"what": what, "why": why})


def shims() -> str:
    return json.dumps(SHIMS)


# The kernel binding here is one extension module, not a package of them (the native wheel's ``OCP`` is a folder).
# cad's lazy import of the kernel (``cad/_internal/lazy_kernel.py``: ``KERNEL``, its finder wraps ``OCP``'s loader in
# ``LazyLoader``) then leaves ``from OCP.BRep import ...`` with a parent that is no package and has not yet put its
# submodules in ``sys.modules``: "No module named 'OCP.BRep'; 'OCP' is not a package" (first at
# ``cad/engine/kernel/memo.py:183``). Imported here, before cad installs its finder, it is an ordinary loaded module.
import OCP  # noqa: E402,F401

shim("OCP imported before cad", "cad/_internal/lazy_kernel.py makes OCP lazy, which a one-file OCP (no package) "
     "cannot be: from OCP.X import fails (cad/engine/kernel/memo.py:183)")

WORK = Path("/work")


def warm() -> None:
    """Import what a build imports (build123d, the kernel's modules, cad's build), once, so a build's time is its own."""
    import build123d

    build123d.Box  # the lazy module's first attribute loads it
    from cad.engine import build as _build, document as _document, mesh as _mesh  # noqa: F401
    from cad.engine.kernel import determinism as _determinism, memo as _memo  # noqa: F401


def _write(request: dict) -> Path:
    folder = WORK
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in (request.get("files") or {}).items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    script = folder / request["name"]
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(request["text"], encoding="utf-8")
    return script


def build(request_json: str):
    from cad.engine.build import build as cad_build

    request = json.loads(request_json)
    script = _write(request)
    log: list[str] = []
    started = time.perf_counter()
    reports = cad_build(script, request.get("functions"), log=log.append, cwd=script.parent)
    seconds = time.perf_counter() - started
    # What the build said of the script's parameters, kept here as it said it (a round trip through JSON in
    # JavaScript makes 2.0 the integer 2, which ``parameters.standing`` rightly refuses as another value).
    _ROWS[request["name"]] = (request["text"], [row for report in reports for row in report.get("parameters") or []])
    written = sorted(str(path) for path in script.parent.rglob("*.xbf"))
    first = next((path for path in written if Path(path).stem in {r.get("name") for r in reports}), written[0] if written else None)
    data = Path(first).read_bytes() if first else b""
    return json.dumps({"reports": reports, "log": log, "seconds": seconds, "written": written, "file": first},
                      default=str), data


_ROWS: dict[str, tuple[str, list[dict]]] = {}


def with_values(request_json: str):
    """The text of the script last built under ``name`` with parameters set to ``values``, written as cad's Save
    writes them: checked against the rows that build reported (``parameters.changes``, ``standing``), each number
    spelled (``spelled``) in place of the one there (``splice``)."""
    from cad.engine import parameters

    request = json.loads(request_json)
    text, rows = _ROWS[request["name"]]
    data = text.encode("utf-8")
    edits = parameters.changes(rows, request["values"])
    parameters.standing(data, [row for row in rows if row.get("span")], request["name"])
    made = parameters.splice(data, [(row["span"][0], row["span"][1], parameters.spelled(value, row["kind"]))
                                    for row, value in edits])
    return json.dumps({"text": made.decode("utf-8"), "changed": [row["name"] for row, _value in edits]}), b""


def preview(request_json: str):
    """A model at other parameter values, nothing written: ``cad.engine.build.preview`` on the script a build left
    in the kernel's folder. Its structure, and each part's shape bytes one after another."""
    from cad.engine.build import preview as cad_preview

    request = json.loads(request_json)
    script = WORK / request["name"]
    started = time.perf_counter()
    report, data = cad_preview(script, request["model"], request["values"], cwd=script.parent)
    return json.dumps({**report, "seconds": time.perf_counter() - started}, default=str), data
