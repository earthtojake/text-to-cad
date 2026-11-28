#!/usr/bin/env bash
# Build OCP, the Python binding of OCCT 8.0.1 (cadquery-ocp 8.0.1.1's sources), as a Pyodide 314.0.8 wheel (prototype recipe).
# Usage: ocp.sh [--plib-fast] [--simd] [--freetype-src DIR] [-j N] EMSDK_DIR OCCT_SRC XBUILDENV_DIR MODULES WORK_DIR
#   EMSDK_DIR      an emsdk with Emscripten 5.0.3 installed and activated (the version Pyodide 314.0.8 is built with:
#                  `pyodide config get emscripten_version`; a side module must match its main module's)
#   OCCT_SRC       OCCT's source at tag V8_0_1, unchanged (git clone --depth 1 --branch V8_0_1 https://github.com/Open-Cascade-SAS/OCCT.git)
#   XBUILDENV_DIR  Pyodide's cross-build environment (pip install pyodide-build==0.39.0; pyodide xbuildenv install --path DIR 314.0.8):
#                  CPython's headers, the flags its packages are built with, and the main module the wheel is checked against
#   MODULES        the OCP submodules to bind, one per line (scripts/ocp-modules.txt), or `all` for every one of them
#   WORK_DIR       downloads, build trees and dist/, the wheel; a rerun resumes from the last step that finished
#   --plib-fast    OCCT's PLib.cxx with patches/occt-plib-max-opt-dim.patch (one file, compiled here and linked ahead of
#                  OCCT's own); off by default: the default build compiles OCCT as released
#   --simd         -msimd128 everywhere (OCCT, OCP and the link); off by default
#   --freetype-src a checkout of FreeType at VER-2-13-3 (Emscripten 5.0.3's port) for OCCT's fonts (text to shapes);
#                  without it OCCT is built without FreeType and Font_FTFont reports no font
#   -j N           parallel jobs (default: nproc); a job compiling OCP's larger files takes up to ~3 GB
#
# What it does, each step once (WORK_DIR/stamps): fetch OCP's generated binding sources (the CadQuery/OCP release
# 8.0.1.1's archive) and the binding's header-only dependencies, each pinned below; prepare the binding sources for
# the module list (OCP.cpp registers the listed modules only, the instantiated collections keep the entries whose
# types the list holds, and an import of a module left out raises ModuleNotFoundError naming it); build the OCCT
# toolkits those modules live in, static, position independent; compile the binding; link one Pyodide side module,
# OCP.cpython-314-wasm32-emscripten.so; check that every function it imports is one Pyodide's main module exports;
# optimise it with Binaryen (Emscripten's own wasm-opt); and write the wheel with the licences of all it contains.
#
# The list is the only input that changes what is bound: `all` builds the full binding, the same steps. A list that
# leaves out a module a listed one needs to import (a base class, a default argument) is refused, naming both.
#
# Flags (all compiles): -O3 -DNDEBUG (CMake's Release, as cadquery-ocp's wheels), Pyodide's -fPIC -fwasm-exceptions
# -sSUPPORT_LONGJMP=wasm, and -fvisibility=hidden -fvisibility-inlines-hidden (OCP's own build sets both for the
# binding; set for OCCT here too, so the module's own inline and template functions are called directly instead of
# through an import of themselves that the loader resolves at run time). OCCT's CMake defines OCC_CONVERT_SIGNALS,
# as in every OCP build. No SIMD unless --simd.
#
# Licences of what the wheel contains, written into its .dist-info/licenses: OCCT (GNU LGPL 2.1 with the Open
# CASCADE exception 1.0; whoever ships the wheel offers OCCT's source, tag V8_0_1, and this script), OCP's
# generated sources (Apache-2.0), pybind11 (BSD-3-Clause), fmt (MIT), RapidJSON (MIT; OCCT's glTF writer), and
# with --freetype-src FreeType (the FreeType License).
set -euo pipefail

