#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scripts/test/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Unlike the full policy/skill suites these contracts do not read built bundles.
# CAD/DXF examples use requirements-dev.txt and compiled core exports; other
# prose contracts run with stdlib Python plus Node, without pip/npm installs.
exec "$PYTHON_BIN" "$SCRIPT_DIR/skill_doc_contracts.py"
