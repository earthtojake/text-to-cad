#!/usr/bin/env bash
# Exercise the three distributions the way a user gets them: built into wheels, pip-installed
# together, run from a directory that is not this repo.
#
# Every other check in this repo runs against the source tree, where the repo root is on
# sys.path and the apps' builds sit beside the packages. None of that is true after
# `pip install texttocad-server`, so the failures this catches are exactly the ones no other
# check can: an asset left out of package-data, a module that resolves only because a sibling
# directory happened to be adjacent. Those all pass locally and break for the person who
# installed it.
#
# The scratch venv reuses the repo venv's heavy dependencies (OCP, build123d) rather than
# reinstalling half a gigabyte -- but the wheels' own packages must WIN over the repo's
# editable ones, or this would silently test the source tree again. See _link_repo_deps.
#
# Usage: scripts/test/test-installed.sh [--wheels DIR]
#   DIR holds the library's, the server's and the shim's wheels (texttocad, texttocad_server,
#   texttocad_mcp), as scripts/release/check-wheel-contents.sh leaves them; without it they are built.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Shared resolution: the repo venv in a checkout, python3 otherwise. CI installs the CAD
# dependencies into the interpreter that setup-python provides and has no .venv at all, so
# hardcoding one here fails there and only there.
# shellcheck source=scripts/test/common.sh
source "$SCRIPT_DIR/common.sh"

# The server's command, and the shim's.
COMMAND=cadgen
SHIM_COMMAND=cad-mcp
USAGE="Usage: scripts/test/test-installed.sh [--wheels DIR]"

WHEELS=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --wheels)
      [ "$#" -ge 2 ] || { echo "--wheels requires a folder" >&2; exit 2; }
      [ -d "$2" ] || { echo "no such folder: $2" >&2; exit 2; }
      WHEELS="$(cd "$2" && pwd -P)"
      shift 2
      ;;
    -h|--help)
      echo "$USAGE"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "$USAGE" >&2
      exit 2
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [ ! -x "$PYTHON_BIN" ]; then
  echo "No usable Python ($PYTHON_BIN). Set PYTHON_BIN to an interpreter with the CAD deps." >&2
  exit 1
fi

# The wheels are installed with --no-deps and reuse this interpreter's heavy packages, so it
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
  # The installed server stops the daemon its builds started.
  if [ -x "$VENV/bin/python" ]; then
    "$VENV/bin/python" -m cad_server.engine stop >/dev/null 2>&1 \
      || echo "warning: this run's engine daemon did not stop; it goes once idle" >&2
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
# What the CAD app remembers (its library, release checks) stays in the throwaway directory too.
export CADGEN_STATE_DIR="$WORK/state"
# And the command the installation writes for the skills: never this machine's ~/.local/bin.
export CADGEN_LAUNCHER_DIR="$WORK/bin"
unset CADGEN_INSTALLATION_VERSION CADGEN_VERSION

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

if [ -z "$WHEELS" ]; then
  step "Build the wheels"
  "$REPO_ROOT/scripts/bundle/bundle.sh" >/dev/null
  for project in texttocad texttocad-server texttocad-mcp; do
    "$PYTHON_BIN" -m build --wheel --outdir "$DIST" "$REPO_ROOT/packages/$project" >"$WORK/build.log" 2>&1 \
      || { cat "$WORK/build.log" >&2; fail "the $project wheel's build"; }
  done
  WHEELS="$DIST"
else
  step "Use the supplied wheels"
fi
# One wheel of each distribution: a wheel's name spells a distribution's hyphens as underscores.
installing=()
for distribution in texttocad texttocad_server texttocad_mcp; do
  found=("$WHEELS/$distribution"-[0-9]*.whl)
  [ "${#found[@]}" -eq 1 ] && [ -f "${found[0]}" ] || fail "expected one $distribution wheel in $WHEELS"
  installing+=("${found[0]}")
  echo "   $(basename "${found[0]}")"
done

step "Install them together into a scratch venv"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --no-deps "${installing[@]}"

_link_repo_deps() {
  # Expose the repo venv's site-packages for OCP/build123d/etc WITHOUT letting its editable
  # packages win. A plain path line in a .pth is sys.path.append, so it lands AFTER this
  # venv's own site-packages (where the wheels are) and its .pth files are not processed --
  # which is what keeps the editable packages out.
  local repo_sp scratch_sp
  repo_sp="$("$PYTHON_BIN" -c 'import site; print(site.getsitepackages()[0])')"
  scratch_sp="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "$repo_sp" >"$scratch_sp/zz-repo-deps.pth"
}
_link_repo_deps

