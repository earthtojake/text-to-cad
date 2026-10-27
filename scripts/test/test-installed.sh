#!/usr/bin/env bash
# Exercise cadgen the way a user gets it: built into a wheel, pip-installed, run from a
# directory that is not this repo.
#
# Every other check in this repo runs against the source tree, where the repo root is on
# sys.path and the apps' builds sit beside the package. None of that is true after
# `pip install cadgen`, so the failures this catches are exactly the ones no other check
# can: an asset left out of package-data, a module that resolves only because a sibling
# directory happened to be adjacent. Those all pass locally and break for the person who
# installed it.
#
# The scratch venv reuses the repo venv's heavy dependencies (OCP, build123d) rather than
# reinstalling half a gigabyte -- but the wheel's own cadgen must WIN over the repo's
# editable one, or this would silently test the source tree again. See _link_repo_deps.
#
# Usage: scripts/test/test-installed.sh [--wheel PATH]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Shared resolution: the repo venv in a checkout, python3 otherwise. CI installs the CAD
# dependencies into the interpreter that setup-python provides and has no .venv at all, so
# hardcoding one here fails there and only there.
# shellcheck source=scripts/test/common.sh
source "$SCRIPT_DIR/common.sh"

WHEEL=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --wheel)
      [ "$#" -ge 2 ] || { echo "--wheel requires a path" >&2; exit 2; }
      [ -f "$2" ] || { echo "wheel not found: $2" >&2; exit 2; }
      WHEEL="$(cd "$(dirname "$2")" && pwd -P)/$(basename "$2")"
      shift 2
      ;;
    -h|--help)
      echo "Usage: scripts/test/test-installed.sh [--wheel PATH]"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "Usage: scripts/test/test-installed.sh [--wheel PATH]" >&2
      exit 2
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [ ! -x "$PYTHON_BIN" ]; then
  echo "No usable Python ($PYTHON_BIN). Set PYTHON_BIN to an interpreter with the CAD deps." >&2
  exit 1
fi

# The wheel is installed with --no-deps and reuses this interpreter's heavy packages, so it
# must actually have them; otherwise the failure surfaces much later in a build that
# cannot import its kernel.
if ! "$PYTHON_BIN" -c "import OCP, build123d" >/dev/null 2>&1; then
  echo "$PYTHON_BIN cannot import OCP/build123d; installed-mode checks need the CAD deps." >&2
  exit 1
fi

