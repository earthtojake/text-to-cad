# Document lifetime

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model's document is its `.xbf`: every run writes it (law 10), and a document outlives the worker that
built it, the engine's memory and the engine itself, and lives until a person deletes it (**Delete**;
[models.py](../models.py), the library's `cad.engine.serve`). What the engine knows of a model comes from a run
alone (law 21): a run of its script pushes the model's code, its key and its document, and outside a run the
engine reads and watches no script and runs nothing -- a file's bytes, which are the disk, and the registry's
records, which runs wrote, are no model's code. A document's state (`models.STATES`, what `cad server status`
lists):

- `live`: a live worker holds it, with its memo and its trace: its page is the model, its parameters editable
  and its provenance asked of that worker.
- `held`: no worker holds it, and its `.xbf` is there: the engine answers it from that file, as it answers any
  file -- a page reads it by its id and reads it again when its bytes change, `cad <type> inspect`, an export and
  a snapshot by its id go to the documents worker with its path (`Daemon.document`), and what made an element is
  null (law 7: provenance is the worker's).
- `building`, `failed`: its build now, or its last one.
- `unsaved`: no worker holds it, and its `.xbf` is gone (deleted or moved by hand, or never written): the one
  state that says to build it again, with the command.
- `detached`: its `.xbf` is gone and so is the script it points at (moved, deleted): listed in Recents, saying
  so, until the person deletes it. Nothing removes it on its own. A shape handed over is never detached:
  nothing builds it again.

**Two kinds.** A function in a file is a model: the registry points at its script, and its document is
its `.xbf`. A shape is handed over (**Shapes handed over**), and its document is its `.xbf` too. Nothing
else is kept, and how is not the author's to choose: every document is recorded alike, and the decorators and
`model(shape, ...)` take no store (`store=` is an unexpected keyword argument, as any other). A function in no
saved file (a notebook cell, a REPL, `python -c`) is refused, with the words that hand its shape over instead
(`model(shape, name=...)`).

**Shapes handed over.** `model(shape, name="plate")` (`api.hand_over`) makes a document of any
build123d shape a program holds, from a script or a REPL. In the caller, the shape is made a
document as a build makes one (`document.collect`, `to_xcaf`) and serialised (`document.to_bytes`),
the declarations on it with it -- its joints, mechanism states, configuration sequences and
couplings -- and its GLB animations, passed as `animations=[...]` (the `animation()` builders, each
on the shape or a part of it), since there is no body to declare them in. The daemon (`{"op":
"shape"}`, `Models.hand_over`) reads the bytes through the documents worker, writes them as its `.xbf` (at
the path given, else `<name>.xbf` beside the calling script or in a REPL's working folder; the caller writes it
where the engine could not), serves its page from that file, and records it as `kind: "shape"`, its scope as
`home` and the program that handed it over as `program` (none from a REPL or a notebook), from which every
surface words it: a program the engine did not run showed it, so no command builds it again. `name=` is
required; its id is its `.xbf`'s. The handle's `.shape` is the shape passed. Called inside a model's body it is
refused: a body returns its shape.

**The registry.** One record per document the engine built, and per CAD file a page opened,
`documents/<id>/document.json` in the state folder ([registry.py](../registry.py); the
distribution names the folder, `places.state_dir`): it points; a document's bytes are its file's.
A model's id is its `.xbf`'s (**Model ids**), so the model's record is that file's record: one record, one
row, one card. Every record has one shape, `{schema, id, kind, root, home, entry, namespace, name, fingerprint?,
module?, relocated?, revision, built, created?, facts?, saved?, version?, aliases?, program?, python?, with?,
opened?, pinned?, preview?}`, and holds what a restart needs and no more. `kind` says what it is: `model` (`home`
and `entry`, its script and function; `saved`, its `.xbf`; the command that builds it again is `cad run` of its
home, with the requirements its last run's `cad run --with` was given, `with`, or, where its last run was in a
Python of its own, `python`, that Python and its home), `shape` (a shape handed over: `saved`, its `.xbf`;
`program`, where there was one, names the program that showed it, and nothing builds it again) or `file` (any
other CAD file a page opened: its path, `opened` and `pinned`, never a revision or bytes). A model's and a shape's
hold their revision and when they were built, their name, a build's facts (what the delta says against; a
shape's, its parts' occurrences alone, counted from the structure handed over) and the `.xbf`'s version as the
engine wrote or kept it (`version`: `mtime_ns-size`, `registry.file_version`), which a run takes the model from
(**The store**); a file's its parts' occurrences and the file's version they are of (`facts`: `{parts, version}`,
`Registry.counted`), written only where the engine already holds the document: an `.xbf` it exports, from the
document it writes it from (`Models.exported`; a file with no record is given one, with no `opened`, which no list
shows until a page opens it); any other `.xbf` or STEP from the read the engine made because a page opened it.
Nothing is ever read to count. Recents lists that count as a row's `parts`, while the file is that version
(`cad_server.viewer.recents`). An `.xbf` exported to another path, or copied, is another file, so another
document with its own id and card. Any record keeps its Recents picture (`preview`, UI state: the PNG under
`recents/thumbnails`). `created` is when the record was first made -- a model's first run, a shape's first
hand-over, a file's first open on a page -- kept through every rebuild and reopen (the home's Created column);
a record from before the engine kept it has none, and every reader takes that as null. Its closure is its
document's own (**Build closure**): it is not copied here. Every path in it is relative to its one `root`, so a
record moves by one field. It is written synchronously as a build registers, and only when a field differs: an
unchanged build rewrites nothing; each write is then told to `registry.OBSERVERS`, never waited on. After the
independent startup identity migration below, it is read on demand: an id no worker holds (after a restart) is
answered from its record -- its `.xbf`, `unsaved` with its command, or `detached` -- and nothing runs. The
registry is the ids' reverse map, never their authority (`ids`). `namespace` equals `root` (the script's folder,
a shape's scope, a file's folder), and `name` is the explicit name or the entry function; `entry` still names the
Python function. A model records SHA-256 of its script's bytes on each run (`fingerprint`; files and shapes have
none) and its Python module qualifier (`module`). Recents passes `namespace` and `name` through (`CadRecent`): a
named model's row shows its name. Two models that write one `.xbf` share its id and its record: the last build
wins.

