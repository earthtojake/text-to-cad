# Parameters

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A script declares a model's parameters at a module's top level (law 30), and goes on with the numbers
they return:

```python
from cad import model
import build123d as bd

WALL = model.param("wall", 2.0, min=1, max=5)             # a float; WALL is 2.0
HOLES = model.param("holes", 6, min=3, max=12)            # an integer; HOLES is 6
ANGLE = model.param("angle", 30.0, min=0, max=90, unit="deg")

@model
def bracket():
    ...
```

**Declaring.** `param(name, default, *, min=None, max=None, step=None, unit=None)` (`parameters.py`) is
`cad.model.param`, the standard library alone, so `import cad` imports no kernel. It returns `default`
unchanged, a plain `int` or `float`: the memo's keys, what a body retains and the closure see a number like
any other. An `int` default makes an integer parameter, whose bounds, step and values are whole numbers; a
`float` default a float one. Refused by name: a `bool`, a number that is not finite, anything else; a name that
is not `[a-z][a-z0-9_]*`; an option outside `min`, `max`, `step` and `unit` (law 15); `min` not below `max`, a
default outside them, a `step` not above zero, a unit other than `mm` or `deg`; and a call whose caller is not a
module's top-level code (a body replayed from the memo does not run, and its declaration would be lost). In
the program's own process that is all it does.

