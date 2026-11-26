#!/usr/bin/env bash
# Build the profiling core and each cheaper variant (src/profile.hpp), natively and/or as wasm, for tools/profile.py.
# Usage: variants.sh native OCCT_INCLUDE_DIR OCCT_LIB_DIR OUT_DIR [NAME...]
#        variants.sh wasm EMSDK_DIR OCCT_INSTALL_DIR [NAME...]      (modules land in dist/viewcore-<name>.wasm)
# NAMEs (default all): profile shared nocheck nofacebox plainbox optimalbox unionbox lean gpropeps leaner
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
declare -A SWITCHES=(
  [profile]=""
  [shared]="-DVC_SHARED_PART"
  [nocheck]="-DVC_NO_CHECK"
  [nofacebox]="-DVC_NO_FACE_BOX"
  [plainbox]="-DVC_PLAIN_BOX"
  [optimalbox]="-DVC_OPTIMAL_BOX"
  [unionbox]="-DVC_SHARED_PART -DVC_UNION_BOX"
  [lean]="-DVC_SHARED_PART -DVC_UNION_BOX -DVC_NO_CHECK"
  [gpropeps]="-DVC_GPROP_EPS=1e-3"
  [leaner]="-DVC_SHARED_PART -DVC_UNION_BOX -DVC_NO_CHECK -DVC_GPROP_EPS=1e-3"
)
ORDER=(profile shared nocheck nofacebox plainbox optimalbox unionbox lean gpropeps leaner)
host=$1; shift
if [ "$host" = native ]; then
  INC=$1 LIB=$2 OUT=$3; shift 3
  for name in "${@:-${ORDER[@]}}"; do
    # shellcheck disable=SC2086
    "$HERE/tools/native.sh" "$INC" "$LIB" "$OUT/viewcore-$name.so" -DVC_PROFILE ${SWITCHES[$name]} &
  done
  wait
else
  EMSDK=$1 OCCT=$2; shift 2
  for name in "${@:-${ORDER[@]}}"; do
    # shellcheck disable=SC2086
    "$HERE/scripts/core.sh" "$EMSDK" "$OCCT" "viewcore-$name.wasm" -DVC_PROFILE ${SWITCHES[$name]}
  done
fi
