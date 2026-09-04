#!/usr/bin/env bash
set -euo pipefail

# Assert the cadgen wheel actually contains its runtime assets.
#
# cadgen ships JavaScript it executes (Node builders, the snapshot browser bundle, the
# CAD Viewer's built client) and non-Python data its server reads (collation.json).
# Those arrive through `[tool.setuptools.package-data]`, which is exactly the kind of
# declaration that fails QUIETLY: a glob that does not match nested files produces a
# wheel that imports fine, passes every Python test, and then cannot build a DXF preview
# -- or serve a Viewer -- on a user's machine. The repo has already been bitten by the
# same shape of bug in JS bundling (an entry tree-shaken to a 20-byte shebang, exit
# code 0).
#
# So: build the wheel, list it, and require the paths to be present. The viewer client
# is NOT committed (scripts/bundle/cadgen-runtime.sh --viewer writes it
# right before the build), so this is the only gate proving it made the wheel.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PACKAGE_DIR="$REPO_ROOT/packages/cadgen"
OUT_DIR="${CADGEN_WHEEL_OUT_DIR:-$REPO_ROOT/tmp/cadgen-wheel-check}"
KEEP_WHEEL="${CADGEN_KEEP_WHEEL:-0}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

# Paths every wheel must carry. The Node builders are what cadgen spawns for DXF and mesh
# export; the browser bundle is what the snapshot CLI loads in a page.
REQUIRED=(
  # The Python the wheel must actually contain. Asset globs were the whole list once,
  # back when cadgen was Python-plus-data; it now also carries the CLI parsers and the
  # warm daemon, and a packages.find regression that dropped any of them would produce a
  # wheel whose `cadgen` console script dies at import. This is the ONLY packaging gate
  # the publish job runs -- test-installed.sh covers the same ground far better but runs
  # in test.yml, not at publish.
  "cadgen/__init__.py"
  "cadgen/assets.py"
  "cadgen/cli/__init__.py"
  "cadgen/cli/step_build.py"
  "cadgen/cli/viewer.py"
  "cadgen/viewer/__init__.py"
  "cadgen/viewer/__main__.py"
  "cadgen/viewer/main.py"
  "cadgen/viewer/compiles.py"
  "cadgen/viewer/collation.json"
  "cadgen/authoring.py"
  "cadgen/build123d.py"
  # The robot validators moved out of skills/{sdf,srdf,urdf}/scripts into cadgen, so a
  # packaging regression here would ship a cadgen whose `cadgen urdf validate` cannot import.
  "cadgen/cli/urdf_validate.py"
  "cadgen/urdf_source.py"
  "cadgen/srdf_validation.py"
  "cadgen/findings.py"
  "cadgen/daemon/__init__.py"
  "cadgen/daemon/server.py"
  # The warm-worker pool. Without these the daemon supervisor starts and then
  # cannot spawn a worker, so every build silently falls back to cold.
  "cadgen/daemon/pool.py"
  "cadgen/daemon/worker.py"
  "cadgen/cli/daemon_status.py"
  # Doubles as a rename sentinel: step_artifacts.py became step_topology_artifact.py, so a
  # merge that resurrected the old name would ship a wheel missing this one.
  "cadgen/step_topology_artifact.py"
  "cadgen/_internal/node_resolve_register.mjs"
  "cadgen/_internal/node_resolve_hooks.mjs"
  "cadgen/_runtime/node/dxf-mesh.mjs"
  "cadgen/_runtime/node/mesh-export.mjs"
  "cadgen/_runtime/node/package.json"
  "cadgen/_runtime/node/THIRD_PARTY_LICENSES.txt"
  "cadgen/_runtime/browser/snapshot-render.js"
  "cadgen/_runtime/browser/render.html"
  "cadgen/_runtime/viewer/index.html"
)

echo "Building cadgen wheel for content check..."
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
"$PYTHON_BIN" -m build --wheel --outdir "$OUT_DIR" "$PACKAGE_DIR" >"$OUT_DIR/build.log" 2>&1 || {
  echo "Wheel build failed:" >&2
  tail -40 "$OUT_DIR/build.log" >&2
  echo "" >&2
  echo "If this is a missing build backend, install it: $PYTHON_BIN -m pip install build" >&2
  exit 1
}

wheel="$(find "$OUT_DIR" -name '*.whl' -type f | head -n 1)"
if [ -z "$wheel" ]; then
  echo "No wheel produced in $OUT_DIR" >&2
  exit 1
fi
echo "Built $(basename "$wheel")"

listing="$OUT_DIR/contents.txt"
"$PYTHON_BIN" -c "
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    sys.stdout.write('\n'.join(sorted(zf.namelist())) + '\n')
" "$wheel" > "$listing"

missing=""
for path in "${REQUIRED[@]}"; do
  if ! grep -Fxq "$path" "$listing"; then
    missing="$missing  - $path"$'\n'
  fi
done

# A nested-glob failure usually loses MANY files at once rather than one, so report the
# count too: it distinguishes "one file moved" from "package-data is not matching".
runtime_count="$(grep -c '^cadgen/_runtime/' "$listing" || true)"

if [ -n "$missing" ]; then
  echo "" >&2
  echo "The cadgen wheel is missing required runtime assets:" >&2
  printf '%s' "$missing" >&2
  echo "" >&2
  echo "cadgen/_runtime entries in the wheel: $runtime_count" >&2
  echo "Wheel listing: $listing" >&2
  echo "" >&2
  echo "Check [tool.setuptools.package-data] in packages/cadgen/pyproject.toml. Nested" >&2
  echo "globs behave differently across setuptools versions; if whole directories are" >&2
  echo "absent, switch to include-package-data + a MANIFEST.in with:" >&2
  echo "  graft src/cadgen/_runtime" >&2
  echo "Assets are built by: scripts/bundle/bundle.sh" >&2
  exit 1
fi

echo "cadgen wheel carries its runtime assets ($runtime_count entries under cadgen/_runtime)."
if [ "$KEEP_WHEEL" != "1" ]; then
  rm -rf "$OUT_DIR"
fi
