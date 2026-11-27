"""Which release is newest: PyPI, as cad's own automatic update reads it at most once an hour and ``cad update`` asks it
at once; and the project's notices.

At most once an hour, a server reads, in the background (``refresh``), never waited on:

- **PyPI** (``pypi``: ``GET https://pypi.org/pypi/cad/json``), cad's own project, read into one shape::

      {"latest": "1.2.0", "lines": {"0": "0.12.3", "1": "1.2.0"}}

  from PyPI's ``releases`` (every release, and each of its files with ``yanked``): the newest plain ``X.Y.Z`` with a
  file that is not yanked as ``latest``, and the newest such of each major as ``lines`` (``newest_of_major``); where
  PyPI's answer has no ``releases``, its ``info.version`` (which leaves yanked releases out) as ``latest``, with no
  ``lines``. A release is held back from every computer by yanking it on PyPI, and nothing else: no hour's wait, no
  list of held releases. The ``cad`` project also lists another owner's releases of 2020 (0.8 to 1.1.2), every one of
  them yanked, so none is ever read.
- **The notices** (``GET /v1/notices``, ``cad_server/_internal/api.py``: ``{"notices": [...]}``), the project's words
  for every cad older than a release (``parse_notices``, ``notices_for``; said by ``cad_server.notices``), kept with
  the releases as ``notices`` where there are any.

Either that cannot be read leaves what was last read of it as it was. Each is one anonymous request: no id, no path,
nothing about the person or their machine beyond what any web request carries. ``CAD_UPDATE_CHECK=0`` turns both off,
and they never run in CI (``CI`` set) or for a development build (``cad_server._internal.editable.development``). What
was last read is kept in the state folder (``FILE``, ``releases.json``), where every process of the person's reads it:
cad's own automatic update moves to the newest release of its own major that it names
(``cad_server._internal.auto_update``). Releases 0.11.12 to 0.11.18 read the version feed of ``apps/api``
(``/v1/releases``) into the same file in the same shape, and 0.10.0 to 0.11.11 theirs (``/v1/versions``) into
``versions.json``; nothing here reads either address, or writes that file. Nothing here updates anything, and nothing
here says anything to a person or an agent.

``cad update`` asks PyPI the same way (``pypi``), once, ``TIMEOUT_SECONDS`` at most, the asking thread waiting.
``CAD_PYPI_URL`` names another address for PyPI's JSON API (a test's stand-in).

Nothing here ever raises, or waits longer than ``TIMEOUT_SECONDS`` for each. Each hour's attempt is spent before it is
made, so what cannot be reached is tried once an hour.
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

# What was last read of PyPI and the notices, in the state folder: never ``versions.json``, the file of 0.10.0 to
# 0.11.11 (see the module).
FILE = "releases.json"
ADDRESS = "/notices"  # the notices' address under the service's base (``api_url``)
CHECK_SECONDS = 60 * 60  # how old what was read may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # at most ten notices of a few hundred bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")
# A notice's rules (``parse_notices``), apps/api's own (``noticesOf``): what it answers is never trusted.
NOTICES_MAX = 10
NOTICE_TEXT_MAX = 240  # characters
_NOTICE_ID = re.compile(r"[a-z0-9-]{1,40}")
_NOTICE_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")  # control characters and every line break
# A link's site, then nothing or a path, query or fragment of printable ASCII: never another host behind it.
_NOTICE_SITES = ("https://texttocad.dev", "https://github.com/earthtojake/text-to-cad")
_NOTICE_URL = re.compile(f"(?:{'|'.join(map(re.escape, _NOTICE_SITES))})" + r"(?:[/?#][\x21-\x7e]*)?")
_NOTICE_URL_MAX = 500


def parse_release(value: Any) -> tuple[int, int, int] | None:
    """A release, a plain ``X.Y.Z``, as its three numbers; None for anything else (a development or
    pre-release version)."""
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as the server reads it: a release as ``latest`` (``None`` when there is none), and ``lines``, each major
    version's newest release by its number as a string (``{"0": "0.12.3"}``): an entry whose release is of another
    major, or no release, is left out, and a feed with none is read with ``lines`` empty; and ``notices``, only where
    it carries one that passes (``parse_notices``), so a feed with none is read, and kept, as it was before notices.
    Anything else in it is left out, so the feed can grow without a release of cad."""
    if not isinstance(data, dict) or parse_release(data.get("latest")) is None:
        return None
    given = data.get("lines")
    lines = {major: release for major, release in (given.items() if isinstance(given, dict) else ())
             if isinstance(major, str) and (numbers := parse_release(release)) is not None
             and str(numbers[0]) == major}
    notices = parse_notices(data.get("notices"))
    return {"latest": data["latest"], "lines": lines, **({"notices": notices} if notices else {})}


