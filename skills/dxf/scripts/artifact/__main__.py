from __future__ import annotations

import os
import sys
from pathlib import Path

# Drawing packages are content-addressed (drawing.json dxfHash) and must be
# byte-deterministic. ezdxf's object-section creation order depends on Python
# hash randomization, so pin the seed and re-run once before any ezdxf import.
#
# subprocess rather than os.execv: on Windows execv hands the argument vector to the C
# runtime, which re-joins it into a command line WITHOUT quoting, so an interpreter path
# containing a space -- C:\Program Files\Python311\python.exe, which is where the
# python.org all-users installer puts it -- arrives as two arguments and the child tries to
# run "Files\Python311\python.exe" as a script relative to the working directory. subprocess
# applies Windows quoting rules. Nothing is lost on POSIX either: os.execv never replaced the
# process on Windows, so the parent lingered there regardless, and the child's exit code is
# passed straight through here.
if os.environ.get("PYTHONHASHSEED") != "0":
    import subprocess

    os.environ["PYTHONHASHSEED"] = "0"
    raise SystemExit(subprocess.run([sys.executable, *sys.argv], check=False).returncode)

# Prefer the skill's bundled cadgen over any pip-installed copy, exactly as
# skills/dxf/scripts/gen/__main__.py does.
# This skill got away without it only because its requirements.txt installs
# `--editable ./scripts/packages/cadgen`; run without that install and it silently binds
# whichever cadgen is on the interpreter's path -- a different checkout, at a different
# version. That is now worse than a version mismatch: node_package_root() derives the Node
# builder directory from cadgen's own __file__, so the wrong cadgen resolves
# preview.glb's builder to another skill's runtime, or to none.
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