step "The installed packages are the WHEELS', not the checkout's; cadgen is the library's alias"
"$VENV/bin/python" - <<'PY' || exit 1
import pathlib, sys
import cad, cad_mcp, cad_server, cadgen
import cadgen.ap242
for package in (cad, cad_server, cad_mcp, cadgen):
    where = pathlib.Path(package.__file__).resolve()
    if "site-packages" not in where.parts:
        sys.exit(f"FAIL: imported {package.__name__} from {where}, not an installed wheel")
    print(f"   {package.__name__} at {where.parent}")
import cad.ap242
if cadgen.ap242 is not cad.ap242 or cadgen.model is not cad.model:
    sys.exit("FAIL: the cadgen alias is not the library's own modules and names")
releases = {cad.__version__, cad_server.__version__, cad_mcp.__version__}
if len(releases) != 1:
    sys.exit(f"FAIL: the three wheels are not one release: {sorted(releases)}")
print(f"   one release: {releases.pop()}")
PY

step "import build123d is lazy from interpreter start: the library wheel's .pth is in site-packages"
scratch_sp="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
PTH="$scratch_sp/texttocad-lazy-kernel.pth"
[ -f "$PTH" ] || fail "texttocad-lazy-kernel.pth is not in $scratch_sp"
[ "$(cat "$PTH")" = "import cad._internal.lazy_kernel" ] || fail "texttocad-lazy-kernel.pth does not import the finder"
# Bound, not loaded: the kernel is untouched until an attribute is read from it.
lazy="$(cd "$EMPTY" && "$VENV/bin/python" -c "import build123d as bd; import sys; print('OCP' in sys.modules)")"
[ "$lazy" = "False" ] || fail "import build123d loaded the kernel ($lazy)"
loaded="$(cd "$EMPTY" && "$VENV/bin/python" -c "import build123d as bd, sys; bd.Box(1, 1, 1); print('OCP' in sys.modules)")"
[ "$loaded" = "True" ] || fail "the first attribute of build123d did not load the kernel ($loaded)"
echo "   $PTH"

step "Assets resolve to the packaged runtime"
"$VENV/bin/python" - <<'PY' || exit 1
import sys
from cad_server.assets import viewer_dist_dir
from cad_server.mcp.ui import app_dir
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

step "Every subcommand dispatches from an empty directory, and so does the shim's command"
cd "$EMPTY"
"$VENV/bin/$COMMAND" --help >/dev/null || fail "$COMMAND --help"
"$VENV/bin/$SHIM_COMMAND" --help >/dev/null || fail "$SHIM_COMMAND --help"
echo "   $SHIM_COMMAND"
# The list comes from the INSTALLED registry, not from a copy of it here: a
# hand-written list goes stale silently the first time a command is renamed, and
# then this step passes while checking commands that no longer exist.
"$VENV/bin/python" -c 'from cad_server.cli import _COMMANDS; print("\n".join(sorted(_COMMANDS)))' \
  >"$WORK/commands.txt" || fail "read the installed command registry"
[ -s "$WORK/commands.txt" ] || fail "the installed command registry is empty"
while read -r command; do
  [ -n "$command" ] || continue
  # shellcheck disable=SC2086
  "$VENV/bin/$COMMAND" $command --help >/dev/null 2>&1 || fail "$COMMAND $command --help"
  echo "   $COMMAND $command"
done <"$WORK/commands.txt"

step "Serve the CAD app over MCP through the shim, as an agent host starts it"
"$VENV/bin/python" - "$VENV/bin/$SHIM_COMMAND" "$WORK" <<'PY' || exit 1
import json, os, subprocess, sys, threading
import cad_server

