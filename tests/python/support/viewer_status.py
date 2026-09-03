"""Query the artifact-status authority (``cadgen.viewer.artifact_status``).

Freshness verdicts have exactly one implementation and it lives in the viewer
server, so cadgen suites that need a verdict (portability, concurrency) ask it
through this shim rather than keeping a second implementation alive just for
tests. The server is ``cadgen.viewer`` now, so this is a plain import; the
JSON round trip stays so callers see exactly the wire shape the client does.
"""

from __future__ import annotations

import json
from pathlib import Path


def viewer_artifact_status(file_ref: str | Path, root: str | Path) -> dict:
    from cadgen.viewer.artifact_status import artifact_status

    return json.loads(json.dumps(artifact_status(str(file_ref), str(root))))
