"""Which release is newest: the version feed, as cad's own automatic update reads it, and PyPI, as ``cad update`` asks.

At most once an hour, a server reads the version feed (``GET /v1/releases``, ``cad_server/_internal/api.py``)::

    {"latest": "1.2.0", "lines": {"0": "0.12.3", "1": "1.2.0"}}

in the background (``refresh``), never waited on: ``latest`` the newest release, ``lines`` the newest release of each
major version (``newest_of_major``). Releases 0.7.12 to 0.11.11 read ``/v1/versions``, which names ``latest`` alone and
never a release from 0.12.0 on: it is kept for them as it is, and nothing here reads it. It is one anonymous request:
no id, no path, nothing about the person or their machine beyond what any web request carries.
``CAD_UPDATE_CHECK=0`` turns it off, and it never runs in CI (``CI`` set) or for a development build
(``cad_server._internal.editable.development``). The feed as last read is kept in the state folder (``FILE``,
``releases.json``), where every process of the person's reads it: cad's own automatic update moves to the newest
release of its own major that it names (``cad_server._internal.auto_update``). A file of its own: releases 0.10.0 to
0.11.11 keep their feed, ``/v1/versions``'s, in ``versions.json`` in the same folder and read it while a computer is
carried over, so a ``latest`` of 0.12.0 or later written there would reach them; nothing here reads or writes that
file. A feed with ``latest`` alone (a stand-in's) is read with no ``lines``. Nothing here updates anything, and nothing
here says anything to a person or an agent.

``cad update`` asks PyPI instead (``pypi``: ``GET https://pypi.org/pypi/cad/json``), once, ``TIMEOUT_SECONDS`` at most,
the asking thread waiting: the feed names a release up to an hour after PyPI does. Its answer is read into the feed's
shape: from PyPI's ``releases`` (every release, and each of its files with ``yanked``), the newest plain ``X.Y.Z`` with
a file that is not yanked as ``latest``, and the newest such of each major as ``lines``; where PyPI's answer has no
``releases``, its ``info.version`` (which leaves yanked releases out) as ``latest``, with no ``lines``.
``CAD_PYPI_URL`` names another address for PyPI's JSON API (a test's stand-in).

Nothing here ever raises, or waits longer than ``TIMEOUT_SECONDS``. Each hour's attempt is spent before it is made,
so a feed that cannot be reached is tried once an hour.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cad_server._internal.api import api_url
from cad._internal.atomic_replace import write_bytes_atomic

LOG = logging.getLogger("cad_server.updates")

# The feed as last read, in the state folder: never ``versions.json``, the file of 0.10.0 to 0.11.11 (see the module).
FILE = "releases.json"
ADDRESS = "/releases"  # the feed's address under the service's base (``api_url``)
CHECK_SECONDS = 60 * 60  # how old the feed may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")


def parse_release(value: Any) -> tuple[int, int, int] | None:
    """A release, a plain ``X.Y.Z``, as its three numbers; None for anything else (a development or
    pre-release version)."""
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as the server reads it: a release as ``latest`` (``None`` when there is none), and ``lines``, each major
    version's newest release by its number as a string (``{"0": "0.12.3"}``): an entry whose release is of another
    major, or no release, is left out, and a feed with none is read with ``lines`` empty. Anything else in it is left
    out, so the feed can grow without a release of cad."""
    if not isinstance(data, dict) or parse_release(data.get("latest")) is None:
        return None
    given = data.get("lines")
    lines = {major: release for major, release in (given.items() if isinstance(given, dict) else ())
             if isinstance(major, str) and (numbers := parse_release(release)) is not None
             and str(numbers[0]) == major}
    return {"latest": data["latest"], "lines": lines}


def newest_of_major(major: int, known: dict[str, Any] | None) -> str | None:
    """The newest release of major version ``major`` that the feed ``known`` (as ``feed`` returns it) names in its
    ``lines``; None where it names none (a feed with ``latest`` alone, or no feed)."""
    lines = known.get("lines") if isinstance(known, dict) else None
    found = lines.get(str(major)) if isinstance(lines, dict) else None
    numbers = parse_release(found)
    return found if numbers is not None and numbers[0] == major else None