PLIB=0 SIMD=0 FREETYPE_SRC="" JOBS=$(nproc)
while [ $# -gt 0 ]; do
  case $1 in
    --plib-fast) PLIB=1; shift ;;
    --simd) SIMD=1; shift ;;
    --freetype-src) FREETYPE_SRC=$(cd "$2" && pwd); shift 2 ;;
    -j) JOBS=$2; shift 2 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    --*) echo "ocp.sh: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[ $# -eq 5 ] || { echo "usage: ocp.sh [--plib-fast] [--simd] [--freetype-src DIR] [-j N] EMSDK_DIR OCCT_SRC XBUILDENV_DIR MODULES WORK_DIR" >&2; exit 2; }
EMSDK_DIR=$(cd "$1" && pwd) OCCT_SRC=$(cd "$2" && pwd) XBUILDENV=$(cd "$3" && pwd) WORK=$5
MODULES=$4; [ "$MODULES" = all ] || MODULES=$(cd "$(dirname "$4")" && pwd)/$(basename "$4")
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)

# ---- pins ----
PYODIDE_VERSION=314.0.8 EMSCRIPTEN_VERSION=5.0.3 PYTHON_TAG=cp314 PLATFORM_TAG=pyemscripten_2026_0_wasm32
OCP_VERSION=8.0.1.1
OCP_URL=https://github.com/CadQuery/OCP/releases/download/8.0.1.1/OCP_src_stubs_Linux.zip
OCP_SHA256=bbab4dc85fdba87ac8f024e13a3e9dba0e268f4b204c9c60c53edf2522ced46e
OCP_LICENSE_URL=https://raw.githubusercontent.com/CadQuery/OCP/8.0.1.1/LICENSE
OCP_LICENSE_SHA256=a13caea71627202ad33cc4cafafdd18e667e16716488f8d9c568127121fb89fd
# name, repository, tag (or commit), commit: what cadquery-ocp's Pyodide build uses
GIT_DEPS=(
  "pybind11 https://github.com/pybind/pybind11.git v3.1.0 97bf890db679505a14dfe547a5e77bb2bd05dc90"
  "fmt https://github.com/fmtlib/fmt.git 12.2.0 1be298e1bd68957e4cd352e1f676f00e07dcfb57"
  "rapidjson https://github.com/Tencent/rapidjson.git 24b5e7a8b27f42fa16b96fc70aade9106cf7102f 24b5e7a8b27f42fa16b96fc70aade9106cf7102f"
)
OCCT_TAG=V8_0_1

