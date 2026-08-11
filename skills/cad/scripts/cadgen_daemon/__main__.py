from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    tool_dir = Path(__file__).resolve().parent
    if str(tool_dir) not in sys.path:
        sys.path.insert(0, str(tool_dir))
    from server import main
else:
    from .server import main


if __name__ == "__main__":
    raise SystemExit(main())
