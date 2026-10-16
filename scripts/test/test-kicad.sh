#!/usr/bin/env bash
set -euo pipefail

# The suite that needs KiCad itself: boards built headless through @pcb on KiCad's API
# server (`kicad-cli api-server`) and checked by `kicad-cli pcb drc`. It lives apart from
# the cadgen package suite because that one runs on machines without KiCad (its Windows
# job among them): everything here drives a real KiCad end to end.
#
#   scripts/test/test-kicad.sh
#
# KiCad 10.99 (the nightly, the KiCad 11 API) or newer must be installed: cadgen finds its
# kicad-cli at CADGEN_KICAD_CLI, on PATH as kicad-cli-nightly or kicad-cli, or in the
# installers' folders (cadgen.kicad.install). A missing or too-old KiCad fails the run
# rather than skipping it. Nothing here needs the packaged runtime: a build is one
# KiCad process, no daemon, store or renderer.

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/packages/cadgen/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -c \
  "from cadgen.kicad.install import check_version, find_kicad_cli, kicad_version
cli = find_kicad_cli(); print(f'KiCad {check_version(cli, kicad_version(cli))}: {cli}')" \
  || { echo "test-kicad.sh: KiCad 10.99 (the nightly) or newer is required for this suite" >&2; exit 1; }

# The `cadgen` commands a test runs keep their notices and markers out of the developer's
# ~/.cache/cadgen, as the cadgen suite's runner does.
CADGEN_TEST_CACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cadgen-test-store.XXXXXX")"
trap 'rm -rf "$CADGEN_TEST_CACHE_DIR"' EXIT
export CADGEN_CACHE_DIR="$CADGEN_TEST_CACHE_DIR"

run_python_unittest "KiCad board Python tests" "tests/python/packages/kicad" "packages/cadgen/src"
