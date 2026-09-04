#!/usr/bin/env bash
# Exercise cadgen the way a user gets it: built into a wheel, pip-installed, run from a
# directory that is not this repo.
#
# Every other check in this repo runs against the source tree, where the repo root is on
# sys.path and `packages/cadgen-js/bin` exists. None of
# that is true after `pip install cadgen`, so the failures this catches are exactly the
# ones no other check can: an asset left out of package-data, a module that resolves only
# because a sibling directory happened to be adjacent, a builder that still imports a bare
# specifier. Those all pass locally and break for the person who installed it.
#
# The scratch venv reuses the repo venv's heavy dependencies (OCP, build123d) rather than
# reinstalling half a gigabyte -- but the wheel's own cadgen must WIN over the repo's
# editable one, or this would silently test the source tree again. See _link_repo_deps.
#
# Usage: scripts/test/test-installed.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Shared resolution: the repo venv in a checkout, python3 otherwise. CI installs the CAD
# dependencies into the interpreter that setup-python provides and has no .venv at all, so
# hardcoding one here fails there and only there.
# shellcheck source=scripts/test/common.sh
source "$SCRIPT_DIR/common.sh"

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

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

VENV="$WORK/venv"
EMPTY="$WORK/empty"
DIST="$WORK/dist"
mkdir -p "$EMPTY" "$DIST"

fail() { echo "FAIL: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

step "Build the wheel"
"$REPO_ROOT/scripts/bundle/cadgen-runtime.sh" >/dev/null
"$PYTHON_BIN" -m build --wheel --outdir "$DIST" "$REPO_ROOT/packages/cadgen" >"$WORK/build.log" 2>&1 \
  || { cat "$WORK/build.log" >&2; fail "wheel build"; }
WHEEL="$(find "$DIST" -name '*.whl' -type f | head -n 1)"
[ -n "$WHEEL" ] || fail "no wheel produced"
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

step "Assets resolve to the packaged runtime"
"$VENV/bin/python" - <<'PY' || exit 1
import sys
from cadgen.assets import browser_runtime_dir, node_builders_dir
for label, resolved in (
    ("node builders", node_builders_dir()),
    ("browser runtime", browser_runtime_dir()),
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

step "Build a real STEP with no repo in sight"
mkdir -p "$EMPTY/models"
cat >"$EMPTY/models/probe.py" <<'PY'
# A model script declares one @step function and builds it from __main__
# (library-first: there is no gen verb). Deliberately the simplest one that
# exists: this checks
# that an installed cadgen can build at all, not that it models anything
# interesting. @stl declares a mesh serialization so the mesh door has something
# to produce below.
from cadgen import build123d as bd
from cadgen import step, stl


@step
@stl
def probe():
    return bd.Box(10, 10, 10)


if __name__ == "__main__":
    probe()
PY
# Running the script IS the build: its __main__ calls the model, and no CLI verb
# takes its place.
"$VENV/bin/python" models/probe.py >"$WORK/build.log" 2>&1 \
  || { cat "$WORK/build.log" >&2; fail "python <model>.py"; }
[ -f "$EMPTY/models/probe.step" ] \
  || { cat "$WORK/build.log" >&2; fail "the model script produced no STEP document"; }
echo "   built a STEP document and package"

step "Re-emit the document through the build door"
"$VENV/bin/cadgen" step build models/probe.step models/reemit.step \
  >"$WORK/reemit.log" 2>&1 \
  || { cat "$WORK/reemit.log" >&2; fail "cadgen step build"; }
[ -f "$EMPTY/models/reemit.step" ] \
  || { cat "$WORK/reemit.log" >&2; fail "step build produced no STEP document"; }
echo "   re-emitted a document to a new document"

# Running the script above already wrote the STL the model DECLARES. This is
# the other half: the ad-hoc door, taking a document and an explicit OUT. It
# needs that OUT because the written document carries no trace of the model's
# declarations — generated files hold no metadata.
step "Export it through a format door"
rm -f "$EMPTY/models/probe.stl"
"$VENV/bin/cadgen" stl build models/probe.step models/probe.stl >"$WORK/stl.log" 2>&1 \
  || { cat "$WORK/stl.log" >&2; fail "cadgen stl build"; }
[ -s "$EMPTY/models/probe.stl" ] \
  || { cat "$WORK/stl.log" >&2; fail "stl build produced no mesh"; }
echo "   wrote an STL from the document"

printf '\nInstalled-mode checks passed.\n'