def checking() -> bool:
    """Whether to read the feed at all: not turned off (``CAD_UPDATE_CHECK=0``), not in CI, and no development
    build."""
    if str(os.environ.get("CAD_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    from cad_server._internal.editable import development

    return not development()


def _cache() -> Path:
    """The feed's cache, in the state folder (``places.state_dir``)."""
    from cad.engine.places import state_dir

    return state_dir() / FILE


def _load(path: Path) -> dict[str, Any]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _save(path: Path, checked: float, feed: dict[str, Any] | None) -> None:
    """The file as it is read: when the feed was last asked for (``checked``) and the feed as last
    read (``feed``), and nothing else."""
    kept: dict[str, Any] = {"checked": checked, **({"feed": feed} if feed is not None else {})}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, json.dumps(kept, sort_keys=True).encode("utf-8"))
    except OSError:
        LOG.debug("could not keep the version feed in %s", path, exc_info=True)


def _due(kept: dict[str, Any], key: str, now: float) -> bool:
    """Whether an hour has passed since ``key`` (a clock set back counts as an hour)."""
    then = kept.get(key)
    return not isinstance(then, (int, float)) or not 0 <= now - then < CHECK_SECONDS


def _get(url: str) -> Any:
    """The feed's JSON, or ``None`` when it could not be read: offline, slow, refused, or not JSON."""
    try:
        import urllib.request

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cad"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`api_url`)
            return json.loads(response.read(MAX_BYTES))
    except Exception:  # noqa: BLE001 - a check that fails is tried again in an hour
        LOG.debug("could not read the version feed at %s", url, exc_info=True)
        return None


def feed(*, fetch: bool = True, force: bool = False, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None) -> dict[str, Any] | None:
    """The feed as last read, read again first (``fetch``) when that was an hour ago or more -- or now,
    ``force``."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and checking() and (force or _due(kept, "checked", now)):
        known = _read(path, now, known, get) or known
    return known


def _read(path: Path, now: float, known: dict[str, Any] | None,
          get: Callable[[str], Any] | None) -> dict[str, Any] | None:
    """The feed read and kept: what it says, or None where it could not be read."""
    # The hour's attempt is spent before it is made: a process that exits mid-request, or a feed
    # that never answers, costs one wait an hour.
    _save(path, now, known)
    fresh = parse_feed((get or _get)(f"{api_url()}{ADDRESS}"))
    if fresh is not None:
        _save(path, now, fresh)
    return fresh


PYPI = "https://pypi.org/pypi"
PYPI_ENV = "CAD_PYPI_URL"
PYPI_MAX_BYTES = 16 * 1024 * 1024  # a project's JSON lists every file of every release: a few hundred KB


def pypi_url() -> str:
    """PyPI's JSON API: ``CAD_PYPI_URL`` when it is http(s), else PyPI's own."""
    override = str(os.environ.get(PYPI_ENV) or "").strip().rstrip("/")
    return override if override.startswith(("https://", "http://")) else PYPI


def _get_within(url: str, seconds: float) -> Any:
    """The JSON at ``url``, all of it, read in ``seconds`` at most, by the caller waiting on a thread that reads it (a
    socket's timeout bounds each read, not all of them); ``None`` when it could not be (offline, slow, refused, too
    big, or not JSON)."""
    found: list[Any] = []

    def read() -> None:
        try:
            import urllib.request

            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cad"})
            with urllib.request.urlopen(request, timeout=seconds) as response:  # noqa: S310 - http(s) only (`pypi_url`)
                data = response.read(PYPI_MAX_BYTES + 1)
            if len(data) <= PYPI_MAX_BYTES:
                found.append(json.loads(data))
        except Exception:  # noqa: BLE001 - PyPI out of reach: no answer
            LOG.debug("could not read %s", url, exc_info=True)

    reading = threading.Thread(target=read, name="cad-pypi", daemon=True)
    reading.start()
    reading.join(seconds)
    return found[0] if found else None


def pypi(*, get: Callable[[str], Any] | None = None) -> dict[str, Any] | None:
    """cad's releases on PyPI (``<CAD_PYPI_URL>/cad/json``) in the feed's shape, ``{"latest", "lines"}`` (see the
    module): only plain ``X.Y.Z`` releases with a file that is not yanked. None where PyPI could not be asked or named
    no such release. Asked once, ``TIMEOUT_SECONDS`` at most."""
    found = (get or (lambda url: _get_within(url, TIMEOUT_SECONDS)))(f"{pypi_url()}/cad/json")
    if not isinstance(found, dict):
        return None
    given = found.get("releases")
    if not isinstance(given, dict):  # no list of releases: PyPI's own newest, which leaves yanked ones out
        info = found.get("info")
        version = info.get("version") if isinstance(info, dict) else None
        return {"latest": version, "lines": {}} if parse_release(version) is not None else None
    out = [numbers for version, files in given.items() if (numbers := parse_release(version)) is not None
           and isinstance(files, list) and any(isinstance(file, dict) and file.get("yanked") in (None, False)
                                               for file in files)]
    if not out:
        return None
    lines: dict[str, tuple[int, int, int]] = {}
    for numbers in out:
        lines[str(numbers[0])] = max(lines.get(str(numbers[0]), numbers), numbers)
    named = lambda numbers: ".".join(map(str, numbers))  # noqa: E731
    return {"latest": named(max(out)), "lines": {major: named(numbers) for major, numbers in sorted(lines.items())}}


def _quietly() -> None:
    try:
        feed()
    except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
        LOG.debug("the version check failed", exc_info=True)


def refresh() -> threading.Thread | None:
    """Read the feed in the background when it is due, so what cad's own update reads stays current: as a server
    starts and as it tends (a server can run for days). The thread reading it, if one started."""
    try:
        if not (checking() and _due(_load(_cache()), "checked", time.time())):
            return None
        thread = threading.Thread(target=_quietly, name="cad-update-check", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - a check that cannot start is tried at the next one
        LOG.debug("the version check could not start", exc_info=True)
        return None
