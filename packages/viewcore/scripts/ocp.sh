#!/usr/bin/env bash
# Build OCP, the Python binding of Open CASCADE Technology (OCCT), as a Pyodide wheel (prototype recipe).
# Usage: ocp.sh [--plib-fast] [--no-opt] [--freetype-src DIR] [-j N] EMSDK_DIR OCCT_SRC XBUILDENV_DIR MODULES WORK_DIR
#   Every version, URL, hash and flag that decides what is built is in kernel-pins.json beside this script: a bump of
#   OCCT, OCP or Pyodide edits that file only. The arguments are directories:
#   EMSDK_DIR      an emsdk with the pinned Emscripten installed and activated (the version Pyodide's own build used,
#                  `pyodide config get emscripten_version`: a side module must match its main module)
#   OCCT_SRC       OCCT's source at the pinned tag, unchanged (git clone --depth 1 --branch TAG <the pinned repository>)
#   XBUILDENV_DIR  Pyodide's cross-build environment (pip install pyodide-build==<pinned>; pyodide xbuildenv install
#                  --path DIR <pinned Pyodide>): CPython's headers, and the main module the wheel is checked against
#   MODULES        the OCP submodules to bind, one per line (ocp-modules.txt beside this script), or `all`
#   WORK_DIR       downloads, build trees, logs/ and dist/ (the wheel and its .sha256); a rerun resumes after the
#                  last step that finished with the same inputs
#   --plib-fast    OCCT's PLib.cxx with flags.plib_fast_patch, compiled with flags.plib_fast (SIMD) and linked ahead
#                  of OCCT's own: one file differs. Off by default: the default build compiles OCCT as released. SIMD
#                  in one function makes the whole module need WebAssembly SIMD (every current engine has it)
#   --freetype-src a checkout of FreeType at the pinned freetype.tag (Emscripten's port) for OCCT's fonts (text to
#                  shapes); without it OCCT is built without FreeType and Font_FTFont reports no font
#   -j N           parallel jobs (default: nproc); a job compiling the binding's largest files takes up to ~1.7 GB
#   --no-opt       skip Binaryen's pass (flags.wasm_opt), for a machine short of the memory it takes (~5.6 GB at
#                  its peak, ~20 min with BINARYEN_CORES=2); the wheel's version says so (+...noopt)
#   --keys         fetch and prepare, then print each later stage's key (what a CI cache of OCCT's build is keyed by)
#                  and stop
#
# The steps: fetch OCP's generated binding sources (an archive the OCP project attaches to its release) and the
# binding's header-only dependencies; prepare the binding's sources for the module list (OCP.cpp registers the
# listed modules only, the instantiated collections keep the entries whose types the list holds, and importing a
# module left out raises ModuleNotFoundError naming it and the list); build the OCCT toolkits those modules live in,
# static, position independent; compile the binding; link one Pyodide side module; check that every function it
# imports is one Pyodide's main module exports; optimise it with Binaryen (the emsdk's wasm-opt); write the wheel
# with the licences of all it contains, and its sha256.
#
# The list is the only input that changes what is bound: `all` builds the full binding, the same steps. A list that
# names a module OCP does not have, or leaves out one a listed module needs to import (a base class, a default
# argument), is refused before anything is built, naming both.
#
# Flags: kernel-pins.json's flags.common for every compile and the link (Pyodide's -fPIC -fwasm-exceptions
# -sSUPPORT_LONGJMP=wasm, and -fvisibility=hidden -fvisibility-inlines-hidden: OCP's own build sets both for the
# binding; set for OCCT too, so the module's inline and template functions are called directly instead of through
# an import of themselves that the loader resolves at run time); OCCT's CMake build type (Release: -O3 -DNDEBUG) and
# flags.occt after OCCT's own: -UOCC_CONVERT_SIGNALS, which OCCT's CMake defines and which makes each
# OCC_CATCH_SIGNALS a setjmp inside a try; with wasm exceptions and wasm setjmp together LLVM writes invalid
# WebAssembly for some such functions (ShapeCustom_BSplineRestriction::ConvertSurface: a br_table to a label that
# does not exist, "popping from empty stack"). A WebAssembly module has no signals to convert; OCCT's exceptions are
# C++ exceptions either way. flags.cxx for the binding.
#
# Licences of what the wheel contains, written into its .dist-info/licenses: OCCT (GNU LGPL 2.1 with the Open
# CASCADE exception 1.0; whoever ships the wheel offers OCCT's source at the pinned tag, and this script), OCP's
# generated sources (Apache-2.0), pybind11 (BSD-3-Clause), fmt (MIT), RapidJSON (MIT; OCCT's glTF writer), and
# with --freetype-src FreeType (the FreeType License).
set -euo pipefail

