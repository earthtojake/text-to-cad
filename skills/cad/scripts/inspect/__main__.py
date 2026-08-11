from __future__ import annotations

import os
import sys
from pathlib import Path

# Warm-daemon shim: must run BEFORE the cli import below (which loads cadgen at
# module import time). The daemon sets CADGEN_DAEMON_CHILD so it never
# recurses; the stdlib-only client keeps the cold path overhead-free.
if os.environ.get("CADGEN_WARM") == "1" and not os.environ.get("CADGEN_DAEMON_CHILD"):
    scripts_dir = str(Path(__file__).resolve().parents[1])
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from cadgen_daemon.client import run_via_daemon

    warm_exit = run_via_daemon("inspect", sys.argv[1:], os.getcwd())
    if warm_exit is not None:
        raise SystemExit(warm_exit)

# Prefer the skill's bundled cadgen over any pip-installed copy, exactly like
# snapshot's entry: the vendored scripts/packages/cadgen is the version this
# skill runtime was built against, while the interpreter's site-packages may
# hold a different checkout/release. Falls back to the installed package when
# the vendored path is absent (e.g. PyPI-pinned plugin installs).
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
PACKAGES_DIR = SCRIPTS_DIR / "packages"
CADPY_SRC_DIR = PACKAGES_DIR / "cadgen" / "src"
for _runtime_path in (SCRIPTS_DIR, PACKAGES_DIR, CADPY_SRC_DIR):
    _runtime_path_text = str(_runtime_path)
    if _runtime_path.is_dir() and _runtime_path_text not in sys.path:
        sys.path.insert(0, _runtime_path_text)

TOOL_DIR = Path(__file__).resolve().parent
tool_path = str(TOOL_DIR)
if tool_path not in sys.path:
    sys.path.insert(0, tool_path)

from cli import main


if __name__ == "__main__":
    raise SystemExit(main())
