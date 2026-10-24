#!/usr/bin/env bash
# One self-contained browser gate for the CAD Viewer's format and camera
# contracts. It runs exactly what CI runs. The project, the engine daemon, the
# Viewer, and the browser are all owned by this process.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/common.sh"
python_candidate="${VIEWER_PYTHON:-$PYTHON_BIN}"
PYTHON="$(command -v "$python_candidate" 2>/dev/null || true)"
RUNTIME="${VIEWER_RUNTIME_DIR:-$REPO_ROOT/packages/cadgen/src/cadgen/_runtime/viewer}"
FIXTURE="$REPO_ROOT/tests/fixtures/cad/import-smoke.step"
HOST=127.0.0.1

export PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}"

if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import cadgen' >/dev/null 2>&1; then
  echo "FAIL: ${python_candidate:-python} cannot import cadgen; set VIEWER_PYTHON to the test interpreter" >&2
  exit 1
fi
if [ ! -f "$RUNTIME/index.html" ]; then
  echo "FAIL: bundled Viewer missing at $RUNTIME; run scripts/bundle/bundle.sh first" >&2
  exit 1
fi
if ! head -1 "$FIXTURE" | grep -q 'ISO-10303-21'; then
  echo "FAIL: test fixture is not STEP text: $FIXTURE" >&2
  exit 1
fi

out_dir=""
only_gate=""
while [ "$#" -ne 0 ]; do
  case "$1" in
    --out|--only)
      if [ "$#" -lt 2 ] || [[ "$2" == --* ]] || [ -z "$2" ]; then
        echo "usage: $0 [--out SCREENSHOT_DIR] [--only GATE]" >&2
        exit 2
      fi
      if [ "$1" = "--out" ]; then out_dir="$2"; else only_gate="$2"; fi
      shift 2 ;;
    # --only: one gate while working on it: format, camera, library.
    *) echo "usage: $0 [--out SCREENSHOT_DIR] [--only GATE]" >&2; exit 2 ;;
  esac
done
started_at="$(date +%s)"
# macOS Unix sockets have a 104-byte path limit. Keep the test's engine daemon's
# folder and child-process scratch paths short as well as private.
if [ "$(uname -s)" = "Darwin" ]; then
  project="$(mktemp -d /tmp/cvb.XXXXXX)"
  export TMPDIR="$project/tmp"
  mkdir -p "$TMPDIR"
else
  project="$(mktemp -d)"
fi
log="$(mktemp)"
viewer_pidfile="$project/viewer.pid"
# The model library every Viewer writes: the test's own, never the user's.
export CADGEN_STATE_DIR="$project/state"
# The engine that builds the fixtures and serves the STEP and .xbf ones to the page: this
# test's own daemon, one part meshed at a time, stopped on the way out.
export CADGEN_ENGINE_DIR="$project/engine" CADGEN_ENGINE_MESH=inline CADGEN_ENGINE_IDLE=120 CADGEN_CACHE_DIR="$project/no-0.7-store"
export CADGEN_VIEWER_DIST="$RUNTIME"
cleanup() {
  "$PYTHON" -m cadgen.engine stop >/dev/null 2>&1 || true
  rm -rf "$project" "$log"
}
trap cleanup EXIT

cp "$FIXTURE" "$project/smoke.step"

# The mesh fixture is an export of the STEP fixture, by the engine.
if ! (cd "$project" && "$PYTHON" -m cadgen.engine export smoke.step smoke.stl) >"$log" 2>&1 \
   || [ ! -f "$project/smoke.stl" ]; then
  echo "FAIL: the mesh fixture did not export" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# The canonical STEP fixture is intentionally one part. A model places it twice to exercise
# the positive STEP assembly-tree capability, with no other CAD construction or any
# repository model dependency; its script goes once it is built.
cat > "$project/assembly_fixture.py" <<'ASSEMBLY'
from pathlib import Path

from cadgen.engine import read_step, step
import build123d as bd

HERE = Path(__file__).resolve().parent


@step(out="assembly.step")
def smoke_assembly():
    left = read_step(HERE / "smoke.step")
    left.label = "left_cylinder"
    right = left.moved(bd.Pos(10, 0, 0))
    right.label = "right_cylinder"
    return bd.Compound(children=[left, right], label="smoke_assembly")

if __name__ == "__main__":
    smoke_assembly()
ASSEMBLY

# A STEP model the camera gate saves a rebuilt revision over. Built from
# primitives, so it imports nothing.
cat > "$project/hinge.py" <<'HINGE'
from cadgen.engine import step
import build123d as bd