**Re-attachment.** A run's models with nothing to take up -- no document its worker built or took,
and no record of their own at their id (their script moved, or new) -- are asked of the daemon in one request
before the worker reads any `.xbf` (`build._reattach`, `Models.reattach`, `identity.reattach`), of the engine that
runs the worker, never of one it would start; a model with a record of its own costs a record's read. The daemon
reads the registry once for all of them, parsing only the records whose text holds one of their fingerprints, for
model records with the same name, function and script fingerprint whose script is gone from its path -- or is
there as this very script, under its id from before its id was its `.xbf`'s, or under another spelling, a
symlinked folder or a case-only rename: a move. A record whose script is there as another file is the original of
a copy, and is never adopted. One candidate is adopted; of several, the most recently built (the id breaks a
tie), the choice logged; none, and the model is a new document. The record is re-pointed under the new id with its
history, creation time, pins and thumbnail, its old id among its `aliases` (`identity.repoint`): the new record
first, and only then is the old one forgotten, so a stop at any step leaves the old identity whole. `relocated`
keeps the script and module its `.xbf` was built from, where that is another: paths and module qualifiers are
projected for the closure comparison alone, never written into its XBF; its code, modules, inputs and toolchain
are checked all the same, and a fresh build clears it. Nothing reads or runs a script outside a run but the
migration's one pass: a fingerprint filled.

