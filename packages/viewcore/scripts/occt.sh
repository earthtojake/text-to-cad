#!/usr/bin/env bash
# Build OCCT's static libraries for WebAssembly, the subset the view core links (prototype recipe).
# Usage: occt.sh EMSDK_DIR OCCT_SRC BUILD_DIR INSTALL_DIR
#   EMSDK_DIR  an activated emsdk (the prototype used Emscripten 7.0.1)
#   OCCT_SRC   OCCT's source at tag V8_0_1 (git clone --depth 1 --branch V8_0_1 https://github.com/Open-Cascade-SAS/OCCT.git)
# Every module is off but FoundationClasses; the two toolkits named pull in their dependencies (OCCT's CMake
# resolves them). WebAssembly exceptions, compiled in the legacy encoding: Emscripten 7.0.1's LLVM crashes
# (WebAssemblyCFGStackify addNestedTryTable) on BRepCheck_Analyzer.cxx when asked for the standard (exnref) one,
# so the core's link turns the module into exnref afterwards (Binaryen's wasm-opt --translate-to-exnref), which
# wasmtime and current browsers load; no threads; no FreeType, RapidJSON, Draco, TBB, FreeImage, OpenVR, FFmpeg, VTK, Tcl/Tk or jemalloc: OCCT alone
# (LGPL 2.1 with the Open CASCADE exception), no other licence enters.
set -euo pipefail
EMSDK_DIR=$1 OCCT_SRC=$2 BUILD_DIR=$3 INSTALL_DIR=$4
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null
# `-include mutex`: OCCT 8.0.1 uses std::lock_guard in NCollection_IncAllocator.cxx without including <mutex>,
# which Emscripten 7's libc++ no longer pulls in through <shared_mutex>; forced here so OCCT's source stays as released.
FLAGS="-fwasm-exceptions"
CXX_FLAGS="$FLAGS -include mutex"
emcmake cmake -S "$OCCT_SRC" -B "$BUILD_DIR" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="$CXX_FLAGS" -DCMAKE_C_FLAGS="$FLAGS" \
  -DBUILD_LIBRARY_TYPE=Static -DINSTALL_DIR="$INSTALL_DIR" \
  -DBUILD_MODULE_FoundationClasses=ON -DBUILD_MODULE_ModelingData=OFF -DBUILD_MODULE_ModelingAlgorithms=OFF \
  -DBUILD_MODULE_Visualization=OFF -DBUILD_MODULE_ApplicationFramework=OFF -DBUILD_MODULE_DataExchange=OFF \
  -DBUILD_MODULE_Draw=OFF -DBUILD_ADDITIONAL_TOOLKITS="TKBinXCAF TKRWMesh" \
  -DUSE_FREETYPE=OFF -DUSE_RAPIDJSON=OFF -DUSE_DRACO=OFF -DUSE_TBB=OFF -DUSE_FREEIMAGE=OFF -DUSE_OPENVR=OFF \
  -DUSE_FFMPEG=OFF -DUSE_VTK=OFF -DUSE_TK=OFF -DUSE_EIGEN=OFF -DUSE_JEMALLOC=OFF \
  -DBUILD_DOC_Overview=OFF -DBUILD_GTEST=OFF
make -C "$BUILD_DIR" -j"$(nproc)"
make -C "$BUILD_DIR" install
