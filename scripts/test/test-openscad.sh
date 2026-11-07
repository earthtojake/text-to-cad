#!/usr/bin/env bash
set -euo pipefail

# OpenSCAD programs rendered by the real OpenSCAD, where the `cad` command and the engine run it: in its own
# process, headless, in private homes (the person's libraries kept reachable). The reader, the commands
# (inspect, export to STL/3MF/GLB, dfm, snapshot) and the engine's kept mesh (`cad_server._internal.scads`),
# each on this run's own engine, state and cache (the runner gives each test file its own). Needs
# `openscad` on PATH (or CAD_OPENSCAD): the job installs the distribution's package; the snapshot draws on
# the display the job gives the engine's OCCT stills (xvfb-run, as the package suite's). No browser.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

if [ -n "${CAD_OPENSCAD:-}" ]; then
  openscad_bin="$CAD_OPENSCAD"
else
  openscad_bin="$(command -v openscad || true)"
fi
if [ -z "$openscad_bin" ]; then
  echo "test-openscad.sh: no openscad on PATH and CAD_OPENSCAD is not set: install OpenSCAD 2021.01 or newer" >&2
  exit 1
fi
"$openscad_bin" --version

run_python_unittest "OpenSCAD Python tests" "tests/python/packages/openscad" "${PACKAGE_SOURCES[@]}"