PLIB=0 FREETYPE_SRC="" JOBS=$(nproc) KEYS=0 NOOPT=0
while [ $# -gt 0 ]; do
  case $1 in
    --plib-fast) PLIB=1; shift ;;
    --freetype-src) FREETYPE_SRC=$(cd "$2" && pwd); shift 2 ;;
    -j) JOBS=$2; shift 2 ;;
    --keys) KEYS=1; shift ;;
    --no-opt) NOOPT=1; shift ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    --*) echo "ocp.sh: unknown option $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[ $# -eq 5 ] || { echo "usage: ocp.sh [--plib-fast] [--no-opt] [--freetype-src DIR] [-j N] EMSDK_DIR OCCT_SRC XBUILDENV_DIR MODULES WORK_DIR" >&2; exit 2; }
EMSDK_DIR=$(cd "$1" && pwd) OCCT_SRC=$(cd "$2" && pwd) XBUILDENV=$(cd "$3" && pwd) WORK=$5
MODULES=$4; [ "$MODULES" = all ] || MODULES=$(cd "$(dirname "$4")" && pwd)/$(basename "$4")
mkdir -p "$WORK"; WORK=$(cd "$WORK" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
die() { echo "ocp.sh: $*" >&2; exit 1; }
log() { echo "[ocp.sh $(date +%H:%M:%S)] $*" | tee -a "$WORK/logs/steps.log"; }
mkdir -p "$WORK/logs"

# ---- pins: kernel-pins.json, read once into shell variables ----
PINS=$HERE/kernel-pins.json
PINVARS=$(python3 -I - "$PINS" <<'PY'
import json, shlex, sys
p = json.load(open(sys.argv[1]))
def need(*path):
    v = p
    for k in path:
        if not isinstance(v, dict) or k not in v: sys.exit(f"ocp.sh: kernel-pins.json has no {'.'.join(path)}")
        v = v[k]
    return v
out = {
    "OCCT_TAG": need("occt", "tag"), "OCP_VERSION": need("ocp", "version"),
    "OCP_URL": need("ocp", "sources", "url"), "OCP_SHA256": need("ocp", "sources", "sha256"),
    "OCP_LICENSE_URL": need("ocp", "license", "url"), "OCP_LICENSE_SHA256": need("ocp", "license", "sha256"),
    "PYODIDE_VERSION": need("pyodide", "version"), "PYTHON_VERSION": need("pyodide", "python"),
    "PYTHON_TAG": need("pyodide", "python_tag"), "PYODIDE_ABI": need("pyodide", "abi"),
    "PLATFORM_TAG": need("pyodide", "platform_tag"), "EMSCRIPTEN_VERSION": need("pyodide", "emscripten"),
    "OCCT_BUILD_TYPE": need("flags", "occt_build_type"), "PLIB_PATCH": need("flags", "plib_fast_patch"),
    "WHEEL_NAME": need("wheel", "name"),
}
for k, v in out.items(): print(f"{k}={shlex.quote(str(v))}")
for k, key in (("COMMON", "common"), ("OCCTFLAGS", "occt"), ("CXXFLAGS", "cxx"), ("LINKFLAGS", "link"), ("OPTFLAGS", "wasm_opt"), ("PLIBFLAGS", "plib_fast")):
    print(f"{k}=({' '.join(shlex.quote(x) for x in need('flags', key))})")
deps = need("binding_deps")
print("DEPS=(" + " ".join(shlex.quote(n) for n in deps) + ")")
for n, d in deps.items():
    u = n.upper()
    print(f"DEP_{u}_REPO={shlex.quote(d['repository'])} DEP_{u}_REF={shlex.quote(d['ref'])} DEP_{u}_COMMIT={shlex.quote(d['commit'])} "
          f"DEP_{u}_LICENSE={shlex.quote(d['license'])}")
    print(f"DEP_{u}_PATCHES=(" + " ".join(shlex.quote(x) for x in d.get("patches", [])) + ")")
PY
) || exit 1
eval "$PINVARS"
PYMAJMIN=${PYTHON_VERSION/./}                  # X.Y -> XY
EXT_SUFFIX=cpython-$PYMAJMIN-wasm32-emscripten  # CPython's extension suffix under Pyodide
SO=OCP.$EXT_SUFFIX.so

# ---- toolchain checks: each mismatch named before anything is built ----
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null 2>&1
have=$(emcc --version | sed -n '1s/.* \([0-9][0-9.]*\) (.*/\1/p')
[ "$have" = "$EMSCRIPTEN_VERSION" ] || die "Emscripten $have is active; kernel-pins.json pins $EMSCRIPTEN_VERSION (Pyodide $PYODIDE_VERSION's)"
PYROOT=$XBUILDENV/$PYODIDE_VERSION/xbuildenv/pyodide-root
[ -f "$PYROOT/Makefile.envs" ] || die "no Pyodide $PYODIDE_VERSION cross-build environment in $XBUILDENV"
grep -q "PYODIDE_EMSCRIPTEN_VERSION ?= $EMSCRIPTEN_VERSION\$" "$PYROOT/Makefile.envs" ||
  die "Pyodide $PYODIDE_VERSION's cross-build environment is not built with Emscripten $EMSCRIPTEN_VERSION: $(grep 'PYODIDE_EMSCRIPTEN_VERSION ?=' "$PYROOT/Makefile.envs")"
grep -q "PYODIDE_ABI_VERSION ?= $PYODIDE_ABI\$" "$PYROOT/Makefile.envs" ||
  die "Pyodide $PYODIDE_VERSION's ABI is not $PYODIDE_ABI: $(grep 'PYODIDE_ABI_VERSION ?=' "$PYROOT/Makefile.envs")"
PYINC=$(echo "$PYROOT"/cpython/installs/python-"$PYTHON_VERSION".*/include/python"$PYTHON_VERSION")
MAIN_WASM=$PYROOT/dist/pyodide.asm.wasm
[ -f "$PYINC/Python.h" ] || die "no CPython $PYTHON_VERSION headers in $PYROOT"
[ -f "$MAIN_WASM" ] || die "no pyodide.asm.wasm in $PYROOT/dist"
[ "$(git -C "$OCCT_SRC" describe --tags --exact-match 2>/dev/null)" = "$OCCT_TAG" ] || die "$OCCT_SRC is not OCCT at $OCCT_TAG"
[ -z "$(git -C "$OCCT_SRC" status --porcelain --untracked-files=no)" ] || die "$OCCT_SRC has local changes; OCCT is built as released"
WASM_OPT=$EMSDK_DIR/upstream/bin/wasm-opt

FLAGS=("${COMMON[@]}")
VARIANT=base; [ -n "$FREETYPE_SRC" ] && VARIANT=$VARIANT-ft
STAMPS=$WORK/stamps; mkdir -p "$STAMPS"
key() { printf '%s\n' "$@" | sha256sum | cut -c1-12; }
done_() { [ -f "$STAMPS/$1" ]; }
mark() { touch "$STAMPS/$1"; }

# ---- 1. sources ----
SRC=$WORK/src; mkdir -p "$SRC"
fetch() { # url sha256 dest
  [ -f "$3" ] && echo "$2  $3" | sha256sum -c --quiet - 2>/dev/null && return
  curl -sSfL -o "$3.part" "$1" || die "could not download $1"
  echo "$2  $3.part" | sha256sum -c --quiet - 2>/dev/null || die "$1 does not match its sha256 in kernel-pins.json (got $(sha256sum "$3.part" | cut -c1-64))"
  mv "$3.part" "$3"
}
SOURCES_KEY=$(key "$OCP_URL" "$OCP_SHA256" "$(for d in "${DEPS[@]}"; do u=${d^^}; eval "echo $d \$DEP_${u}_COMMIT \${DEP_${u}_PATCHES[*]}"; done)" \
  "$(cat "$HERE"/patches/*.patch | sha256sum)")
if ! done_ "sources-$SOURCES_KEY"; then
  log "fetching sources (OCP $OCP_VERSION)"
  fetch "$OCP_URL" "$OCP_SHA256" "$SRC/OCP_src.zip"
  fetch "$OCP_LICENSE_URL" "$OCP_LICENSE_SHA256" "$SRC/OCP-LICENSE"
  for d in "${DEPS[@]}"; do
    u=${d^^}; eval "repo=\$DEP_${u}_REPO ref=\$DEP_${u}_REF commit=\$DEP_${u}_COMMIT; patches=(\${DEP_${u}_PATCHES[@]+\"\${DEP_${u}_PATCHES[@]}\"})"
    rm -rf "$SRC/$d"; git init -q "$SRC/$d"
    git -C "$SRC/$d" fetch -q --depth 1 "$repo" "$ref" || die "could not fetch $d $ref from $repo"
    git -C "$SRC/$d" checkout -q FETCH_HEAD
    [ "$(git -C "$SRC/$d" rev-parse HEAD)" = "$commit" ] || die "$d $ref is $(git -C "$SRC/$d" rev-parse HEAD), kernel-pins.json says $commit"
    for p in ${patches[@]+"${patches[@]}"}; do
      git -C "$SRC/$d" apply --check "$HERE/patches/$p" 2>/dev/null ||
        die "patches/$p does not apply to $d $ref: update it, or drop it from kernel-pins.json if $d no longer needs it"
      git -C "$SRC/$d" apply "$HERE/patches/$p"
    done
  done
  rm -rf "$SRC/OCP"; mkdir -p "$SRC/OCP"; (cd "$SRC/OCP" && unzip -q ../OCP_src.zip)
  [ -f "$SRC/OCP/OCP.cpp" ] || die "the OCP archive has no OCP.cpp at its top: its layout changed ($(ls "$SRC/OCP" | head -5 | tr '\n' ' '))"
  rm -f "$STAMPS"/prepare-*
  mark "sources-$SOURCES_KEY"
fi
if [ -n "$FREETYPE_SRC" ]; then
  # Emscripten's FreeType port, built from the given checkout instead of its download.
  export EMCC_LOCAL_PORTS="freetype=$FREETYPE_SRC"
fi

# ---- 2. the binding's sources for the list ----
OCPSRC=$WORK/ocp-src
LISTSUM=$([ "$MODULES" = all ] && echo all || sha256sum <"$MODULES" | cut -c1-12)
PREP_KEY=$(key "$SOURCES_KEY" "$LISTSUM" "$OCCT_TAG" "$(sed -n '/^# ---- 2\./,/^PY$/p' "$0" | sha256sum)")  # this step's own code
if ! done_ "prepare-$PREP_KEY"; then
  log "preparing OCP's sources for $( [ "$MODULES" = all ] && echo all modules || basename "$MODULES")"
  python3 -I - "$SRC/OCP" "$OCPSRC" "$MODULES" "$OCCT_SRC" <<'PY'
import os, re, shutil, sys, glob, hashlib
src, out, listfile, occt = sys.argv[1:5]
ocp = open(f"{src}/OCP.cpp").read()
# The generated OCP.cpp's layout, which everything below edits: a PYBIND11_MODULE(OCP, m) that first registers each
# module's enums and classes, then "// register modules" and each module's definitions.
if "PYBIND11_MODULE(OCP, m)" not in ocp or "// register modules" not in ocp:
    sys.exit("ocp.sh: OCP.cpp's layout changed (no PYBIND11_MODULE(OCP, m) or no '// register modules'): "
             "the preparation step in ocp.sh needs updating for this OCP release")
head, body = ocp.split("// register modules", 1)
# OCP's VTK and OpenGL modules have nothing to bind against here (no VTK, no OpenGL): dropped, as every Pyodide build does.
gl = lambda name: re.search(r"vtk|opengl", name, re.I)
every = [m for m in re.findall(r"register_(\w+)\(m\);", body) if not gl(m) and not m.startswith("collections_")]
if len(every) < 50:
    sys.exit(f"ocp.sh: found only {len(every)} module registrations in OCP.cpp: its layout changed")
known = set(every)
nofiles = [m for m in every if not (os.path.exists(f"{src}/{m}.cpp") and os.path.exists(f"{src}/{m}_pre.cpp"))]
if nofiles:
    sys.exit(f"ocp.sh: OCP.cpp registers modules without their <name>.cpp and <name>_pre.cpp: {' '.join(nofiles)}")
if listfile == "all":
    wanted, listname = list(every), "all"
else:
    wanted, listname = [], os.path.basename(listfile)
    for n, line in enumerate(open(listfile), 1):
        name = line.split("#", 1)[0].strip()
        if not name: continue
        if name not in known:
            sys.exit(f"ocp.sh: {listfile}:{n}: this OCP release has no module {name} (renamed or removed?); "
                     "fix or drop the line")
        wanted.append(name)
chosen = set(wanted)
new = sorted(known - chosen)

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
if not tk:
    sys.exit("ocp.sh: no src/*/TK*/PACKAGES.cmake in OCCT's source: its layout changed; the toolkit lookup in ocp.sh needs updating")
untk = sorted(m for m in chosen if m not in tk)
tks = sorted({tk[m] for m in chosen if m in tk})
open(f"{out}/toolkits.txt", "w").write(" ".join(tks) + "\n")
open(f"{out}/modules.txt", "w").write("\n".join(sorted(chosen, key=str.lower)) + "\n")
open(f"{out}/list-id.txt", "w").write(("all" if not absent else "m" + listhash) + "\n")
cpp = sorted(os.path.basename(f) for f in glob.glob(f"{out}/*.cpp"))
open(f"{out}/sources.txt", "w").write("\n".join(cpp) + "\n")
print(f"{len(chosen)} of {len(every)} modules, {len(cpp)} sources, OCCT toolkits: {' '.join(tks)}")
if untk: print(f"modules in no OCCT toolkit (headers only, or not OCCT's): {' '.join(untk)}")
if listfile != "all" and new: print(f"{len(new)} modules not in the list (unbound): {' '.join(new)}")
PY
  mark "prepare-$PREP_KEY"
fi
TOOLKITS=$(cat "$OCPSRC/toolkits.txt")
LIST_ID=$(cat "$OCPSRC/list-id.txt")

# Each later stage's key: what changes its output. A rerun redoes a stage only when its key changed.
HEADERS=$WORK/occt-headers-$OCCT_TAG
OCCT_KEY=$(key "$OCCT_TAG" "$OCCT_BUILD_TYPE" "${FLAGS[*]} ${OCCTFLAGS[*]}" "$TOOLKITS" "$FREETYPE_SRC" "$(sed -n '/^# ---- 3\./,/^# ---- 4\./p' "$0" | sha256sum)")
OCCT_BUILD=$WORK/occt-$OCCT_KEY OCCT=$WORK/occt-$OCCT_KEY-install
CXX="em++ ${CXXFLAGS[*]} ${FLAGS[*]} -w -I$OCPSRC -I$SRC/pybind11/include -I$SRC/fmt/include -I$SRC/rapidjson/include \
-I$OCCT/include/opencascade -I$HEADERS -I$PYINC"
# The binding reads OCCT's headers only: its key is OCCT's tag and toolkits, not OCCT's flags.
COMPILE_KEY=$(key "$PREP_KEY" "$OCCT_TAG" "$TOOLKITS" "${CXX//$OCCT/OCCT}")
OBJ=$WORK/obj-$COMPILE_KEY
LINK_KEY=$(key "$COMPILE_KEY" "$OCCT_KEY" "${LINKFLAGS[*]}" "$([ $NOOPT = 1 ] && echo noopt || echo "${OPTFLAGS[*]}")" \
  "$([ $PLIB = 1 ] && echo "plib ${PLIBFLAGS[*]} $(sha256sum <"$HERE/patches/$PLIB_PATCH")")")
OUT=$WORK/link-$LINK_KEY
if [ $KEYS = 1 ]; then echo "occt $OCCT_KEY"; echo "compile $COMPILE_KEY"; echo "link $LINK_KEY"; exit 0; fi

# ---- 3. OCCT ----
if ! done_ "occt-$OCCT_KEY"; then
  log "building OCCT $OCCT_TAG ($VARIANT, $OCCT_KEY): $TOOLKITS"
  FT=(-DUSE_FREETYPE=OFF)
  if [ -n "$FREETYPE_SRC" ]; then
    embuilder build freetype --pic >"$WORK/logs/freetype.log" 2>&1 || die "FreeType's port did not build, see $WORK/logs/freetype.log"
    SYSROOT=$(em-config CACHE)/sysroot
    FT=(-DUSE_FREETYPE=ON -D3RDPARTY_FREETYPE_DIR="$SYSROOT" -D3RDPARTY_FREETYPE_INCLUDE_DIR_ft2build="$SYSROOT/include/freetype2"
        -D3RDPARTY_FREETYPE_INCLUDE_DIR_freetype2="$SYSROOT/include/freetype2"
        -D3RDPARTY_FREETYPE_LIBRARY="$SYSROOT/lib/wasm32-emscripten/pic/libfreetype.a"
        -D3RDPARTY_FREETYPE_LIBRARY_DIR="$SYSROOT/lib/wasm32-emscripten/pic")
  fi
  emcmake cmake -S "$OCCT_SRC" -B "$OCCT_BUILD" -G "Unix Makefiles" -DCMAKE_BUILD_TYPE="$OCCT_BUILD_TYPE" \
    -DCMAKE_C_FLAGS="${FLAGS[*]} ${OCCTFLAGS[*]}" -DCMAKE_CXX_FLAGS="${FLAGS[*]} ${OCCTFLAGS[*]}" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DBUILD_LIBRARY_TYPE=Static -DINSTALL_DIR="$OCCT" \
    -DBUILD_MODULE_FoundationClasses=ON -DBUILD_MODULE_ModelingData=OFF -DBUILD_MODULE_ModelingAlgorithms=OFF \
    -DBUILD_MODULE_Visualization=OFF -DBUILD_MODULE_ApplicationFramework=OFF -DBUILD_MODULE_DataExchange=OFF \
    -DBUILD_MODULE_Draw=OFF -DBUILD_MODULE_DETools=OFF -DBUILD_ADDITIONAL_TOOLKITS="$TOOLKITS" \
    "${FT[@]}" -DUSE_RAPIDJSON=ON -D3RDPARTY_RAPIDJSON_DIR="$SRC/rapidjson" -D3RDPARTY_RAPIDJSON_INCLUDE_DIR="$SRC/rapidjson/include" \
    -DUSE_OPENGL=OFF -DUSE_GLES2=OFF -DUSE_XLIB=OFF -DUSE_DRACO=OFF -DUSE_TBB=OFF -DUSE_FREEIMAGE=OFF -DUSE_OPENVR=OFF \
    -DUSE_FFMPEG=OFF -DUSE_VTK=OFF -DUSE_TK=OFF -DUSE_EIGEN=OFF -DUSE_JEMALLOC=OFF -DUSE_D3D=OFF \
    -DBUILD_DOC_Overview=OFF -DBUILD_GTEST=OFF -DBUILD_SAMPLES_QT=OFF >"$WORK/logs/occt-cmake.log" 2>&1 ||
    die "OCCT's CMake failed (a renamed option or toolkit?), see $WORK/logs/occt-cmake.log: $(grep -m3 -A2 'CMake Error' "$WORK/logs/occt-cmake.log" | tr '\n' ' ')"
  if ! make -C "$OCCT_BUILD" -k -j"$JOBS" >"$WORK/logs/occt-make.log" 2>&1; then
    echo "ocp.sh: OCCT did not compile, see $WORK/logs/occt-make.log. The files that failed:" >&2
    grep -B1 -m20 ' error: ' "$WORK/logs/occt-make.log" | grep -E 'error:|Building' | head -20 >&2
    exit 1
  fi
  make -C "$OCCT_BUILD" install >"$WORK/logs/occt-install.log" 2>&1 || die "OCCT's install failed, see $WORK/logs/occt-install.log"
  mark "occt-$OCCT_KEY"
fi
# Every OCCT header, also of the toolkits not built: OCP's sources include some to resolve forward declarations.
if [ ! -d "$HEADERS" ]; then
  mkdir -p "$HEADERS.part"
  find "$OCCT_SRC/src" -path "$OCCT_SRC/src/Draw" -prune -o -type f \( -name '*.hxx' -o -name '*.lxx' -o -name '*.gxx' -o -name '*.pxx' -o -name '*.h' \) \
    -exec ln -sf {} "$HEADERS.part/" \;
  mv "$HEADERS.part" "$HEADERS"
fi

# ---- 4. the binding ----
if ! done_ "compile-$COMPILE_KEY"; then
  log "compiling $(wc -l <"$OCPSRC/sources.txt") binding sources ($VARIANT, $COMPILE_KEY), -j$JOBS"
  mkdir -p "$OBJ"
  { echo "all:"; while read -r f; do o="$OBJ/${f%.cpp}.o"; echo "all: $o"; echo "$o: $OCPSRC/$f"; printf '\t%s -c $< -o $@\n' "$CXX"; done <"$OCPSRC/sources.txt"; } >"$OBJ/Makefile"
  if ! make -k -f "$OBJ/Makefile" -j"$JOBS" >"$WORK/logs/compile.log" 2>&1; then
    echo "ocp.sh: the binding did not compile, see $WORK/logs/compile.log. The first errors:" >&2
    grep -m20 ' error: ' "$WORK/logs/compile.log" >&2
    grep -q -E 'Killed|signal 9|out of memory' "$WORK/logs/compile.log" && echo "ocp.sh: a compiler was killed (memory): rerun with a lower -j" >&2
    exit 1
  fi
  mark "compile-$COMPILE_KEY"
fi

# ---- 5. link, check, optimise ----
if ! done_ "link-$LINK_KEY"; then
  log "linking the module ($VARIANT$([ $PLIB = 1 ] && echo ', --plib-fast'), $LINK_KEY)"
  rm -rf "$OUT"; mkdir -p "$OUT"
  EXTRA=()
  if [ $PLIB = 1 ]; then
    # The patched PLib.cxx, compiled with the command OCCT's build used for its own, linked before libTKMath.a: the
    # archive's PLib object is then never taken (every symbol it defines is already defined).
    PLIB_REL=$(cd "$OCCT_SRC" && find src -name PLib.cxx | head -1)
    [ -n "$PLIB_REL" ] || die "--plib-fast: OCCT $OCCT_TAG has no PLib.cxx"
    mkdir -p "$OUT/plib/$(dirname "$PLIB_REL")"; cp "$OCCT_SRC/$PLIB_REL" "$OUT/plib/$PLIB_REL"
    (cd "$OUT/plib" && patch -s -p1 --dry-run <"$HERE/patches/$PLIB_PATCH" >/dev/null 2>&1) ||
      die "--plib-fast: patches/$PLIB_PATCH does not apply to OCCT $OCCT_TAG's $PLIB_REL"
    (cd "$OUT/plib" && patch -s -p1 <"$HERE/patches/$PLIB_PATCH")
    read -r DIR CMD < <(python3 -I -c 'import json,sys; e = next(e for e in json.load(open(sys.argv[1])) if e["file"].endswith("/PLib/PLib.cxx")); print(e["directory"], e["command"])' "$OCCT_BUILD/compile_commands.json")
    CMD=${CMD/"$OCCT_SRC/$PLIB_REL"/"$OUT/plib/$PLIB_REL"}
    CMD="$(echo "$CMD" | sed "s| -o [^ ]*| -o $OUT/plib/PLib.o|") ${PLIBFLAGS[*]}"
    (cd "$DIR" && eval "$CMD") || die "--plib-fast: the patched PLib.cxx did not compile"
    EXTRA=("$OUT/plib/PLib.o")
  fi
  LIBS=$(cd "$OCCT/lib" && ls libTK*.a | sed 's/^lib\(.*\)\.a$/-l\1/' | tr '\n' ' ')
  FTLINK=(); [ -n "$FREETYPE_SRC" ] && FTLINK=(-sUSE_FREETYPE=1)
  # The link's own optimisation is low (flags.link); Binaryen optimises the module below, once (flags.wasm_opt).
  em++ "${LINKFLAGS[@]}" "${FLAGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"} "$OBJ"/*.o -L"$OCCT/lib" -Wl,--start-group $LIBS -Wl,--end-group \
    ${FTLINK[@]+"${FTLINK[@]}"} -o "$OUT/linked.wasm" >"$WORK/logs/link.log" 2>&1 ||
    die "the link failed, see $WORK/logs/link.log: $(grep -m5 -E 'error|undefined' "$WORK/logs/link.log" | tr '\n' ' ')"
  EMJS=$(grep -rhoE 'EM_JS\([^,]+, *[A-Za-z_][A-Za-z0-9_]*' "$OCCT_SRC/src" --include='*.cxx' | sed 's/.*, *//' | sort -u | tr '\n' ' ')
  python3 -I - "$OUT/linked.wasm" "$MAIN_WASM" "${MAIN_WASM%.wasm}.mjs" "$EMJS" <<'PY' | tee "$OUT/imports.txt"
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
js = open(sys.argv[3]).read()  # the main module's JavaScript: Emscripten's library functions a side module may import
emjs = set(sys.argv[4].split())
fn = [f for m, f, k in imps if m == "env" and k == 0]
self_ = [f for f in fn if f in exps]
cxx = [f for f in fn if f.startswith("_Z")]
unresolved = [f for f in fn if f not in main and f not in exps and not f.startswith("invoke_")]
fromjs = [f for f in unresolved if f"_{f}=" in js or f"function _{f}(" in js]
oc = [f for f in unresolved if f in emjs]
missing = [f for f in unresolved if f not in fromjs and f not in oc]
print(f"functions {funcs}; env function imports {len(fn)}, of them C++ {len(cxx)}, defined in the module itself {len(self_)}; "
      f"from Pyodide's JavaScript {len(fromjs)}")
