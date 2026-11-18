#!/usr/bin/env bash
# Exercise cad the way a user gets it: built into wheels (cad, and its aliases cad-server and cad-mcp),
# pip-installed together, run from a directory that is not this repo; installed as the uv tool the install
# command makes (`uv tool install cad`, the newest release uv is offered), and as a uv tool by the server's old name
# (`uv tool install cad-server`, which keeps the cad command); and installed the old way the updaters
# of 0.10.0 to 0.11.11 still bring a release (`uv pip install cad-server==<release>` into a venv of their own).
#
# Every other check in this repo runs against the source tree, where the repo root is on
# sys.path and the apps' builds sit beside the packages. None of that is true after
# `pip install cad`, so the failures this catches are exactly the ones no other
# check can: an asset left out of package-data, a module that resolves only because a sibling
# directory happened to be adjacent. Those all pass locally and break for the person who
# installed it.
#
# The scratch venv reuses the repo venv's heavy dependencies (OCP, build123d) rather than
# reinstalling half a gigabyte -- but the wheels' own packages must WIN over the repo's
# editable ones, or this would silently test the source tree again. See _link_repo_deps.
#
# Usage: scripts/test/test-installed.sh [--wheels DIR]
#   DIR holds cad's wheel and its aliases' (cad, cad_server, cad_mcp), as
#   scripts/release/check-wheel-contents.sh leaves them; without it they are built.
# The uv tool and the old way install the same wheels written again as a release no index holds, above PyPI's
# newest (scripts/test/real_computer.py stamp and publish): an index's release never stands in. They need uv and
# the network (the wheels' dependencies).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Shared resolution: the repo venv in a checkout, python3 otherwise. CI installs the CAD
# dependencies into the interpreter that setup-python provides and has no .venv at all, so
# hardcoding one here fails there and only there.
# shellcheck source=scripts/test/common.sh
source "$SCRIPT_DIR/common.sh"