server = subprocess.Popen([sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
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
    sys.exit(f"FAIL: {os.path.basename(sys.argv[1])} exited during {method}")


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
# Showing a model mounts a view whose launch says which server serves it: this install's.
mesh = os.path.join(sys.argv[2], "shown.stl")
with open(mesh, "w", encoding="utf-8") as handle:
    handle.write("solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n")
shown = call(4, "tools/call", {"name": "cad_show", "arguments": {"source": mesh}})
launch = (shown.get("structuredContent") or {}).get("launch") or {}
if shown.get("isError") or launch.get("version") != cad_server.__version__ or launch.get("model") != os.path.abspath(mesh):
    sys.exit(f"FAIL: cad_show answered {shown}")
server.stdin.close()
if server.wait(30) != 0:
    sys.exit(f"FAIL: {os.path.basename(sys.argv[1])} exited {server.returncode} when the host closed its input")
watchdog.cancel()
print(f"   {len(tools)} tools; the app is {len(page) // 1024} KiB at {uri}")
PY

step "Starting the CAD app registered the server and wrote the $COMMAND command the skills run"
VERSION_INSTALLED="$("$VENV/bin/python" -c 'import cad_server; print(cad_server.__version__)')"
RECORD="$CADGEN_STATE_DIR/installations/$VERSION_INSTALLED.json"
PROXY="$CADGEN_LAUNCHER_DIR/$COMMAND"
[ -f "$RECORD" ] || fail "no record of $VERSION_INSTALLED in $CADGEN_STATE_DIR/installations"
# Compared resolved: the temporary folder's path may be spelled through a symlink (/var, /private/var).
"$VENV/bin/python" - "$RECORD" "$VENV" <<'PY' || exit 1
import json, os, sys
record = json.load(open(sys.argv[1], encoding="utf-8"))
if os.path.realpath(record["prefix"]) != os.path.realpath(sys.argv[2]):
    sys.exit(f"FAIL: {sys.argv[1]} names {record['prefix']}, not {sys.argv[2]}")
PY
[ -x "$PROXY" ] && grep -q "^# $COMMAND proxy: " "$PROXY" || fail "$PROXY is not the $COMMAND command"
same() { "$VENV/bin/python" -c 'import os, sys; sys.exit(os.path.realpath(sys.argv[1]) != os.path.realpath(sys.argv[2]))' "$1" "$2"; }
same "$("$PROXY" "+$VERSION_INSTALLED" run -c 'import sys; print(sys.prefix)')" "$VENV" \
  || fail "$COMMAND +$VERSION_INSTALLED run does not run the installation's python"
# The first installation on this machine is its current one, and the command runs it whatever release a
# skill names: nothing on the machine compares versions.
[ "$(cat "$CADGEN_STATE_DIR/installations/current")" = "$VERSION_INSTALLED" ] \
  || fail "$VERSION_INSTALLED is not the current installation"
same "$("$PROXY" +0.0.1 run -c 'import sys; print(sys.prefix)')" "$VENV" \
  || fail "$COMMAND +0.0.1 run does not run the current installation"
echo "   $(basename "$RECORD"), current, and $PROXY"

step "Build a real model with no repo in sight"
mkdir -p "$EMPTY/models"
cat >"$EMPTY/models/probe.py" <<'PY'
# A model script explicitly calls its model, writing what its decorators declare. Deliberately the simplest one that
# exists: this checks that an installed server can build at all, not that it models anything interesting.
from cad.engine import step, stl, xbf
import build123d as bd


@xbf("XBF/probe.xbf")
@step("probe.step")
@stl("probe.stl")
def probe():
    return bd.Box(10, 10, 10)


if __name__ == "__main__":
    probe()
PY
# Running the script IS the build: no CLI verb takes its place. Run as a skill runs it: $COMMAND +V run.
"$PROXY" "+$VERSION_INSTALLED" run models/probe.py >"$WORK/build.log" 2>&1 \
  || { cat "$WORK/build.log" >&2; fail "$COMMAND +$VERSION_INSTALLED run <model>.py"; }
for written in XBF/probe.xbf probe.step probe.stl; do
  [ -s "$EMPTY/models/$written" ] \
    || { cat "$WORK/build.log" >&2; fail "the model script did not write models/$written"; }
done
echo "   built an xbf and the STEP and STL it declares"

# The script above wrote the files the model DECLARES. This is the other half: an export of
# the document to a destination the command names.
step "Export the document"
"$PROXY" "+$VERSION_INSTALLED" export models/XBF/probe.xbf models/exported.step models/exported.stl \
  >"$WORK/export.log" 2>&1 || { cat "$WORK/export.log" >&2; fail "$COMMAND +$VERSION_INSTALLED export"; }
for written in exported.step exported.stl; do
  [ -s "$EMPTY/models/$written" ] || { cat "$WORK/export.log" >&2; fail "export wrote no models/$written"; }
done
echo "   wrote a STEP and an STL from the document"

printf '\nInstalled-mode checks passed.\n'
