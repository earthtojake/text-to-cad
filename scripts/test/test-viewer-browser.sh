#!/usr/bin/env bash
# One self-contained browser gate for the CAD Viewer's format, placement,
# appearance, LOD, and picking contracts. The project, store, Viewer, and
# browser are all owned by this process.
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
ci_subset=""
while [ "$#" -ne 0 ]; do
  case "$1" in
    --out|--only)
      if [ "$#" -lt 2 ] || [[ "$2" == --* ]] || [ -z "$2" ]; then
        echo "usage: $0 [--out SCREENSHOT_DIR] [--only GATE] [--ci]" >&2
        exit 2
      fi
      if [ "$1" = "--out" ]; then out_dir="$2"; else only_gate="$2"; fi
      shift 2 ;;
    # One gate while working on it: picking, pick, format, scene, quality,
    # kinematics, camera.
    # The CI-sized subset (format, pick, kinematics, camera). Without it this is
    # the full manual gate; tests/browser/viewer-e2e.mjs says what each covers and
    # why the rest stays manual.
    --ci) ci_subset=1; shift ;;
    *) echo "usage: $0 [--out SCREENSHOT_DIR] [--only GATE] [--ci]" >&2; exit 2 ;;
  esac
done
started_at="$(date +%s)"
# macOS Unix sockets have a 104-byte path limit. Keep the test's daemon state
# and child-process scratch paths short as well as private.
if [ "$(uname -s)" = "Darwin" ]; then
  project="$(mktemp -d /tmp/cvb.XXXXXX)"
  export TMPDIR="$project/tmp"
  mkdir -p "$TMPDIR"
else
  project="$(mktemp -d)"
fi
log="$(mktemp)"
viewer_pidfile="$project/viewer.pid"
export CADGEN_CACHE_DIR="$project/cache"
export CADGEN_DAEMON=0
export CADGEN_DAEMON_STATE_DIR="$project/daemon-state"
export CADGEN_VIEWER_DIST="$RUNTIME"
unset CADGEN_BROKER CADGEN_BROKER_KEY CADGEN_BROKER_STATS CADGEN_DAEMON_CHILD CADGEN_ROOT_ID
server_pid=""

cleanup() {
  if [ -n "$server_pid" ]; then
    # Use the native PID written by Python: under MSYS, bash's $! is not a
    # Windows PID. POSIX descendants share this test-owned process group;
    # taskkill /T owns the corresponding Windows tree.
    "$PYTHON" - "$viewer_pidfile" <<'PY' 2>/dev/null || kill "$server_pid" 2>/dev/null || true
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

pid_path = Path(sys.argv[1])
if pid_path.is_file():
    pid = int(pid_path.read_text(encoding="ascii"))
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(20):
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
PY
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$project" "$log"
}
trap cleanup EXIT

cp "$FIXTURE" "$project/smoke.step"

# One imported document and one tessellation produce every mesh fixture. This
# keeps format parity meaningful without five model builds or repository data.
"$PYTHON" - "$project" <<'PY'
import sys
from pathlib import Path

from cadgen import build123d as bd
from cadgen.step_export import export_build123d_step_scene
from cadgen.step_export_target import export_cad_target

root = Path(sys.argv[1])
result = export_cad_target(
    root / "smoke.step",
    [("stl", root / "smoke.stl"), ("3mf", root / "smoke.3mf"), ("glb", root / "smoke.glb")],
    repo_root=root,
)
if len(result.get("files") or []) != 3:
    raise RuntimeError(f"mesh setup did not write three outputs: {result}")

# The canonical fixture is intentionally one part. Reuse its exact solid twice
# to exercise the positive STEP assembly-tree capability without another CAD
# construction or any repository model dependency.
left = bd.import_step(root / "smoke.step")
left.label = "left_cylinder"
right = left.moved(bd.Pos(10, 0, 0))
right.label = "right_cylinder"
assembly = bd.Compound(children=[left, right], label="smoke_assembly")
export_build123d_step_scene(assembly, root / "assembly.step")
PY

# Two tiny authored mesh objects retain distinct display names and stable CAD
# identities. Use the compiled GLB writer, with no extra CAD construction.
node --input-type=module - "$project" "$REPO_ROOT" <<'JS'
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(path.join(process.argv[3], 'package.json'));
const { writeGlb } = await import(require.resolve('@hardcore/core/lib/glb/writeGlb.js'));
function tetrahedron(offset) {
  const vertices = [[offset, 0, 0], [offset + 0.01, 0, 0], [offset, 0.01, 0], [offset, 0, 0.01]];
  return Float32Array.from([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]].flatMap(face => face.flatMap(index => vertices[index])));
}
fs.writeFileSync(path.join(process.argv[2], 'named-components.glb'), writeGlb({ primitives: [
  { positions: tetrahedron(0), name: 'bracket', occurrenceId: 'o1', color: '#e88c30' },
  { positions: tetrahedron(0.02), name: 'pulley', occurrenceId: 'o2', color: '#4080d0' },
] }, { preset: 'export', upAxis: 'z', units: 'm' }));
JS

# A STEP document whose sidecar declares a mate: the other way a model is posed,
# and the one whose pose reaches the scene through cadScene parameters rather
# than a posed mesh wrapper. Built from primitives, so it imports nothing.
cat > "$project/hinge.py" <<'HINGE'
import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("swing", parent="#base", child="#arm",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
}


