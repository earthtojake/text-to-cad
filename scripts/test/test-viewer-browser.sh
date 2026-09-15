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
if [ "$#" -ne 0 ]; then
  if [ "$#" -ne 2 ] || [ "$1" != "--out" ] || [ -z "$2" ]; then
    echo "usage: $0 [--out SCREENSHOT_DIR]" >&2
    exit 2
  fi
  out_dir="$2"
fi

project="$(mktemp -d)"
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

if [ -n "$out_dir" ]; then
  node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" \
    --out "$out_dir" --dir "$project" --url "http://$HOST:$port"
else
  node "$REPO_ROOT/tests/browser/viewer-e2e.mjs" \
    --dir "$project" --url "http://$HOST:$port"
fi
