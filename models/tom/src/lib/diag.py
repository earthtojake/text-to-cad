"""Build diagnostics -- the geometry summaries these models print as they build.

These go to STDERR, deliberately. stdout is the RESULT channel: a model run prints its outcome and
package path there, and `--json` puts one parseable object there. A generator writing its own text
to stdout corrupts that -- `python model.py --json | jq .` fails on the first summary line -- so
every diagnostic in this repo goes through here instead.

`2>/dev/null` therefore leaves a clean parseable result, and `>/dev/null` leaves a readable log.
Phase labels for a long build are a different thing: the engine names each `@memo` stage it runs.
"""

from __future__ import annotations

import sys
from typing import Any


def say(*args: Any, **kwargs: Any) -> None:
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)