**Identity migration.** At engine start, before the daemon is reachable, `identity.migrate` makes
one pass over the records' JSON, independent of document format validation. It fills a missing
`namespace`, `name` and a model's `fingerprint` (its script's bytes; null where the script is gone,
until a run supplies one), moves each record identified by the earlier `uuid5(NAMESPACE, "key::" + key)`
formula to its folder/name id, and moves each model's and shape's record that names its `.xbf` (`saved`) from
its id before ids were the file's (`identity.former`: its script and function, or its folder and explicit name)
to that file's id (`identity._to_file`): what a record of the file there held of a person's use of its card -- its
creation, opening, pin and picture -- carried (`identity.carry`), the old id kept among its `aliases`, and the
file's version as the engine wrote it, where that file's record said so, kept, so its next run takes it. A record
that names no `.xbf` is moved by its next run (`Models.record`, with the same carry). An id from before is looked
up among the records' `aliases` wherever an id is named -- a page, `cad model <op> ID`, `cad delete` -- and answers
as the document it moved to (`Registry.resolve`: the records read once, then kept up as they are written). It reads
JSON and, only to fill a fingerprint, a script's bytes: it imports no kernel and parses or rewrites no XBF. A second
pass writes nothing. A record that does not read is skipped, never deleted, and listed in the pass's one log line
(`identity migration: filled N, moved N, skipped N`, then each skipped record and why), which `cad server status`
says too while that engine runs (a started engine's stderr is no one's); a pass with nothing to do says nothing,
and a pass that fails never keeps the engine from starting.

A record's `revision` is its closure's key (the same code, the same revision, after a
restart too) -- digested with the document's parameters' record where it records any (`models.revision`,
**Parameters**) -- or a token of the build's own where the closure has none. A served document's
generation (its structure's `version`, which a page waits on and the viewer's export compares)
is a token of its build's own: a rebuild is a new generation, and no generation is a counter that
a restart starts again. A document is what its last run made: a run of the same revision in the worker
that holds the last build (nothing ran, or it ran to the same bytes) keeps its generation, so a page
waiting on it is not woken and an export of the revision it shows still writes it. Recents is the registry's view (`cad_server.viewer.recents`): pinned
first, then by last activity, the later of a row's `opened` (a page opened it) and `updated` (a
file's time on disk, a model's run), each row carrying both; a model's script is never read for it.

