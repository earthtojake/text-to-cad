"""The two services cad talks to.

api.texttocad.dev: telemetry (``cad_server/analytics.py``: ``/events`` and ``/forget``) and the hourly version check
(``cad_server/updates.py``: ``/releases``). It is ours, so the service behind it can change without a release.
``CAD_API_URL`` points both at another -- a local receiver -- when it is http(s).

cad.fun: the share service ``cad share`` uploads a document's view bundle to and deletes it from
(``cad_server/sharing.py``), asked only by that command, which a person runs by name. ``CAD_SHARE_URL`` points it at
another origin when it is http(s): a test's stand-in, a local run of the service.
"""

from __future__ import annotations

import os

API = "https://api.texttocad.dev/v1"
SHARE = "https://cad.fun"


def _override(name: str) -> str | None:
    given = str(os.environ.get(name) or "").strip().rstrip("/")
    return given if given.startswith(("https://", "http://")) else None


def api_url() -> str:
    """The service's base: ``CAD_API_URL`` when it is http(s), else ours."""
    return _override("CAD_API_URL") or API


def share_url() -> str:
    """The share service's origin: ``CAD_SHARE_URL`` when it is http(s), else ours."""
    return _override("CAD_SHARE_URL") or SHARE
