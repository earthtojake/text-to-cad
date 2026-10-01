"""The newest CAD release, for the page's update button.

GitHub's latest release, asked at most every few hours and kept in the user's state directory, so
every view and every server process shares one answer. It is the one request this server makes to
the network, and a failure (offline, rate-limited, a bad reply) is no answer, never an error.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

LATEST_URL = "https://api.github.com/repos/earthtojake/text-to-cad/releases/latest"
FRESH_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 4


def _version_key(value: Any) -> tuple[int, ...] | None:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def _fetch() -> dict[str, Any]:
    request = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "cadgen"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - a fixed https URL
        return json.load(response)


def _ask(fetch: Callable[[], dict[str, Any]]) -> dict[str, str] | None:
    try:
        reply = fetch()
    except Exception:  # noqa: BLE001 - no answer is the answer
        return None
    version, url = str(reply.get("tag_name") or "").strip(), str(reply.get("html_url") or "").strip()
    if not _version_key(version) or not url.startswith("https://"):
        return None
    return {"version": version.removeprefix("v"), "url": url}


def _read(cache: Path, now: float) -> dict[str, str] | None:
    try:
        kept = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fresh = isinstance(kept, dict) and now - float(kept.get("checkedAt") or 0) < FRESH_SECONDS
    return {"version": kept["version"], "url": kept["url"]} if fresh and _version_key(kept.get("version")) and kept.get("url") else None


def _write(cache: Path, found: dict[str, Any]) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(found), encoding="utf-8")
    except OSError:  # a state directory it cannot write only means asking again
        pass


def latest_release(current: str, *, cache: Path, fetch: Callable[[], dict[str, Any]] | None = None,
                   now: float | None = None) -> dict[str, Any] | None:
    """``{version, url, newer}`` for the newest release, or None when it cannot be known."""
    now = time.time() if now is None else now
    found = _read(cache, now)
    if found is None:
        found = _ask(fetch or _fetch)
        if found is None:
            return None
        _write(cache, {**found, "checkedAt": now})
    newest, running = _version_key(found["version"]), _version_key(current)
    return {"version": found["version"], "url": found["url"], "newer": bool(newest and running and newest > running)}