if oc:
    print("note: OCCT's EM_JS functions, which a side module cannot carry, stay unresolved (calling one fails, as in any "
          "Pyodide build of OCCT; OSD_MemInfo's heap query and Message_PrinterSystemLog): " + " ".join(sorted(oc)))
if missing:
    print(f"ocp.sh: {len(missing)} functions the module imports are not exported by Pyodide's main module (it would fail "
          "when one is called): an OCCT toolkit missing from the build, or a Pyodide/Emscripten mismatch:",
          *sorted(missing)[:50], sep="\n  ")
    sys.exit(1)
PY
  if [ $NOOPT = 1 ]; then cp "$OUT/linked.wasm" "$OUT/$SO"; else
  log "optimising (wasm-opt ${OPTFLAGS[*]})"
  "$WASM_OPT" "${OPTFLAGS[@]}" "$OUT/linked.wasm" -o "$OUT/$SO" >"$WORK/logs/wasm-opt.log" 2>&1 || {
    [ $? = 137 ] && die "wasm-opt was killed, most likely for memory (it needs ~5.6 GB): rerun where it has that much free (BINARYEN_CORES=1 or 2 lowers it a little), or with --no-opt"
    die "wasm-opt failed, see $WORK/logs/wasm-opt.log (a validation error there is a compiler fault in the module itself: $(grep -m2 -i -E 'error|invalid' "$WORK/logs/wasm-opt.log" | tr '\n' ' '))"; }
  fi
  mark "link-$LINK_KEY"
