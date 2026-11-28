#!/usr/bin/env bash
# Compile the view core and link it with OCCT's static libraries into dist/viewcore.wasm (prototype recipe).
# Usage: core.sh EMSDK_DIR OCCT_INSTALL_DIR [OUT_NAME [DEFINE...]]
#   EMSDK_DIR         an activated emsdk (the prototype used Emscripten 7.0.1)
#   OCCT_INSTALL_DIR  what scripts/occt.sh installed (include/opencascade, lib/libTK*.a)
#   OUT_NAME          the module's name in dist/ (default viewcore.wasm)
#   DEFINE...         measurement builds only (src/profile.hpp): -DVC_PROFILE, which also exports vc_profile, and the
#                     variants' switches (-DVC_SHARED_PART, -DVC_NO_CHECK, ...). None is in the default build.
# The flags are OCCT's own (occt.sh): wasm exceptions in the legacy encoding, which Emscripten 7's LLVM compiles
# OCCT with (it crashes asked for exnref), the same defines (no signal conversion), no threads, no SIMD but in the stills'
# rasterizer (src/render.cpp), which lights four pixels at a time in 128-bit SIMD. The linked module is a standalone
# reactor, PURE_WASI so that it imports WASI alone (src/wasi_only.cpp answers the few non-WASI calls OCCT's linked
# code names), exporting every vc_* function and its memory; Binaryen then translates its exceptions to the standard
# exnref encoding, which wasmtime and current browsers load. Binaryen is given the module's features by name: with
# -all it would also write proposals' encodings (compact imports) that wasmtime does not parse. zlib (the 3MF's deflate)
# is Emscripten's port, which Emscripten downloads; where it cannot, ZLIB_SRC=DIR names a checkout of
# github.com/madler/zlib (the port's tag, v1.4 for Emscripten 7.0.1), whose sources are compiled here instead.
set -euo pipefail
EMSDK_DIR=$1 OCCT=$2 NAME=${3:-viewcore.wasm}
DEFINES=("${@:4}")
HERE=$(cd "$(dirname "$0")/.." && pwd)
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1
OUT="$HERE/dist"
OBJ="$OUT/obj-${NAME%.wasm}"
mkdir -p "$OBJ"

ZLIB=(-sUSE_ZLIB=1)
if [ -n "${ZLIB_SRC:-}" ]; then
  ZLIB=(-I"$ZLIB_SRC")
  mkdir -p "$OBJ/zlib"
  for source in adler32 crc32 deflate trees zutil; do
    emcc -O2 -c "$ZLIB_SRC/$source.c" -o "$OBJ/zlib/$source.o"
  done
fi
CXXFLAGS=(-std=c++17 -O2 -ffp-contract=off -fwasm-exceptions -include mutex -DNo_Exception -DOCCT_NO_PLUGINS "${ZLIB[@]}"
          -I"$OCCT/include/opencascade" -Wall -Wno-deprecated-declarations ${DEFINES[@]+"${DEFINES[@]}"})
pids=()
for source in "$HERE"/src/*.cpp; do
  own=()
  [ "$(basename "$source")" = render.cpp ] && own=(-msimd128)
  em++ "${CXXFLAGS[@]}" ${own[@]+"${own[@]}"} -c "$source" -o "$OBJ/$(basename "$source" .cpp).o" & pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done

EXPORTS=$(grep -o 'vc_[a-z0-9_]*(' "$HERE/include/viewcore.h" | tr -d '(' | sort -u | sed 's/^/_/' | paste -sd, -)
case " ${DEFINES[*]-} " in *" -DVC_PROFILE "*) EXPORTS="$EXPORTS,_vc_profile" ;; esac
LIBS=(TKDESTEP TKXSBase TKBinXCAF TKXCAF TKVCAF TKV3d TKService TKBin TKBinL TKCAF TKLCAF TKCDF TKRWMesh TKDE TKMesh TKHLR TKBO TKPrim
      TKShHealing TKTopAlgo TKGeomAlgo TKBRep TKGeomBase TKG3d TKG2d TKMath TKernel)
LINK_ZLIB=(-sUSE_ZLIB=1)
[ -n "${ZLIB_SRC:-}" ] && LINK_ZLIB=("$OBJ"/zlib/*.o)
em++ -O2 -fwasm-exceptions "${LINK_ZLIB[@]}" -sSTANDALONE_WASM -sPURE_WASI --no-entry -sALLOW_MEMORY_GROWTH=1 -sMAXIMUM_MEMORY=4GB \
  -sSTACK_SIZE=8MB -sEXPORTED_FUNCTIONS="$EXPORTS" \
  "$OBJ"/*.o -L"$OCCT/lib" "${LIBS[@]/#/-l}" -o "$OUT/${NAME%.wasm}.legacy.wasm"
FEATURES=(--enable-exception-handling --enable-reference-types --enable-bulk-memory --enable-bulk-memory-opt
          --enable-sign-ext --enable-nontrapping-float-to-int --enable-mutable-globals --enable-multivalue
          --enable-call-indirect-overlong --enable-simd)
"$EMSDK_DIR/upstream/bin/wasm-opt" "${FEATURES[@]}" --translate-to-exnref -O2 "$OUT/${NAME%.wasm}.legacy.wasm" \
  -o "$OUT/$NAME"
rm -f "$OUT/${NAME%.wasm}.legacy.wasm"
# The module is OCCT's too: its licence texts lie beside it wherever it goes from here.
cp "$HERE"/licenses/LICENSE_LGPL_21.txt "$HERE"/licenses/OCCT_LGPL_EXCEPTION.txt "$OUT/"
ls -l "$OUT/$NAME"
