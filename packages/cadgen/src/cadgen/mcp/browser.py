"""The CAD Viewer's page for a text host, and the words the stdio transport and the server say of it.

A text host's ``cad_show`` opens the model's page in the person's browser, but never from the server: the
server runs in the environment of whatever started it (another agent's shell, another ``BROWSER``, no
display), so its open could land in the wrong browser, or nowhere. The stdio transport the host started
(``cad_mcp.browser``), which runs in the agent's own environment, opens it instead. It says at initialize
that it opens a browser for its host, and whether it can; the server's answer then carries the page to
open in its result's ``_meta`` (``OPEN``), which the transport opens and strips before the host sees the
result, and before that it tells the server on its session whether the page opened (``OPENED``): the server
counts a page as open in the person's browser only once told it opened, so after a failed open the next
``cad_show`` opens it again. A client with no such transport is given the URL in words and nothing opens.
"""
from __future__ import annotations

import os

from cadgen.engine.client import request

# A text host's cad_show result: ``{"url", "said", "failed"}``, the page the stdio peer opens, the
# sentence of the result that says it opened, and the one it says in its place where the open
# fails (``{reason}`` the failure). Only the peer that declared ``transport_browser`` is sent it.
OPEN = 'dev.texttocad/open'
# The peer's word on that page, the notification it sends on its session once its open returned and
# before its host has the answer: ``{"url", "opened"}``, the page asked and whether it opened. The
# engine reads only the first word on a page it asked that session's peer for (``Server.notify``).
OPENED = 'notifications/dev.texttocad/opened'


class ViewerUnavailable(Exception):
    """The engine could not provide its viewer page."""


def viewer_url(model: str | None = None, *, cwd: str | None = None) -> str:
    """The viewer page of ``model`` (an absolute CAD file path, or a document id the engine holds),
    ``/<id>``, the file registered by the launch; the home's without one."""
    try:
        answer = request({'op': 'viewer', 'start': cwd or os.path.expanduser('~'),
                          'files': [model] if model else []})
    except OSError as error:
        raise ViewerUnavailable(str(error)) from error
    if not answer or 'failed' in answer:
        raise ViewerUnavailable((answer or {}).get('failed', 'engine did not answer'))
    return answer['url']
