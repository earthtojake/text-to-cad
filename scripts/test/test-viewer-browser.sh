#!/usr/bin/env bash
# One self-contained browser gate for the viewer's format and camera
# contracts, and for a model, a KiCad board and a schematic shared by `cad share`
# and opened, with no engine running, from the share service. It runs exactly what CI runs. The project, the
# engine daemon, the Viewer, the share service and the browser are all owned by
# this process.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/common.sh"
python_candidate="${VIEWER_PYTHON:-$PYTHON_BIN}"
PYTHON="$(command -v "$python_candidate" 2>/dev/null || true)"
RUNTIME="${VIEWER_RUNTIME_DIR:-$REPO_ROOT/packages/cad/src/cad_server/_runtime/viewer}"
HOST=127.0.0.1

# The checkout's own packages (common.sh's PACKAGE_SOURCES), ahead of whatever is installed.
for source in "${PACKAGE_SOURCES[@]}"; do
  sources="${sources:+$sources:}$REPO_ROOT/$source"
done
export PYTHONPATH="$sources${PYTHONPATH:+:$PYTHONPATH}"

if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import cad, cad_server' >/dev/null 2>&1; then
  echo "FAIL: ${python_candidate:-python} cannot import the server; set VIEWER_PYTHON to the test interpreter" >&2
  exit 1
fi
if [ ! -f "$RUNTIME/index.html" ]; then
  echo "FAIL: bundled Viewer missing at $RUNTIME; run scripts/bundle/bundle.sh first" >&2
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
    # --only: one gate while working on it: format, camera, prompt, share.
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
export CAD_STATE_DIR="$project/state"
# The engine that builds the fixtures and serves the STEP and .xbf ones to the page: this
# test's own daemon, one part meshed at a time, stopped on the way out.
export CAD_ENGINE_DIR="$project/engine" CAD_ENGINE_MESH=inline CAD_CACHE_DIR="$project/no-0.7-store"
# A board is drawn as saved, as the package suites draw one: the gates fetch no KiCad (its refill is the KiCad suite's).
export CAD_KICAD_REFILL=0
export CAD_VIEWER_DIST="$RUNTIME"
share_pidfile="$project/share.pid"
cleanup() {
  "$PYTHON" -m cad_server.engine stop >/dev/null 2>&1 || true
  if [ -f "$share_pidfile" ]; then kill "$(cat "$share_pidfile")" 2>/dev/null || true; fi
  rm -rf "$project" "$log"
}
trap cleanup EXIT
# No command starts it: this checkout's server is started here, as a person or an agent starts one.
if ! (cd "$project" && "$PYTHON" -m cad_server.cli server start) >"$log" 2>&1; then
  echo "FAIL: this checkout's server did not start" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# The STEP the gates open: one cylinder, written by build123d's own STEP export, which the engine
# imports as it does any STEP it did not write. It is made here so that no CAD file is committed.
"$PYTHON" - "$project/smoke.step" <<'PY'
import sys

import build123d as bd

part = bd.Pos(42, 0, 2) * bd.Cylinder(3, 14)
part.label = "smoke"
bd.export_step(part, sys.argv[1])
PY
if ! head -1 "$project/smoke.step" | grep -q 'ISO-10303-21'; then
  echo "FAIL: the STEP fixture did not export" >&2
  exit 1
fi

# The mesh fixture is an export of the STEP fixture, by the engine.
if ! (cd "$project" && "$PYTHON" -m cad_server.engine export smoke.step smoke.stl) >"$log" 2>&1 \
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

from cad.engine import read_step, step
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
from cad.engine import step
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
# source edit saved while the model was open, and then the first one (kept there
# too) back over it, for a rebuild that shrinks the model.
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
        && mkdir -p .revision && mv hinge_grown.step .revision/hinge.step && cp hinge.step .revision/hinge-first.step \
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
from cad.engine import model


@model("smoke.xbf")
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

