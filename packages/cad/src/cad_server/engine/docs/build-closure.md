# Build closure

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model's document is its own cache, as a FreeCAD document is: opened, it is what was last
computed, and only what changed is computed again. It is kept in the engine's cache (**The
cache**), and written as the model's xbf where one is declared, the same bytes. Its main label names what
wrote it (`cadgen.engine xbf/9 (cadgen <release>)`, `document.Loaded.writer`) and holds the model's build
closure (`previous.py`, a `TDataStd_AsciiString` beside the writer's, schema `cadgen.engine
closure/2`), pointers and digests only (law 1), and nothing of a version control's -- the engine calls
no git. It names what the document was built from and what built it, the toolchain:

```
schema    "cadgen.engine closure/2"
engine    {"release": "cadgen 0.10.0", "format": "xbf/9", "digest": ...}  the format (keyed); the release and
                                                                     the engine's code digest (information only)
libs      {"build123d": "0.13.0", "OCP": "8.0.1.1",                   geometry and materials libraries (keyed);
           "bd_materials": "...", "threejs_materials": "..."}         OCP leads with the OCCT it wraps
platform  {"python": "3.12.10", "system": "Darwin", "arch": "arm64"}  the system and architecture (keyed),
                                                                     Python (information only):
                                                                     platform.python_version(), .system(), .machine()
source    {"kind": "script", "path": "../src/tom.py", "function": "tom"}
modules   [["../src/lib/arm_parts.py", "9f3c..."], ...]
inputs    [["file", "../STEP/gripper.step", "c0de..."], ["read", "../src/lib/ids.json", "77ab..."], ...]
bodies    how many bodies the model is
key       one digest over the format, libs, system and architecture, and the code (source,
          modules and inputs); null where the closure cannot say all the model is made of
```

Beside it on the main label, a document whose build made an `animation()` holds the compiled
tracks as a second build record (**Animations**); the closure neither counts nor keys them: they
are what the code the key covers made.

Every path is relative to the xbf's folder (the script's, for a model that declares none). `modules` lists each first-party module the
script's load imported or the model reaches, with a digest of what the model reaches in it: its
functions' code objects with no line tables or docstrings, its classes, the values its bindings
hold (a path value inside the script's folder relative to it), and, for a module that falls back
to its bytes (**Body retention**), each file of its import closure by its bytes. A comment or a
blank line changes no digest; a module the model loads and does not reach holds the empty one.
`inputs` lists every file a body read -- through the engine (`file`: `step.read`, `xbf.read`,
`stl.read`, build123d's importers), itself (`read`, a `null` digest for one it found missing;
a motion's function's reads too, **Configuration sequences**), or a text's font (`font`) -- by its digest; a file read past the engine's readers leaves the key
null (**Body retention**). `cad xbf inspect DOC` prints the closure, `cad.inspect(doc)` and
`document.Loaded.closure` read it.

**When the toolchain or the format moves.** The key covers the document format
(`previous.FORMAT`), the kernel and library versions (`libs`: build123d, OCP,
bd_materials and threejs_materials), the operating
system and the architecture, along with the model's code and inputs. An arm64 kernel and an
x86-64 one write other bytes of one model; a system, architecture or library change rebuilds it,
saying what moved (`rebuilt: arm64 became x86_64`). The release (`engine.release`, spelled
`cadgen <release>` as every document has spelled it) and
Python version (`platform.python`) are recorded in the closure but not keyed: a change to either
alone does not rebuild. The engine's code digest is information only too; an engine edit that
leaves the written document alone keeps every xbf current. `FORMAT` is bumped deliberately when
the stored representation changes. A new format or build key can invalidate reuse for a new
build; keeping a saved document readable is a separate obligation (**Document compatibility**
below). Earlier formats also used this marker for changes to what the build key covers. The bumps so far:
`xbf/2`, the key left the release, the engine digest and numpy, and the closure its commit;
`xbf/3`, the mechanism subtree took AP242's form (**Kinematics**); `xbf/4`, a function
motion's samples are made for linear interpolation (**Configuration sequences**); `xbf/5`, files read by motion
functions join the closure (**Configuration sequences**); `xbf/6`, the closure counted the build's
animations, and a document with any was not taken; `xbf/7`, the compiled animations are a build
record on the main label, the closure counts none, and an animated document is taken like any
(**Animations**); `xbf/8`, the closure names its toolchain (`closure/2`: system and architecture
join the key; release and Python are recorded); `xbf/9`, materials use native bd_materials
physics and `PbrProperties`, and both material libraries join the key.

**Document compatibility.** The engine reads `xbf/8` and `xbf/9`. Loading an `xbf/8`
document converts its persisted material metadata to native material data in memory before
viewing, inspection, snapshots, import or export. No model source is needed or executed.
Geometry, placements, names, appearance, physical meaning, painted faces, mechanism and animation
data remain the saved document's. Reading a current `xbf/9` is unchanged; formats outside this
supported set are refused with a clear error.

The conversion is idempotent. It leaves the original build closure and toolchain provenance
unchanged: metadata conversion does not mean the geometry was built by the current kernel.
A separate migration record identifies the conversion (`Loaded.migration`, `Source.migration`)
without replacing that provenance. Opening a file never rewrites its bytes. A cached snapshot
is read the same way without rewriting its bytes, changing its record or advancing its revision.
An unsupported or failed conversion preserves the original bytes and cache record.

To keep an upgraded file, explicitly export the converted document to a different XBF path:

```bash
cad xbf export saved-v8.xbf upgraded-v9.xbf
```

This serializes the complete upgraded XCAF document, including its separate migration record,
and replaces the destination atomically only after success. Export back to the source path is
refused. The migration record retains the original file path and its closure's relative-path
base, so saving in a different directory does not silently rebase the original build provenance.
A cached document exported by id to XBF writes the upgraded document too, preserving its known
document id and source script. Historical caches did not record the declared XBF folder: their
closure base is explicitly unknown, never guessed from the export destination. Export over the
engine's original cache file is refused. The existing
refusal of ordinary current-format XBF-to-XBF translation remains. The viewer's `original`
download of an opened XBF file returns its original bytes, even when the displayed document was
converted in memory; use the explicit export above to persist the conversion.

Saved-document access is separate from build reuse. Explicit source execution compares the
current format, material libraries and other build inputs with the original build key and
builds normally when they differ. No build closure is restamped to manufacture a cache hit.
The JSON identity migration (**Identity migration**) is independent of document contents, and
this data conversion restores no retired Python authoring API or class.

Before a body runs or is replayed, the build makes the closure again -- the script loaded,
its modules digested, each input hashed again -- and compares its key with the one the model's
document holds: this worker's own, the document it last built or took (`"from": "memory"`), else
the engine's cache file of it (`"from": "cache"`, **The cache**), every model alike. The same key,
in a cache file written by this engine that reads whole, and the body is not run: the report says
`cache: {"used": true, "from": "cache"}`, `memo.bodies_loaded` the bodies the document is, `bodies`
the root `loaded`, `timings` the key (`key`) and the read (`read`). A later build in the same worker
takes it from memory without reading it: one taken, or one this worker built, so an unchanged warm
build costs what a restart's second build does, the key alone (the w16: 59 s replaying, against
under a second), and the declared files' translation and compare. Its bodies' memo entries count as
used by that build, as a replay's do, so an edit after any number of them still replays what it
leaves alone. The key alone decides: a declared file, the model's xbf among them, is never read to
take the model, and one moved, deleted or edited by hand changes nothing of it -- a model taken writes
its declared files after, exactly as `cad <type> export` would (**Exports**), so that file is written
again from the document, and every file `written: false` where each holds its bytes already.
Anything else builds as before, and `cache.reason` says why: the cache holds none of it, written
by another engine or program, a cache file that does not read, no key in it, or what changed, by
name (`cache.changed`, each change; the CLI prints `rebuilt: ../src/lib/arm_parts.py changed`): a
module changed, is new or is no longer imported, an input changed or is missing, the format, a
library, the system, the architecture or the source moved.
`CAD_ENGINE_MEMO=0` and `CAD_ENGINE_BODIES=0` turn it off with the rest of retention.

The document is taken whole or not at all, never one body's part of it. OCCT's BinXCAF
reader does not give back the doubles it was given: it makes each direction and placement
anew, and a direction made again is normalized again, a rotation orthogonalized again,
one unit in the last place apart. Measured on the corpus: an `l_bracket` read and saved
is four doubles apart, and `motorbike` read and saved twice is 3,839 bytes apart from
once (no fixed point). A document holding a body's result read back would drift from the
cold build's bytes, build after build. So what is written is always made from what this
process's bodies made, and a document read is never written or patched: the first edit
after a restart runs the model, and writes the cold build's bytes. A taken document has
no worker that built it: `made_by` is null until a build of it runs.
