# Body retention

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A body -- a model's, or a `@memo` call's (**Memo functions**), whose key also holds its
arguments -- is one coarse entry above its calls, kept in the worker's memory
(`kernel/memo.py`, `body`). Its key is what it is made of:

- the symbols its function reaches (`sources.py`, `Symbols`): the global names
  its code and the code nested in it load, read through module attributes, its
  defaults and closure cells, and from there, transitively, every first-party
  function, class, child model and value. A function counts by its code: its
  instructions with their constants and names, its variables, arguments and
  flags, but not its file, its lines or its docstring. A class counts by its
  bases and its attributes. A value counts by a canonical form: numbers,
  strings, containers, enums, build123d vectors, locations and colours, numpy
  arrays, first-party dataclass and class instances. Each global binding the
  code reads counts as what it is bound to, by the module that holds it, so
  rebinding a name is an edit. The walk stops at what is not first-party (the
  standard library, build123d, OCP, numpy): the engine's own code covers those.
  Library code is what lies in the interpreter's library folders
  (`trace._library_roots`), never its whole prefix: a project inside its own
  virtual environment's folder is first-party, and a model script that does lie
  in a library folder is said on the build's log, since its edits rebuild nothing;
- every file it reads through the engine, by its bytes: `step.read`, `xbf.read`, `stl.read`,
  and build123d's importers (`import_step`, `import_brep`, `import_stl`), which the memo keys
  as it keys the engine's readers;
- every file it reads itself, observed, by its bytes: an audit hook on `open`
  (`kernel/memo.py`, `_audited`) hears each file the body opens for reading
  (`open`, `json.load`, `Path.read_text`, `np.loadtxt`), Python's own files
  aside (a `.py` or `.pyc`, one of the standard library or an installed
  package). When the body returns, each is held as its size, mtime and blake2b
  digest, or as missing. On the next build a file with the same size and mtime
  is the same; one whose stat moved is hashed again, and the same bytes keep
  the body (and the new stat); other bytes, or a file gone or come, run it. A
  file opened only for writing is an output, not an input. A pipe, a socket or a
  device has no bytes to hold: the body runs on every build, and the report's
  `retention.fallbacks` names the file. `retention.reads` lists, per body, the
  files it read;
- the engine's own code.

A model's inputs are its code, what it reads through the engine, and every file
its body reads, observed, by their bytes. A file read past the engine's readers is read
in C or C++, where the hook on `open` hears nothing, into a shape no key names: build123d's
`Mesher.read` and the OCCT readers a model may drive itself
(`STEPControl_Reader.ReadFile`, `STEPCAFControl_Reader.ReadFile` and `.Perform`, IGES's
readers, `RWStl.ReadFile_s`, `StlAPI`, `BRepTools.Read_s` and `BinTools.Read_s` given a
path, `RWMesh_CafReader.Perform`: glTF's and OBJ's; `kernel/memo.py`, `_READER_TARGETS`).
A body that calls one is never retained, so any edit runs it whole, and `retention.fallbacks`
names the call: `reads ../part.brep through OCCT's BRepTools.Read_s: its body is never retained
(any edit runs it whole); use step.read/xbf.read/stl.read`. (build123d's `import_step`,
`import_brep` and `import_stl` are not on that list: the memo wraps them as operations keyed by
the file's bytes, as the engine's readers are, so a body that calls one is kept.) The file it named is one of its
inputs all the same, held to its bytes (a read of what is no regular file leaves its closure with no
key): a build with nothing changed takes its document, after a restart too, and one after the file
changed builds it. What the engine
cannot see is the author's: the clock, environment variables, randomness, a file only
tested for (`Path.exists`, `os.stat`: an open is heard, a lookup is not), a folder listed
(`glob`, `os.listdir`: a file added to it is not heard), and a file a C library opens for
a reader not on that list. The engine hears Python's `open`, its own readers and the calls on
that list, and none of the rest: no interposer on the C library's `open` hears every open by
any code (an OCCT reader of any name, a C extension's own reader, FreeType loading a font
outside a text), every folder listing, environment variable or program a model's code used.