fi

# ---- 6. the wheel ----
DIST=$WORK/dist; mkdir -p "$DIST"
LOCAL=""; [ "$LIST_ID" = all ] || LOCAL=$LIST_ID
[ $PLIB = 1 ] && LOCAL=${LOCAL:+$LOCAL.}plib
[ -n "$FREETYPE_SRC" ] || LOCAL=${LOCAL:+$LOCAL.}noft
[ $NOOPT = 1 ] && LOCAL=${LOCAL:+$LOCAL.}noopt
VERSION=$OCP_VERSION${LOCAL:++$LOCAL}
log "writing the wheel, version $VERSION"
LICENCES=("$OCCT_SRC/LICENSE_LGPL_21.txt" "$OCCT_SRC/OCCT_LGPL_EXCEPTION.txt" "$SRC/OCP-LICENSE")
for d in "${DEPS[@]}"; do u=${d^^}; eval "LICENCES+=(\"\$SRC/$d/\$DEP_${u}_LICENSE\")"; done
[ -n "$FREETYPE_SRC" ] && LICENCES+=("$FREETYPE_SRC/docs/FTL.TXT")
python3 -I - "$OUT/$SO" "$DIST" "$WHEEL_NAME" "$VERSION" "$PYTHON_TAG-$PYTHON_TAG-$PLATFORM_TAG" "$OCPSRC/modules.txt" \
  "$OCCT_TAG" "$PYTHON_VERSION" "${LICENCES[@]}" <<'PY'
