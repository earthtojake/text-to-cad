#!/usr/bin/env bash
set -euo pipefail

# Assert the four projects' wheels carry what they must, and only their own packages: cad's (the library,
# the server and the shim), and its aliases' (cad-server, cad-mcp, cadgen), which carry nothing but cad at
# the release and the commands each shipped until 0.11.11 (cad-server's `cad`, cad-mcp's `cad-mcp`).
#
# The server ships JavaScript it serves (the viewer's built client, the CAD app page) and
# non-Python data it reads (collation.json); the library ships the page `serve` shows a document
# in and the environment image its look lights with.
# Those arrive through `[tool.setuptools.package-data]`, which is exactly the kind of
# declaration that fails QUIETLY: a glob that does not match nested files produces a
# wheel that imports fine, passes every Python test, and then cannot serve a Viewer or
# the CAD app on a user's machine. The repo has already been bitten by the
# same shape of bug in JS bundling (an entry tree-shaken to a 20-byte shebang, exit
# code 0).
#
# So: build each in clean scratch, require the paths, keep each wheel to its own top-level
# packages, and compare every runtime file's bytes with the bundled source. The release builds each wheel
# from its sdist (`python -m build`), so each is built that way too and must hold exactly the files of the
# wheel built from source: a file the sdist leaves out (the .pth, the runtime) ships missing otherwise. Reusing setuptools'
# build/lib can retain obsolete hashed viewer chunks even after the source bundle removed them.
# The viewer client is NOT committed (scripts/bundle/cadgen-runtime.sh --viewer writes it
# right before the build), so this is the only gate proving it made the wheel.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${CAD_WHEEL_OUT_DIR:-$REPO_ROOT/tmp/wheel-check}"
KEEP_WHEEL="${CAD_KEEP_WHEEL:-0}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  elif [ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
  else
    PYTHON_BIN="python3"
  fi
fi

# Paths cad's wheel must carry. The Python a wheel must actually contain is listed beside the asset
# globs: a packages.find regression that dropped any of it would produce a wheel whose console script
# dies at import. This is the ONLY packaging gate the publish job runs -- test-installed.sh covers the
# same ground far better but runs in test.yml, not at publish.
REQUIRED=(
  "cad/__init__.py"
  # The library's earlier import name, an alias of it.
  "cadgen/__init__.py"
  # `import build123d` made lazy at interpreter start: the finder, and the .pth at the root of
  # site-packages that installs it.
  "cad/_internal/lazy_kernel.py"
  "cad-lazy-kernel.pth"
  # The document types and their registry, and the robot checks' library: a packaging regression
  # here would ship a server whose `cad urdf validate` cannot import.
  "cad/registry.py"
  "cad/_internal/document_type.py"
  "cad/_internal/aliases.py"
  "cad/_internal/programs.py"
  "cad/urdf/_source.py"
  "cad/srdf/_validation.py"
  "cad/_internal/findings.py"
  "cad/kicad_pcb/__init__.py"
  "cad/kicad/_program.py"
  # The blender integration: what a render script imports (cad.blender.load), in place of a helper a skill shipped.
  "cad/blender/__init__.py"
  "cad/blender/_scene.py"
  # The engine's library half: the worker every build runs in, and the client every command reaches
  # the server by.
  "cad/engine/__init__.py"
  "cad/engine/worker.py"
  "cad/engine/client.py"
  "cad/engine/places.py"
  # The engine's data: the environment image its look lights the display modes with.
  "cad/engine/render/studio.hdr"
  # The server, and the `cad` command's code.
  "cad_server/__init__.py"
  "cad_server/assets.py"
  "cad_server/cli/__init__.py"
  "cad_server/cli/viewer.py"
  "cad_server/cli/urdf.py"
  "cad_server/cli/document_types.py"
  "cad_server/viewer/__init__.py"
  "cad_server/viewer/__main__.py"
  "cad_server/viewer/main.py"
  "cad_server/viewer/documents.py"
  "cad_server/viewer/collation.json"
  # The engine's server half: its daemon and the commands. Without the daemon the server starts no
  # engine, and every build fails.
  "cad_server/engine/daemon.py"
  "cad_server/engine/cli.py"
  "cad_server/cli/server.py"
  "cad_server/cli/cache.py"
  "cad_server/_internal/engine_daemon.py"
  # cad's own update: the switches and their command, and the helper, whose SOURCE the update reads and runs
  # with another Python (auto_update.HELPER): without the file no cad ever updates itself.
  "cad_server/_internal/auto_update.py"
  "cad_server/_internal/auto_update_helper.py"
  "cad_server/cli/auto_update.py"
  # The install command as the bridge's install mode runs it, once (`install_script`); and `cad plugin`, its command:
  # `cad plugin install`, which the server of a newer cad runs where `cad plugin update auto` is on (`plugin_catch_up`,
  # the rule it runs by), and which the install command hands the agent apps to.
  "cad_server/_internal/install_script.py"
  "cad_server/_internal/plugin_catch_up.py"
  "cad_server/cli/plugin.py"
  # What those two run: the plugin in the agent apps, every module of it, each imported before a run begins. A
  # wheel without one is a cad whose `cad plugin install` dies at import, and with it every run of the install
  # command, which gets PyPI's newest cad and hands over to it.
  "cad_server/plugin/__init__.py"
  "cad_server/plugin/computer.py"
  "cad_server/plugin/source.py"
  "cad_server/plugin/apps.py"
  "cad_server/plugin/terminal.py"
  "cad_server/plugin/run.py"
  # What the updaters and launchers of 0.10.0 to 0.11.11 run in a release they bring: `cad setup
  # --engine-update`, the records their switch starts a server by, and the module their `cad` command runs.
  "cad_server/cli/setup.py"
  "cad_server/_internal/installations.py"
  "cad_server/_internal/proxy.py"
  # The script Open in starts a person's Blender with on a GLB or an STL (apps.BLENDER_SCRIPT).
  "cad_server/_internal/open_in_blender.py"
  # Its README and the pages it indexes: the mechanisms the package's laws name. Two pages stand for the folder,
  # which the package data takes whole.
  "cad_server/engine/README.md"
  "cad_server/engine/docs/architecture.md"
  "cad_server/engine/docs/wire-format.md"
  "cad_server/_runtime/viewer/index.html"
  # Each page's third-party notice, written by its build: the wheel redistributes what they inline.
  "cad_server/_runtime/viewer/THIRD_PARTY_LICENSES.txt"
  # CAD in an agent host: the server's MCP endpoint and the one page it serves.
  "cad_server/mcp/server.py"
  "cad_server/mcp/tunnel.py"
  "cad_server/_runtime/mcp/shell.html"
  "cad_server/_runtime/mcp/app.js"
  "cad_server/_runtime/mcp/THIRD_PARTY_LICENSES.txt"
  # The stdio transport an agent app starts: the standard library alone.
  "cad_mcp/__init__.py"
  "cad_mcp/shim.py"
  "cad_mcp/protocol.py"
)

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
BUILD_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/wheel-build.XXXXXX")"
trap 'rm -rf "$BUILD_SCRATCH"' EXIT

