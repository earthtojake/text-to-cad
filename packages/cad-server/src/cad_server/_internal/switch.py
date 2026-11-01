"""The switch: the device's engine handed from one release to another, the one move of ``current``.

An update ends here, whichever way it was asked for. The release it moves to is installed already
(``cad_server._internal.releases``, set up by its own ``cad setup``); then:

1. The engine running drains (``cad_server.engine.daemon.Daemon.drain``): no build, draw, export or agent's
   MCP call in flight -- open pages and held sessions do not count --, its door closed, and it exits.
2. A process that is not that engine -- the process being replaced is never the one replacing it --
   waits for it to be gone, takes the engine's lock (so no client starts the release before in the
   gap), points ``current`` at the release (``cad_server._internal.installations.point``) and lets go.
3. It starts that release's engine, as any client would (``cad.engine.client``: the current
   installation's), and checks it: its door answers, it runs from the release's folder, and it serves
   on the port the engine before it served (the page token is the user's, so every link stays).
4. Should any of that fail, ``current`` goes back to the release before and its engine is started
   again, on the same port.

That process is ``cad update --switch <release>`` (``helper``), which the engine starts detached
as it drains for the button (``spawn``); ``cad setup`` -- ``cad update`` from a terminal, the
install command run again -- asks the engine to drain and is that process itself (``handover``). With
no engine running there is nothing to hand over: ``current`` is pointed at the release under the
engine's lock, and the next client starts its engine. After a switch the release folders but this
one and the one before go, once nothing runs from them (``releases.collect``), and the plugin folder
follows the release left current (``follow``: its own ``cad plugin --refresh``, which writes the folder
again and, should that change it -- a switch that went back --, the copies the apps keep of it).

What a switch did is the state folder's ``update.json`` -- the releases, whether it held, why not,
and how long no engine served (``gapMs``) --, and the helper's lines go to ``update.log`` beside it. A
switch that failed is kept there before the release before's engine starts again, which reads it and says
the update failed to the pages that watched it go (``failed_lately``, ``cad_server._internal.update``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

__all__ = ["LOG", "RESULT", "failed_lately", "follow", "handover", "helper", "last", "spawn", "switch"]

LOG = "update.log"
RESULT = "update.json"
# How long the helper waits for the engine it replaces to drain and exit: a build in flight runs to its
# end, however long it takes, and a switch never cuts one.
DRAIN_SECONDS = 3600.0
# How long a release's engine has to answer at its door once started.
START_SECONDS = 60.0
# How long the release now current has to write its plugin folder and bring the apps' copies to it
# (an `npx skills add` among them).
FOLLOW_SECONDS = 600.0
# On Windows: the helper outlives the engine that started it, in a process group of its own, with no
# console of its own (``subprocess``'s names, by number, as Windows alone has them).
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def _state() -> Path:
    from cad.engine.places import state_dir

    return Path(state_dir())


def _said(told: Callable[[str], None] | None) -> Callable[[str], None]:
    """``told``, else a line on stderr, stamped: the helper's stderr is the update log."""
    if told is not None:
        return told
    return lambda line: print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} cad update: {line}", file=sys.stderr, flush=True)