**The store.** A model's store is its `.xbf`; the engine keeps no copy of it. Its cache folder (`places.cache_dir`:
`CAD_CACHE_DIR`, else `$XDG_CACHE_HOME/cad`, else `~/.cache/cad`) holds only what it derived from a document and
can make again, under that document's folder, keyed by its bytes: a KiCad board's plot, refilled pours, DRC and
kept exports, `documents/<id>/kicad/<key>/` (`formats/kicad/poured.folder`), and a manufacturing check's kept
results, a model's and a file's (`documents/<id>/checks/`, `checks.Disk`), removed with the document
(`Registry.delete` removes `documents/<id>` whole). The folder is shared with any 0.7 install's store: the engine
reads, writes and removes only under `documents/` there (its processes' bytecode is under `pycache/`), and lists,
counts and removes nothing else (`cad cache clean` neither). A record moved to its file's id has what the cache
folder kept under its old id removed, the `document.xbf` an earlier release kept there among it.

A run takes the model from its `.xbf`, every model alike. A fresh worker -- after a restart, or once the script's
worker retired -- reads the model's `.xbf` before its body runs (**Build closure**), only while the file is the
one the engine wrote: its version is the one its record names (`build._written_by_engine`). With the key the model
has now, the document is taken whole and nothing runs (`cache: {"used": true, "from": "xbf"}`; the CLI's `took
tube.py::tube cold in 0.42s: its .xbf holds the model's key`), its bytes kept as they are, the file never written
again; a file edited, replaced or copied over since, or any other key, builds the model, which writes its `.xbf`
again, and says why. A later unchanged run in that worker takes it from memory, as it does a document the worker
built itself: no body runs or is replayed. A model taken writes its other declared files all the same, as exports
of the document it took (**Exports**): each translated, compared with the file, and written only where it differs
or is missing, so a declared file someone deleted or edited is written again from the document with nothing run.
A verb given an `.xbf`'s path reads the file, in the documents worker (`Daemon._routed`); a page given it serves the
model while a live worker holds it (`serve.Server.add`), else the file, as it serves any file: its version is the
file's, it is read again when the file's bytes change (**The page's route**), and it names no model -- no
`made_by`, no worker kept warm.

An `xbf/8` `.xbf` is converted in memory when read (**Document compatibility**). Viewing, inspection, snapshots,
imports and exports require no model source or execution. The file's bytes, record and revision remain unchanged;
loading a conversion rewrites nothing. Unsupported or failed format conversion preserves those bytes and that
record and reports a clear error. Explicitly running the model still compares the current build key and rebuilds
where it differs.

**The last run.** A document is what its model's last run made, and that is all the engine knows
of the code: it never compares a script, a module or an input file on disk with what a build read,
and no surface -- the page, `status`, `inspect`, `export`, `snapshot`, `cad_show` -- says whether
the code has changed since. When to run the code again is the agent's call (`cad run`), and
nothing reruns on its own. What the engine knows from its own last run it says: a document whose
last run failed is served as its previous good build, and every verb that reads it by its id
(`export`, `snapshot`, `inspect`, with a ref or without) says so once on stderr (`cli.told_state`,
from `model_info`) -- "the last run of turbine failed; exporting its previous good build; fix it
and run `cad run …/turbine.py` to update it" -- and goes on: a notice, never a refusal. `cad server
status` ends that document's line with "serving its previous good build"; an `unsaved` one names
the command that builds it again (**The rebuild command**).

**Kept until deleted.** Nothing removes a record on its own: a model's whose `.xbf` is gone stays, `unsaved`,
listed as a missing file is, until a person deletes it (**Delete**). An unsupported document format or a failed
saved-format conversion preserves the file and the record (**Document compatibility**).

**Delete.** A document stays until a person deletes it: `cad delete DOC [DOC ...]` (each DOC a
document's id, a model's script -- every document recorded of it, a shape it handed over among
them -- or the path of a CAD file opened before), or the home's Delete on a model's row. Both are
one function (`models.delete`): what the engine holds of the document goes first, when an engine
runs (`Models.forget`: its row, the server's copy and its page; a live document's worker keeps its memo, and
its next run registers the document again), then its record and what the cache folder derived of it
(`Registry.delete`). Nothing of the person's is touched: a model's script, its `.xbf` and its other declared
files, and an opened file, stay where they are; a file's row on the home
says Remove, which forgets its entry alone. `cad delete` prints a line per document deleted,
`deleted <name> <id>` (`--json`: `{"ok": true, "deleted": [{id, name, kind}]}`), never starts an
engine, and refuses a DOC that names nothing recorded, by name and before anything is deleted
(exit 2).

**Drain.** Before the supervisor stops a worker -- the count cap's least recently used, replaced for
another environment, retired for memory -- the daemon lets go of every document of it (`Models.drain`,
`Models.release`): its row goes, and its page and every verb by its id read its `.xbf` from then on, which its
build wrote. Nothing is taken from the worker, and nothing is written. A worker over its memory cap no longer
exits on its own: it answers, and is stopped. A worker that died is let go of the same way (`Models.prune`).

**One budget.** Everything the daemon holds is counted against one budget: each served
document's structure (as JSON), its shape bytes and the bytes made from live shapes (`Served.size`), every
tessellation (`MeshCache`, which has no cap of its
own in the daemon) and every part's facts (`FactCache`, each counted as its JSON). Evicting a document drops all of it.
Bytes are counted as they are put, never sampled. Workers and render processes are processes of
their own, held together to the workers' memory cap (**The engine server and its workers**). The budget is `CAD_ENGINE_MEMORY_MB`, else a quarter
of the machine's physical memory (`serve.memory_budget`: macOS `hw.memsize`, Linux
`sysconf(SC_PHYS_PAGES)` or the cgroup's `memory.max` when that is less, Windows
`GlobalMemoryStatusEx`). Past it, what is held is evicted from memory down to 80 % of it
(`Server.trim`): tessellations first, least recently used first (a tessellation is made again from
its shape), then the parts' facts (measured again when asked); then documents, least recently used first, in one order: every document is read again
from where it is kept, under the same id, on its next access, and reading runs no code -- a file
from its file, a model's document from its worker, or from its `.xbf` once no worker holds it. A document a page watches is never
evicted, nor its tessellations or its parts' facts (law 18, connected means warm), nor the document being served as it is put.
The STEP reads held by their bytes go with the first document evicted.

**Pressure.** The daemon's server asks the operating system's memory-pressure signal every two
seconds (`serve.Pressure`) and, under pressure, evicts in the same order down to the low-water
mark, half the budget:

- macOS: `sysctlbyname("kern.memorystatus_vm_pressure_level")`, 1 normal, 2 warning, 4 critical;
  warning and critical are pressure. It is the level `DISPATCH_SOURCE_TYPE_MEMORYPRESSURE`
  reports, polled: the dispatch source wants a block callback, which Python cannot hand it.
- Windows: `CreateMemoryResourceNotification(LowMemoryResourceNotification)` once, then
  `QueryMemoryResourceNotification` each time.
- Linux: pressure stall information, the cgroup's `memory.pressure`, else `/proc/pressure/memory`;
  `some avg10` over 10 is pressure.

Where none can be read, the budget alone applies. `Pressure.simulate` is the tests' hook.

**The rebuild command.** A document that is not held -- `unsaved` -- names the exact
command that builds it again: `cad run` and the script that defines its model -- never a
program that imported it and called it, a check script, whose next run may do something else -- the engine that says it is the one `cad run` reaches, and its
python has the kernel a bare `python` may lack -- with the options its last run's command line was
given, one word each (`--python=3.13`, `--project=/work/gearbox`, `--index-url=...`), and `--with` and
each requirement it was given (its record's `with`; a header's are its script's, which `cad run` reads
again); for one its last run built in a Python of its own (its record's `python`: a venv's, with
packages the base lacks), that Python and the script, which `cad run` could not build -- from the
daemon's record of it, or after a restart the registry's. Each word is quoted for the shell a person
pastes it into (`records.rerun`): `shlex.quote` on POSIX; on Windows the double quotes cmd.exe and
PowerShell both read, only where a space, a quote or an operator of cmd.exe's needs them
(`records._windows`: `"pandas>=2"`, a redirection bare), since to cmd.exe a single quote is part of
the path; a word holding a `%` is quoted between each one, `"C:\my"%"20dir"`, since cmd.exe expands a
`%NAME%` inside double quotes too, and a name with quotes in it is none it holds. A shape handed over has none: its words say that a program the engine did
not run showed it, and that only running that program again hands it over again. A child model's is its own script too. The page
reads it from its document's 404 (`GET /api/v1/documents/<id>`: `{"error", "hint", "state"}`; a read of
its kind's, `{"error", "state", "rebuild", "hint"}`),
`cad <type> inspect` and `cad_show` of its id refuse with it, as `{"op": "state"}` answers it. The engine never runs it: no access, no start
and no restart runs code to bring a document back.
Asked of the server, a document it does not hold is a refusal (`serve.NotHeld`): the server answers
its type, state and command with its words (`daemon.refused`) and the caller raises it as that
type (`api._failed`), so `cad <type> inspect`, `export`, `snapshot` and `serve` of such an id exit 2.

`cad server stop` stops the engine, whatever release runs it (`places.endpoints()`: its one door).
Both `stop` and `status` remove the door and lock of a dead server (nothing reads the door and nobody
holds its lock) and say so on stderr. `stop` prints a line per server it stopped
(`stopped the engine server at DOOR`), or `no engine server is running`; `--json` prints
`{"ok": true, "stopped": [DOOR, ...]}` instead.