**Recording.** The worker loads the script inside `parameters.recording` (`build._build`), which starts from
no declaration, as the load starts from no model. Each call from a first-party file (`kernel.trace`'s: the
model's own code, never a library's) is recorded as a `Declared`: what it declares, the file and line of the
call, and where its default is spelled -- the call found by the code position its frame stands at
(`f_lasti`, `co_positions()`; where the interpreter keeps no columns, the one call on the line that declares
the name), its default argument found in the file's syntax tree (`ast`, columns in UTF-8 bytes), and kept as a
byte span only when it is a plain numeric literal, with or without a leading minus, whose bytes read back as
the value; the span comes with the digest of the file's bytes it was found in (`digest`). A default that is
anything else (a name, an expression) is recorded with no span, and so is one the engine cannot tell is that
declaration's alone: a call whose name is not a string in the code (`param(n, 1)` in a loop, `param(f"x{i}", 1)`
in a comprehension: one literal, many names), two declarations at one literal (both lose it), and every call in
a file whose bytes are not UTF-8 or whose coding cookie names another coding (the parser's columns are bytes of
the text as UTF-8, the file's own only then). Each is listed `expression`. A name declared twice in a run is
refused, naming both `file:line`.

**Which a model has.** `BuildContext.parameters(model)` (`parameters.rows`): every declaration of the run,
the model's own -- declared in its script, writable where it has a span (`expression` where it has none)
-- and the shared ones, declared in any other first-party module the run loaded, listed and never writable
(`shared`). Every model of one script lists the same. A child model of another script lists what a build of
its own script would: the declarations of the files its script's closure reaches.

**The document.** The record (`parameters.record`): ASCII JSON on the main label under `PARAMETERS_GUID`
(`document.py`), beside the closure and the animations' record: a list of `{name, value, kind, min, max,
step, unit}`, an option not declared `null`, in the order declared; no file, no line, no span. A model whose
script declares none writes no attribute, so its bytes are what they were before parameters existed. The
record is part of the document's signature, and a model taken from its key (the worker's last build, the
engine's cache) is built again when the record the script declares now differs from the one it holds
(`build._taken`), so a document never lists values its code no longer has. The record is part of its revision
too (`models.revision`: the closure's key and the record, digested, for a document that records any): a model
whose body reads no parameter of its script -- a sibling's `wall` -- has the same key after `wall` changes, but
not the same document, so it is a new generation, its pages fetch it again, its cache file is saved again and
its rows are served at it, however the record changed (the viewer's Save, or an edit and a run). A declared or exported xbf carries
the same record (`Loaded.parameters`; an export writes the document's own, `export/tree.py`'s `tree_of`); opening
that file shows them, read-only. It is an attribute of its
own under a GUID of its own, which a reader that does not know it passes over, and a document without it reads
as one with none: the format stays `xbf/9`, and documents earlier releases wrote read as they did (law 14,
tier 3). STEP, GLB and the other translations carry none.

**Held while the worker lives.** The build's report carries the rows with their spans and digests
(`report["parameters"]`); the daemon takes them out of it as it registers the document (`models.Models.register`)
and keeps them beside its record, in memory alone, never in the registry, the cache or an answer. They are
the worker's to say: `Models.live` answers them only while the worker that recorded them is live in the
supervisor and of the generation asked; a worker retired or gone (`prune`) takes them with it, and a build
that records others replaces them.

**What the page reads.** `serve.Server.structure` adds `parameters` to every structure it serves, `[]` for a
document that records none, through `parameters.served`: each recorded parameter with `writable`, `reason`
and `source`. `writable` is true only for a model's document whose live worker recorded a span for the value
the document holds; else `reason` is one of `file` (a file's document: a declared or exported xbf, a STEP),
`no_worker` (no live worker recorded where it is: the script must run again), `shared` or `expression` (no
span: an expression, or a literal not that declaration's alone, above).
`source` is the declaring file relative to the script's folder where it is under it, else its name, and null
where nothing live says it. `cad model inspect` and `cad xbf inspect` list the same rows (`api._summary`'s
`parameters`).

**Setting.** One entrance, the viewer's Save: the page's `POST /api/v1/documents/model/<id>/parameters` with
`{"values": {...}}` (`viewer/http_app.py`, behind the guard header and the page token every changing route has;
only a model's document has it, and it names a document and parameters alone, never a path or text). No command
or library function writes parameters: an agent changes a value by editing the script and running it. The route
reaches `parameters.Setting.set` in the daemon (the server's `set_parameters`), which does in order, and changes
nothing on disk before the fifth:

1. The model's rows, while its worker is live (`Models.live`), else `no_worker`; a document the engine does
   not hold at all is not held (`serve.NotHeld`).
2. Every name one of the rows, else `unknown_parameter`; every one writable, else `not_writable` with its
   `reason` (`parameters.changes`).
3. Every value a finite number of its parameter's kind -- an integer parameter takes an integral one -- within
   its declared range, else `not_a_number` or `out_of_range`. An integer beyond what a float holds (`10**400`)
   is `not_a_number` whatever the range, refused before anything converts it. A float parameter's value is
   rounded to six decimals, and that rounded value is the one checked against the range, written and answered
   (`written[].to`); a value that is not zero but rounds to zero (`1e-7`) is `not_a_number`, never written as
   `0.0`. A value equal to the one the code holds is no change, and a request that changes nothing writes and
   builds nothing.
4. No build under way, in any worker (another Python's build of the script is another worker's), of the file
   it writes or of the script whose run it builds again, and no other set of either, else `busy`; the check and
   the claim are one step (`Setting._claim`), and from then until its answer those scripts are the set's: a
   build asked meanwhile waits for it, told so on its log (`Setting.building`, which the daemon's build path
   enters from a build's request to its answer), so no build reads the file between the check of its bytes and
   the set's own build of them. (A program reads its own script before it asks for a build -- `python
   bracket.py` runs its top level first -- which no engine sees; the build it then asks reads the file as it is.)
   Then the script's bytes on disk of the digest its last run recorded, and the bytes at each span still
   spelling the recorded value (`parameters.standing`), else `script_changed`: run the script first.
5. Each number spelled by the library (`parameters.spelled`: an integer as its digits, a float in the
   shortest text that reads back as it, always with a point or an exponent, so its kind is kept), the spans
   replaced from the last to the first (`parameters.splice`: every other byte as it was), and the file
   replaced at once, its mode kept (`atomic_replace.put`), only while it holds the bytes step 4 checked: read
   again once the new file is made, just before it moves over (`_write`); a file another writer changed since
   is left as it is, and the set is `script_changed`, nothing written. Nothing locks a file another program
   writes, so the window that remains is the rename's own.
6. The script's last run built again (`Setting._built`): the daemon keeps, per worker, the run its last builds
   were part of (`parameters.ran`: the script, the models every build of that run named, its working folder,
   its environment, the Python it ran with and the program that asked), and sends that as one build order of a
   run of its own through the daemon's one build path, so the model's warm worker builds it, its pages see the
   new version as a run's, and every model the run built is built again. The answer: `{"id", "written": [{name,
   from, to, file, line}], "rebuilt": [ids]}`.
7. The build is judged by the models the change can break (`parameters._failure`). `ran` keeps, beside the run,
   how each of its models and child models last ended (`failed`: by id, the last line of its error). A model
   that failed in that run and fails now with the same last line is the script's own trouble, not the
   change's: it does not fail the set (the set's answer lists the models that built). A model that built then
   and fails now, one that fails otherwise than it did, and the worker's own failure do. A build that fails so
   puts the previous bytes back the same way -- only while the file holds the bytes step 5 wrote -- and builds
   the run again, so the document and the rows are the last good ones, and answers `build_failed` with the
   build's words: its last line in the refusal, all of it as `detail`, and what the file holds: as it was; or,
   where another writer changed it while it built, that change, left as it is and not built; or, where the
   bytes could not be put back (the folder refused them), the new values, named with the file's path. The
   document served is the last good build's in every case (a failed run keeps it).

A refusal is `parameters.ParameterRefused`, a `ValueError` with `code` (one of `parameters.CODES`), `hint` and,
for `not_writable`, `reason`; the daemon answers it with those beside its words, and the library raises it as
that type (`api._failed`). The command exits 2 for a parameter the model has not or a value it does not take
(`unknown_parameter`, `not_a_number`, `out_of_range`: `invalid_argument`) and 1 for what the model's state
refuses now (`no_worker`, `not_writable`, `script_changed`, `busy`) and for `build_failed` (`failed`); its
`--json` refusal is the failure contract's document with `code`, `hint`, `parameterReason` (for
`not_writable`) and `detail` (for `build_failed`). The route answers `200` with the answer, and a refusal as
every route does (`{"error", "hint"}`) with `code`, `reason` and `detail` likewise, `400` for
`unknown_parameter`, `not_a_number` and `out_of_range` and `409` for the rest (`http_app.PARAMETER_STATUS`); a
body that is not `{"values": {...}}` is a `400` with no `code`. It answers once the build is done.

What it does not do: write a parameter another module declares, one with no span (`expression`), or one
of a document no live worker built; overwrite a file another writer changed while it worked; build anything but
the run that last ran; write the record into a STEP, a GLB or any other translation.

**Previewing.** Before a Save, the page's Parameters tab shows the model at its drafts as a person moves them:
`POST /api/v1/documents/model/<id>/preview` with `{"values": {...}, "page": token}` (`viewer/http_app.py`, behind
the guard header and the page token as `set`'s route is; `page` a token of the page's own making, letters,
digits, `-` and `_`, which keeps one page's previews from another's), answered by `parameters.Previewing.preview`
in the daemon (`client.previewModelParameters` on the page; no command and no library function: nothing but the
page reads what it makes). It writes nothing, and does in order:

1. The values checked against the live rows as `set` checks them (steps 1 to 3: `no_worker`, `unknown_parameter`,
   `not_writable`, `not_a_number`, `out_of_range`). Values that are all the document's build nothing: the page's
   previews are let go and the answer is `{"id", "preview": null}` (the page's Reset, a Save that landed).
2. A build or a `set` of the script comes first: one under way (`Setting.building`, which the daemon's build
   path holds from a build's request to its answer, and a set's claim) refuses the preview `busy`.
3. Per document, one preview builds at a time and one waits: a request that comes while one builds waits in the
   slot, and a newer one takes its place, the one replaced answered `{"id", "superseded": true}`, never built. A
   build or a set that begins answers the one waiting `busy` (`Previewing.yield_to`), so a preview never runs
   before a run; one already building finishes -- a kernel call is not cut short -- and the run's lease waits for
   it, that one build at most.
4. Its turn come, the values are checked again (a run may have landed meanwhile), and the script's bytes against
   the digest and spans its last run recorded (`parameters.standing`: `script_changed`). A preview runs the
   script as it is on disk -- the worker loads its modules again from their files, and keys the memo by their
   source there -- so a script changed by hand since its run is refused, never built: its new code at the last
   run's positions of the numbers would be neither run. The engine never looks at the file for any other
   reason, and says nothing of it before a preview or a set reads it.
5. The worker that recorded the rows, under a lease of the preview's own (no other worker: one started afresh
   holds neither the rows nor the memo, `no_worker`), is sent `{"op": "preview", "script", "name", "values",
   "digest", "known"}` with the last run's working folder and environment (`worker.py`, `build.preview`). It loads
   the script as a build does but inside `parameters.recording` given the values: each declaration of those names
   in the model's own script returns the value asked, not its default, and records it as its value; a load whose
   declarations are not where the run recorded them, or not of its digest, is `script_changed`
   (`parameters.previewed`). It builds the one model on screen, not the run, in a run of the worker's memo, so
   every kernel call keyed by its inputs is a hit where the values do not reach it, and a value tried before (a
   slider dragged back) is a hit throughout while the memo keeps that run (its last `RUNS_KEPT` runs, previews
   among them). A body whose key falls back to its module's bytes (law 5's fallbacks: a `globals()`, a value with
   no canonical form) is keyed by the values too (`BuildContext.preview`), since a preview leaves those bytes as
   they are and must not replay another value's run. Nothing a build keeps is touched: no declared file is
   written, no document is kept (`_WRITTEN`, `_BUILT`, the provenance `made_by` answers), no closure is made,
   nothing is taken from or saved to the engine's cache, and the worker's last run (`ran`, which `set` builds
   again) is not changed; no progress frame is sent, so no page shows a build. It answers the structure and the
   shape bytes of each part whose key the daemon does not hold already (`known`: the document's and the page's
   last previews'), as `result` answers a held model.
6. A model that fails at those values is `build_failed` with the build's words as `detail`; the page keeps the
   last preview that built. Else the preview is held in the server's memory under an id of its own,
   `<id>~preview-<token>` (`serve.Server.keep_preview`), and answered `{"id", "preview": {"id", "version",
   "basis", "values", "seconds", "memo"}}` -- `basis` the document version it was built against, `memo` the
   build's hits and misses.

A preview is read at the document's read routes under its id, and at those alone
(`serve.Server._preview_route`): its structure, its parts' buffers (meshed by geometry key in the one mesh cache,
so a part the values did not change is never meshed again and the page fetches only the parts whose keys it has
not held: `xbfDocument.js`), a part's groups, an element's facts, the parts' facts. It has no envelope, no
version to wait on, no pose, no kinematics, no mesh run, no export, no thumbnail and no Recents row
(`http_app.PREVIEW_MARK`); only the page that asked is told its id. It is never the document: the document's
structure, version, record, cache file and every verb of it are as they were. A page holds two at most (the one
drawn and the next), the server those of eight pages; a page's are let go by its next preview, by values equal to
the document's, by a new version of the document (`Models.register`), and once nobody has read them for
`PREVIEW_IDLE` seconds (two minutes, `Previewing.expire` at the daemon's `tend`).