@step(kinematics=KINEMATICS)
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    # Long enough that swinging it rewrites the model's bounding box: framing the
    # posed model puts the camera somewhere the zero pose never would.
    arm = label_shape(bd.Pos(30, 0, 6) * bd.Box(56, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
HINGE
# A SECOND revision of the same model, with an arm long enough that the model
# no longer fits the frame the first one was fitted to. It is built into a
# dot-directory, which the catalog scan skips, so the served root still holds
# one hinge; the gate copies it over the first to stand in for a rebuild that a
# source edit saved while the model was open.
# The model name decides the output name, so the two revisions build side by
# side instead of one overwriting the other. Literal substitutions only: GNU and
# BSD sed do not spell a word boundary the same way.
sed -e 's/bd.Pos(30, 0, 6) \* bd.Box(56, 4, 4)/bd.Pos(80, 0, 6) * bd.Box(156, 4, 4)/' \
    -e 's/def hinge()/def hinge_grown()/' \
    -e 's/^    hinge()$/    hinge_grown()/' \
  "$project/hinge.py" > "$project/hinge_grown.py"
if ! grep -q 'bd.Box(156, 4, 4)' "$project/hinge_grown.py" \
   || ! grep -q 'def hinge_grown()' "$project/hinge_grown.py"; then
  echo "FAIL: the grown hinge revision did not diverge from the first" >&2
  exit 1
fi

# The served project holds artifacts only: a model script beside them would
# enter the catalog as a buildable entry and change what the other gates see.
if ! (cd "$project" && "$PYTHON" hinge.py && "$PYTHON" hinge_grown.py \
        && mkdir -p .revision && mv hinge_grown.step .revision/hinge.step \
        && mv hinge_grown.step.json .revision/hinge.step.json \
        && rm hinge.py hinge_grown.py) >"$log" 2>&1; then
  echo "FAIL: the kinematics STEP fixture did not build" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

# Mesh export necessarily materializes source surfaces and tessellations. The
# browser gate starts with a new store so its first STEP page remains a true
# cold import/derive path; only this test's private cache is removed.
rm -rf "$CADGEN_CACHE_DIR"
mkdir -p "$CADGEN_CACHE_DIR"

cat > "$project/smoke.dxf" <<'DXF'
0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
OUTLINE
90
4
70
1
10
-10
20
-6
10
10
20
-6
10
10
20
6
10
-10
20
6
0
ENDSEC
0
EOF
DXF

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

# A linked mesh retains its two authored object names in both robot formats.
cat > "$project/named-components.urdf" <<'URDF'
<?xml version="1.0"?>
<robot name="viewer_named_components">
  <link name="base">
    <visual><geometry><box size="0.10 0.08 0.02"/></geometry></visual>
  </link>
  <link name="arm">
    <visual><geometry><mesh filename="named-components.glb" scale="0.001 0.001 0.001"/></geometry></visual>
  </link>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="arm"/>
    <origin xyz="0 0 0.06"/><axis xyz="0 1 0"/>
    <limit lower="-1.0" upper="1.0" effort="1" velocity="1"/>
  </joint>
</robot>
URDF
cat > "$project/named-components.srdf" <<'SRDF'
<?xml version="1.0"?>
<robot name="viewer_named_components">
  <group name="arm_group"><joint name="shoulder"/></group>
  <group_state name="lifted" group="arm_group"><joint name="shoulder" value="0.5"/></group_state>
</robot>
SRDF

# A robot whose base link origin sits ABOVE its lowest geometry: the clamp hangs
# entirely below z=0, which is where the photographic floor used to be pinned.
# Its own name, so the SRDF below still pairs with smoke.urdf alone.
cat > "$project/below-origin.urdf" <<'URDF'
<?xml version="1.0"?>
<robot name="viewer_below_origin">
  <link name="base">
    <visual><geometry><box size="0.10 0.08 0.02"/></geometry></visual>
  </link>
  <link name="clamp">
    <visual><geometry><box size="0.06 0.06 0.08"/></geometry></visual>
  </link>
  <joint name="clamp_mount" type="fixed">
    <parent link="base"/><child link="clamp"/>
    <origin xyz="0 0 -0.05"/>
  </joint>
</robot>
URDF

# Paired by matching <robot name>, so the same two links carry the SRDF
# planning semantics whose group state is the other way a joint is driven.
cat > "$project/smoke.srdf" <<'SRDF'
<?xml version="1.0"?>
<robot name="viewer_smoke">
  <group name="arm_group">
    <joint name="shoulder"/>
  </group>
  <group_state name="lifted" group="arm_group">
    <joint name="shoulder" value="0.5"/>
  </group_state>
</robot>
SRDF

"$PYTHON" -c 'import os, pathlib, sys; os.setsid() if os.name != "nt" else None; pathlib.Path(sys.argv[3]).write_text(str(os.getpid()), encoding="ascii"); os.chdir(sys.argv[1]); os.execv(sys.executable, [sys.executable, "-m", "cadgen.viewer", "--host", sys.argv[2], "--json", "--new", "--no-registry"])' \
  "$project" "$HOST" "$viewer_pidfile" >"$log" 2>&1 &
server_pid=$!

port=""
for _ in $(seq 1 30); do
  port="$(sed -n 's/^{.*"port":\([0-9]*\).*}$/\1/p' "$log" | tail -1)"
  [ -n "$port" ] && break
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "FAIL: Viewer exited before announcing its port" >&2
    sed 's/^/    /' "$log" >&2
    exit 1
  fi
  sleep 1
done
if [ -z "$port" ]; then
  echo "FAIL: Viewer did not announce a port" >&2
  sed 's/^/    /' "$log" >&2
  exit 1
fi

e2e_args=(--dir "$project" --url "http://$HOST:$port")
[ -n "$out_dir" ] && e2e_args+=(--out "$out_dir")
[ -n "$only_gate" ] && e2e_args+=(--only "$only_gate")
[ -n "$ci_subset" ] && e2e_args+=(--ci)
echo "  [setup] $(( $(date +%s) - started_at ))s to fixtures, viewer and port"
node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" "${e2e_args[@]}"