def _notice(given: Any) -> dict[str, str] | None:
    """One notice as ``parse_notices`` keeps it, or None where it breaks a rule."""
    if not isinstance(given, dict):
        return None
    notice_id, below, text, url = (given.get(key) for key in ("id", "below", "text", "url"))
    if not (isinstance(notice_id, str) and _NOTICE_ID.fullmatch(notice_id)) or parse_release(below) is None:
        return None
    if not isinstance(text, str) or re.fullmatch(" *", text) or len(text) > NOTICE_TEXT_MAX \
            or _NOTICE_CONTROL.search(text):
        return None
    if "url" in given and not (isinstance(url, str) and len(url) <= _NOTICE_URL_MAX and _NOTICE_URL.fullmatch(url)):
        return None
    return {"id": notice_id, "below": below, "text": text, **({"url": url} if "url" in given else {})}


def parse_notices(given: Any) -> list[dict[str, str]]:
    """The feed's ``notices`` checked by the rules the feed posts them by (apps/api's ``noticesOf``), never trusted:
    each ``{"id", "below", "text", "url"?}`` with those keys alone, ``id`` a slug (``[a-z0-9-]``, 1 to 40),
    ``below`` a release, ``text`` one line of at most ``NOTICE_TEXT_MAX`` characters with no control character, not
    blank, and ``url``, where there is one, ``https://`` on texttocad.dev or the project's GitHub repository. One that
    breaks a rule is left out, as is an id named before and any past ``NOTICES_MAX``; anything but a list is none."""
    notices: list[dict[str, str]] = []
    for given_one in given if isinstance(given, list) else ():
        notice = _notice(given_one)
        if notice is not None and len(notices) < NOTICES_MAX and all(kept["id"] != notice["id"] for kept in notices):
            notices.append(notice)
    return notices


def notices_for(version: str, known: dict[str, Any] | None) -> list[dict[str, str]]:
    """The notices of the feed ``known`` (as ``feed`` returns it) that are for cad ``version``: each whose ``below`` is
    a release newer than it, checked again (``parse_notices``). None for a version that is no release (a development
    build)."""
    mine = parse_release(version)
    if mine is None or not isinstance(known, dict):
        return []
    return [notice for notice in parse_notices(known.get("notices")) if mine < parse_release(notice["below"])]


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
    """The JSON at ``url`` (the notices), or ``None`` when it could not be read: offline, slow, refused, or not
    JSON."""
    try:
        import urllib.request

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cad"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`api_url`)
            return json.loads(response.read(MAX_BYTES))
    except Exception:  # noqa: BLE001 - a check that fails is tried again in an hour
        LOG.debug("could not read %s", url, exc_info=True)
        return None


def feed(*, fetch: bool = True, force: bool = False, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None) -> dict[str, Any] | None:
    """What was last read, in the version feed's shape (``{"latest", "lines", "notices"?}``), read again first
    (``fetch``) when that was an hour ago or more -- or now, ``force``. ``get``: each address's JSON (a test's
    stand-in)."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and checking() and (force or _due(kept, "checked", now)):
        known = _read(path, now, known, get) or known
    return known


def asked(path: Path | None = None) -> float | None:
    """When PyPI and the notices were last asked for, by any process of the person's (read, never fetched): a time, or
    None where they never were. An answer or not: each hour's attempt is spent before it is made."""
    checked = _load(path or _cache()).get("checked")
    return float(checked) if isinstance(checked, (int, float)) and not isinstance(checked, bool) else None


def _read(path: Path, now: float, known: dict[str, Any] | None,
          get: Callable[[str], Any] | None) -> dict[str, Any] | None:
    """PyPI (``pypi``) and the notices (``ADDRESS``) read and kept together, each standing as last read where it could
    not be read again: what is known then, or None where neither could be read."""
    # The hour's attempt is spent before it is made: a process that exits mid-request, or an address that never
    # answers, costs one wait an hour.
    _save(path, now, known)
    releases = pypi(get=get)
    said = (get or _get)(f"{api_url()}{ADDRESS}")
    notices = parse_notices(said.get("notices")) if isinstance(said, dict) else None
    if releases is None and notices is None:
        return None
    base = releases or ({"latest": known["latest"], "lines": known["lines"]} if known else None)
    if base is None:  # the notices alone, with no release ever read: nothing to keep them by
        return None
    notices = (known or {}).get("notices", []) if notices is None else notices
    fresh = parse_feed({**base, **({"notices": notices} if notices else {})})
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
    """Read PyPI and the notices in the background when they are due, so what cad's own update reads stays current:
    as a server starts and as it tends (a server can run for days). The thread reading them, if one started."""
    try:
        if not (checking() and _due(_load(_cache()), "checked", time.time())):
            return None
        thread = threading.Thread(target=_quietly, name="cad-update-check", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - a check that cannot start is tried at the next one
        LOG.debug("the version check could not start", exc_info=True)
        return None
