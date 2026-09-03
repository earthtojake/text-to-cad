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
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic

__all__ = [
    "REGISTRY_DIR_NAME",
    "PROBE_TIMEOUT_SECONDS",
    "registry_dir",
    "entry_path",
    "register",
    "unregister",
    "read_entries",
    "find_by_port",
    "probe",
    "live_entries",
]

REGISTRY_DIR_NAME = "cadgen-viewer-info"
PROBE_TIMEOUT_SECONDS = 0.5

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


def register(*, host, port, root: str = "", viewer_version: str = "", token: str = "", started_at=None) -> str:
    """Announce this process. Returns the entry path, or ``""`` on any failure.

    ``token`` is the launcher's reuse identity (version salted with the app
    files' newest mtime — ``identity_token`` in http_app.py), recorded at
    START time so a later reuse probe compares against the code this instance
    is actually running. ``version`` stays alongside it for the human `list`
    printout.
    """
    import time

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
    try:
        os.unlink(entry_path(os.getpid() if pid is None else pid))
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
    """Every entry whose identity probe succeeds, oldest first. Stale files are deleted.

    Probing runs in parallel. Node probed serially, which cost N x 500ms on
    every ``list`` AND on every default launch's reuse lookup; the output is
    identical because the result is re-sorted by ``startedAt`` rather than by
    probe completion order.
    """
    entries = read_entries()
    if not entries:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(entries))) as pool:
        alive = list(pool.map(probe, entries))
    live = []
    for entry, is_alive in zip(entries, alive):
        if is_alive:
            live.append(entry)
        elif reap:
            unregister(entry.get("pid"))
    live.sort(key=lambda entry: entry.get("startedAt") or 0)
    return live