@step("hinge.step")
def hinge():
    base = bd.Box(20, 20, 4)
    base.label = "base"
    arm = bd.Pos(30, 0, 6) * bd.Box(56, 4, 4)
    arm.label = "arm"
    return bd.Compound(children=[base, arm], label="hinge")

if __name__ == "__main__":
    hinge()
HINGE
# A SECOND revision of the same model, with an arm long enough that the model
# no longer fits the frame the first one was fitted to. It is built into a
# dot-directory, which the explorer skips, so the model's folder still holds
# one hinge; the gate copies it over the first to stand in for a rebuild that a
# source edit saved while the model was open.
# Each revision declares its output name, so the two revisions build side by
# side instead of one overwriting the other. Literal substitutions only: GNU and
# BSD sed do not spell a word boundary the same way.
sed -e 's/bd.Pos(30, 0, 6) \* bd.Box(56, 4, 4)/bd.Pos(80, 0, 6) * bd.Box(156, 4, 4)/' \
    -e 's/hinge()/hinge_grown()/g' \
    -e 's/"hinge.step"/"hinge_grown.step"/' \
  "$project/hinge.py" > "$project/hinge_grown.py"
if ! grep -q 'bd.Box(156, 4, 4)' "$project/hinge_grown.py" \
   || ! grep -q 'def hinge_grown()' "$project/hinge_grown.py"; then
  echo "FAIL: the grown hinge revision did not diverge from the first" >&2
  exit 1
fi

# The served project holds artifacts only: a model script beside them would
# enter the catalog as an entry of its own and change what the gates see. A build
# returns once every file it declares is on disk.
if ! (cd "$project" && "$PYTHON" assembly_fixture.py && "$PYTHON" hinge.py && "$PYTHON" hinge_grown.py \
        && mkdir -p .revision && mv hinge_grown.step .revision/hinge.step \
        && rm assembly_fixture.py hinge.py hinge_grown.py) >"$log" 2>&1 \
   || [ ! -f "$project/assembly.step" ] || [ ! -f "$project/hinge.step" ]; then
  echo "FAIL: the STEP model fixtures did not build" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# An engine document: a plate with a hole and a peg placed on it, built as a model script runs
# (through this test's own engine daemon). Its script goes once it is built, as the hinge's does.
cat > "$project/smoke_xbf.py" <<'XBF'
import build123d as bd
from cadgen.engine import xbf


@xbf(out="smoke.xbf")
def smoke():
    plate = bd.Box(30, 20, 4) - bd.Cylinder(3, 10)
    plate.label = "plate"
    peg = bd.Pos(8, 0, 6) * bd.Cylinder(2, 8)
    peg.label = "peg"
    return bd.Compound(children=[plate, peg], label="smoke")

if __name__ == "__main__":
    smoke()
XBF
if ! (cd "$project" && "$PYTHON" smoke_xbf.py && rm smoke_xbf.py) >"$log" 2>&1 \
   || [ ! -f "$project/smoke.xbf" ]; then
  echo "FAIL: the engine document fixture did not build" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# A closed 20 x 12 outline on layer OUTLINE, written by ezdxf (cadgen's DXF reader) so it is a
# DXF the backend reads: a hand-written one lacks the subclass markers it requires.
"$PYTHON" - "$project/smoke.dxf" <<'PY'
import sys

import ezdxf

document = ezdxf.new()
document.modelspace().add_lwpolyline([(-10, -6), (10, -6), (10, 6), (-10, 6)], close=True, dxfattribs={"layer": "OUTLINE"})
document.saveas(sys.argv[1])
PY

cat > "$project/smoke.urdf" <<'URDF'
<?xml version="1.0"?>
<robot name="viewer_smoke">
  <link name="base">
    <visual><geometry><box size="0.10 0.08 0.02"/></geometry></visual>
  </link>
  <link name="arm">
    <visual><geometry><cylinder radius="0.012" length="0.10"/></geometry></visual>
  </link>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="arm"/>
    <origin xyz="0 0 0.06"/><axis xyz="0 1 0"/>
    <limit lower="-1.0" upper="1.0" effort="1" velocity="1"/>
  </joint>
</robot>
URDF

(cd "$project" && "$PYTHON" -m cadgen.viewer --json) >"$log"
url="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["apiUrl"])' "$log")"
export VIEWER_TEST_TOKEN="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$log")"
e2e_args=(--dir "$project" --url "$url")
[ -n "$out_dir" ] && e2e_args+=(--out "$out_dir")
[ -n "$only_gate" ] && e2e_args+=(--only "$only_gate")
echo "  [setup] $(( $(date +%s) - started_at ))s to fixtures, viewer and port"
node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" "${e2e_args[@]}"