A module falls back to its bytes, and those of every first-party module it
imports, wherever the walk cannot follow a reference by its value: a `getattr`,
`setattr`, `hasattr` or `delattr` with a computed name, `globals()`, `locals()`,
`vars()`, `eval`, `exec`, `compile`, `__import__` or `importlib` in a function
the body reaches (that function's module falls back); a `from x import *`; a
first-party module the code holds as a value (stored in a local it uses other
than to read attributes, passed, or put in a container); a module a function
imports when it runs that the script's load does not import (whether it is in
memory would depend on which bodies ran); a value with no canonical form (a
shape made at import, an open file). Where no module holds what cannot be
keyed, the body always runs. The report's `retention` gives the time keys took
and, per body, each fallback with its reason.

When the key is what it was in the body's last run in this worker, the body is
not called. That run is replayed instead: each entry it hit or made is bound to
this run as a hit binds it, and each feature it recorded is recorded again, in
order. The result is the same live objects, as the body returned them. The trace
is the one a run leaves, so names, the xbf and the caller's own calls come out as
if the body had run. A body that ran a call plain, or whose entries are gone, runs.

Beside a model body's run the worker keeps its **harvest** (`kernel/memo.py`, `harvest_of`):
what the build made of the result's joints, mechanism states, configuration sequences (a
function's samples) and animations (`document.Harvest`), with the tree it was made of (each
prototype's TShape, label, colour and placement) and the files the sequences' functions read.
The harvest is a function of the result as the body returned it and of the code that made it,
which the body's key covers: a function of time is code the body reaches, wherever it is
defined. So a build that replays the very run the harvest was made from, to the same tree, and
whose functions' files hold their bytes, hands it back instead of sampling again; the report
says `"harvest": "reused"` (`"run"` where it was made), and `cache.reason` ends `the harvest
reused`. A body that ran makes a record with none, a verifying build harvests afresh, and
functions that read what cannot be held to its bytes are sampled on every build. It is memory
only, gone with the body's record, and what it writes -- the xbf's mechanism, animations record
and closure, the GLB, the served structure -- is a fresh harvest's, byte for byte. On tom, a
no-op's `collect` went from 1.50 s to 0.03 s, and the run from 2.47 s to 1.01 s.

Retained bodies follow the memo's retention: what the last four builds used. An
edit to a constant or a function re-runs the bodies that reach it, and the
bodies that hold their results. A comment, a blank line or a docstring re-runs
nothing. An edit to the root re-runs the root alone. A changed input file
re-runs the body that reads it and the bodies that hold its result. The
report's `memo` counts `bodies_run` and `bodies_skipped`, and `bodies` says of each
body of the model how it went: `run` or `replayed`.
`CAD_ENGINE_BODIES=0` turns retention off and nothing else. Otherwise a body
must be a function of its inputs: a body that reads the clock or the environment
is not seen to change, and nor is state one body leaves in a module for another
(a registry it fills). A
replayed body's features keep the `file:line` of the run that recorded them,
so after a line-only edit the provenance the worker serves can name a line that moved.

Keys are worked out once a build, for every body the build asks about, against
the namespaces as they are when the first body asks. A code object is read once
per value of it (a module loaded again makes equal code objects), and a file's
dynamic spots once per digest, in the worker's memory.

Measured on a 60,000-call model whose 14 bodies all ran, the logging added
nothing measurable to the build (body 12.4–12.6 s, against 12.7 s with retention
off). The logs do keep about a million more objects alive (2.6 million against
1.6 million). The worker's cyclic collection after each build has to walk them.
Measured with retention on, that collection takes 2.0–2.2 s on a 987-part model,
about 1.3 s of which it also takes with retention off, and 0.7–0.8 s on a
619-part model. It runs after the answer, so only a build sent while it is still
running waits for it.

The read hook costs nothing measurable: on a small model, built in-process, a
no-op took a median 50–51 ms and an edit 0.89–0.95 s with the hook, against
51 ms and 0.89 s with no hook installed.
