"""A link to a model in the CAD Viewer, for an app that cannot show CAD views itself.

``cadgen viewer --json --detach``, run from a folder, reuses the Viewer serving that folder or starts
one in the background (its own session, its output to a log beside its registry entry), prints its
``{url, port, action}`` line and exits. So a started Viewer outlives this server, as one an agent
starts from a shell does, and nothing it writes later comes back here. It never opens a browser: the
link is the user's to open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.parse import quote

LAUNCH = (sys.executable, "-m", "cadgen.cli", "viewer", "--host", "127.0.0.1", "--json", "--detach")
LAUNCH_SECONDS = 30.0


class ViewerUnavailable(Exception):
    """The CAD Viewer could not be started for a folder."""


def viewer_url(folder: str, *, command=LAUNCH, timeout: float = LAUNCH_SECONDS) -> str:
    """The URL of the CAD Viewer serving ``folder``: the running one, or one started now."""
    try:
        process = subprocess.Popen(list(command), cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
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


def model_link(url: str, folder: str, model: str) -> str:
    """``url`` opened at ``model``, which lies under the folder that Viewer serves."""
    relative = os.path.relpath(model, folder).replace(os.sep, "/")
    return f"{url}?file={quote(relative, safe='/')}"
