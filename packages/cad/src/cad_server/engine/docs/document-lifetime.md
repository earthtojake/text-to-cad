# Document lifetime

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model's document is its `.xbf`: every run writes it (law 10), and a document outlives the worker that
built it, the engine's memory and the engine itself: it is its file, and lives while its file does
([models.py](../models.py), the library's `cad.engine.serve`). What the engine knows of a model comes from a run
alone (law 21): a run of its script pushes the model's code, its key and its document, and outside a run the
engine reads and watches no script and runs nothing -- a file's bytes, which are the disk, are no model's code.
The engine keeps no record of a document: what it says of one is read from the file, or worked out from its
path. A document's state (`models.STATES`, what `cad server status` lists):

- `live`: a live worker holds it, with its memo and its trace: its page is the model, its parameters editable
  and its provenance asked of that worker.
- `held`: no worker holds it, and its `.xbf` is there: the engine answers it from that file, as it answers any
  file -- a page reads it by its id and reads it again when its bytes change, `cad inspect`, an export and
  a snapshot by its id go to the documents worker with its path (`Daemon.document`), and what made an element is
  null (law 7: provenance is the worker's).
- `building`, `failed`: its build now, or its last one.

An id whose file is gone names nothing: `no document <id> is held` (`serve.NotHeld`: a page's 404, a verb's
exit 2), whether or not a live worker still holds its build (`Models.held` lets go of that row, as `release` does),
and running its script writes the file again. Nothing says which script: the file is not there to
read it from. One whose `.xbf` another process wrote since its run (a copy, a checkout, a sync folder) is that
file from then on, as after a restart: the row keeps the version of the file its run left (`written`,
`state.file_version`), and `Models.held` lets go of a row whose file is another version, unless a request of
its worker is under way (its lease, taken before the request is sent and let go once its answer gave the row
the version its run left: the daemon knows it before any of the run's progress reaches it); the server asks it
before it serves a model from its worker (`serve.Server.model_held`), so every verb and page reads the file at
once, and a page on it follows as it follows any file changed on disk. Nothing the engine's own runs write lets
a row go: a run that fails keeps the file it left as its row's (one that wrote its `.xbf` before a declared file
failed), and only the row judged is let go, never one an answer put in its place meanwhile -- a row let go hears
no progress or failure of the next run, which the daemon tells the rows of the worker that runs it. A file
another process writes while a request of its worker is under way is seen once that request ends, and is taken
as the run's own when the request is a run of its model. Running its script builds and holds it again. A rewrite of the same size within
one tick of the file system's clock keeps the version, and is not seen.

**Two kinds.** A function in a file is a model: its document is
its `.xbf`, which `@xbf` declares; one with file decorators alone writes those files and is no document
(`Models.unsaved`: no document, its page its first file's; law 6). A shape is saved (**Shapes handed over**), and its document is its `.xbf` too. Nothing
else is kept, and how is not the author's to choose: the decorators and
`cad.save` take no store (`store=` is an unexpected keyword argument, as any other). A function in no
saved file (a notebook cell, a REPL, `python -c`) is refused, with the words that save its shape instead
(`cad.save(shape, "plate.xbf")`).

**Shapes handed over.** `cad.save(shape, "plate.xbf")` (`api.hand_over`) makes a document of any
build123d shape a program holds, from a script or a REPL. In the caller, the shape is made a
document as a build makes one (`document.collect`, `to_xcaf`) and serialised (`document.to_bytes`),
the declarations on it with it -- its joints, mechanism states, configuration sequences and
couplings -- and its GLB animations, passed as `animations=[...]` (the `animation()` builders, each
on the shape or a part of it), since there is no body to declare them in. The daemon (`{"op":
"shape"}`, `Models.hand_over`) reads the bytes through the documents worker, writes them as its `.xbf` (at
the path given, relative to the calling script's folder or, where there is none, the working folder; the caller
writes it where the engine could not) and serves its page from that file, a file like any model's from then on.
Its name is its path's stem (`cad.save(shape, "crate.xbf")` is `crate`); its id is its `.xbf`'s. The handle's `.shape` is the shape passed. Called inside a model's body it is
refused: a body returns its shape.

**The library.** One file in the state folder, `library.json` ([library.py](../library.py); the distribution
names the folder, `places.state_dir`), holds what a person keeps in cad and nothing of a document's content:

```json
{"schema": 1,
 "projects": {"<project id>": {"root": "/abs/folder", "created": 1764000000.0, "opened": 1764000100.0}},
 "files": {"<file id>": {"path": "/abs/file.xbf", "created": 1764000000.0, "opened": 1764000100.0,
                         "pinned": true, "reached": "/abs/as/a/page/named/it.xbf"}}}
```

A project is a folder a person opened as one, keyed by its id (`ids.derived_id` of its canonical `root`). A
file is keyed by its id (`ids.file_id` of its canonical `path`), so an id is one lookup; the id stays a
function of the path, never read back as its authority. An entry is made when a page opens the file (`opened`),
when a person pins it (`pinned`, kept only while true), and the first time a run or a hand-over writes it as a
model's `.xbf` (`created` alone: `Models.noted`), so a model a run just built answers by its id after a restart
wherever its file is. Nothing else makes one: not an export, not a folder's listing, not a picture, not a count.
`reached` is kept only while a page named the file by another path that still reaches it (a file in a linked
folder is in the project it was reached in). An entry goes when the home's Remove forgets it (**Forgetting**),
and, with any write, once its file is gone, unless it is pinned: a pinned file comes back with its file.
Recents is every entry whose file is there now (`cad_server.viewer.recents`): pinned first, then by last
activity, the later of a row's `opened` and `updated` (the file's time on disk), with the file's size from the
same one `stat`; a model's script is never read for it. A file that is gone is on no list.

The file is written whole (`state.Folder.write`: beside its target, then replaced), and a change is a read and a
write under one lock of the engine's process, which is its one writer; two processes writing in the same instant
can lose one of the two changes (an open's time, a pin), and nothing is corrupted. A file that does not read is
set aside as `library.json.unreadable`, said once on stderr, and started again.

**A file's note.** What was last seen of a file is the cache's, `documents/<id>/note.json` with `picture.png`
beside it in the cache folder (`library.Notes`): `{schema, path, version, parts?, pictured?}`. `path` is the file's
canonical path, the one its id is of, so a folder whose file is gone is known without the library: `cad cache prune`
removes it (one an earlier build wrote names none, and goes once nothing in it was written for a month). `version` is
the file's when the note was written (`mtime_ns-size`, `state.file_version`), and a note is read only while it is
the file's version now: a file that changed has no count and no picture until one is in hand again, which replaces the note
whole. It is filled only with what the engine already holds, and nothing is ever read to fill one: a file's
part occurrences from the read the engine made because a page opened it (an `.xbf`, a STEP), from a build's facts
or a hand-over's structure as it registers, and from the document an export wrote an `.xbf` from
(`Models.exported`); its picture when the page showing it sends one. Recents and a project's page list `parts` and
the picture from it. An `.xbf` exported to another path, or copied, is another file, so another document with its
own id, note and card.

**An id's path.** With no record, an id is found from its path alone (`Models.locate`, the application's
`projects.locate`), stopping at the first path that is a file now: the `.xbf` a live worker's row names; the
files the engine was named since it started (`serve.Server.files`: by a launcher, a page, a folder's listing, a
hand-over, a worker's retirement); the library's entry; then the project folders, the one opened last first,
each by a bounded walk (**Wire format**: 1,000 files, 24 folders down, 1.5 seconds, kept 4 seconds). A path found
is known from then on, so a folder is walked at most once for a file. A file in a project that nobody opened has
no entry anywhere and still opens by `/<id>` after a restart; one past the walk's bounds does once its folder's
page lists it. The folders are the application's to walk, so a verb's id the library does not know starts the
server's listener where none is bound yet.

**Coming from an earlier release.** A release that kept a record per document
(`documents/<id>/document.json` in the state folder) and per project (`projects/<id>.json`) is read once: the
first read of the library that finds those folders carries them into it and removes them (`Library.migrate`,
at the engine's start, before it is reachable). A record that names a file that is there -- a file's own path,
or the `.xbf` a model's record names -- becomes that file's entry, with when it was made and opened and whether
it was pinned; a project's record its project. An entry the library has already stays as it is. Then the
records, the pictures kept beside them (`recents/`) and each copy of a model's document in the cache
(`documents/<id>/document.xbf`) are removed, only once the library has landed, so a stop at any step loses
nothing and the next read finishes it. A record that names no file is not carried: 0.11.17's of a model names
none, so its model is listed again, by its `.xbf` and under that file's id, when its script next runs. The pass
says one line on stderr, `library: carried N files and M projects from the records of an earlier release; K not
carried`, which `cad server status` says too while that engine runs (`--json`: `library`, with the ids not
carried); a pass with nothing to do says nothing, and one that fails never keeps the engine from starting.

A live document's `revision` is its closure's key (the same code, the same revision, after a
restart too) -- digested with the document's parameters' record where it records any (`models.revision`,
**Parameters**) -- or a token of the build's own where the closure has none. A served document's
generation (its structure's `version`, which a page waits on and the viewer's export compares)
is a token of its build's own: a rebuild is a new generation, and no generation is a counter that
a restart starts again. A document is what its last run made: a run of the same revision in the worker
that holds the last build (nothing ran, or it ran to the same bytes) keeps its generation, so a page
waiting on it is not woken and an export of the revision it shows still writes it. After a restart a run says
no delta against the build before: the facts it compares are memory's.

**The store.** A model's store is its `.xbf`; the engine keeps no copy of it. Its cache folder (`places.cache_dir`:
`CAD_CACHE_DIR`, else `$XDG_CACHE_HOME/cad`, else `~/.cache/cad`) holds only what it derived from a document and
can make again, under that document's folder, keyed by its bytes: a KiCad board's plot, refilled pours, DRC and
kept exports, `documents/<id>/kicad/<key>/` (`formats/kicad/poured.folder`), a manufacturing check's kept
results, a model's and a file's (`documents/<id>/checks/`, `checks.Disk`), and the file's note: facts of the
file's bytes, which Remove leaves (**Forgetting**). The folder is shared with any 0.7 install's store: the engine
reads, writes and removes only under `documents/` there (its processes' bytecode is under `pycache/`), and lists,
counts and removes nothing else (`cad cache clean` neither).

A run takes the model from its `.xbf`, every model alike. A fresh worker -- after a restart, or once the script's
worker retired -- reads the model's `.xbf` before its body runs (**Build closure**). With the key the model
has now, the document is taken whole and nothing runs (`cache: {"used": true, "from": "xbf"}`; the CLI's `took
tube.py::tube cold in 0.42s: its .xbf holds the model's key`), its bytes kept as they are, the file never written
again, whoever wrote it last: a file whose key is the model's now is the model. Any other key, or a file that
does not read, builds the model, which writes its `.xbf` again, and says why. A later unchanged run in that worker takes it from memory, as it does a document the worker
built itself: no body runs or is replayed. A model taken writes its other declared files all the same, as exports
of the document it took (**Exports**): each translated, compared with the file, and written only where it differs
or is missing, so a declared file someone deleted or edited is written again from the document with nothing run.
A verb given an `.xbf`'s path reads the file, in the documents worker (`Daemon._routed`); a page given it serves the
model while a live worker holds it and the file is the one its run left (`serve.Server.add`), else the file, as it serves any file: its version is the
file's, it is read again when the file's bytes change (**The page's route**), and it names no model -- no
`made_by`, no worker kept warm.

An `xbf/8` `.xbf` is converted in memory when read (**Document compatibility**). Viewing, inspection, snapshots,
imports and exports require no model source or execution. The file's bytes remain unchanged;
loading a conversion rewrites nothing. Unsupported or failed format conversion preserves those bytes
and reports a clear error. Explicitly running the model still compares the current build key and rebuilds
where it differs. A file or bytes that are no `.xbf` cad wrote are refused before OCCT's reader is handed them,
since that reader ends its process on such input rather than report it (`document.NoXbf`, `document._whole`): no
BinOcaf header is another file; a header, or a root label whose declared size, that does not end where the file
does is a file cut short. What the reader still cannot read of a body is the same refusal, so every verb, a
script's `xbf.read` and the page say it in one line (a verb exits 2). A file damaged inside at its full length can
still end the process reading it (the documents worker, the page's reader, a build's worker), never the engine.

**The last run.** A document is what its model's last run made, and that is all the engine knows
of the code: it never compares a script, a module or an input file on disk with what a build read,
and no surface -- the page, `status`, `inspect`, `export`, `snapshot`, `cad_show` -- says whether
the code has changed since. When to run the code again is the agent's call (`cad run`), and
nothing reruns on its own. What the engine knows from its own last run it says: a document whose
last run failed is served as its previous good build, and every verb that reads it by its id
(`export`, `snapshot`, `inspect`, with a ref or without) says so once on stderr (`cli.told_state`,
from `model_info`) -- "the last run of turbine failed; exporting its previous good build; fix
…/turbine.py and run it again" -- and goes on: a notice, never a refusal. `cad server
status` ends that document's line with "serving its previous good build".

**Forgetting.** cad deletes no document: a document is its file, and deleting a file is the person's own act,
after which it is on no list and its id names nothing. What a person can take back is its place in the library:
the home's Remove (`PATCH /api/v1/documents` with `remove`) forgets the file (`Models.forget`) -- what the engine
holds of it (its row, the server's copy and its page; a live document's worker keeps its memo, and its next run
registers the document again) and its library entry -- and touches no file, nor what the cache derived of its
bytes (its note, its kept checks), which is the file's whether or not it is in Recents. A file in a project's folder stays on its folder's page: the folder lists it. An
unsupported document format or a failed saved-format conversion preserves the file (**Document compatibility**).

**Drain.** Before the supervisor stops a worker -- the count cap's least recently used, replaced for
another environment, retired for memory -- the daemon lets go of every document of it (`Models.drain`,
`Models.release`): its row goes, and its page and every verb by its id read its `.xbf` from then on, which its
build wrote. Nothing is taken from the worker, and nothing is written. A worker over its memory cap no longer
exits on its own: it answers, and is stopped. A worker that died is let go of the same way (`Models.prune`).

**One budget.** Everything the daemon holds is counted against one budget: each served
document's structure (as JSON), its shape bytes and the bytes made from live shapes (`Served.size`), every
tessellation (`MeshCache`, which has no cap of its
own in the daemon), every part's facts (`FactCache`, each counted as its JSON) and every part's face table (`Server.tables`,
a second `FactCache`, each counted as its JSON). Evicting a document drops all of it.
Bytes are counted as they are put, never sampled. Workers and render processes are processes of
their own, held together to the workers' memory cap (**The engine server and its workers**). The budget is `CAD_ENGINE_MEMORY_MB`, else a quarter
of the machine's physical memory (`serve.memory_budget`: macOS `hw.memsize`, Linux
`sysconf(SC_PHYS_PAGES)` or the cgroup's `memory.max` when that is less, Windows
`GlobalMemoryStatusEx`). Past it, what is held is evicted from memory down to 80 % of it
(`Server.trim`): tessellations first, least recently used first (a tessellation is made again from
its shape), then the parts' face tables (made again when asked), then the parts' facts (measured again when asked); then documents, least recently used first, in one order: every document is read again
from where it is kept, under the same id, on its next access, and reading runs no code -- a file
from its file, a model's document from its worker, or from its `.xbf` once no worker holds it. A document a page watches is never
evicted, nor its tessellations, its parts' tables or its parts' facts (law 18, connected means warm), nor the document being served as it is put.
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

Asked of the server, an id that names nothing is a refusal (`serve.NotHeld`): the server answers
its type with its words (`daemon.refused`) and the caller raises it as that type (`api._failed`), so
`cad inspect`, `export`, `snapshot` and `viewer` of such an id exit 2. The engine runs nothing to bring a
document back: no access, no start and no restart runs code.

`cad server stop` stops the engine, whatever release runs it (`places.endpoints()`: its one door).
Both `stop` and `status` remove the door and lock of a dead server (nothing reads the door and nobody
holds its lock) and say so on stderr. `stop` prints a line per server it stopped
(`stopped the engine server at DOOR`), or `no engine server is running`; `--json` prints
`{"ok": true, "stopped": [DOOR, ...]}` instead.
