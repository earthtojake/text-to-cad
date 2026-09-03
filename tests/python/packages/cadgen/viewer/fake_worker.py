"""A stand-in compile worker that speaks the real frame protocol.

Used by ``test_compile_integration.py`` to drive the supervisor through
outcomes a real kernel would take minutes to reach — and through a crash, which
a real kernel reaches only by being handed a document that segfaults it.

It never imports cadgen. The BEHAVIOUR is selected by a MARKER in the document's
name, so a test picks an outcome by asking to compile a differently-named file:

    crash   one progress frame, then os.abort() mid-work
    raise   an error frame (the worker caught an exception)
    hang    silence forever, for the idle watchdog
    long    ~8s of narrated work, long enough to exhaust the pool
    slow    ~2s of narrated work, for concurrency tests
    (else)  four frames and a result, as fast as the pipe allows

Matched as a SUBSTRING, deliberately. An ``endswith`` check reads fine and is
quietly wrong: ``slow2.step`` does not end with ``slow.step``, so a concurrency
test using ``slow.step`` and ``slow2.step`` as its two documents would have one
real build and one instant one, and would pass without ever putting two builds
in flight at the same time.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

SPAWN_LOG = os.environ.get("FAKE_WORKER_SPAWN_LOG")


def main(argv: list[str]) -> int:
    port = int(argv[argv.index("--frame-port") + 1])
    token = argv[argv.index("--token") + 1]
    sock = socket.create_connection(("127.0.0.1", port))

    def send(frame: dict) -> None:
        sock.sendall(json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n")

    send({"hello": token, "pid": os.getpid()})
    if SPAWN_LOG:
        with open(SPAWN_LOG, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        request_id = request.get("id")
        candidate = str(request.get("candidate") or "")
        run_id = f"run-{os.getpid()}"

        def progress(**fields):
            payload = {
                "phase": "components",
                "label": "Meshing components",
                "index": 3,
                "count": 4,
                "detail": "",
                "done": 0,
                "total": 4,
                "determinate": True,
                "phaseStartedAt": 0,
                "elapsedMs": 0,
            }
            payload.update(fields)
            send({"id": request_id, "runId": run_id, "progress": payload})

        name = os.path.basename(candidate)
        if "hang" in name:
            time.sleep(3600)
        elif "crash" in name:
            progress(done=1)
            time.sleep(0.05)
            os.abort()
        elif "raise" in name:
            # The real worker's error frame: `error` is the exception's BARE
            # message, because the parent splices it into "STEP import failed:
            # {error}" and a person reads the result. The class name is its own
            # field and never part of that sentence.
            send(
                {
                    "id": request_id,
                    "error": "widget.step is stale relative to its source",
                    "errorType": "StaleDocumentError",
                    "traceback": "...",
                }
            )
        else:
            steps, pause = 4, 0.0
            if "long" in name:
                steps, pause = 16, 0.5
            elif "slow" in name:
                steps, pause = 4, 0.5
            for index in range(1, steps + 1):
                progress(done=index, total=steps, detail=f"component-{index}")
                if pause:
                    time.sleep(pause)
            send(
                {
                    "id": request_id,
                    "result": {
                        "ok": True,
                        "document": candidate,
                        "package": "/store/pkg",
                        "skipped": False,
                        "contended": False,
                    },
                }
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
