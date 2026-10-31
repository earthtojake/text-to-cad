#!/usr/bin/env bash
set -euo pipefail

# Assert the five distributions' wheels carry what they must, and only their own packages: the library's,
# the server's and the shim's, and the aliases' (cadgen, text-to-cad), which carry nothing but the library
# at the release.
#
# The server ships JavaScript it serves (the CAD Viewer's built client, the CAD app page) and
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
# packages, and compare every runtime file's bytes with the bundled source. Reusing setuptools'
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

# Paths each wheel must carry. The Python a wheel must actually contain is listed beside the asset
# globs: a packages.find regression that dropped any of it would produce a wheel whose console script
# dies at import. This is the ONLY packaging gate the publish job runs -- test-installed.sh covers the
# same ground far better but runs in test.yml, not at publish.
LIBRARY_REQUIRED=(
  "cad/__init__.py"
  # The library's earlier import name, an alias of it.
  "cadgen/__init__.py"
  # `import build123d` made lazy at interpreter start: the finder, and the .pth at the root of
  # site-packages that installs it.
  "cad/_internal/lazy_kernel.py"
  "texttocad-lazy-kernel.pth"
  # The robot validators' library: a packaging regression here would ship a server whose
  # `urdf validate` cannot import.
  "cad/urdf_source.py"
  "cad/srdf_validation.py"
  "cad/findings.py"
  # The engine's library half: the worker every build runs in, and the client every command reaches
  # the server by.
  "cad/engine/__init__.py"
  "cad/engine/worker.py"
  "cad/engine/client.py"
  "cad/engine/places.py"
  # The engine's data: the page `serve` shows a document in and the environment image its look
  # lights the display modes with.
  "cad/engine/page/index.html"
  "cad/engine/page/viewer.js"
  "cad/engine/render/studio.hdr"
)
SERVER_REQUIRED=(
  "cad_server/__init__.py"
  "cad_server/assets.py"
  "cad_server/cli/__init__.py"
  "cad_server/cli/viewer.py"
  "cad_server/cli/urdf_validate.py"
  "cad_server/viewer/__init__.py"
  "cad_server/viewer/__main__.py"
  "cad_server/viewer/main.py"
  "cad_server/viewer/documents.py"
  "cad_server/viewer/collation.json"
  # The engine's server half: its daemon and the commands. Without the daemon the server starts no
  # engine, and every build fails.
  "cad_server/engine/daemon.py"
  "cad_server/engine/cli.py"
  "cad_server/_internal/engine_daemon.py"
  # Its README: the mechanisms the package's laws name.
  "cad_server/engine/README.md"
  "cad_server/_runtime/viewer/index.html"
  # Each page's third-party notice, written by its build: the wheel redistributes what they inline.
  "cad_server/_runtime/viewer/THIRD_PARTY_LICENSES.txt"
  # CAD in an agent host: the server's MCP endpoint and the one page it serves.
  "cad_server/mcp/server.py"
  "cad_server/mcp/tunnel.py"
  "cad_server/_runtime/mcp/shell.html"
  "cad_server/_runtime/mcp/app.js"
  "cad_server/_runtime/mcp/THIRD_PARTY_LICENSES.txt"
)
SHIM_REQUIRED=(
  # The stdio transport an agent app starts: the standard library alone.
  "cad_mcp/__init__.py"
  "cad_mcp/shim.py"
  "cad_mcp/engine.py"
  "cad_mcp/protocol.py"
)

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
BUILD_SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/wheel-build.XXXXXX")"
trap 'rm -rf "$BUILD_SCRATCH"' EXIT

# check PROJECT DISTRIBUTION TOP REQUIRED...: build packages/PROJECT's wheel, and hold it to the paths it
# must carry and to TOP, the top-level entries it may hold beside its dist-info (its packages, its .pth;
# none for an alias).
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
}

# An alias, packages/aliases/PROJECT: its dist-info alone, and the library at the release (a project that
# declares the earlier name gets the library it names).
check_alias() {
  local project="$1" distribution="$2"
  check "aliases/$project" "$distribution" ""
  "$PYTHON_BIN" - "$wheel" "$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")" <<'PY'
import sys, zipfile

wheel, version = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(wheel) as archive:
    metadata = [archive.read(name).decode() for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
requires = [line for text in metadata for line in text.splitlines() if line.startswith("Requires-Dist:")]
if requires != [f"Requires-Dist: texttocad=={version}"]:
    sys.exit(f"{wheel} requires {requires or 'nothing'}, not the library at the release (texttocad=={version}) alone")
PY
}

check texttocad texttocad "cad|cadgen|texttocad-lazy-kernel\.pth" "${LIBRARY_REQUIRED[@]}"
check texttocad-mcp texttocad_mcp "cad_mcp" "${SHIM_REQUIRED[@]}"
check_alias cadgen cadgen
check_alias text-to-cad text_to_cad
# The server's last: the runtime checks below read its wheel and listing.
check texttocad-server texttocad_server "cad_server" "${SERVER_REQUIRED[@]}"

# The server's runtime. A nested-glob failure usually loses MANY files at once rather than one, so
# report the count too: it distinguishes "one file moved" from "package-data is not matching".
runtime_count="$(grep -c '^cad_server/_runtime/' "$listing" || true)"

# The runtime is exactly the stages the bundler builds: an entry beside them (a folder a retired
# stage left in a checkout, which package-data ships whole) is a file the wheel carries that
# nothing builds, and the byte comparison below would pass it, since it is in the source too.
expected_runtime="$("$REPO_ROOT/scripts/bundle/cadgen-runtime.sh" --print-outputs | sed 's|.*/||' | sort -u)"
shipped_runtime="$(sed -n 's|^cad_server/_runtime/\([^/]*\).*|\1|p' "$listing" | sort -u)"
if [ "$shipped_runtime" != "$expected_runtime" ]; then
  echo "The server wheel's cad_server/_runtime holds $(echo $shipped_runtime); the bundler builds $(echo $expected_runtime)." >&2
  echo "Rebuild it with scripts/bundle/bundle.sh, which removes what no stage builds." >&2
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/wheel_contents.py" verify "$wheel" "$REPO_ROOT/packages/texttocad-server"
echo "The five wheels carry their own packages (the aliases none, only the library at the release); the server's carries its runtime ($runtime_count entries under cad_server/_runtime)."
if [ "$KEEP_WHEEL" != "1" ]; then
  rm -rf "$OUT_DIR"
fi
