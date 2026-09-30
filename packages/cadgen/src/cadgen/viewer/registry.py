"""A best-effort registry of running CAD Viewers, so instances can be found and
stopped (``main.py list`` / ``main.py stop`` read this directory).

Modelled on TensorBoard's ``.tensorboard-info``: each live server drops a small
JSON file in the system temp dir naming itself. Liveness is an HTTP IDENTITY
PROBE against ``/__cad/server`` requiring a matching pid, never a signal —
after a hard kill the port is free for anything else to take, and acting on a
stale file that names a stranger's port would be the worst thing ``stop`` could
do.

Failing closed here always means "no registry entry", never "no viewer": a
shared ``/tmp`` we do not own must not stop a viewer from starting.

A DETACHED viewer's output goes to a log in the same directory, and the log
outlives the server: a server that crashes, or is killed, leaves the only
account of why. A clean ``stop`` removes its instance's log; the logs of
instances that ended any other way are pruned (``prune_logs``) once a day old,
or beyond the newest ``LOG_KEEP_COUNT``.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic

__all__ = [
    "REGISTRY_DIR_NAME",
    "PROBE_TIMEOUT_SECONDS",
    "LOG_ENV",
    "LOG_KEEP_SECONDS",
    "LOG_KEEP_COUNT",
    "registry_dir",
    "entry_path",
    "create_log",
    "remove_log",
    "prune_logs",
    "register",
    "unregister",
    "read_entries",
    "find_by_port",
    "probe",
    "live_entries",
]

REGISTRY_DIR_NAME = "cadgen-viewer-info"
PROBE_TIMEOUT_SECONDS = 0.5
# How a --detach launcher tells its server which log its output goes to.
LOG_ENV = "CADGEN_VIEWER_LOG"
# A gone instance's log is kept this long, and only the newest this many.
LOG_KEEP_SECONDS = 24 * 60 * 60
LOG_KEEP_COUNT = 10

# The server source directory. Node computed this as the pathname of an
# import.meta.url, which percent-encodes spaces and yields a leading-slash
# drive path on Windows; nothing pins that shape and only the `list` printout
# reads it, so this is simply the correct spelling.
_PACKAGE_DIR = str(Path(__file__).resolve().parent)


def registry_dir() -> str:
    # tempfile.gettempdir() honours TMPDIR/TEMP/TMP exactly as Node's
    # os.tmpdir() does; reading TMPDIR directly would diverge.
    return os.path.join(tempfile.gettempdir(), REGISTRY_DIR_NAME)


def _ensure_registry_dir() -> str | None:
    """Create 0700 and use an existing directory only when we own it.

    On a shared ``/tmp`` another user could pre-create the directory. Returning
    ``None`` means no registry entry, which must never be fatal.
    """
    directory = registry_dir()
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        if hasattr(os, "getuid") and os.stat(directory).st_uid != os.getuid():
            return None
    except OSError:
        return None
    return directory


def entry_path(pid) -> str:
    return os.path.join(registry_dir(), f"viewer-{int(pid)}.json")


def _is_log_name(name: str) -> bool:
    return name.startswith("viewer-") and name.endswith(".log")


def create_log() -> tuple[int, str]:
    """A new log for a DETACHED viewer's stdout and stderr: ``(descriptor, path)``.

    Named for the moment the launch began, never for a pid, and never renamed:
    the launcher creates it before the server's pid exists, a pid is reused
    once its process is gone (a later launch must not truncate a log another
    server still writes), and Windows refuses to rename a file its server holds
    open. Created exclusively (``mkstemp``, 0600). The server records the path
    in its registry entry, which is how ``list``, ``stop`` and ``prune_logs``
    tell a live instance's log from a gone one's.

    Falls back to the plain temp dir when the registry directory is unusable,
    for the same reason registration fails soft: a shared ``/tmp`` we do not own
    must not stop a viewer from starting. Nothing prunes that fallback.
    """
    directory = _ensure_registry_dir() or tempfile.gettempdir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return tempfile.mkstemp(prefix=f"viewer-{stamp}-", suffix=".log", dir=directory)


def remove_log(entry: dict) -> None:
    """Delete the log a registry entry names (a clean ``stop``). Best-effort."""
    path = str(entry.get("log") or "")
    if path and _is_log_name(os.path.basename(path)):
        try:
            os.unlink(path)
        except OSError:
            pass  # Windows may hold a terminated process's handle a moment longer


def prune_logs(live: list[dict], *, now: float | None = None) -> None:
    """Delete the logs of instances that are gone, once they are a day old or
    beyond the newest ``LOG_KEEP_COUNT``.

    A log that a live entry names is never touched, whatever its age: a quiet
    server writes nothing for days. Everything else in the registry directory
    that is a viewer log belongs to an instance that crashed, was killed, or
    stopped without ``stop`` — or to a launch still starting, which is the
    newest file there and so the last one pruned.
    """
    directory = registry_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return
    held = {os.path.basename(str(entry.get("log") or "")) for entry in live}
    gone = []
    for name in names:
        if not _is_log_name(name) or name in held:
            continue
        path = os.path.join(directory, name)
        try:
            gone.append((os.stat(path).st_mtime, path))
        except OSError:
            continue
    gone.sort(reverse=True)
    now = time.time() if now is None else now
    for rank, (modified, path) in enumerate(gone):
        if rank >= LOG_KEEP_COUNT or now - modified > LOG_KEEP_SECONDS:
            try:
                os.unlink(path)
            except OSError:
                pass  # best-effort, like every registry write


def register(
    *, host, port, root: str = "", viewer_version: str = "", token: str = "", log: str = "", started_at=None
) -> str:
    """Announce this process. Returns the entry path, or ``""`` on any failure.

    ``token`` is the launcher's reuse identity (version plus the Python runtime
    and selected client digest — ``identity_token`` in http_app.py), recorded
    at START time so a later reuse probe compares against the code this
    instance is actually running. ``version`` stays alongside it for the human
    `list` printout. ``log`` is where a detached instance's output goes (``""``
    for one in the foreground).
    """
    directory = _ensure_registry_dir()
    if not directory:
        return ""
    pid = os.getpid()
    payload = {
        "pid": pid,
        "host": str(host),
        "port": int(port),
        "version": str(viewer_version or ""),
        "token": str(token or ""),
        "root": str(root or ""),
        "packageDir": _PACKAGE_DIR,
        "log": str(log or ""),
        "startedAt": float(time.time() if started_at is None else started_at),
    }
    target = entry_path(pid)
    temporary = f"{target}.{pid}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        replace_atomic(temporary, target)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass  # best-effort
        return ""
    return target


def unregister(pid=None) -> None:
    """Remove the entry. Never its log: an instance that exits by any path but a
    clean ``stop`` keeps it for diagnosis (see ``prune_logs``)."""
    pid = os.getpid() if pid is None else pid
    try:
        os.unlink(entry_path(pid))
    except OSError:
        pass  # best-effort


def _is_int(value) -> bool:
    # JSON has one number type, so Node's Number.isInteger accepts 3245.0.
    # Python's bool is an int subclass and must not pass as a pid.
    return isinstance(value, int) and not isinstance(value, bool)


def read_entries() -> list[dict]:
    try:
        names = sorted(os.listdir(registry_dir()))
    except OSError:
        return []
    entries = []
    for name in names:
        if not name.startswith("viewer-") or not name.endswith(".json"):
            continue
        try:
            # errors="replace", as `readFileSync(path, "utf8")` did. An entry is
            # written by another live viewer and can be read mid-write; a torn
            # multi-byte character should be judged as the JSON it decodes to,
            # not raise a UnicodeDecodeError that lands in the same clause and
            # makes every read failure indistinguishable.
            path = os.path.join(registry_dir(), name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                entry = json.load(handle)
        except (OSError, ValueError):
            continue  # skip corrupt entries
        if isinstance(entry, dict) and _is_int(entry.get("pid")) and _is_int(entry.get("port")):
            entries.append(entry)
    return entries


def find_by_port(port) -> dict | None:
    wanted = int(port)
    for entry in read_entries():
        if entry.get("port") == wanted:
            return entry
    return None


def probe(entry, timeout_seconds: float = PROBE_TIMEOUT_SECONDS) -> bool:
    """True when the recorded port answers ``/__cad/server`` AS the recorded pid."""
    host = str(entry.get("host") or "127.0.0.1")
    url = f"http://{host}:{entry.get('port')}/__cad/server"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - loopback only
            if not (200 <= response.status < 300):
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    return isinstance(payload, dict) and payload.get("pid") == entry.get("pid")


def live_entries(*, reap: bool = True) -> list[dict]:
    """Every entry whose identity probe succeeds, oldest first. Stale entries are
    deleted and gone instances' logs pruned (``prune_logs``).

    Probing runs in parallel. Node probed serially, which cost N x 500ms on
    every ``list`` AND on every default launch's reuse lookup; the output is
    identical because the result is re-sorted by ``startedAt`` rather than by
    probe completion order.
    """
    entries = read_entries()
    live = []
    if entries:
        with ThreadPoolExecutor(max_workers=min(8, len(entries))) as pool:
            alive = list(pool.map(probe, entries))
        for entry, is_alive in zip(entries, alive):
            if is_alive:
                live.append(entry)
            elif reap:
                unregister(entry.get("pid"))
    if reap:
        prune_logs(live)
    live.sort(key=lambda entry: entry.get("startedAt") or 0)
    return live
