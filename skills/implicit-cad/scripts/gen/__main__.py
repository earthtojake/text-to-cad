from __future__ import annotations

import sys
from pathlib import Path

# Prefer the skill's bundled cadgen over any pip-installed copy, exactly like `cad`'s gen
# entry: the vendored scripts/packages/cadgen is the version this skill runtime was built
# against, while the interpreter's site-packages may hold a different checkout or release.
# Falls back to the installed package when the vendored path is absent (a PyPI-pinned plugin
# install).
#
# There is no warm-daemon shim here, unlike `cad`'s: that exists solely to amortize the OCP
# import, and an implicit model is GLSL and JS -- nothing in this path loads a CAD runtime.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
PACKAGES_DIR = SCRIPTS_DIR / "packages"
CADGEN_SRC_DIR = PACKAGES_DIR / "cadgen" / "src"
for _runtime_path in (SCRIPTS_DIR, PACKAGES_DIR, CADGEN_SRC_DIR):
    _runtime_path_text = str(_runtime_path)
    if _runtime_path.is_dir() and _runtime_path_text not in sys.path:
        sys.path.insert(0, _runtime_path_text)

if __package__ in {None, ""}:
    tool_dir = Path(__file__).resolve().parent
    if str(tool_dir) not in sys.path:
        sys.path.insert(0, str(tool_dir))
    from cli import main
else:
    from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