def spawn(target: str, *, port: int | None, previous: str | None) -> subprocess.Popen:
    """``cad update --switch <target>``, this installation's own, started detached -- a session of
    its own (on Windows a process group of its own, no console) -- with its output appended to the
    update log: the helper that waits for this engine to exit and starts ``target``'s."""
    argv = [sys.executable, "-P", "-m", "cad_server.cli", "update", "--switch", target]
    if port:
        argv += ["--port", str(port)]
    if previous:
        argv += ["--previous", previous]
    folder = _state()
    folder.mkdir(parents=True, exist_ok=True)
    log = open(folder / LOG, "ab")  # noqa: SIM115 - handed to the child, closed here once it has it
    try:
        options: dict[str, Any] = ({"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                                   else {"start_new_session": True})
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True,
                                cwd=str(folder), **options)
    finally:
        log.close()


def _record(result: dict[str, Any]) -> None:
    """What a switch did, kept as the state folder's ``update.json``."""
    from cad._internal.atomic_replace import write_bytes_atomic

    try:
        write_bytes_atomic(_state() / RESULT, (json.dumps(result, indent=1) + "\n").encode("utf-8"))
    except OSError:
        pass


def last() -> dict[str, Any] | None:
    """The last switch, as ``update.json`` keeps it, or None."""
    try:
        found = json.loads((_state() / RESULT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def failed_lately(within: float) -> dict[str, Any] | None:
    """The last switch when it failed and ``update.json`` was written in the last ``within`` seconds, else
    None: the release before's engine, started again by that switch, reads it as it starts serving
    (``update.Update.recall``), the failure kept before it starts (``switch``)."""
    try:
        age = time.time() - (_state() / RESULT).stat().st_mtime
    except OSError:
        return None
    found = last()
    if found is None or found.get("ok") is not False or not found.get("error") or not 0 <= age <= within:
        return None
    return found


def _point(version: str, told: Callable[[str], None]) -> bool:
    """``current`` pointed at ``version`` under the engine's lock, no engine running: so no client starts
    the release before meanwhile. False when an engine holds the lock (one a client started)."""
    from cad_server._internal import installations
    from cad_server.engine import daemon
    from cad.engine import places

    held = places.lock()
    if held is None:
        return False
    try:
        installations.point(version)
        told(f"current is text-to-cad {version}")
    finally:
        daemon._drop_lock(held, places.lock_path())
    return True


def _started(version: str, port: int | None, told: Callable[[str], None]) -> tuple[bool, str]:
    """The current installation's engine started (``version``'s) and checked: its door answers, it runs
    from that installation's environment, and it serves on ``port`` when one is named. ``(ok, why not)``."""
    from cad_server._internal import installations
    from cad.engine import client

    record = installations.current()
    if record is None or record["version"] != version:
        return False, f"text-to-cad {version} is not the current installation"
    try:
        connection = client.connect(start=True, timeout=START_SECONDS)
    except ConnectionError as error:
        return False, f"text-to-cad {version}'s engine did not start: {error}"
    if connection is None:
        return False, f"text-to-cad {version}'s engine did not start"
    connection.close()
    status = client.request({"op": "status"}, start=False) or {}
    prefix = status.get("prefix")
    if not isinstance(prefix, str) or not installations._same_place(prefix, record["prefix"]):
        return False, f"the engine that answered runs from {prefix}, not text-to-cad {version}'s {record['prefix']}"
    if port:
        answer = client.request({"op": "http", "port": port}, start=False) or {}
        if "failed" in answer or not answer.get("url"):
            return False, f"text-to-cad {version}'s engine could not serve on port {port}: {answer.get('failed', 'no answer')}"
    told(f"text-to-cad {version}'s engine answers (pid {status.get('pid')})" + (f" on port {port}" if port else ""))
    return True, ""


def switch(target: str, *, port: int | None = None, previous: str | None = None,
           told: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The engine running handed to ``target``'s (steps 2 to 4 of the module), once it has exited:
    ``previous`` is the release it goes back to should ``target``'s fail, ``port`` the one the engine
    served on. What it did (``update.json``): ``ok``, ``error``, ``gapMs``."""
    from cad_server._internal import installations, releases
    from cad.engine import client

    told = _said(told)
    result: dict[str, Any] = {"from": previous, "to": target, "port": port, "ok": False, "error": None,
                              "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if not client.wait_gone(timeout=DRAIN_SECONDS):
        result["error"] = "the engine before did not stop"
        told(result["error"])
        _record(result)
        return result
    gone = time.monotonic()
    for _attempt in range(3):
        if _point(target, told):
            break
        # A client started an engine in the gap (the release before's): it goes again, at once.
        client.request({"op": "stop", "drain": True}, start=False)
        client.wait_gone(timeout=DRAIN_SECONDS)
    else:
        result["error"] = "an engine started meanwhile, and would not stop"
        told(result["error"])
        _record(result)
        return result
    ok, why = _started(target, port, told)
    result["gapMs"] = round((time.monotonic() - gone) * 1000)
    if ok:
        result["ok"] = True
        told(f"switched to text-to-cad {target} ({result['gapMs']} ms without an engine)")
        _record(result)
        try:
            removed = releases.collect({target, *([previous] if previous else [])})
            for path in removed:
                told(f"removed {path}")
        except OSError:
            pass
        return result
    result["error"] = why
    told(f"text-to-cad {target} did not take over: {why}")
    if previous and installations.current_version() == target:
        # Kept first: the release before's engine, which starts again next, reads it as it starts serving and
        # says the update failed to the pages that watched it go (``update.Update.recall``).
        _record(result)
        client.request({"op": "stop"}, start=False)
        client.wait_gone(timeout=START_SECONDS)
        if _point(previous, told):
            back, why_not = _started(previous, port, told)
            result["restored"] = back
            if not back:
                told(f"text-to-cad {previous}'s engine did not start again either: {why_not}")
    _record(result)
    return result


def handover(target: str, *, told: Callable[[str], None] | None = None) -> dict[str, Any] | None:
    """``cad setup``'s switch to ``target``: with an engine running, it is asked to drain and this
    process switches it (``switch``); with none, ``current`` points at ``target`` and the next client
    starts its engine. None when there was nothing to do: ``target`` current, and its engine running or
    none running."""
    from cad_server._internal import installations
    from cad.engine import client

    told = _said(told)
    status = client.request({"op": "status"}, start=False)
    record = installations.current()
    if status is None:
        if record is not None and record["version"] == target:
            return None
        if not _point(target, told):
            status = client.request({"op": "status"}, start=False)  # one started meanwhile: handed over
        else:
            return {"from": record["version"] if record else None, "to": target, "ok": True, "gapMs": None}
    if status is None:
        return None
    named = installations.installation_record(installations.state().read(installations._inside(target)))
    if named is not None and installations._same_place(str(status.get("prefix") or ""), named["prefix"]):
        if record is None or record["version"] != target:
            installations.point(target)
        return None
    serving = status.get("serving")
    port = serving.get("port") if isinstance(serving, dict) else None
    previous = installations.current_version()
    told(f"the engine (pid {status.get('pid')}) drains, then text-to-cad {target}'s takes its place"
         + (f" on port {port}" if port else ""))
    client.request({"op": "stop", "drain": True}, start=False)
    return switch(target, port=port, previous=previous, told=told)


def follow(told: Callable[[str], None] | None = None) -> bool:
    """The plugin folder follows the release now current (``cad_server._internal.plugin``): that
    installation's own ``cad plugin --refresh`` writes it again -- nothing changes when that release's
    setup already did -- and, should that change it (a switch that went back), brings the copies apps
    keep of it to it. Run once no lock of the installer's is held. Whether it ran and succeeded; a
    release before 0.10 has no such command, and its plugin no folder."""
    from cad_server._internal import installations

    told = _said(told)
    record = installations.current()
    if record is None:
        return False
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    named = installations.named(record)
    if named:
        environment[installations.NAME_ENV] = named
    else:
        environment.pop(installations.NAME_ENV, None)
    try:
        done = subprocess.run([record["cadgen"], "plugin", "--refresh"], env=environment, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=FOLLOW_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        told(f"the plugin folder was not written again: {type(error).__name__}: {error}")
        return False
    for line in (done.stderr or "").splitlines():
        if line.strip():
            told(line.rstrip())
    if done.returncode != 0:
        told(f"text-to-cad {record['version']}'s `cad plugin --refresh` exited {done.returncode}")
    return done.returncode == 0


def helper(target: str, *, port: int | None, previous: str | None) -> int:
    """``cad update --switch <target>``: the switch, from a process of its own, then the plugin folder
    following the release it left current (``follow``); 0 when the switch held."""
    told = _said(None)
    told(f"waiting for the engine to drain, to switch to text-to-cad {target}")
    held = switch(target, port=port, previous=previous, told=told)["ok"]
    follow(told)
    return 0 if held else 1