# check PROJECT DISTRIBUTION TOP REQUIRED...: build packages/PROJECT's wheel, and hold it to the paths it
# must carry and to TOP, the top-level entries it may hold beside its dist-info (its packages, its .pth;
# none for an alias); then build it as the release does, its sdist and a wheel from that, which must hold
# the same files.
check() {
  local project="$1" distribution="$2" top="$3"
  local label="${project//\//-}"
  shift 3
  echo "Building the $project wheel for its content check..."
  "$PYTHON_BIN" "$SCRIPT_DIR/wheel_contents.py" stage "$REPO_ROOT/packages/$project" "$BUILD_SCRATCH/$project"
  "$PYTHON_BIN" -m build --wheel --outdir "$OUT_DIR" "$BUILD_SCRATCH/$project" >"$OUT_DIR/$label-build.log" 2>&1 || {
    echo "The $project wheel's build failed:" >&2
    tail -40 "$OUT_DIR/$label-build.log" >&2
    echo "" >&2
    echo "If this is a missing build backend, install it: $PYTHON_BIN -m pip install build" >&2
    exit 1
  }
  local wheels=("$OUT_DIR/$distribution"-[0-9]*.whl)
  if [ "${#wheels[@]}" -ne 1 ] || [ ! -f "${wheels[0]}" ]; then
    echo "No single $distribution wheel in $OUT_DIR" >&2
    exit 1
  fi
  wheel="${wheels[0]}"
  echo "Built $(basename "$wheel")"

  listing="$OUT_DIR/$label-contents.txt"
  "$PYTHON_BIN" -c "
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    sys.stdout.write('\n'.join(sorted(zf.namelist())) + '\n')
" "$wheel" > "$listing"

  local path missing=""
  for path in "$@"; do
    if ! grep -Fxq "$path" "$listing"; then
      missing="$missing  - $path"$'\n'
    fi
  done
  if [ -n "$missing" ]; then
    echo "" >&2
    echo "The $project wheel is missing required files:" >&2
    printf '%s' "$missing" >&2
    echo "Wheel listing: $listing" >&2
    echo "Check [tool.setuptools.packages.find] and [tool.setuptools.package-data] in packages/$project/pyproject.toml." >&2
    exit 1
  fi

  # Its own packages alone: a package another distribution ships, in this one too, is two copies of one
  # module on a user's path.
  local strays own="${distribution}-[^/]*\.dist-info"
  [ -z "$top" ] || own="$top|$own"
  strays="$(sed 's|/.*||' "$listing" | sort -u | grep -Ev "^(${own})$" || true)"
  if [ -n "$strays" ]; then
    echo "The $project wheel carries what is not its own: $(echo $strays)" >&2
    exit 1
  fi

  # The engine's test goldens (pictures and payloads its tests compare against) are the tests'
  # own and never ship: a wheel that carries one carries a fixture a user never reads.
  local shipped_goldens
  shipped_goldens="$(grep -E '^cad(_server)?/engine/.*(golden|\.png$)' "$listing" || true)"
  if [ -n "$shipped_goldens" ]; then
    echo "The $project wheel ships engine test goldens:" >&2
    printf '%s\n' "$shipped_goldens" >&2
    exit 1
  fi

  # The release's way: the sdist, and the wheel built from it (`python -m build`, no flag).
  local released="$BUILD_SCRATCH/released-$label"
  "$PYTHON_BIN" -m build --outdir "$released" "$BUILD_SCRATCH/$project" >"$OUT_DIR/$label-sdist-build.log" 2>&1 || {
    echo "The $project sdist, or the wheel built from it, failed:" >&2
    tail -40 "$OUT_DIR/$label-sdist-build.log" >&2
    exit 1
  }
  local from_sdist=("$released/$distribution"-[0-9]*.whl)
  "$PYTHON_BIN" -c "
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    sys.stdout.write('\n'.join(sorted(zf.namelist())) + '\n')
" "${from_sdist[0]}" > "$OUT_DIR/$label-sdist-contents.txt"
  if ! diff -u "$listing" "$OUT_DIR/$label-sdist-contents.txt" >&2; then
    echo "The $project wheel built from its sdist differs from the one built from source (above):" >&2
    echo "the sdist leaves out what the wheel needs; check MANIFEST.in and the package data." >&2
    exit 1
  fi
}

