#!/usr/bin/env bash
# Build the core natively, as a shared library on a native OCCT 8.0.1 (e.g. the one in cad's OCP wheel), to tell
# a difference of the port from one of WebAssembly: tools/smoke.py --native OUT.so answers through it.
# Usage: native.sh OCCT_INCLUDE_DIR OCCT_LIB_DIR OUT.so   (the libraries may carry a wheel's hashed names)
set -euo pipefail
INC=$1 LIBDIR=$2 OUT=$3
HERE=$(cd "$(dirname "$0")/.." && pwd)
LIBS=$(ls "$LIBDIR"/libTK*.so* | grep -E "/libTK(BinXCAF|XCAF|VCAF|V3d|Service|Bin|BinL|CAF|LCAF|CDF|RWMesh|DE|Mesh|HLR|BO|Prim|ShHealing|TopAlgo|GeomAlgo|BRep|GeomBase|G3d|G2d|Math|ernel)[-.]")
g++ -std=c++17 -O2 -fPIC -shared -DOCC_CONVERT_SIGNALS -DNo_Exception -I"$INC" -Wno-deprecated-declarations \
  "$HERE"/src/{document,mesh,topology,viewcore}.cpp $LIBS -Wl,-rpath,"$LIBDIR" -o "$OUT"
