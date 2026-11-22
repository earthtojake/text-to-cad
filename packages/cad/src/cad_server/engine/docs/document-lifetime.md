# Document lifetime

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A document outlives the worker that built it, the engine's memory and the engine itself, and lives
until a person deletes it (**Delete**; [models.py](../models.py), the library's `cad.engine.serve`). What the
engine knows of a model comes from a run alone (law 21): a run of its script pushes the model's
code, its key and its document, and outside a run the engine reads and watches no script and runs
nothing -- a file document's bytes, which are the disk, and the registry's records, which runs
wrote, are no model's code. A document's state (`models.STATES`, what `cad server status` lists):

- `live`: a live worker holds it, with its memo and its trace.
- `held`: no worker holds it and the engine answers it all the same: in memory, on disk (**The
  cache**), or both (`Models.where`). In memory the daemon holds it whole: its served structure and shape bytes,
  and the document as the xbf bytes `@xbf` would write of it, mechanism and every assembly's
  placement included, and its build records with it -- the closure and the compiled animations
  (**Animations**) -- so a GLB of it is the build's own. A page and `cad <type> inspect` read the
  served structure; an export or a
  snapshot by its id, and the viewer's export, go to the documents worker with the xbf bytes
  (`Daemon.document`), which reads them as it reads an xbf on disk, so no worker of its script
  starts. What made an element is null (law 7: provenance is the worker's). A document its worker
  exited before draining, but that a page had opened, is held for viewing only: an export of it
  names the command that builds it again.
- `building`, `failed`: its build now, or its last one.
- `unsaved`: neither a worker nor the daemon's memory holds it, and the cache holds no file of its
  last build -- deleted by hand, or never written: the cache folder could not be written when it was
  to be saved, or its worker crashed before it was. Nothing else empties the cache, so this is the one
  state that says to build it again, with the command.
- `detached`: not held, and the script it points at is gone (moved, deleted): listed in Recents,
  saying so, until the person deletes it. Nothing removes it on its own. A shape handed over is
  never detached: nothing of it can go missing, and nothing builds it again.

**Two kinds.** A function in a file is a model: the registry points at its script. A shape is
handed over (**Shapes handed over**). Nothing else is kept, and how is not the author's to choose:
every document is recorded and kept in the cache alike, and the decorators and `model(shape, ...)`
take no store (`store=` is an unexpected keyword argument, as any other). A function in no saved
file (a notebook cell, a REPL, `python -c`) is refused, with the words that hand its shape over
instead (`model(shape, name=...)`).

**Shapes handed over.** `model(shape, name="plate")` (`api.hand_over`) makes a document of any
build123d shape a program holds, from a script or a REPL. In the caller, the shape is made a
document as a build makes one (`document.collect`, `to_xcaf`) and serialised (`document.to_bytes`),
the declarations on it with it -- its joints, mechanism states, configuration sequences and
couplings -- and its GLB animations, passed as `animations=[...]` (the `animation()` builders, each
on the shape or a part of it), since there is no body to declare them in. The daemon (`{"op":
"shape"}`, `Models.hand_over`) reads the bytes through the documents worker, holds them as a drained
document is held (in memory, whole, and in the cache), registers its page, and records it as
`kind: "shape"`, its scope as `home` and the program that handed it over as `program` (none from a
REPL or a notebook), from which every surface words it: a program the engine did not run showed it,
so no command builds it again. `name=` is required; its id is
`ids.derived_id` of the calling script (or the working folder, from a REPL) and the name. The handle's `.shape` is the shape passed. Called inside a model's body
it is refused: a body returns its shape. A shape is refused the id of a model a script still
declares -- handed over from a REPL in a folder one of whose scripts gives a model `name=` the same,
or from a script one of whose functions has its name -- naming that declaration (`identity.handed`):
one id is one document.

**The registry.** One record per document the engine built, and per CAD file a page opened,
`documents/<id>/document.json` in the state folder ([registry.py](../registry.py); the
distribution names the folder, `places.state_dir`): it points; a document's bytes
are the cache's, in the cache folder (**The cache**).
Every record has one shape, `{schema, id, kind, root, home, entry, namespace, name, fingerprint?, module?, line?, declares?, relocated?, revision, built, created?, facts?,
program?, python?, with?, cache?{revision, bytes}, opened?, pinned?, preview?}`, and holds what a restart
needs and no more. `kind` says what it is: `model` (`home` and `entry`, its script and function; the
command that builds it again is `cad run` of its home, with the requirements its last run's `cad run
--with` was given, `with`, or, where its last run was in a Python of its own, `python`, that Python and
its home), `shape` (a shape handed over:
`program`, where there was one, names the program that showed it, and nothing builds it again) or
`file` (a CAD file a page opened: its path, `opened` and `pinned`, never a revision or bytes). A
model's and a shape's hold their revision and when they were built, their name and a build's facts
(what the delta says against); any record its Recents picture (`preview`, UI state: the PNG under
`recents/thumbnails`), and a model's or a shape's `cache` once the cache holds it (**The cache**).
`created` is when the record was first made -- a model's first run, a shape's first hand-over, a
file's first open on a page -- kept through every rebuild and reopen (the home's Created column);
a record from before the engine kept it has none, and every reader takes that as null.
Its closure is its document's own (**Build closure**): it is not copied here. Nothing records which files a model declared or wrote: a
declared file is an export, a plain file to every surface. Every path in it is relative to its one `root`, so a record moves by one field. It is written synchronously
as a build registers, and only when a field differs: an unchanged build rewrites
nothing; each write is then told to `registry.OBSERVERS`, never waited on. After the independent
startup identity migration below, it is read on demand: an id the engine does not hold (after a
restart) is answered from its record,
`held` from its cache file, `unsaved` with its command, or `detached`, and nothing runs. The registry is the ids' reverse map,
never their authority: ids use the canonical script/function or folder/explicit-name formula
(`ids`). `namespace` equals `root` (the script's folder, a shape's scope, a file's folder), and
`name` is the explicit name or the entry function; `entry` still names the Python function. A model
records SHA-256 of its script's bytes on each run (`fingerprint`; files and shapes have none) and
its Python module qualifier (`module`); an explicit declaration keeps its first line, its claim of
the name and a collision's words (`line`, dropped when its script's run gives the name up), and a
model of the run's script the explicit names that script declared (`declares`). Recents passes
`namespace` and `name` through (`CadRecent`): a named model's row shows its name.

**Re-attachment.** A run's models with nothing to take up -- no document its worker built or took,
and no cache file at the model's id (its script moved, or new), or a named model whose record points
at another file -- are asked of the daemon in one request before the worker reads any cache
(`build._reattach`, `Models.reattach`, `identity.reattach`), of the engine that runs the worker,
never of one it would start; a model with a document or a cache file costs a stat. The daemon reads
the registry once for all of them, parsing only the records whose text holds one of their
fingerprints, for model records with the same name, function and script fingerprint whose script is
gone from its path -- or is there as this very script under another spelling, a symlinked folder or
a case-only rename: a move. A record whose script is there as another file is the original of a
copy, and is never adopted. One candidate is adopted; of several, the most recently built (the id
breaks a tie), the choice logged; none, and the model is a new document. A live document not saved
yet is saved first, so its cache file moves with it. The record is re-pointed under the new id with
its history, creation time, pins, thumbnail and cache bytes (`identity.repoint`): the cache file
lands at the new id first, then the new record, and only then is the old one forgotten, so a stop
at any step leaves the old identity whole, and the next move finishes it. A function renamed
without an explicit name is a new document. A named model moved between files of its folder keeps
its id and is re-pointed too. `relocated` keeps the script and module its cache file was built
from: paths and module qualifiers are projected for the closure comparison alone, never written
into its XBF; its code, modules, inputs and toolchain are checked all the same, and a fresh build
clears it. Nothing reads or runs a script outside a run but the migration's one pass: a
fingerprint filled, and a record moved from its key given its function's line.

**Identity migration.** At engine start, before the daemon is reachable, `identity.migrate` makes
one pass over the records' JSON, independent of document format validation. It fills a missing
`namespace`, `name` and a model's `fingerprint` (its script's bytes; null where the script is gone,
until a run supplies one), and moves each record identified by the earlier
`uuid5(NAMESPACE, "key::" + key)` formula, with its cache file, to its folder/name id (a shape
once given a key: its calling scope and its name). It reads JSON and, only to fill a fingerprint or
find a moved record's line, a script's bytes: it imports no kernel and parses or rewrites no XBF. A second pass writes nothing. A
record that does not read, or whose new id another record holds, is skipped, never deleted, and
listed in the pass's one log line (`identity migration: filled N, moved N, skipped N`, then each
skipped record and why), which `cad server status` says too while that engine runs (a started engine's
stderr is no one's); a pass with nothing to do says nothing, and a pass that fails never keeps the
engine from starting.

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

**The cache.** For every model and shape document -- never a file's, which is its own
file -- the engine keeps `documents/<id>/document.xbf` in the cache folder its host names
([cache.py](../cache.py); `places.cache_dir`: `CAD_CACHE_DIR`, else
`$XDG_CACHE_HOME/cad`, else `~/.cache/cad`, on Windows too, where 0.10.0 kept it in
`%LOCALAPPDATA%\cad`; releases before 0.10 kept theirs in the same places named `cadgen`, which no build reads), written through a `registry.Folder` with `replace_atomic`, its record staying in the state
folder. The bytes are the hold's (`document.to_bytes`: the document, its closure record and its
compiled animations), the engine's own file always: a declared `@xbf` or an exported xbf is the
author's, never used as the cache nor pointed at by it. A file's document has no bytes there, but the views
derived from its bytes go under it, keyed by them: a KiCad board's plot, refilled pours, DRC and kept exports,
`documents/<id>/kicad/<key>/` (`formats/kicad/poured.folder`), regenerable, and removed with the document
(`Registry.delete` removes `documents/<id>` whole); so are a manufacturing check's kept results, a model's and a
file's (`documents/<id>/checks/`, `checks.Disk`). The folder is shared with any 0.7 install's
store: the engine's cache reads, writes, sizes and removes only under `documents/` (its processes'
bytecode is under `pycache/`), and lists, counts and removes nothing else there (0.7's store among
it, which nothing removes but the person; `cad cache clean` neither). It is written never on the run path:

- after `CACHE_IDLE_SECONDS` (10 s) with no build and no read of the document: the daemon asks the
  worker that holds it to save it (its `save`, `Process.tell`), which the worker does only when no request waits
  for it; a build arriving during the one serialisation waits for it. Measured on juno (29
  documents, 17.2 MB cached; the assembly's 9.6 MB): its serialisation and the pipe take 80-100 ms,
  the file's write 2-6 ms, and a warm build landing 50 ms into the save took 150-170 ms against
  120-140 ms alone. A document no worker holds is written from the bytes the daemon holds;
- at retirement, from the bytes the drain takes;
- at shutdown (`cad server stop`, a terminate), best effort within 10 s (`cache.SHUTDOWN_SECONDS`), for
  the documents built or read in the last idle window.

Once per revision: the record gains `cache: {revision, bytes}`, and a document
whose revision is the cache's is never written again. A restart indexes the cache files (a listing
and a stat, nothing read); a document with one is `held` and answers every verb -- page, export,
snapshot, inspect, `cad_show` -- by reading its bytes through the documents worker, as a held
document does; no worker of its script starts and nothing runs. Loaded, it is under the memory
budget like any document, and leaves memory for its file again when the budget needs the room. The
record is authoritative: a cache file missing, or not the size its record says, is not cached.

A cached `xbf/8` snapshot is converted in memory when read, just like an explicit file
(**Document compatibility**). Viewing, inspection, snapshots, imports and exports require no
model source or execution. The original cache bytes, record and revision remain unchanged;
loading a conversion does not schedule a cache rewrite. Unsupported or failed format conversion
preserves those bytes and that record and reports a clear error. Explicitly running the model
still compares the current build key and rebuilds where it differs.

A run takes it too, every model alike. A build is handed the cache's `documents/` folder, and a
fresh worker -- after a restart, or once the script's worker retired -- reads a model's cache file
before its body runs (**Build closure**): with the key the model has now, the document is taken
whole and nothing runs (`cache: {"used": true, "from": "cache"}`; the CLI's `took tube.py::tube cold
in 0.42s: the engine's cache holds the model's key`), its bytes kept as they are, never written
again; any other key builds the model, and says why. A later unchanged run in that worker takes it
from memory, as it does a document the worker built itself: no body runs or is replayed. The key
alone decides: a declared file, the model's xbf among them, is never read to take a model, and
whether it is there or as its build left it plays no part. A model taken writes its declared files
all the same, as exports of the document it took (**Exports**): each translated, compared with
the file, and written only where it differs or is missing, so a declared file someone deleted or
edited is written again from the document with nothing run. Nothing is recorded of what was
written, and nothing records which model wrote a file: an exported or declared file on disk is a
plain file to every surface. A verb given its path reads the file, in the documents worker, never
the document of the model whose build wrote it (`Daemon._routed`), and the engine lists a model that
declares files like any other. A page given its path serves it as it serves any file: its version
is the file's, it is read again when the file's bytes change (**The page's route**), and it names no
model -- no `made_by`, no worker kept warm, and nothing of a run sent to it, its progress and its
failure among them.

**The last run.** A document is what its model's last run made, and that is all the engine knows
of the code: it never compares a script, a module or an input file on disk with what a build read,
and no surface -- the page, `status`, `inspect`, `export`, `snapshot`, `cad_show` -- says whether
the code has changed since. When to run the code again is the agent's call (`cad run`), and
nothing reruns on its own. What the engine knows from its own last run it says: a document whose
last run failed is served as its previous good build, and every verb that reads it by its id
(`export`, `snapshot`, `inspect`, with a ref or without) says so once on stderr (`cli.told_state`,
from `model_info`) -- "the last run of turbine failed; exporting its previous good build; fix it
and run `cad run …/turbine.py` to update it" -- and goes on: a notice, never a refusal. `cad server
status` ends that document's line with "serving its previous good build"; an `unsaved` one's with
the command that builds it again (**The rebuild command**).

**Kept until deleted.** Nothing removes a cache file on its own: the cache has no size cap, no
least recently used and no age, and keeps every model document -- a shape handed over's as a
model's -- until a person deletes it, its record and its file together (**Delete**). The one other
removal is a corrupt file whose bytes do not read: it goes, its record kept without `cache`,
and the next build writes it again (`Models.unreadable`). An unsupported document format or a
failed saved-format conversion preserves the cache file and record (**Document compatibility**). A save that fails is logged and listed by `cad server
status`, never raised: with the cache folder read-only, or not writable at all, the engine saves
nothing and does everything else as it would.

**Delete.** A document stays until a person deletes it: `cad delete DOC [DOC ...]` (each DOC a
document's id, a model's script -- every document recorded of it, a shape it handed over among
them -- or the path of a CAD file opened before), or the home's Delete on a model's row. Both are
one function (`models.delete`): what the engine holds of the document goes first, when an engine
runs (`Models.forget`: its row, the server's copy and its page, the cache's timer and index; a
live document's worker keeps its memo, and its next run registers the document again), then its
record and its file in the cache (`Registry.delete`). Nothing of the person's is touched: a model's
script and its declared files, and an opened file, stay where they are; a file's row on the home
says Remove, which forgets its entry alone. `cad delete` prints a line per document deleted,
`deleted <name> <id>` (`--json`: `{"ok": true, "deleted": [{id, name, kind}]}`), never starts an
engine, and refuses a DOC that names nothing recorded, by name and before anything is deleted
(exit 2).

**Drain.** Before the supervisor stops a worker -- the count cap's least recently used, replaced for
another environment, retired for memory -- the daemon asks it
(the `result` request with `whole`, nothing meshed) for every document of it the server
does not hold whole at its version (`Models.drain`), out of the supervisor, then closes its stdin. The
worker serializes the document in memory (`document.to_bytes`: `TDocStd_Application.SaveAs` to a
stream, the bytes `@xbf` writes), and the documents worker reads them in memory too
(`document.read_bytes`: the application's stream read, overwriting into a document of its own).
Nothing is written to disk. A worker over its
memory cap no longer exits on its own: it answers, is drained, and is stopped. A worker that died
drains nothing: its documents the server and the cache lacked are `unsaved`.

**One budget.** Everything the daemon holds is counted against one budget: each served
document's structure (as JSON), its shape bytes, the bytes made from live shapes and a held
document's xbf bytes, its records among them (`Served.size`), every tessellation (`MeshCache`, which has no cap of its
own in the daemon) and every part's facts (`FactCache`, each counted as its JSON). Evicting a document drops all of it.
Bytes are counted as they are put, never sampled. Workers and render processes are processes of
their own, held together to the workers' memory cap (**The engine server and its workers**). The budget is `CAD_ENGINE_MEMORY_MB`, else a quarter
of the machine's physical memory (`serve.memory_budget`: macOS `hw.memsize`, Linux
`sysconf(SC_PHYS_PAGES)` or the cgroup's `memory.max` when that is less, Windows
`GlobalMemoryStatusEx`). Past it, what is held is evicted from memory down to 80 % of it
(`Server.trim`): tessellations first, least recently used first (a tessellation is made again from
its shape), then the parts' facts (measured again when asked); then documents, least recently used first, in one order: every document is read again
from where it is kept, under the same id, on its next access, and reading runs no code -- a file
from its file, a model's document from the cache, which is handed its bytes as it leaves when it
does not hold them yet (`Server.leaving`, `Models.leaving`). A document a page watches is never
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
`cad <type> inspect` and `cad_show` of its id refuse with it, and `cad server status` lists it. The engine never runs it: no access, no start
and no restart runs code to bring a document back.
Asked of the server, a document it does not hold is a refusal (`serve.NotHeld`): the server answers
its type, state and command with its words (`daemon.refused`) and the caller raises it as that
type (`api._failed`), so `cad <type> inspect`, `export`, `snapshot` and `serve` of such an id exit 2.

`cad server stop` stops the engine, whatever release runs it (`places.endpoints()`: its one door).
Both `stop` and `status` remove the door and lock of a dead server (nothing reads the door and nobody
holds its lock) and say so on stderr. `stop` prints a line per server it stopped
(`stopped the engine server at DOOR`), or `no engine server is running`; `--json` prints
`{"ok": true, "stopped": [DOOR, ...]}` instead.
