"""Persistent warm-OCCT CAD worker for the CAD Viewer (viewer-specific).

A long-lived subprocess that imports cadgen / OpenCASCADE ONCE and then services
many STEP build/export requests in-process, so the viewer pays the ~OCP-import +
kernel-warm cost a single time instead of per request. It is the CAD Viewer's
specific wrapper around the GENERAL cadgen cores — it adds no geometry logic of its
own; it only calls :func:`cadgen.step_artifact_cli.run_cli_payload` and
:func:`cadgen.step_export_target.run_cli_payload` (the same callables the agent CLI
uses), passing ``reset_runtime_closure=True`` so repeated warm builds record the
identical source closure a cold CLI would.

There is NO process channel back to the agent's STEP CLI: this worker is a peer
entrypoint that calls the shared cadgen functions directly. It is the web viewer
server's build/export backend.

Protocol — newline-delimited JSON-RPC 2.0 on stdio:
  request : {"jsonrpc":"2.0","id":N,"method":"invoke",
             "params":{"module":"cadgen.step_artifact_cli","args":[...],"repo_root":"..."}}
  response: {"jsonrpc":"2.0","id":N,"result":{...cadgen payload dict...}}
            {"jsonrpc":"2.0","id":N,"error":{"code":C,"message":"..."}}

Build/export FAILURES are returned as a normal ``result`` dict shaped
``{"ok": false, "error": ...}`` (mirroring the cold-subprocess contract the bridge
already understands); JSON-RPC ``error`` is reserved for PROTOCOL faults (bad
method / malformed request). A hard OCP fault that kills the process is detected by
the client as EOF and respawned.

stdout is reserved exclusively for protocol frames: at startup fd 1 is redirected
to fd 2, so any stdout writes from cadgen/OCP (C-level included) land on stderr and
cannot corrupt the frame stream. Frames are written to a dup() of the original
stdout taken before the redirect.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

# --- stdout isolation: do this BEFORE importing cadgen (which may print) ----------
_RPC_OUT_FD = os.dup(1)  # keep the real stdout (the pipe to the client) for frames
os.dup2(2, 1)  # fd 1 -> stderr; all later stdout (incl. C-level OCP prints) -> stderr
_RPC_OUT = os.fdopen(_RPC_OUT_FD, "w", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr  # Python-level insurance; the C-level guarantee is the dup2

# --- JSON-RPC error codes --------------------------------------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _module_dispatch():
    """Map a cadgen CLI module name to its in-process payload entrypoint. Imported
    lazily inside the worker process so the (warm) OCP import happens here, not in
    the parent server."""
    from cadgen import dxf_artifact, implicit_artifact, implicit_export, step_artifact_cli, step_export_target

    return {
        "cadgen.dxf_artifact": dxf_artifact.run_cli_payload,
        "cadgen.implicit_artifact": implicit_artifact.run_cli_payload,
        "cadgen.implicit_export": implicit_export.run_cli_payload,
        "cadgen.step_artifact_cli": step_artifact_cli.run_cli_payload,
        "cadgen.step_export_target": step_export_target.run_cli_payload,
    }


_DISPATCH = None


def _invoke(params: dict) -> dict:
    """Handle an ``invoke`` request: run the requested cadgen CLI module in-process,
    warm, and return its payload dict. Build/export failures become an
    ``{"ok": false, "error": ...}`` result (not a JSON-RPC error)."""
    global _DISPATCH
    if _DISPATCH is None:
        _DISPATCH = _module_dispatch()
    module = str(params.get("module") or "")
    run = _DISPATCH.get(module)
    if run is None:
        return {"ok": False, "error": f"Unknown cadgen module for worker: {module!r}"}
    args = list(params.get("args") or [])
    repo_root = str(params.get("repo_root") or "")
    # Match the cold subprocess exactly: it ran with cwd=repo_root. cadgen resolves
    # geometry via the explicit --repo-root, but chdir keeps any cwd-relative logging
    # / parity identical. Process-global + single-threaded request loop => safe.
    if repo_root and os.path.isdir(repo_root):
        try:
            os.chdir(repo_root)
        except OSError:
            pass
    try:
        return dict(run(args, reset_runtime_closure=True))
    except SystemExit as exc:  # argparse error => exit(2); surface as a failure dict
        return {"ok": False, "error": f"cadgen {module} argument error (exit {exc.code})"}
    except Exception as exc:  # noqa: BLE001 — build/export failure -> contract dict
        return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}


def _handle(request: dict) -> dict | None:
    """Dispatch one parsed request to a response (or None for a notification)."""
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _error(req_id, INVALID_PARAMS, "params must be an object")
    if method == "invoke":
        return _result(req_id, _invoke(params))
    if method == "ping":
        return _result(req_id, {"ok": True, "pid": os.getpid()})
    if method == "shutdown":
        return _result(req_id, {"ok": True})
    return _error(req_id, METHOD_NOT_FOUND, f"Unknown method: {method!r}")


def _result(req_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _write(frame: dict) -> None:
    _RPC_OUT.write(json.dumps(frame, separators=(",", ":")))
    _RPC_OUT.write("\n")
    _RPC_OUT.flush()


def serve(stdin=None) -> int:
    """Read newline-delimited JSON-RPC requests until EOF or ``shutdown``."""
    stream = stdin if stdin is not None else sys.stdin
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            _write(_error(None, PARSE_ERROR, "Invalid JSON"))
            continue
        if not isinstance(request, dict):
            _write(_error(None, INVALID_REQUEST, "Request must be an object"))
            continue
        try:
            response = _handle(request)
        except Exception as exc:  # noqa: BLE001 — never let one request kill the loop
            _write(_error(request.get("id"), INTERNAL_ERROR, str(exc)))
            continue
        if response is not None:
            _write(response)
        if request.get("method") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
