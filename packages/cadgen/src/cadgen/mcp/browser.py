"""A link to a model in the CAD Viewer, for an app that cannot show CAD views itself.

``cadgen viewer --json``, run from a folder, reuses the Viewer serving that folder or starts one, and
prints its ``{url, port, action}`` line: after two lines of narration when it reuses one and exits;
as its only stdout when it starts one and goes on serving. A started Viewer is that process, so it is
spawned in its own session and outlives this server, as one an agent starts from a shell does. It
never opens a browser: the link is the user's to open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from urllib.parse import quote

LAUNCH = (sys.executable, "-m", "cadgen.cli", "viewer", "--host", "127.0.0.1", "--json")
LAUNCH_SECONDS = 30.0


class ViewerUnavailable(Exception):
    """The CAD Viewer could not be started for a folder."""


def viewer_url(folder: str, *, command=LAUNCH, timeout: float = LAUNCH_SECONDS) -> str:
    """The URL of the CAD Viewer serving ``folder``: the running one, or one started now."""
    detached = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt" else {"start_new_session": True})
    try:
        process = subprocess.Popen(list(command), cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, **detached)
    except OSError as error:
        raise ViewerUnavailable(str(error)) from error
    found: list[dict] = []

    def read() -> None:
        for raw in iter(process.stdout.readline, b""):
            try:
                payload = json.loads(raw)
            except ValueError:
                continue  # the reuse narration
            if isinstance(payload, dict) and isinstance(payload.get("url"), str):
                found.append(payload)
                return

    reader = threading.Thread(target=read, name="cadgen-mcp-viewer", daemon=True)
    reader.start()
    reader.join(timeout)
    if not found:
        exited = process.poll()
        if exited is None:
            process.kill()
        reader.join(5)
        raise ViewerUnavailable(f"`cadgen viewer` exited ({exited}) without a URL" if exited is not None
                                else f"`cadgen viewer` gave no URL within {timeout:.0f} s")
    if found[0].get("action") == "reused":
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    # A started Viewer writes nothing more to stdout (its --json contract), so the pipe can go.
    process.stdout.close()
    return found[0]["url"]


def model_link(url: str, folder: str, model: str) -> str:
    """``url`` opened at ``model``, which lies under the folder that Viewer serves."""
    relative = os.path.relpath(model, folder).replace(os.sep, "/")
    return f"{url}?file={quote(relative, safe='/')}"
