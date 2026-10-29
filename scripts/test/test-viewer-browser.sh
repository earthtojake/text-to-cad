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
    # --only: one gate while working on it: format, camera.
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
export CADGEN_ENGINE_DIR="$project/engine" CADGEN_ENGINE_MESH=inline CADGEN_CACHE_DIR="$project/no-0.7-store"
export CADGEN_VIEWER_DIST="$RUNTIME"
CADGEN_PORT="$("$PYTHON" - <<'PY'
import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
export CADGEN_PORT
server_pid=""
server_log="$project/server.log"
cleanup() {
  exit_status=$?
  diagnostics="${out_dir:-${VIEWER_TEST_DIAGNOSTICS_DIR:-}}"
  if [ "$exit_status" -ne 0 ] && [ -n "$diagnostics" ] && [ -f "$server_log" ]; then
    mkdir -p "$diagnostics" && "$PYTHON" - "$server_log" "$diagnostics/server.log" <<'PY' || true
import re, sys
from pathlib import Path

with Path(sys.argv[1]).open("rb") as log:
    log.seek(0, 2)
    log.seek(max(0, log.tell() - 256 * 1024))
    text = log.read().decode("utf-8", errors="replace")
text = re.sub(r"https?://[^\s<>\"']+", "<URL redacted>", text)
text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", text)
text = re.sub(r"(?i)(\b[\w-]*(?:token|authorization|cookie|secret|password)[\w-]*[\"']?\s*[:=]\s*)[^\r\n]+", r"\1<redacted>", text)
Path(sys.argv[2]).write_text(text, encoding="utf-8")
PY
  fi
  "$PYTHON" -m cadgen.engine stop >/dev/null 2>&1 || true
  if [ -n "$server_pid" ]; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
  rm -rf "$project" "$log"
}
trap cleanup EXIT

# Document operations only attach. Bootstrap this gate's selected server before
# the first export, then wait until that exact process answers its private door.
"$PYTHON" -m cadgen.engine server >"$server_log" 2>&1 &
server_pid=$!
"$PYTHON" - "$server_pid" "$server_log" <<'PY'
import json, os, subprocess, sys, time
from pathlib import Path

pid, log = int(sys.argv[1]), Path(sys.argv[2])
deadline = time.monotonic() + 60
while True:
    status = subprocess.run([sys.executable, "-m", "cadgen.engine", "status", "--json"],
                            capture_output=True, text=True, timeout=10)
    if status.returncode == 0 and (json.loads(status.stdout) or {}).get("pid") == pid:
        break
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        raise SystemExit("FAIL: explicit engine bootstrap exited: " + log.read_text())
    if time.monotonic() >= deadline:
        raise SystemExit("FAIL: explicit engine bootstrap did not become ready: " + log.read_text())
    time.sleep(0.02)
PY

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
