#!/usr/bin/env bash
set -euo pipefail

# Time every Python test module on its own -- one interpreter and one fresh store per
# file -- and print the modules sorted by wall clock. This is how a bloat check starts:
# the runner's parallel wall clock hides which modules are slow.
#
#   scripts/test/time-python.sh [parallel N]      # default 3 at a time; results in tmp/timing/
#
# Manual only; nothing in CI calls it.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

JOBS="${1:-3}"
OUT="$REPO_ROOT/tmp/timing"
mkdir -p "$OUT/results"
rm -f "$OUT"/results/*.json

time_one() {
  local file="$1" repo="$2" python="$3" out="$4"
  local extra="$repo/packages/cadgen/src"
  case "$file" in
    tests/python/skills/*)
      local skill
      skill="$(echo "$file" | cut -d/ -f4)"
      extra="$repo/skills/$skill/scripts:$extra"
      ;;
  esac
  local store key
  store="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-timing.XXXXXX")"
  key="$(echo "$file" | tr '/' '_')"
  CADGEN_CACHE_DIR="$store" PYTHONPATH="$repo:$extra" \
    "$python" "$repo/scripts/test/time_module.py" "$repo" "$repo/$file" "$out/results/$key.json" \
    >/dev/null 2>"$out/results/$key.err" || true
  rm -rf "$store"
}
export -f time_one

cd "$REPO_ROOT"
find tests/python -name 'test*.py' -not -path '*/support/*' | sort \
  | xargs -P "$JOBS" -I{} bash -c 'time_one "$@"' _ {} "$REPO_ROOT" "$PYTHON_BIN" "$OUT"

"$PYTHON_BIN" - "$OUT/results" <<'PY'
import glob, json, sys
rows = [json.load(open(p)) for p in glob.glob(sys.argv[1] + "/*.json")]
rows.sort(key=lambda r: -r["seconds"])
print(f"{'seconds':>8} {'tests':>5} {'s/test':>7}  module")
for r in rows:
    n = max(r["tests"], 1)
    flag = "" if r["status"] == "ok" else f"  [{r['status']}]"
    print(f"{r['seconds']:8.1f} {r['tests']:5d} {r['seconds']/n:7.2f}  {r['module'].replace('tests.python.', '')}{flag}")
print(f"\n{len(rows)} modules, {sum(r['tests'] for r in rows)} tests, {sum(r['seconds'] for r in rows):.0f}s summed")
PY
