#!/usr/bin/env bash
# Compile the view core and link it with OCCT's static libraries into dist/viewcore.wasm (prototype recipe).
# Usage: core.sh EMSDK_DIR OCCT_INSTALL_DIR [OUT_NAME [DEFINE...]]
#   EMSDK_DIR         an activated emsdk (the prototype used Emscripten 7.0.1)
#   OCCT_INSTALL_DIR  what scripts/occt.sh installed (include/opencascade, lib/libTK*.a)
#   OUT_NAME          the module's name in dist/ (default viewcore.wasm)
#   DEFINE...         measurement builds only (src/profile.hpp): -DVC_PROFILE, which also exports vc_profile, and the
#                     variants' switches (-DVC_SHARED_PART, -DVC_NO_CHECK, ...). None is in the default build.
# The flags are OCCT's own (occt.sh): wasm exceptions in the legacy encoding, which Emscripten 7's LLVM compiles
# OCCT with (it crashes asked for exnref), the same defines, no threads, no SIMD. The linked module is a standalone
# reactor, PURE_WASI so that it imports WASI alone (src/wasi_only.cpp answers the few non-WASI calls OCCT's linked
# code names), exporting every vc_* function and its memory; Binaryen then translates its exceptions to the standard
# exnref encoding, which wasmtime and current browsers load. Binaryen is given the module's features by name: with
# -all it would also write proposals' encodings (compact imports) that wasmtime does not parse.
set -euo pipefail
EMSDK_DIR=$1 OCCT=$2 NAME=${3:-viewcore.wasm}
DEFINES=("${@:4}")
HERE=$(cd "$(dirname "$0")/.." && pwd)
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1
OUT="$HERE/dist"
OBJ="$OUT/obj-${NAME%.wasm}"
mkdir -p "$OBJ"

CXXFLAGS=(-std=c++17 -O2 -fwasm-exceptions -include mutex -DOCC_CONVERT_SIGNALS -DNo_Exception -DOCCT_NO_PLUGINS
          -I"$OCCT/include/opencascade" -Wall -Wno-deprecated-declarations ${DEFINES[@]+"${DEFINES[@]}"})
pids=()
for source in "$HERE"/src/*.cpp; do
  em++ "${CXXFLAGS[@]}" -c "$source" -o "$OBJ/$(basename "$source" .cpp).o" & pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done

EXPORTS=$(grep -o 'vc_[a-z_]*(' "$HERE/include/viewcore.h" | tr -d '(' | sort -u | sed 's/^/_/' | paste -sd, -)
case " ${DEFINES[*]-} " in *" -DVC_PROFILE "*) EXPORTS="$EXPORTS,_vc_profile" ;; esac
LIBS=(TKBinXCAF TKXCAF TKVCAF TKV3d TKService TKBin TKBinL TKCAF TKLCAF TKCDF TKRWMesh TKDE TKMesh TKHLR TKBO TKPrim
      TKShHealing TKTopAlgo TKGeomAlgo TKBRep TKGeomBase TKG3d TKG2d TKMath TKernel)
em++ -O2 -fwasm-exceptions -sSTANDALONE_WASM -sPURE_WASI --no-entry -sALLOW_MEMORY_GROWTH=1 -sMAXIMUM_MEMORY=4GB \
  -sSTACK_SIZE=8MB -sEXPORTED_FUNCTIONS="$EXPORTS" \
  "$OBJ"/*.o -L"$OCCT/lib" "${LIBS[@]/#/-l}" -o "$OUT/${NAME%.wasm}.legacy.wasm"
FEATURES=(--enable-exception-handling --enable-reference-types --enable-bulk-memory --enable-bulk-memory-opt
          --enable-sign-ext --enable-nontrapping-float-to-int --enable-mutable-globals --enable-multivalue
          --enable-call-indirect-overlong)
"$EMSDK_DIR/upstream/bin/wasm-opt" "${FEATURES[@]}" --translate-to-exnref -O2 "$OUT/${NAME%.wasm}.legacy.wasm" \
  -o "$OUT/$NAME"
rm -f "$OUT/${NAME%.wasm}.legacy.wasm"
ls -l "$OUT/$NAME"