# The share gate's model: one part whose width is a parameter, built by the engine into its .xbf beside its script, in
# a dot-directory a project's page skips. A share carries the .xbf and the files that made it.
mkdir -p "$project/.share"
cat > "$project/.share/plate.py" <<'PLATE'
import build123d as bd
from cad import model

width = model.param("width", 40.0, min=20, max=80, unit="mm")


@model
def plate():
    body = bd.Box(width, 30, 6) - bd.Pos(width / 4, 0, 0) * bd.Cylinder(4, 10)
    body.label = "plate"
    return body


if __name__ == "__main__":
    plate()
PLATE
if ! (cd "$project/.share" && "$PYTHON" plate.py) >"$log" 2>&1 || [ ! -f "$project/.share/plate.xbf" ]; then
  echo "FAIL: the share fixture's model did not build" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# The share fixture's model by its document id, its .xbf's: the prompt gate copies a Quick Edit of it from the
# engine's page, and the share gate compares the shared page's with it.
plate_id="$("$PYTHON" -c 'import sys; from cad.engine.ids import file_id; print(file_id(sys.argv[1]))' \
  "$project/.share/plate.xbf")"

# The share gate's share: the model, shared by its .xbf with `cad share --yes` as a person's agent shares one,
# against this checkout's share service run locally (apps/share/serve.mjs: the Worker itself, over Node's http, with
# stand-ins for its bucket and limiter), which serves the bundled client too. The command runs while the
# engine runs, since the engine makes the bundle it uploads; the gate opens what it printed, the engine stopped.
share_args=()
if [ -z "$only_gate" ] || [ "$only_gate" = share ]; then
  node "$REPO_ROOT/apps/share/serve.mjs" --port 0 --assets "$RUNTIME" >"$project/share.origin" 2>"$project/share.log" &
  echo "$!" >"$share_pidfile"
  for _ in $(seq 1 300); do
    [ -s "$project/share.origin" ] && break
    kill -0 "$(cat "$share_pidfile")" 2>/dev/null || break
    sleep 0.1
  done
  share_origin="$(head -1 "$project/share.origin" 2>/dev/null || true)"
  if [[ "$share_origin" != http://* ]]; then
    echo "FAIL: the share service did not start" >&2
    sed 's/^/    /' "$project/share.log" >&2
    exit 1
  fi
  if ! (cd "$project" && CAD_SHARE_URL="$share_origin" "$PYTHON" -m cad_server.cli share .share/plate.xbf --yes --json) \
       >"$project/share.json" 2>"$log"; then
    echo "FAIL: cad share did not share the fixture's model" >&2
    sed 's/^/    /' "$project/share.json" "$log" >&2
    exit 1
  fi
  # And again, unchanged and by its document's id, as an agent shares after each edit: the same file, the same
  # link, and nothing but the commit travels. The person's yes is this computer's now, so the command no longer
  # asks for it.
  if ! (cd "$project" && CAD_SHARE_URL="$share_origin" "$PYTHON" -m cad_server.cli share "$plate_id" --json) \
       >"$project/share-again.json" 2>"$log"; then
    echo "FAIL: cad share did not share the fixture's model again" >&2
    sed 's/^/    /' "$project/share-again.json" "$log" >&2
    exit 1
  fi
  # The files that made it, as an agent on another computer takes them from the link (a state and a cache of
  # their own: no record of this share): `cad fork` downloads the zip the service makes of them and writes them
  # into a folder, the same bytes as the script that built the model and its .xbf. On this computer, which shared
  # it, the same command downloads nothing and says where its files already are.
  view_link="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["view"])' "$project/share.json")"
  if ! (cd "$project" && CAD_STATE_DIR="$project/elsewhere/state" CAD_CACHE_DIR="$project/elsewhere/cache" \
          CAD_SHARE_URL="$share_origin" "$PYTHON" -m cad_server.cli fork "$view_link" "$project/forked" --json) \
       >"$project/fork.json" 2>"$log" || ! cmp -s "$project/.share/plate.py" "$project/forked/plate.py" \
     || ! cmp -s "$project/.share/plate.xbf" "$project/forked/plate.xbf"; then
    echo "FAIL: cad fork did not write the shared model's files" >&2
    sed 's/^/    /' "$project/fork.json" "$log" >&2
    exit 1
  fi
  if ! (cd "$project" && CAD_SHARE_URL="$share_origin" "$PYTHON" -m cad_server.cli fork "$view_link" --json) \
       >"$project/fork-here.json" 2>"$log" \
     || ! "$PYTHON" -c 'import json,sys; sys.exit(json.load(open(sys.argv[1])).get("local") is not True)' "$project/fork-here.json"; then
    echo "FAIL: cad fork of this computer's own share did not say where its files are" >&2
    sed 's/^/    /' "$project/fork-here.json" "$log" >&2
    exit 1
  fi
  share_args=(--share "$project/share.json" --share-again "$project/share-again.json")
  # A KiCad board and schematic, the KiCad suite's test files, in a dot-directory a project's page skips: the board's
  # LED stands on a STEP of its project's, its resistor on one it names and has not; the schematic draws a second
  # sheet. Each is shared as the model is, by `cad share` while the engine runs.
  if ! PYTHONPATH="$REPO_ROOT:$PYTHONPATH" "$PYTHON" - "$project/.kicad" >"$log" 2>&1 <<'KICAD'
import sys
from pathlib import Path

from build123d import Box, export_step
from tests.python.support.kicad_board import BOARD, MODELS
from tests.python.support.kicad_schematic import write_schematic

folder = Path(sys.argv[1])
(folder / "blinky" / "models").mkdir(parents=True)
missing = '(model "${KIPRJMOD}/models/missing.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))'
(folder / "blinky" / "blinky.kicad_pcb").write_text(BOARD.replace(MODELS["R1"], missing), encoding="utf-8")
export_step(Box(1.6, 0.8, 0.6), str(folder / "blinky" / "models" / "led.step"))
write_schematic(folder / "divider")
KICAD
  then
    echo "FAIL: the KiCad share fixtures did not write" >&2
    sed 's/^/    /' "$log" >&2
    exit 1
  fi
  for kicad in board:.kicad/blinky/blinky.kicad_pcb schematic:.kicad/divider/divider.kicad_sch; do
    if ! (cd "$project" && CAD_SHARE_URL="$share_origin" "$PYTHON" -m cad_server.cli share "${kicad#*:}" --json) \
         >"$project/share-${kicad%%:*}.json" 2>"$log"; then
      echo "FAIL: cad share did not share the fixture's KiCad ${kicad%%:*}" >&2
      sed 's/^/    /' "$project/share-${kicad%%:*}.json" "$log" >&2
      exit 1
    fi
  done
  share_args+=(--share-board "$project/share-board.json" --share-schematic "$project/share-schematic.json")
fi

(cd "$project" && "$PYTHON" -m cad_server.viewer --json) >"$log"
url="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["apiUrl"])' "$log")"
export VIEWER_TEST_TOKEN="$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$log")"
e2e_args=(--dir "$project" --url "$url" --plate "$plate_id" --prompt "$project/prompt-local.txt")
# (An empty array expanded under `set -u` is an error in the bash macOS ships, hence the `+`.)
shared_args=(--prompt "$project/prompt-local.txt" ${share_args[@]+"${share_args[@]}"})
[ -n "$out_dir" ] && e2e_args+=(--out "$out_dir") && shared_args+=(--out "$out_dir")
[ -n "$only_gate" ] && e2e_args+=(--only "$only_gate") && shared_args+=(--only "$only_gate")
echo "  [setup] $(( $(date +%s) - started_at ))s to fixtures, viewer and port"
if [ "$only_gate" != share ]; then
  node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" "${e2e_args[@]}"
fi
# The share gate runs with no engine: the server is stopped first, and the page has only the share service.
if [ -z "$only_gate" ] || [ "$only_gate" = share ]; then
  "$PYTHON" -m cad_server.engine stop >/dev/null 2>&1 || true
  node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" "${shared_args[@]}"
fi