# Short: a Unix socket path caps near 104 bytes, and the engine daemon's sits in this folder.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cti.XXXXXX")"
VENV="$WORK/venv"
EMPTY="$WORK/empty"
DIST="$WORK/dist"
mkdir -p "$EMPTY" "$DIST"
# The builds below run on the engine's daemon, as every build does: this run's own, in a private
# folder, stopped on the way out.
export CADGEN_ENGINE_DIR="$WORK/engine" CADGEN_CACHE_DIR="$WORK/no-0.7-store"
cleanup() {
  # The installed cadgen stops the daemon its builds started.
  if [ -x "$VENV/bin/python" ]; then
    "$VENV/bin/python" -m cadgen.engine stop >/dev/null 2>&1 \
      || echo "warning: this run's engine daemon did not stop; it goes once idle" >&2
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
# What the CAD app remembers (its library, release checks) stays in the throwaway directory too.
export CADGEN_STATE_DIR="$WORK/state"
# And the cadgen command the installation writes for the skills: never this machine's ~/.local/bin.
export CADGEN_LAUNCHER_DIR="$WORK/bin"
unset CADGEN_INSTALLATION_VERSION CADGEN_VERSION

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

if [ -z "$WHEEL" ]; then
  step "Build the wheel"
  "$REPO_ROOT/scripts/bundle/bundle.sh" >/dev/null
  "$PYTHON_BIN" -m build --wheel --outdir "$DIST" "$REPO_ROOT/packages/cadgen" >"$WORK/build.log" 2>&1 \
    || { cat "$WORK/build.log" >&2; fail "wheel build"; }
  WHEEL="$(find "$DIST" -name '*.whl' -type f | head -n 1)"
  [ -n "$WHEEL" ] || fail "no wheel produced"
else
  step "Use the supplied wheel"
fi
echo "   $(basename "$WHEEL")"

step "Install it into a scratch venv"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --no-deps "$WHEEL"

_link_repo_deps() {
  # Expose the repo venv's site-packages for OCP/build123d/etc WITHOUT letting its editable
  # cadgen win. A plain path line in a .pth is sys.path.append, so it lands AFTER this
  # venv's own site-packages (where the wheel is) and its .pth files are not processed --
  # which is what keeps the editable cadgen out.
  local repo_sp scratch_sp
  repo_sp="$("$PYTHON_BIN" -c 'import site; print(site.getsitepackages()[0])')"
  scratch_sp="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "$repo_sp" >"$scratch_sp/zz-repo-deps.pth"
}
_link_repo_deps

step "The installed cadgen is the WHEEL's, not the checkout's"
"$VENV/bin/python" - <<'PY' || exit 1
import sys, pathlib, cadgen
where = pathlib.Path(cadgen.__file__).resolve()
if "site-packages" not in where.parts:
    sys.exit(f"FAIL: imported cadgen from {where}, not the installed wheel")
print(f"   {cadgen.__version__} at {where.parent}")
PY

step "import build123d is lazy from interpreter start: the wheel's .pth is in site-packages"
scratch_sp="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
[ -f "$scratch_sp/cadgen-lazy-kernel.pth" ] || fail "cadgen-lazy-kernel.pth is not in $scratch_sp"
[ "$(cat "$scratch_sp/cadgen-lazy-kernel.pth")" = "import cadgen._internal.lazy_kernel" ] \
  || fail "cadgen-lazy-kernel.pth does not import the finder"
# Bound, not loaded: the kernel is untouched until an attribute is read from it.
lazy="$(cd "$EMPTY" && "$VENV/bin/python" -c "import build123d as bd; import sys; print('OCP' in sys.modules)")"
[ "$lazy" = "False" ] || fail "import build123d loaded the kernel ($lazy)"
loaded="$(cd "$EMPTY" && "$VENV/bin/python" -c "import build123d as bd, sys; bd.Box(1, 1, 1); print('OCP' in sys.modules)")"
[ "$loaded" = "True" ] || fail "the first attribute of build123d did not load the kernel ($loaded)"
echo "   $scratch_sp/cadgen-lazy-kernel.pth"

step "Assets resolve to the packaged runtime"
"$VENV/bin/python" - <<'PY' || exit 1
import sys
from cadgen.assets import viewer_dist_dir
from cadgen.mcp.ui import app_dir
for label, resolved in (
    ("CAD Viewer client", viewer_dist_dir()),
    ("CAD app page", app_dir()),
):
    if "site-packages" not in str(resolved):
        sys.exit(f"FAIL: {label} resolved outside the wheel: {resolved}")
    if not resolved.is_dir():
        sys.exit(f"FAIL: {label} missing: {resolved}")
    print(f"   {label}: {resolved.name}")
PY

step "Every subcommand dispatches from an empty directory"
cd "$EMPTY"
"$VENV/bin/cadgen" --help >/dev/null || fail "cadgen --help"
# The list comes from the INSTALLED registry, not from a copy of it here: a
# hand-written list goes stale silently the first time a command is renamed, and
# then this step passes while checking commands that no longer exist.
"$VENV/bin/python" -c 'from cadgen.cli import _COMMANDS; print("\n".join(sorted(_COMMANDS)))' \
  >"$WORK/commands.txt" || fail "read the installed command registry"
[ -s "$WORK/commands.txt" ] || fail "the installed command registry is empty"
while read -r command; do
  [ -n "$command" ] || continue
  # shellcheck disable=SC2086
  "$VENV/bin/cadgen" $command --help >/dev/null 2>&1 || fail "cadgen $command --help"
  echo "   cadgen $command"
done <"$WORK/commands.txt"

step "Serve the CAD app over MCP, as an agent host starts it"
"$VENV/bin/python" - "$VENV/bin/cadgen" "$WORK" <<'PY' || exit 1
import json, os, subprocess, sys, threading
import cadgen

server = subprocess.Popen([sys.argv[1], "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
watchdog = threading.Timer(60, server.kill)
watchdog.daemon = True
watchdog.start()


def send(message):
    server.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
    server.stdin.flush()


def call(request_id, method, params):
    send({"id": request_id, "method": method, "params": params})
    for line in server.stdout:
        message = json.loads(line)
        if message.get("id") == request_id:
            if "error" in message:
                sys.exit(f"FAIL: {method}: {message['error']}")
            return message["result"]
    sys.exit(f"FAIL: cadgen mcp exited during {method}")


# As an MCP Apps host: one that advertises the UI extension is served the page.
ui = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": ui, "clientInfo": {"name": "test-installed", "version": "0"}})
send({"method": "notifications/initialized"})
tools = {tool["name"]: tool for tool in call(2, "tools/list", {})["tools"]}
uri = tools["cad_show"]["_meta"]["ui"]["resourceUri"]
page = call(3, "resources/read", {"uri": uri})["contents"][0]["text"]
# The page is package data: a wheel without it serves a placeholder that says so.
if "missing from this install" in page or "<script" not in page:
    sys.exit(f"FAIL: {uri} is not the packaged CAD app")
# Showing a model mounts a view whose launch says which cadgen serves it: this install's.
mesh = os.path.join(sys.argv[2], "shown.stl")
with open(mesh, "w", encoding="utf-8") as handle:
    handle.write("solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n")
shown = call(4, "tools/call", {"name": "cad_show", "arguments": {"source": mesh}})
launch = (shown.get("structuredContent") or {}).get("launch") or {}
if shown.get("isError") or launch.get("version") != cadgen.__version__ or launch.get("model") != os.path.abspath(mesh):
    sys.exit(f"FAIL: cad_show answered {shown}")
server.stdin.close()
if server.wait(30) != 0:
    sys.exit(f"FAIL: cadgen mcp exited {server.returncode} when the host closed its input")
watchdog.cancel()
print(f"   {len(tools)} tools; the app is {len(page) // 1024} KiB at {uri}")
PY

step "Starting the CAD app's server registered it and wrote the cadgen command the skills run"
VERSION_INSTALLED="$("$VENV/bin/python" -c 'import cadgen; print(cadgen.__version__)')"
RECORD="$CADGEN_STATE_DIR/installations/$VERSION_INSTALLED.json"
CADGEN_COMMAND="$CADGEN_LAUNCHER_DIR/cadgen"
[ -f "$RECORD" ] || fail "no record of cadgen $VERSION_INSTALLED in $CADGEN_STATE_DIR/installations"
# Compared resolved: the temporary folder's path may be spelled through a symlink (/var, /private/var).
"$VENV/bin/python" - "$RECORD" "$VENV" <<'PY' || exit 1
import json, os, sys
record = json.load(open(sys.argv[1], encoding="utf-8"))
if os.path.realpath(record["prefix"]) != os.path.realpath(sys.argv[2]):
    sys.exit(f"FAIL: {sys.argv[1]} names {record['prefix']}, not {sys.argv[2]}")
PY
[ -x "$CADGEN_COMMAND" ] && grep -q '^# cadgen proxy: ' "$CADGEN_COMMAND" || fail "$CADGEN_COMMAND is not the cadgen command"
same() { "$VENV/bin/python" -c 'import os, sys; sys.exit(os.path.realpath(sys.argv[1]) != os.path.realpath(sys.argv[2]))' "$1" "$2"; }
same "$("$CADGEN_COMMAND" "+$VERSION_INSTALLED" run -c 'import sys; print(sys.prefix)')" "$VENV" \
  || fail "cadgen +$VERSION_INSTALLED run does not run the installation's python"
missing="$("$CADGEN_COMMAND" +0.0.1 status 2>&1)" && fail "cadgen +0.0.1 ran"
case "$missing" in "cadgen 0.0.1 is not installed: run "*) ;; *) fail "cadgen +0.0.1 said: $missing" ;; esac
echo "   $(basename "$RECORD") and $CADGEN_COMMAND"

step "Build a real model with no repo in sight"
mkdir -p "$EMPTY/models"
cat >"$EMPTY/models/probe.py" <<'PY'
# A model script explicitly calls its model, writing what its decorators declare. Deliberately the simplest one that exists: this checks that an installed cadgen can
# build at all, not that it models anything interesting.
from cadgen.engine import step, stl, xbf
import build123d as bd


@xbf("XBF/probe.xbf")
@step("probe.step")
@stl("probe.stl")
def probe():
    return bd.Box(10, 10, 10)


if __name__ == "__main__":
    probe()
PY
# Running the script IS the build: no CLI verb takes its place. Run as a skill runs it: cadgen +V run.
"$CADGEN_COMMAND" "+$VERSION_INSTALLED" run models/probe.py >"$WORK/build.log" 2>&1 \
  || { cat "$WORK/build.log" >&2; fail "cadgen +$VERSION_INSTALLED run <model>.py"; }
for written in XBF/probe.xbf probe.step probe.stl; do
  [ -s "$EMPTY/models/$written" ] \
    || { cat "$WORK/build.log" >&2; fail "the model script did not write models/$written"; }
done
echo "   built an xbf and the STEP and STL it declares"

# The script above wrote the files the model DECLARES. This is the other half: an export of
# the document to a destination the command names.
step "Export the document"
"$CADGEN_COMMAND" "+$VERSION_INSTALLED" export models/XBF/probe.xbf models/exported.step models/exported.stl \
  >"$WORK/export.log" 2>&1 || { cat "$WORK/export.log" >&2; fail "cadgen +$VERSION_INSTALLED export"; }
for written in exported.step exported.stl; do
  [ -s "$EMPTY/models/$written" ] || { cat "$WORK/export.log" >&2; fail "export wrote no models/$written"; }
done
echo "   wrote a STEP and an STL from the document"

step "Read, edit and snapshot a native board from the installed wheel"
"$VENV/bin/python" - <<'PYBOARD' || exit 1
from pathlib import Path
from PIL import Image
from cadgen.engine.api import snapshot
from cadgen.plot import plot_payload_bytes

board = Path("models/native.kicad_pcb").resolve()
board.write_text('''(kicad_pcb (version 20241229) (generator "pcbnew")
 (general (thickness 1.6)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
 (gr_rect (start 0 0) (end 40 30) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))
 (segment (start 5 15) (end 35 15) (width 0.5) (layer "F.Cu") (net 0)))''', encoding="utf-8")
first = plot_payload_bytes(board)
image = board.with_suffix(".png")
snapshot(board, image, width=160, height=120)
with Image.open(image) as picture:
    assert picture.size == (160, 120)
before = image.read_bytes()
board.write_text(board.read_text().replace("(width 0.5)", "(width 3)"), encoding="utf-8")
assert plot_payload_bytes(board) != first, "the native file edit must be read again"
snapshot(board, image, width=160, height=120)
assert image.read_bytes() != before, "the native file edit must reach the rendered picture"
print("   a native file edit reached the plot and the engine's PNG without KiCad or a browser")
PYBOARD

printf '\nInstalled-mode checks passed.\n'
