"""``cadgen daemon status`` — is anything warm, and what is it doing?

Warm compute you cannot see is warm compute you stop trusting. The daemon is on by
default now and starts itself, so the question "why was that build slow" needs an answer
that is not "read the log file beside a hashed socket path". Same reasoning as the
CAD Viewer's instance list (`cadgen viewer list`).

Asks the running daemon rather than inspecting the filesystem: the socket's existence
proves nothing (a stale file outlives a killed daemon), and only the supervisor knows
which workers are busy.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from cadgen.daemon import client as daemon_client

DEFAULT_PROG = "cadgen daemon status"


def _age(started: float) -> str:
    if not started:
        return ""
    seconds = max(0, int(time.time() - started))
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _render(status: dict) -> str:
    workers = status.get("workers") or []
    busy = sum(1 for w in workers if w.get("busy"))
    bound = [w for w in workers if w.get("model")]
    lines = [
        f"CAD daemon running (pid {status.get('pid')}, up {_age(status.get('startedAt') or 0)})",
        f"  socket   {status.get('socket')}",
        f"  version  cadgen {status.get('version') or '?'}  token {status.get('token') or '?'}",
        f"  workers  {len(bound)} bound ({busy} busy), {status.get('spares', 0)} spare"
        f"{f' (+{status.get(\"sparesPending\")} starting)' if status.get('sparesPending') else ''}",
    ]
    for worker in bound:
        state = "busy" if worker.get("busy") else "idle"
        # A worker is bound to ONE model, so which model it holds is the first thing
        # to know about it -- "3 workers" says nothing about whether the build you are
        # waiting on has a warm one. An extra is a second worker on a busy model.
        extra = "  extra" if worker.get("extra") else ""
        lines.append(
            f"    pid {worker.get('pid')}  {state}  {worker.get('jobs', 0)} jobs{extra}  {worker.get('model')}"
        )
    lines.append(
        f"  totals   {status.get('jobs', 0)} jobs, "
        f"{status.get('imports', 0)} imports, "
        f"{status.get('concurrent', 0)} concurrent (extras), "
        f"{status.get('recycles', 0)} recycles, "
        f"{status.get('crashes', 0)} crashes"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="Show the warm CAD daemon's state")
    parser.add_argument("--json", action="store_true", dest="json_result")
    args = parser.parse_args(list(argv) if argv is not None else None)

    status = daemon_client.status()
    if args.json_result:
        sys.stdout.write(json.dumps(status or {}, separators=(",", ":")) + "\n")
        return 0
    if not status:
        # "One starts on the next build" is false where the daemon cannot run at all, and
        # a user following it would keep waiting for a warm process that never appears.
        if not daemon_client.daemon_supported():
            sys.stdout.write(
                "The CAD daemon cannot run on this platform, so builds are always cold. "
                "It needs a local IPC family — AF_UNIX or AF_PIPE — and this Python "
                "offers neither; nothing needs switching off.\n"
            )
            return 0
        sys.stdout.write(
            "No CAD daemon is running. One starts on the next build "
            "(set CADGEN_DAEMON=0 to keep builds cold).\n"
        )
        return 0
    sys.stdout.write(_render(status) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