# cad's command, and the one its cad-mcp alias keeps.
COMMAND=cad
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
export CAD_ENGINE_DIR="$WORK/engine" CAD_CACHE_DIR="$WORK/no-0.7-store"
cleanup() {
  # The server the venv's commands and the CAD app started, the uv tool's, and the old way's, if any.
  if [ -x "$VENV/bin/cad" ]; then
    "$VENV/bin/cad" server stop >/dev/null 2>&1 \
      || echo "warning: this run's server did not stop" >&2
  fi
  if [ -x "$WORK/tool-bin/cad" ]; then
    CAD_STATE_DIR="$WORK/tool-state" CAD_ENGINE_DIR="$WORK/tool-engine" "$WORK/tool-bin/cad" server stop >/dev/null 2>&1 || true
  fi
  if [ -x "$WORK/bridge/bin/python" ]; then
    CAD_STATE_DIR="$WORK/bridge-state" CAD_ENGINE_DIR="$WORK/bridge-engine" "$WORK/bridge/bin/python" -m cad_server.engine stop >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
# What the CAD app remembers (its library, release checks) stays in the throwaway directory too.
export CAD_STATE_DIR="$WORK/state"
# No version feed and no telemetry: nothing here asks the network but for the wheels' dependencies. The servers'
# pages on a free port of this run's, never the machine's 3245.
export CAD_API_URL="http://127.0.0.1:9" CAD_UPDATE_CHECK=0 DO_NOT_TRACK=1 CAD_TELEMETRY=0
CAD_ENGINE_DEFAULT_PORT="$("$PYTHON_BIN" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
export CAD_ENGINE_DEFAULT_PORT
unset CAD_INSTALLATION_VERSION CAD_VERSION
# No uv tool cad, unless a step installs one: a cad that is not the uv tool hands its server to an installed one
# (`cad mcp`), and a developer's own, in uv's real tool folder, is never this run's.
export UV_TOOL_DIR="$WORK/no-tools" UV_TOOL_BIN_DIR="$WORK/no-tool-bin"

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

if [ -z "$WHEELS" ]; then
  step "Build the wheels"
  "$REPO_ROOT/scripts/bundle/bundle.sh" >/dev/null
  for project in cad aliases/cad-server aliases/cad-mcp; do
    "$PYTHON_BIN" -m build --wheel --outdir "$DIST" "$REPO_ROOT/packages/$project" >"$WORK/build.log" 2>&1 \
      || { cat "$WORK/build.log" >&2; fail "the $project wheel's build"; }
  done
  WHEELS="$DIST"
else
  step "Use the supplied wheels"
fi
# cad's wheel and its two aliases': a wheel's name spells a distribution's hyphens as underscores.
installing=()
for distribution in cad cad_server cad_mcp; do
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
import cadgen.build123d
for package in (cad, cad_server, cad_mcp, cadgen):
    where = pathlib.Path(package.__file__).resolve()
    if "site-packages" not in where.parts:
        sys.exit(f"FAIL: imported {package.__name__} from {where}, not an installed wheel")
    print(f"   {package.__name__} at {where.parent}")
import cad.build123d
if cadgen.build123d is not cad.build123d or cadgen.model is not cad.model:
    sys.exit("FAIL: the cadgen alias is not the library's own modules and names")
# One distribution, cad: each package that reports a release reports cad's, never an alias's (cad_mcp, the
# transport inside cad, reports none of its own).
from importlib.metadata import version
releases = {cad.__version__, cad_server.__version__, version("cad")}
if len(releases) != 1:
    sys.exit(f"FAIL: cad and cad_server are not one release: {sorted(releases)}")
print(f"   one release: {releases.pop()}")
PY

step "import build123d is lazy from interpreter start: the library wheel's .pth is in site-packages"
scratch_sp="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
PTH="$scratch_sp/cad-lazy-kernel.pth"
[ -f "$PTH" ] || fail "cad-lazy-kernel.pth is not in $scratch_sp"
[ "$(cat "$PTH")" = "import cad._internal.lazy_kernel" ] || fail "cad-lazy-kernel.pth does not import the finder"
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

step "Every subcommand dispatches from an empty directory, and so does the cad-mcp alias's command"
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

# The same wheels as a release no index holds, for the installs through uv below.
RELEASE="$("$VENV/bin/python" -c 'import cad; print(cad.__version__)')"
STAMP="$("$PYTHON_BIN" "$REPO_ROOT/scripts/test/real_computer.py" stamp "$((9000 + $$ % 900))")" \
  || fail "the release to stamp the wheels with"
"$PYTHON_BIN" "$REPO_ROOT/scripts/test/real_computer.py" publish "$WHEELS" "$STAMP" "$WORK/stamped" >/dev/null \
  || fail "writing the wheels again as $STAMP"
UV=(uv)
command -v uv >/dev/null 2>&1 || UV=("$PYTHON_BIN" -m uv)

# What the install command does: `uv tool install --managed-python --python 3.14 cad`, no release named: uv installs
# the newest it is offered, which is the stamped wheels' (above PyPI's newest). uv's tool, its command and its Python
# in private folders; the tool's receipt names cad, which is what makes it a global install that updates itself.
step "The install command's uv tool: uv tool install cad gives the cad command, a global install"
export UV_TOOL_DIR="$WORK/tools" UV_TOOL_BIN_DIR="$WORK/tool-bin" UV_PYTHON_INSTALL_BIN=0 UV_NO_MODIFY_PATH=1
"${UV[@]}" tool install --quiet --managed-python --python 3.14 --find-links "$WORK/stamped" cad \
  || fail "uv tool install cad"
[ -x "$UV_TOOL_BIN_DIR/cad" ] || fail "uv tool install cad wrote no cad command in $UV_TOOL_BIN_DIR"
grep -q 'name = "cad"' "$UV_TOOL_DIR/cad/uv-receipt.toml" || fail "the tool's receipt does not name cad"
(
  cd "$EMPTY"
  export CAD_STATE_DIR="$WORK/tool-state" CAD_ENGINE_DIR="$WORK/tool-engine"
  [ "$("$UV_TOOL_BIN_DIR/cad" --version | head -n 1)" = "cad $STAMP" ] || fail "the tool's cad --version"
  # On by default for a global install, before anything is written; then turned on, as one line each.
  [ "$("$UV_TOOL_BIN_DIR/cad" update auto status)" = "update auto: on" ] || fail "cad update auto status, by default"
  "$UV_TOOL_BIN_DIR/cad" update auto on >"$WORK/update-auto.log" 2>&1 \
    || { cat "$WORK/update-auto.log" >&2; fail "cad update auto on, which only a global install may do"; }
  [ "$(cat "$WORK/update-auto.log")" = "update auto: on" ] || { cat "$WORK/update-auto.log" >&2; fail "update auto not on"; }
  # The plugin's switch, off by default; the install command turns it on.
  [ "$("$UV_TOOL_BIN_DIR/cad" plugin update auto status)" = "plugin update auto: off" ] \
    || fail "cad plugin update auto status, by default"
  [ "$("$UV_TOOL_BIN_DIR/cad" plugin update auto on)" = "plugin update auto: on" ] || fail "cad plugin update auto on"
  "$UV_TOOL_BIN_DIR/cad" doctor >"$WORK/tool-doctor.log" 2>&1 || true
  grep -q "update auto on, plugin update auto on; a global install by uv " "$WORK/tool-doctor.log" \
    || { cat "$WORK/tool-doctor.log" >&2; fail "cad doctor does not say both switches on and a global install by uv"; }
  # The venv's cad is no global install: it is refused, in one line.
  "$VENV/bin/cad" update auto on >"$WORK/refused.log" 2>&1 && fail "a cad that is not a global install switched update auto on"
  grep -q "not a global install" "$WORK/refused.log" || { cat "$WORK/refused.log" >&2; fail "the refusal does not say why"; }
) || exit 1
echo "   $UV_TOOL_BIN_DIR/cad: cad $STAMP, a global install by uv; cad update auto on accepted there, refused in a venv"
TOOL_DIR="$UV_TOOL_DIR"

# Until 0.11.11 cad-server was the server and carried the cad command, so a uv tool may be installed by that name. uv
# makes a tool only of the commands of the package it names: the alias keeps `cad`, or `uv tool install cad-server`
# fails ("No executables are provided") and `uv tool upgrade cad-server` takes the command away. Folders of its own.
step "A uv tool installed as cad-server: uv tool install cad-server gives the cad command"
(
  export UV_TOOL_DIR="$WORK/alias-tools" UV_TOOL_BIN_DIR="$WORK/alias-bin"
  "${UV[@]}" tool install --quiet --managed-python --python 3.14 --find-links "$WORK/stamped" "cad-server==$STAMP" \
    || fail "uv tool install cad-server"
  [ -x "$UV_TOOL_BIN_DIR/cad" ] || fail "uv tool install cad-server wrote no cad command in $UV_TOOL_BIN_DIR"
  cd "$EMPTY"
  [ "$(CAD_STATE_DIR="$WORK/alias-state" CAD_ENGINE_DIR="$WORK/alias-engine" "$UV_TOOL_BIN_DIR/cad" --version | head -n 1)" = "cad $STAMP" ] \
    || fail "cad --version of the uv tool cad-server"
) || exit 1
echo "   $WORK/alias-bin/cad: cad $STAMP"
# The steps after this one see no uv tool again: what they check is this install's.
export UV_TOOL_DIR="$WORK/no-tools" UV_TOOL_BIN_DIR="$WORK/no-tool-bin"

# What the updaters of 0.10.0 to 0.11.11, already on people's computers, do with a release and cannot be changed:
# they make an environment with uv (`uv venv`, then `uv pip install cad-server==<release>`), take it as complete once
# its `bin/cad` is there, and start its engine as `python -P -m cad_server._internal.engine_daemon`; a `cad` command
# of their layout runs `python -m cad_server._internal.proxy`. The alias cad-server must bring all of that through
# cad, on private state and engine folders.
step "A 0.10-0.11 updater's environment: uv pip install cad-server==<release> gives bin/cad and the modules it runs"
BRIDGE="$WORK/bridge"
BRIDGE_ENGINE="$WORK/bridge-engine"
"${UV[@]}" venv --quiet --no-project --python "$PYTHON_BIN" "$BRIDGE"
"${UV[@]}" pip install --quiet --python "$BRIDGE/bin/python" --find-links "$WORK/stamped" "cad-server==$STAMP" \
  || fail "uv pip install cad-server==$STAMP"
[ -x "$BRIDGE/bin/cad" ] || fail "uv pip install cad-server==$STAMP wrote no bin/cad"
"$BRIDGE/bin/python" - "$WORK/stamped" <<'PY' || exit 1
import glob, hashlib, os, sys, sysconfig, zipfile
site = sysconfig.get_paths()["purelib"]
wheel = glob.glob(os.path.join(sys.argv[1], "cad-[0-9]*.whl"))[0]
with zipfile.ZipFile(wheel) as archive:
    for name in (name for name in archive.namelist() if name.startswith("cad_server/") and name.endswith(".py")):
        path = os.path.join(site, *name.split("/"))
        if not os.path.isfile(path) or hashlib.sha256(open(path, "rb").read()).digest() != hashlib.sha256(archive.read(name)).digest():
            sys.exit(f"FAIL: cad-server's environment is not {os.path.basename(wheel)}: {name} differs")
PY
(cd "$EMPTY" && CAD_STATE_DIR="$WORK/bridge-state" "$BRIDGE/bin/python" -m cad_server._internal.proxy --version \
  >"$WORK/proxy.log" 2>&1) && fail "the proxy ran an installation where none is registered"
expected="$("$BRIDGE/bin/python" -c 'from cad_server._internal.proxy import NONE_INSTALLED; print(NONE_INSTALLED)')"
[ "$(cat "$WORK/proxy.log")" = "$expected" ] || { cat "$WORK/proxy.log" >&2; fail "python -m cad_server._internal.proxy"; }
(cd "$EMPTY" && CAD_STATE_DIR="$WORK/bridge-state" CAD_ENGINE_DIR="$BRIDGE_ENGINE" exec "$BRIDGE/bin/python" -P -m cad_server._internal.engine_daemon \
  >"$WORK/bridge-daemon.log" 2>&1) &
answered=0
for _ in $(seq 300); do
  if CAD_STATE_DIR="$WORK/bridge-state" CAD_ENGINE_DIR="$BRIDGE_ENGINE" "$BRIDGE/bin/cad" server status --json 2>/dev/null | grep -q '"version"'; then
    answered=1
    break
  fi
  kill -0 $! 2>/dev/null || break
  sleep 0.2
done
CAD_STATE_DIR="$WORK/bridge-state" CAD_ENGINE_DIR="$BRIDGE_ENGINE" "$BRIDGE/bin/cad" server stop >/dev/null 2>&1 || true
[ "$answered" -eq 1 ] || { cat "$WORK/bridge-daemon.log" >&2; fail "python -P -m cad_server._internal.engine_daemon never answered"; }
echo "   bin/cad, cad_server._internal.proxy and cad_server._internal.engine_daemon of cad $STAMP"

# The CAD app as an agent host starts it: the cad-mcp alias's command starts the server as `cad server start` does,
# then serves MCP on stdio. The host: the command, a folder, and the release whose server must serve the model.
step "Serve the CAD app over MCP through the shim, as an agent host starts it"
cat >"$WORK/host.py" <<'PY'
import json, os, subprocess, sys, threading

# Served cards through the development switch (CAD_MCP_PRESENTATION): a host that is not the Codex app is
# offered no tools, and cards show the page and its launch with no tab to wait for.
server = subprocess.Popen([sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                          env={**os.environ, "CAD_MCP_PRESENTATION": "inline"})
# Bounds a hang, not the work.
watchdog = threading.Timer(900, server.kill)
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


# As an MCP Apps host shown cards: it is served the page.
ui = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": ui, "clientInfo": {"name": "test-installed", "version": "0"}})
send({"method": "notifications/initialized"})
tools = {tool["name"]: tool for tool in call(2, "tools/list", {})["tools"]}
uri = tools["cad_show"]["_meta"]["ui"]["resourceUri"]
page = call(3, "resources/read", {"uri": uri})["contents"][0]["text"]
# The page is package data: a wheel without it serves a placeholder that says so.
if "missing from this install" in page or "<script" not in page:
    sys.exit(f"FAIL: {uri} is not the packaged CAD app")
# Showing a model mounts a view whose launch says which server serves it: the release expected.
mesh = os.path.join(sys.argv[2], "shown.stl")
with open(mesh, "w", encoding="utf-8") as handle:
    handle.write("solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n")
shown = call(4, "tools/call", {"name": "cad_show", "arguments": {"source": mesh}})
launch = (shown.get("structuredContent") or {}).get("launch") or {}
if shown.get("isError") or launch.get("version") != sys.argv[3] or launch.get("model") != os.path.abspath(mesh):
    sys.exit(f"FAIL: cad_show answered {shown}")
server.stdin.close()
if server.wait(30) != 0:
    sys.exit(f"FAIL: {os.path.basename(sys.argv[1])} exited {server.returncode} when the host closed its input")
watchdog.cancel()
print(f"   {len(tools)} tools; the app is {len(page) // 1024} KiB at {uri}")
PY
"$VENV/bin/python" "$WORK/host.py" "$VENV/bin/$SHIM_COMMAND" "$WORK" "$RELEASE" || exit 1
# With a uv tool cad installed, this shim, which is not it, serves from the tool's server: the tool's release. Its
# server stopped at once, in folders of its own.
(
  export UV_TOOL_DIR="$TOOL_DIR" UV_TOOL_BIN_DIR="$WORK/tool-bin" CAD_STATE_DIR="$WORK/tool-state" \
    CAD_ENGINE_DIR="$WORK/tool-engine"
  status=0
  "$VENV/bin/python" "$WORK/host.py" "$VENV/bin/$SHIM_COMMAND" "$WORK" "$STAMP" || status=$?
  "$WORK/tool-bin/cad" server stop >/dev/null 2>&1 || true
  exit "$status"
) || exit 1

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
COMMAND_PATH="$VENV/bin/$COMMAND"
"$COMMAND_PATH" server start >/dev/null || fail "$COMMAND server start"
# Running the script IS the build: no CLI verb takes its place. Run as a skill runs it: $COMMAND run.
"$COMMAND_PATH" run models/probe.py >"$WORK/build.log" 2>&1 \
  || { cat "$WORK/build.log" >&2; fail "$COMMAND run <model>.py"; }
for written in XBF/probe.xbf probe.step probe.stl; do
  [ -s "$EMPTY/models/$written" ] \
    || { cat "$WORK/build.log" >&2; fail "the model script did not write models/$written"; }
done
echo "   built an xbf and the STEP and STL it declares"

# The script above wrote the files the model DECLARES. This is the other half: an export of
# the document to a destination the command names.
step "Export the document"
"$COMMAND_PATH" xbf export models/XBF/probe.xbf models/exported.step models/exported.stl \
  >"$WORK/export.log" 2>&1 || { cat "$WORK/export.log" >&2; fail "$COMMAND xbf export"; }
for written in exported.step exported.stl; do
  [ -s "$EMPTY/models/$written" ] || { cat "$WORK/export.log" >&2; fail "export wrote no models/$written"; }
done
echo "   wrote a STEP and an STL from the document"

# A manufacturing check's measuring modules ship in the library's wheel and run in the engine's checks
# processes: one left out of the wheel, or one that resolves only beside the repo, fails here and nowhere else.
step "Check the part for each process"
for process in cnc sheet molding printing; do
  status=0
  "$COMMAND_PATH" step dfm models/probe.step --process "$process" >"$WORK/dfm-$process.log" 2>&1 || status=$?
  # A verdict either way (a cube is no sheet): 0 or 1. 2 is the command refused, 3 a check that did not run.
  case "$status" in
    0|1) ;;
    *) cat "$WORK/dfm-$process.log" >&2; fail "$COMMAND step dfm --process $process exited $status" ;;
  esac
done
echo "   a verdict for cnc, sheet, molding and printing"

printf '\nInstalled-mode checks passed.\n'