import base64, hashlib, os, re, sys, zipfile
so, dist, dname, version, tag, modules, occt_tag, pyver, *licences = sys.argv[1:]
name = re.sub(r"[-_.]+", "_", dname).lower()
info = f"{name}-{version}.dist-info"
labels = []
for p in licences:
    parent, base = os.path.basename(os.path.dirname(p)), os.path.basename(p)
    label = base if base.startswith(("OCP", "LICENSE_LGPL", "OCCT_LGPL")) else f"{parent}-{base}"
    labels.append(label)
expr = "LGPL-2.1-only WITH OCCT-exception-1.0 AND Apache-2.0 AND BSD-3-Clause AND MIT" + (" AND FTL" if any(l.endswith("FTL.TXT") for l in labels) else "")
metadata = "\n".join([
    "Metadata-Version: 2.4", f"Name: {dname}", f"Version: {version}",
    f"Summary: OCP, the Python binding of Open CASCADE Technology (OCCT {occt_tag}), built for Pyodide",
    f"License-Expression: {expr}", *[f"License-File: {l}" for l in labels], f"Requires-Python: >={pyver}", "", ""])
wheel = f"Wheel-Version: 1.0\nGenerator: ocp.sh\nRoot-Is-Purelib: false\nTag: {tag}\n"
files = [(os.path.basename(so), open(so, "rb").read()),
         (f"{info}/METADATA", metadata.encode()), (f"{info}/WHEEL", wheel.encode()),
         (f"{info}/OCP_MODULES.txt", open(modules, "rb").read())]
files += [(f"{info}/licenses/{l}", open(p, "rb").read()) for l, p in zip(labels, licences)]
record = [f"{p},sha256={base64.urlsafe_b64encode(hashlib.sha256(d).digest()).rstrip(b'=').decode()},{len(d)}" for p, d in files]
record.append(f"{info}/RECORD,,")
out = f"{dist}/{name}-{version}-{tag}.whl"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p, d in files + [(f"{info}/RECORD", ("\n".join(record) + "\n").encode())]:
        zi = zipfile.ZipInfo(p, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, d)
digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
open(out + ".sha256", "w").write(f"{digest}  {os.path.basename(out)}\n")
print(out, os.path.getsize(out), "bytes, sha256", digest)
PY