# An alias, packages/aliases/PROJECT: its dist-info alone, and cad at the release (a project that declares
# the alias gets cad), its extras cad's `build123d` extra under each name it keeps (`build123d`, and for
# cadgen `kernel` too, its 0.8 spelling), and the commands it shipped until 0.11.11, each the entry point cad
# runs (cad-server's `cad`, which cad declares too, the same script; cad-mcp's `cad-mcp`): uv makes a tool only of
# the commands of the package it names, so a uv tool installed as cad-server keeps its `cad` at an upgrade.
check_alias() {
  local project="$1" distribution="$2" extras="$3" scripts="$4"
  check "aliases/$project" "$distribution" ""
  "$PYTHON_BIN" - "$wheel" "$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")" "$extras" "$scripts" <<'PY'
import configparser, sys, zipfile

wheel, version, extras, scripts = sys.argv[1], sys.argv[2], sys.argv[3].split(), sys.argv[4].split()
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    metadata = [archive.read(name).decode() for name in names if name.endswith(".dist-info/METADATA")]
    points = [archive.read(name).decode() for name in names if name.endswith(".dist-info/entry_points.txt")]
requires = [line for text in metadata for line in text.splitlines() if line.startswith("Requires-Dist:")]
wanted = [f"Requires-Dist: cad=={version}",
          *(f'Requires-Dist: cad[build123d]=={version}; extra == "{extra}"' for extra in extras)]
if requires != wanted:
    sys.exit(f"{wheel} requires {requires or 'nothing'}, not cad at the release and its build123d extra "
             f"({wanted}) alone")
parser = configparser.ConfigParser(delimiters=("=",))
parser.optionxform = str
for text in points:
    parser.read_string(text)
declared = dict(parser["console_scripts"]) if parser.has_section("console_scripts") else {}
wanted = dict(script.split("=", 1) for script in scripts)
if {name: target.strip() for name, target in declared.items()} != wanted:
    sys.exit(f"{wheel} declares the commands {declared}, not {wanted}")
PY
}

check_alias cad-server cad_server "" "cad=cad_server.cli:main"
check_alias cad-mcp cad_mcp "" "cad-mcp=cad_mcp.shim:main"
check_alias cadgen cadgen "build123d kernel" ""
# cad's last: the runtime checks below read its wheel and listing.
check cad cad "cad|cadgen|cad_server|cad_mcp|cad-lazy-kernel\.pth" "${REQUIRED[@]}"

# The server's runtime. A nested-glob failure usually loses MANY files at once rather than one, so
# report the count too: it distinguishes "one file moved" from "package-data is not matching".
runtime_count="$(grep -c '^cad_server/_runtime/' "$listing" || true)"

# The runtime is exactly the stages the bundler builds: an entry beside them (a folder a retired
# stage left in a checkout, which package-data ships whole) is a file the wheel carries that
# nothing builds, and the byte comparison below would pass it, since it is in the source too.
expected_runtime="$("$REPO_ROOT/scripts/bundle/cadgen-runtime.sh" --print-outputs | sed 's|.*/||' | sort -u)"
shipped_runtime="$(sed -n 's|^cad_server/_runtime/\([^/]*\).*|\1|p' "$listing" | sort -u)"
if [ "$shipped_runtime" != "$expected_runtime" ]; then
  echo "The cad wheel's cad_server/_runtime holds $(echo $shipped_runtime); the bundler builds $(echo $expected_runtime)." >&2
  echo "Rebuild it with scripts/bundle/bundle.sh, which removes what no stage builds." >&2
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/wheel_contents.py" verify "$wheel" "$REPO_ROOT/packages/cad"
echo "The four wheels carry their own packages (the aliases none, only cad at the release), each the same built from its sdist; cad's carries its runtime ($runtime_count entries under cad_server/_runtime)."
if [ "$KEEP_WHEEL" != "1" ]; then
  rm -rf "$OUT_DIR"
fi
