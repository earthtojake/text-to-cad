"""Links to the installation's viewer page, for text-only hosts."""
from __future__ import annotations

import os
from cadgen.engine.client import request


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