# ---- toolchain checks ----
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1
have=$(emcc --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')
[ "$have" = "$EMSCRIPTEN_VERSION" ] || { echo "ocp.sh: Emscripten $have active, Pyodide $PYODIDE_VERSION needs $EMSCRIPTEN_VERSION" >&2; exit 1; }
PYROOT=$XBUILDENV/$PYODIDE_VERSION/xbuildenv/pyodide-root
[ -f "$PYROOT/Makefile.envs" ] || { echo "ocp.sh: no Pyodide $PYODIDE_VERSION cross-build environment in $XBUILDENV" >&2; exit 1; }
grep -q "PYODIDE_EMSCRIPTEN_VERSION ?= $EMSCRIPTEN_VERSION\$" "$PYROOT/Makefile.envs" || { echo "ocp.sh: $XBUILDENV is not built with Emscripten $EMSCRIPTEN_VERSION" >&2; exit 1; }
PYINC=$(echo "$PYROOT"/cpython/installs/python-3.14.*/include/python3.14)
MAIN_WASM=$PYROOT/dist/pyodide.asm.wasm
[ -f "$PYINC/Python.h" ] && [ -f "$MAIN_WASM" ] || { echo "ocp.sh: $PYROOT lacks CPython's headers or pyodide.asm.wasm" >&2; exit 1; }
[ "$(git -C "$OCCT_SRC" describe --tags --exact-match 2>/dev/null)" = "$OCCT_TAG" ] || { echo "ocp.sh: $OCCT_SRC is not OCCT at $OCCT_TAG" >&2; exit 1; }
[ -z "$(git -C "$OCCT_SRC" status --porcelain --untracked-files=no)" ] || { echo "ocp.sh: $OCCT_SRC has local changes; OCCT is built as released" >&2; exit 1; }
WASM_OPT=$EMSDK_DIR/upstream/bin/wasm-opt

VARIANT=base; [ $SIMD = 1 ] && VARIANT=simd; [ -n "$FREETYPE_SRC" ] && VARIANT=$VARIANT-ft
FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -fvisibility=hidden -fvisibility-inlines-hidden -g0"
[ $SIMD = 1 ] && FLAGS="$FLAGS -msimd128"
STAMPS=$WORK/stamps; mkdir -p "$STAMPS" "$WORK/logs"
done_() { [ -f "$STAMPS/$1" ]; }
mark() { touch "$STAMPS/$1"; }
log() { echo "[ocp.sh $(date +%H:%M:%S)] $*"; }

# ---- 1. sources ----
SRC=$WORK/src; mkdir -p "$SRC"
fetch() { # url sha256 dest
  [ -f "$3" ] && echo "$2  $3" | sha256sum -c --quiet - && return
  curl -sSfL -o "$3.part" "$1"; echo "$2  $3.part" | sha256sum -c --quiet -; mv "$3.part" "$3"
}
if ! done_ sources; then
  log "fetching sources"
  fetch "$OCP_URL" "$OCP_SHA256" "$SRC/OCP_src.zip"
  fetch "$OCP_LICENSE_URL" "$OCP_LICENSE_SHA256" "$SRC/OCP-LICENSE"
  for dep in "${GIT_DEPS[@]}"; do
    set -- $dep
    if [ ! -d "$SRC/$1/.git" ]; then git init -q "$SRC/$1"; git -C "$SRC/$1" fetch -q --depth 1 "$2" "$3"; git -C "$SRC/$1" checkout -q FETCH_HEAD; fi
    [ "$(git -C "$SRC/$1" rev-parse HEAD)" = "$4" ] || { echo "ocp.sh: $1 is not at $4" >&2; exit 1; }
  done
  git -C "$SRC/pybind11" apply --check "$HERE/patches/pybind11-wasm32-ssize-cast.patch" 2>/dev/null &&
    git -C "$SRC/pybind11" apply "$HERE/patches/pybind11-wasm32-ssize-cast.patch"
  rm -rf "$SRC/OCP"; mkdir -p "$SRC/OCP"; (cd "$SRC/OCP" && unzip -q ../OCP_src.zip)
  mark sources
fi
if [ -n "$FREETYPE_SRC" ]; then
  # Emscripten's FreeType port, built from the given checkout instead of its download.
  export EMCC_LOCAL_PORTS="freetype=$FREETYPE_SRC"
fi

# ---- 2. the binding's sources for the list ----
OCPSRC=$WORK/ocp-src
if ! done_ prepare || { [ "$MODULES" != all ] && [ "$MODULES" -nt "$STAMPS/prepare" ]; }; then
  log "preparing OCP's sources for $( [ "$MODULES" = all ] && echo all modules || basename "$MODULES")"
  python3 -I - "$SRC/OCP" "$OCPSRC" "$MODULES" "$OCCT_SRC" <<'PY'
import os, re, shutil, sys, glob, hashlib
src, out, listfile, occt = sys.argv[1:5]
ocp = open(f"{src}/OCP.cpp").read()
head, body = ocp.split("// register modules", 1)
# OCP's VTK and OpenGL modules have nothing to bind against here (no VTK, no OpenGL): dropped, as every Pyodide build does.
gl = lambda name: re.search(r"vtk|opengl", name, re.I)
every = [m for m in re.findall(r"register_(\w+)\(m\);", body) if not gl(m) and not m.startswith("collections_")]
known = set(every)
if listfile == "all":
    wanted, listname = list(every), "all"
else:
    wanted, listname = [], os.path.basename(listfile)
    for n, line in enumerate(open(listfile), 1):
        name = line.split("#", 1)[0].strip()
        if not name: continue
        if name not in known: sys.exit(f"ocp.sh: {listfile}:{n}: OCP has no module {name}")
        wanted.append(name)
chosen = set(wanted)

def owner(tok):
    if tok in known: return tok
    p = tok.split("_")[0]
    return p if p in known else None
def close(t, i, o, c):
    d = 0
    for j in range(i, len(t)):
        if t[j] == o: d += 1
        elif t[j] == c:
            d -= 1
            if d == 0: return j
    return len(t)
IDENT = re.compile(r"[A-Za-z_]\w*")
def needs(m):
    """The modules m's registration reads at import: base classes, default arguments, values cast at import."""
    texts = [open(f).read() for f in (f"{src}/{m}_pre.cpp", f"{src}/{m}.cpp", f"{src}/{m}_tmpl.hxx") if os.path.exists(f)]
    chunks = []
    for t in texts:
        for x in re.finditer(r"py::class_<|implicitly_convertible<", t):
            chunks.append(t[x.end():close(t, x.end() - 1, "<", ">")])
        for x in re.finditer(r"py::arg\(\"[^\"]*\"\)\s*=\s*static_cast<", t):
            j = close(t, x.end() - 1, "<", ">"); chunks.append(t[x.end():close(t, j + 1, "(", ")") + 1])
        for x in re.finditer(r"\.attr\(\"[^\"]*\"\)\s*=\s*py::cast\(", t):
            chunks.append(t[x.end():close(t, x.end() - 1, "(", ")")])
    return {o for c in chunks for tok in IDENT.findall(c) for o in [owner(tok)] if o and o != m}
gaps = sorted((d, m) for m in wanted for d in needs(m) if d not in chosen)
if gaps:
    sys.exit("ocp.sh: the module list leaves out modules listed ones need to import:\n" +
             "\n".join(f"  {d} (needed by {m})" for d, m in gaps) + f"\nadd them to {listfile}")

if os.path.exists(out): shutil.rmtree(out)
os.makedirs(out)
for f in glob.glob(f"{src}/*"):
    name = os.path.basename(f)
    if os.path.isdir(f) or gl(name): continue
    stem = re.sub(r"(_pre|_tmpl)?\.(cpp|hxx)$", "", name)
    if name.endswith(".cpp") and not stem.startswith("collections") and stem != "OCP" and stem not in chosen: continue
    shutil.copy(f, out)

def edit(path, fn):
    t = open(path).read(); u = fn(t)
    if u != t: open(path, "w").write(u)
# OSD_OpenFile returns a FILE*, which pybind11 cannot bind under Emscripten (an incomplete type): not bound, as in
# every Pyodide build of OCP.
if "OSD" in chosen:
    edit(f"{out}/OSD.cpp", lambda t: re.sub(r"([ \t])(m\.def\(\"OSD_OpenFile\",[^;]*;)", r"\1/*\2*/", t))

def keeps(text):
    owners = {owner(tok) for tok in IDENT.findall(text)} - {None}
    return owners <= chosen
for f in glob.glob(f"{out}/collections_*.cpp"):
    def filt(t):
        lines = []
        for line in t.split("\n"):
            s = line.strip()
            m = re.match(r"#include\s*[<\"](\w+)\.hxx[>\"]", s)
            if (gl(s) and (s.startswith("#include") or s.startswith("class "))) or (m and not keeps(m.group(1))):
                line = "// " + line
            elif "register_template_" in s:
                args = s[s.index("<") + 1:s.rindex(">")] if "<" in s else ""
                if gl(s) or "GLuint" in s or not keeps(args): line = "// " + line
            lines.append(line)
        return "\n".join(lines)
    edit(f, filt)

absent = [m for m in every if m not in chosen]
def calls(t):
    def keep(x):
        name = x.group(2)
        base = re.sub(r"_enums$", "", name)
        return x.group(0) if base.startswith("collections") or base in chosen else x.group(1) + "// " + x.group(0).lstrip()
    return re.sub(r"(\s*)register_(\w+)\(m\);", lambda x: keep(x), t)
listhash = hashlib.sha256("\n".join(sorted(chosen)).encode()).hexdigest()[:8]
finder = r'''
// Modules this build leaves out (ocp.sh's module list): importing one raises ModuleNotFoundError naming it.
{
    py::list absent;
''' + "".join(f'    absent.append("{m}");\n' for m in absent) + r'''    py::dict scope;
    scope["absent"] = absent;
    scope["ocp"] = m;
    scope["listname"] = "''' + listname + r'''";
    py::exec(R"#(
import sys
absent = frozenset(absent)
def _message(name):
    return (f"OCP.{name} is not in this build of OCP: the module list it was built from ({listname}) leaves it out; "
            f"build the wheel with {name} listed")
class _AbsentModules:
    @staticmethod
    def find_spec(fullname, path=None, target=None):
        if fullname.startswith("OCP.") and fullname[4:].split(".")[0] in absent:
            raise ModuleNotFoundError(_message(fullname[4:].split(".")[0]), name=fullname)
        return None
def __getattr__(name):
    if name in absent:
        raise AttributeError(_message(name), name=name, obj=ocp)
    raise AttributeError(f"module 'OCP' has no attribute {name!r}", name=name, obj=ocp)
ocp.__getattr__ = __getattr__
ocp.__path__ = []
ocp.__ocp_modules__ = listname
sys.meta_path.append(_AbsentModules)
)#", scope);
}
'''
text = calls(head) + "// register modules" + calls(body)
text = text.replace("#include <pybind11/stl.h>", "#include <pybind11/stl.h>\n#include <pybind11/eval.h>", 1)
k = text.rstrip().rindex("}")
open(f"{out}/OCP.cpp", "w").write(text[:k] + finder + "\n}\n")

# The OCCT toolkits holding the chosen packages; OCCT's CMake adds what they depend on.
tk = {}
for f in glob.glob(f"{occt}/src/*/TK*/PACKAGES.cmake"):
    for p in re.findall(r"^\s+(\w+)\s*$", open(f).read(), re.M): tk[p] = f.split("/")[-2]
tks = sorted({tk[m] for m in chosen if m in tk})
open(f"{out}/toolkits.txt", "w").write(" ".join(tks) + "\n")
open(f"{out}/modules.txt", "w").write("\n".join(sorted(chosen, key=str.lower)) + "\n")
open(f"{out}/list-id.txt", "w").write(("all" if not absent else "m" + listhash) + "\n")
cpp = sorted(os.path.basename(f) for f in glob.glob(f"{out}/*.cpp"))
open(f"{out}/sources.txt", "w").write("\n".join(cpp) + "\n")
print(f"{len(chosen)} of {len(every)} modules, {len(cpp)} sources, OCCT toolkits: {' '.join(tks)}")
PY
  rm -f "$STAMPS"/compile-* "$STAMPS"/link-* "$STAMPS"/wheel-*
  mark prepare
fi
TOOLKITS=$(cat "$OCPSRC/toolkits.txt")
LIST_ID=$(cat "$OCPSRC/list-id.txt")

# ---- 3. OCCT ----
OCCT_BUILD=$WORK/occt-$VARIANT OCCT=$WORK/occt-$VARIANT-install
if ! done_ "occt-$VARIANT-$(echo $TOOLKITS | sha256sum | cut -c1-8)"; then
  log "building OCCT ($VARIANT): $TOOLKITS"
  FT=(-DUSE_FREETYPE=OFF)
  if [ -n "$FREETYPE_SRC" ]; then
    embuilder build freetype --pic >"$WORK/logs/freetype.log" 2>&1
    SYSROOT=$(em-config CACHE)/sysroot
    FT=(-DUSE_FREETYPE=ON -D3RDPARTY_FREETYPE_DIR="$SYSROOT" -D3RDPARTY_FREETYPE_INCLUDE_DIR_ft2build="$SYSROOT/include/freetype2"
        -D3RDPARTY_FREETYPE_INCLUDE_DIR_freetype2="$SYSROOT/include/freetype2"
        -D3RDPARTY_FREETYPE_LIBRARY="$SYSROOT/lib/wasm32-emscripten/pic/libfreetype.a"
        -D3RDPARTY_FREETYPE_LIBRARY_DIR="$SYSROOT/lib/wasm32-emscripten/pic")
  fi
  emcmake cmake -S "$OCCT_SRC" -B "$OCCT_BUILD" -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="$FLAGS" -DCMAKE_CXX_FLAGS="$FLAGS" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DBUILD_LIBRARY_TYPE=Static -DINSTALL_DIR="$OCCT" \
    -DBUILD_MODULE_FoundationClasses=ON -DBUILD_MODULE_ModelingData=OFF -DBUILD_MODULE_ModelingAlgorithms=OFF \
    -DBUILD_MODULE_Visualization=OFF -DBUILD_MODULE_ApplicationFramework=OFF -DBUILD_MODULE_DataExchange=OFF \
    -DBUILD_MODULE_Draw=OFF -DBUILD_MODULE_DETools=OFF -DBUILD_ADDITIONAL_TOOLKITS="$TOOLKITS" \
    "${FT[@]}" -DUSE_RAPIDJSON=ON -D3RDPARTY_RAPIDJSON_DIR="$SRC/rapidjson" -D3RDPARTY_RAPIDJSON_INCLUDE_DIR="$SRC/rapidjson/include" \
    -DUSE_OPENGL=OFF -DUSE_GLES2=OFF -DUSE_XLIB=OFF -DUSE_DRACO=OFF -DUSE_TBB=OFF -DUSE_FREEIMAGE=OFF -DUSE_OPENVR=OFF \
    -DUSE_FFMPEG=OFF -DUSE_VTK=OFF -DUSE_TK=OFF -DUSE_EIGEN=OFF -DUSE_JEMALLOC=OFF -DUSE_D3D=OFF \
    -DBUILD_DOC_Overview=OFF -DBUILD_GTEST=OFF -DBUILD_SAMPLES_QT=OFF >"$WORK/logs/occt-$VARIANT-cmake.log" 2>&1
  make -C "$OCCT_BUILD" -j"$JOBS" >"$WORK/logs/occt-$VARIANT-make.log" 2>&1
  make -C "$OCCT_BUILD" install >"$WORK/logs/occt-$VARIANT-install.log" 2>&1
  mark "occt-$VARIANT-$(echo $TOOLKITS | sha256sum | cut -c1-8)"
fi
# Every OCCT header, also of the toolkits not built: OCP's sources include some to resolve forward declarations.
HEADERS=$WORK/occt-headers
if [ ! -d "$HEADERS" ]; then
  mkdir -p "$HEADERS.part"
  find "$OCCT_SRC/src" -path "$OCCT_SRC/src/Draw" -prune -o -type f \( -name '*.hxx' -o -name '*.lxx' -o -name '*.gxx' -o -name '*.pxx' -o -name '*.h' \) \
    -exec ln -sf {} "$HEADERS.part/" \;
  mv "$HEADERS.part" "$HEADERS"
fi

# ---- 4. the binding ----
OBJ=$WORK/obj-$VARIANT-$LIST_ID
CXX="em++ -std=c++17 -O3 -DNDEBUG $FLAGS -DFMT_HEADER_ONLY -w -I$OCPSRC -I$SRC/pybind11/include -I$SRC/fmt/include \
-I$SRC/rapidjson/include -I$OCCT/include/opencascade -I$HEADERS -I$PYINC"
if ! done_ "compile-$VARIANT-$LIST_ID"; then
  log "compiling $(wc -l <"$OCPSRC/sources.txt") binding sources ($VARIANT), -j$JOBS"
  mkdir -p "$OBJ"
  { echo "all:"; while read -r f; do o="$OBJ/${f%.cpp}.o"; echo "all: $o"; echo "$o: $OCPSRC/$f"; printf '\t%s -c $< -o $@\n' "$CXX"; done <"$OCPSRC/sources.txt"; } >"$OBJ/Makefile"
  make -k -f "$OBJ/Makefile" -j"$JOBS" >"$WORK/logs/compile-$VARIANT-$LIST_ID.log" 2>&1 ||
    { echo "ocp.sh: compiling failed, see $WORK/logs/compile-$VARIANT-$LIST_ID.log" >&2; exit 1; }
  mark "compile-$VARIANT-$LIST_ID"
fi

# ---- 5. link, check, optimise ----
TAG=$VARIANT-$LIST_ID; [ $PLIB = 1 ] && TAG=$TAG-plib
OUT=$WORK/link-$TAG; SO=OCP.$PYTHON_TAG-wasm32-emscripten.so
if ! done_ "link-$TAG"; then
  log "linking $SO ($TAG)"
  mkdir -p "$OUT"
  EXTRA=()
  if [ $PLIB = 1 ]; then
    # The patched PLib.cxx, compiled with the command OCCT's build used for its own, linked before libTKMath.a: the
    # archive's PLib object is then never taken (every symbol it defines is already defined).
    mkdir -p "$OUT/plib/src/FoundationClasses/TKMath/PLib"
    cp "$OCCT_SRC/src/FoundationClasses/TKMath/PLib/PLib.cxx" "$OUT/plib/src/FoundationClasses/TKMath/PLib/"
    (cd "$OUT/plib" && patch -s -p1 <"$HERE/patches/occt-plib-max-opt-dim.patch")
    read -r DIR CMD < <(python3 -I -c 'import json,sys; e = next(e for e in json.load(open(sys.argv[1])) if e["file"].endswith("/PLib/PLib.cxx")); print(e["directory"], e["command"])' "$OCCT_BUILD/compile_commands.json")
    CMD=${CMD/"$OCCT_SRC/src/FoundationClasses/TKMath/PLib/PLib.cxx"/"$OUT/plib/src/FoundationClasses/TKMath/PLib/PLib.cxx"}
    CMD=$(echo "$CMD" | sed "s| -o [^ ]*| -o $OUT/plib/PLib.o|")
    (cd "$DIR" && eval "$CMD")
    EXTRA=("$OUT/plib/PLib.o")
  fi
  LIBS=$(cd "$OCCT/lib" && ls libTK*.a | sed 's/^lib\(.*\)\.a$/-l\1/' | tr '\n' ' ')
  FTLINK=(); [ -n "$FREETYPE_SRC" ] && FTLINK=(-sUSE_FREETYPE=1)
  # -O1 at the link: the module is optimised by Binaryen below, once, where its memory use can be seen.
  em++ -O1 $FLAGS -sSIDE_MODULE=1 -Wl,--allow-multiple-definition ${EXTRA[@]+"${EXTRA[@]}"} "$OBJ"/*.o \
    -L"$OCCT/lib" -Wl,--start-group $LIBS -Wl,--end-group "${FTLINK[@]}" -o "$OUT/$SO.linked" >"$WORK/logs/link-$TAG.log" 2>&1
  python3 -I - "$OUT/$SO.linked" "$MAIN_WASM" <<'PY' | tee "$OUT/imports.txt"
import sys
def leb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 0x7f) << s; s += 7
        if not c & 0x80: return r, i
def name(b, i):
    n, i = leb(b, i); return b[i:i + n].decode(), i + n
def parse(path):
    b = open(path, "rb").read(); i = 8; imports = []; exports = set(); funcs = 0
    while i < len(b):
        sid = b[i]; n, i = leb(b, i + 1); end = i + n
        if sid == 2:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                m, j = name(b, j); f, j = name(b, j); k = b[j]; j += 1
                if k == 0: _, j = leb(b, j)
                elif k in (1, 2):
                    if k == 1: j += 1
                    fl, j = leb(b, j); _, j = leb(b, j)
                    if fl & 1: _, j = leb(b, j)
                elif k == 3: j += 2
                elif k == 4: j += 1; _, j = leb(b, j)
                imports.append((m, f, k))
        elif sid == 3: funcs, _ = leb(b, i)
        elif sid == 7:
            cnt, j = leb(b, i)
            for _ in range(cnt):
                nm, j = name(b, j); j += 1; _, j = leb(b, j); exports.add(nm)
        i = end
    return imports, exports, funcs
imps, exps, funcs = parse(sys.argv[1])
_, main, _ = parse(sys.argv[2])
fn = [f for m, f, k in imps if m == "env" and k == 0]
self_ = [f for f in fn if f in exps]
cxx = [f for f in fn if f.startswith("_Z")]
missing = [f for f in fn if f not in main and f not in exps and not f.startswith("invoke_")]
print(f"functions {funcs}; env function imports {len(fn)}, of them C++ {len(cxx)}, defined in the module itself {len(self_)}")
if missing:
    print(f"{len(missing)} imported functions Pyodide's main module does not export:", *sorted(missing)[:50], sep="\n  ")
    sys.exit(1)
PY
  log "optimising (wasm-opt -O3)"
  "$WASM_OPT" --post-emscripten -O3 "$OUT/$SO.linked" -o "$OUT/$SO" >"$WORK/logs/wasm-opt-$TAG.log" 2>&1
  mark "link-$TAG"
fi

# ---- 6. the wheel ----
DIST=$WORK/dist; mkdir -p "$DIST"
LOCAL=""; [ "$LIST_ID" = all ] || LOCAL=$LIST_ID
[ $SIMD = 1 ] && LOCAL=${LOCAL:+$LOCAL.}simd
[ $PLIB = 1 ] && LOCAL=${LOCAL:+$LOCAL.}plib
[ -n "$FREETYPE_SRC" ] || LOCAL=${LOCAL:+$LOCAL.}noft
VERSION=$OCP_VERSION${LOCAL:++$LOCAL}
log "writing the wheel, version $VERSION"
python3 -I - "$OUT/$SO" "$DIST" "$VERSION" "$PYTHON_TAG-$PYTHON_TAG-$PLATFORM_TAG" "$OCPSRC/modules.txt" \
  "$OCCT_SRC/LICENSE_LGPL_21.txt" "$OCCT_SRC/OCCT_LGPL_EXCEPTION.txt" "$SRC/OCP-LICENSE" "$SRC/pybind11/LICENSE" \
  "$SRC/fmt/LICENSE" "$SRC/rapidjson/license.txt" ${FREETYPE_SRC:+"$FREETYPE_SRC/docs/FTL.TXT"} <<'PY'
import base64, hashlib, os, sys, zipfile
so, dist, version, tag, modules, *licences = sys.argv[1:]
name = "cad_ocp_wasm"
info = f"{name}-{version}.dist-info"
names = ["OCCT-LICENSE_LGPL_21.txt", "OCCT-OCCT_LGPL_EXCEPTION.txt", "OCP-LICENSE", "pybind11-LICENSE", "fmt-LICENSE",
         "rapidjson-license.txt", "FreeType-FTL.TXT"]
expr = "LGPL-2.1-only WITH OCCT-exception-1.0 AND Apache-2.0 AND BSD-3-Clause AND MIT" + (" AND FTL" if len(licences) > 6 else "")
metadata = "\n".join([
    "Metadata-Version: 2.4", "Name: cad-ocp-wasm", f"Version: {version}",
    "Summary: OCP, the Python binding of Open CASCADE Technology 8.0.1, built for Pyodide (text-to-cad's build)",
    f"License-Expression: {expr}", *[f"License-File: {n}" for n in names[:len(licences)]], "Requires-Python: >=3.14", "", ""])
wheel = f"Wheel-Version: 1.0\nGenerator: ocp.sh\nRoot-Is-Purelib: false\nTag: {tag}\n"
files = [(os.path.basename(so).replace(".linked", ""), open(so, "rb").read()),
         (f"{info}/METADATA", metadata.encode()), (f"{info}/WHEEL", wheel.encode()),
         (f"{info}/OCP_MODULES.txt", open(modules, "rb").read())]
files += [(f"{info}/licenses/{n}", open(p, "rb").read()) for n, p in zip(names, licences)]
record = [f"{p},sha256={base64.urlsafe_b64encode(hashlib.sha256(d).digest()).rstrip(b'=').decode()},{len(d)}" for p, d in files]
record.append(f"{info}/RECORD,,")
out = f"{dist}/{name}-{version}-{tag}.whl"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p, d in files + [(f"{info}/RECORD", ("\n".join(record) + "\n").encode())]:
        zi = zipfile.ZipInfo(p, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, d)
print(out, os.path.getsize(out), "bytes", hashlib.sha256(open(out, "rb").read()).hexdigest())
PY
