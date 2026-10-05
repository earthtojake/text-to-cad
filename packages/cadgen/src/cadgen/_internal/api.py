"""api.texttocad.dev: the one service cadgen talks to.

Two things use it: the usage analytics a person agreed to (``cadgen/analytics.py``: ``/events``
and ``/forget``) and the daily version check (``cadgen/updates.py``: ``/versions``). It is ours,
so the service behind it can change without a release. ``CADGEN_API_URL`` points both at another
-- a local receiver -- when it is http(s).
"""

from __future__ import annotations

import os

API = "https://api.texttocad.dev/v1"


def api_url() -> str:
    """The service's base: ``CADGEN_API_URL`` when it is http(s), else ours."""
    override = str(os.environ.get("CADGEN_API_URL") or "").strip().rstrip("/")
    return override if override.startswith(("https://", "http://")) else API
