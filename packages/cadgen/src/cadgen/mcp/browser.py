"""A link to a model in the CAD Viewer, for an app that cannot show CAD views itself.

``cadgen viewer --json --detach`` reuses this machine's Viewer or starts one in the background (its
own session, its output to the viewer log in the state directory), prints its ``{url, port, action}``
line and exits. So a started Viewer outlives this server, as one an agent starts from a shell does, and
nothing it writes later comes back here. The Viewer opens any model by its absolute path, so the
launch runs from the user's home folder: where it starts only decides how a developer's relative
links resolve. It never opens a browser: the link is the user's to open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.parse import quote

LAUNCH = (sys.executable, "-P", "-m", "cadgen.cli", "viewer", "--host", "127.0.0.1", "--json", "--detach")
LAUNCH_SECONDS = 30.0


class ViewerUnavailable(Exception):
    """The CAD Viewer could not be started."""


def viewer_url(*, cwd: str | None = None, command=LAUNCH, timeout: float = LAUNCH_SECONDS) -> str:
    """The URL of this machine's CAD Viewer: the running one, or one started now from ``cwd`` (the
    user's home folder by default)."""
    from cadgen.analytics import NOTICE_ENV

    try:
        # Its stderr is thrown away, so the analytics notice a command says once would reach nobody.
        process = subprocess.Popen(list(command), cwd=cwd or os.path.expanduser("~"), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env={**os.environ, NOTICE_ENV: "0"})
    except OSError as error:
        raise ViewerUnavailable(str(error)) from error
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ViewerUnavailable(f"`cadgen viewer` gave no URL within {timeout:.0f} s") from None
    for raw in output.splitlines():
        try:
            payload = json.loads(raw)
        except ValueError:
            continue  # narration
        if isinstance(payload, dict) and isinstance(payload.get("url"), str):
            return payload["url"]
    raise ViewerUnavailable(f"`cadgen viewer` exited ({process.returncode}) without a URL")


def model_link(url: str, model: str) -> str:
    """``url`` opened at ``model``, named by its absolute path: readable, with ``/`` and ``:`` kept."""
    return f"{url}?file={quote(model.replace(os.sep, '/'), safe='/:')}"
