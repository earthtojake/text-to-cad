#!/usr/bin/env bash
set -euo pipefail

# A CAM job (cad <type> cam) with its program installed: FreeCAD, the freecad integration's, plans and posts --
# installed as a person installs it (the cam job: the release's AppImage; locally CAD_FREECAD, freecadcmd on PATH or
# the place its installer puts it). The suite's own folder, tests/python/packages/cam, is this job's alone: the
# package jobs install no FreeCAD. The job's parse, the feature reading and the checks run in seconds; the plans
# FreeCAD makes are most of its time. The command runs a job here when this Python holds the kernel, else through
# the library's runner of one operation in the installation's base; the suite runs that path with this Python
# standing in for the base (test_cam_commands.py). The runner gives each test file its own engine, state and cache
# folders. No browser, no person's FreeCAD settings.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="packages/cad/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cad.freecad._program import find_freecad; print(find_freecad())" \
  || { echo "test-cam.sh: FreeCAD is not installed: name its freecadcmd with CAD_FREECAD" >&2; exit 1; }

run_python_unittest "CAM job (cam) Python tests" "tests/python/packages/cam" "${PACKAGE_SOURCES[@]}"
