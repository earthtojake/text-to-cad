# Document types and integrations

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

The words are the library README's (**Definitions**, laws 22 to 27); this is how they work.

**The registry.** `cad.registry` is one table, the standard library alone: `DOCUMENT_TYPES` (each a
`DocumentTypeEntry`: `id`, `title`, `extensions`, `mime`, `view`, `content`, `operations` -- each an
`Operation` with the integration it needs -- `decorator`, `reader` and `wire`) and `INTEGRATIONS` (each
an `Integration`: `name`, `extra`, `process`, the `commands` its extra installs, for an external program
its `Probe` -- the program, the minimum version, the install hint and the variable that names it outright
-- and, only for its tool's own files that are no document type, its `operations` and the `files` those on
one file take (`FILE_OPERATIONS`): `mujoco`'s `check` on `.xml` and `.mjcf`; `orcaslicer`'s `presets` and
`complete`, on presets found by name, take none). `by_extension` and
`type_of` map a file to its type. Every layer reads it: the viewer's file kinds, the content types its
file route sends, the catalog's extensions, the snapshot packets' inputs, the routes each kind
answers, the CAD app's list of formats, the analytics kinds, and the format tables of the @cad/core
runtime bundled at build time, which are generated from it (`python -m cad.registry --js`) and checked
against it. `wire` is the one other spelling, the frozen
protocols': `3mf` for `threemf` in `/api/v1/documents/<kind>/...` and in the analytics schemas.

**A type's object.** Each `cad/<type>/__init__.py` ends by binding its module to `DocumentType`
(`cad._internal.document_type.bind`), the module class of every type (`ModelType` for `cad.model`, whose
`__call__` is the engine's `model` itself): `__call__` is the decorator (`cad.engine.model`'s, for a type
with one), `read` the type's reader, and `export`, `snapshot` and `inspect` the engine's functions (`api`)
behind a check that the source is the type's (`refuse_other`: no file of another type; for `model`, a
handle or an id and no file; for a file's type, no handle or id); a mesh's `export` takes no `tolerance` or `angle`.
`dfm` is the manufacturing check's (below); `drc`, `erc` and `validate` are the type's own functions. Each attribute is resolved on first use and kept, so `cad.step.read
is cad.engine.model.read_step` and `import cad` loads no kernel. The earlier spellings resolve through
`cad._internal.aliases`: names through `lookup` (a module's `__getattr__`), modules through a
meta-path finder that hands out the new module under the old name (and runs it, for `python -m`), each
warning once per process from the lookup, at the caller's line (`skip_file_prefixes` skips the
library's and the import system's frames). Importing `cadgen`, or any module under it, warns the same way, from
`cadgen`'s own import.

**Producers.** A producer is `(type, matcher, writer, integration)` with what it accepts and provides
(`cad.registry.Producer`), registered by its integration (`cad/build123d/_producers.py`) and gathered
by `cad.registry.producers_for`. A model's result is checked against them before anything is made of
it (`model.check_result`): for the document and each file the model declares, exactly one producer
must take the value (`registry.producer_for`), else the build fails, naming what the type is made of
and the integration that would take the value. Today the build123d integration's producers take a
build123d `Shape` for every type with a decorator, and the engine's writers -- the XCAF document
(`document.py`) and its translations (`export.translate`) -- make the files, as before. Every decorated function is the engine's model.

**Edits.** A KiCad board or schematic is no producer's: it is changed in place by its type's edit
(`cad.registry.Edit`), `with kicad_pcb.edit(path) as board:` and `with kicad_sch.edit(path) as
schematic:`, run in the caller's process, never in a worker or the daemon (`cad.kicad._session.edit`): a
private headless `kicad-cli api-server` on the file (kicode's, in private KiCad homes), KiPy connected to
it and the open document handed to the block -- a schematic's project symbol libraries loaded first; a file
not there yet made by KiCad (`CreateDocument`); a shell whose sandbox refuses the server's socket refused in one
line before it starts (`_refused`), and a slow start said once while it waits -- and saved at the block's end when the block changed it
or KiCad made it, never when it raises. One server serves a project: an edit of the project's other file
inside the block joins it (`OpenDocument`), each document saved at its own block's end. Nothing is
declared, and nothing is written from the edited file but what explicit calls after the block write
(`kicad_pcb.export`, `kicad_pcb.drc`, `kicad_sch.export`, `kicad_sch.erc`).

**The commands.** `cad_server.cli.document_types` makes every type's command from the registry:
`OPERATIONS` maps `(type, operation)` to its run -- the engine's verbs (`engine/cli.py`'s parsers and
runners) for `export`, `snapshot` and `inspect`, each with its source said as the type's and a mesh's export
without `--tolerance` or `--angle`; the type's own function for `dfm`, `drc`, `erc` and `validate` (generated from the
function's signature, `cad_server._internal.cli_from_function`, or an adapter's parser where a flag
repeats). A parameter whose type is a `Literal` of strings is an enumeration, its values the flag's
choices (`dfm`'s `process`, `rules`, `units` and `technology`), so a value outside them is the
parser's usage error, naming the flag; a value the function itself refuses by name raises the library's
`ArgumentRefused` (`cad._internal.refused`), which the command says as the command line's
(`invalid_argument`, exit 2), never as a failure of the work. A `Path` option is a file the operation
reads (`srdf.validate`'s `urdf`): one that is not there is refused before it runs (`not_found`), as
its own file is. `cad_server.cli.<type>` is each type's module, and the `cad` dispatcher sends `cad <type>
...` to it (`TYPE_COMMANDS`); `resolve` and `build_parser_for` give a command line's parser. An
integration's operations on its tool's own files are made the same way, by `cad_server.cli.integrations`
(`INTEGRATION_COMMANDS`, `cad_server.cli.<integration>`): each generated from its function's signature,
its file refused by name where it is a document type's (which names that type's own check), any other
file's, or not there, and run in this process where it holds the integration, else in that integration's
environment. A name is a type's or an integration's, never both.

**The manufacturing check.** A 3D type's `dfm` (`model`, `xbf`, `step`, `stl`, `glb`, `threemf`) and a DXF's (a
sheet's cut file) are the registry's `dfm` operation of family `manufacturing`, one function the library
makes for each type (`cad._internal.manufacturing.dfm_for`, bound by `DocumentType`), its signature the
type's: its processes the `--process` choices (a mesh's `printing`, its default -- `cnc`, `sheet` and
`molding` offered and refused with the reason and the fix, judged on exact geometry -- a DXF's `sheet`, its
default), and their options alone; the operation names
the integration that measures the type: `build123d` for `model`, `step`, `xbf` and `dxf`, `trimesh` for the meshes.
Its options belong to a process -- `cnc`, `sheet`, `molding`, `printing`, each a module of
`cad._internal.dfm` with its options, its rules, findings and summary -- or to all (`material`,
`units`), and are resolved there, the standard library alone: an option of another process, a process the
type cannot be measured for (CNC or sheet of a mesh), a pull beside `--candidates`, a unit for a type that
declares its own and a value of another kind are refused before anything is
read, as a STEP given no process is (it keeps none). An xbf or a model given none is checked for the one
its parts declare, its process's options refused once the document is read.

**A B-rep's check is measured in the engine's checks processes.** The caller (the command, or `cad.<type>.dfm`
in any Python) resolves the options and asks the engine (`api.check`): an `export` request carrying a
`check`, its own release (`caller`), what measures in it (`measures`, `contract.measuring`: the digest of the
library's code, every source file of the cad package -- a `.py`, or the `.pyc` an install of bytecode alone holds
in its place -- the digest of the files that measure each manufacturing process alone (`dfm`, `_measuring.DFM`:
what a kept measurement is found by), and the versions of the libraries a B-rep check measures with -- build123d,
OCP, bd_materials, numpy, scipy: every library the measuring files import -- taken once, when the caller first asks a check, and at once as a checks process starts, before
anything a check measures with loads; never as `cad.engine` is imported, which costs nothing for it. It is the code
as the process loaded it: a source file changed since the library began to load there (`cad._LOADED_NS`) makes it
a code no other process has, so no process measures for it. A process with no kernel, the `cad` command's, names
no library) and no destinations.

One class owns a check's life ([checks_runner.py](../checks_runner.py), whose docstring is the mechanism), and
every check is measured in a checks process (`services.CHECKS`), never in a model's worker: a STEP's or an xbf's
from its path, read once while its bytes stay as they were (by their digest, four files and 256 MB of them at
most, `worker._file`); a document the engine holds from its bytes -- the server's or the cache's, else the ones
its worker's protocol-1 `result` gives, one short request of that worker (`Daemon._check_document`) -- read once
per version (four and 256 MB at most, `worker._document`). So a build, an inspection, a snapshot or a view of a
model waits for no check of it, a build has no check to cancel, and a long check or its crash costs no document
anything. The engine measures only for a caller of its own release whose code and libraries are the checks
processes' (`contract.measures_for`; theirs is the base's: the server's own, read at each check, where the kernel
environment is the server's, else what the latest checks process started since the base was made said --
unknown until one has, and again once the base is made again, which retires them all: `Pool.known`,
`rebased`). Any other caller is answered at once with no `checked`, nothing measured, and measures a file in its
own process and a model's document exported and read back there; a `cad` command with no kernel sends either to
the base's environment (`manufacturing.through_engine`, `integration_env`). So does a file's check where no
engine can be reached. Either way `api.check` says so in one line on stderr, in the process that can then
measure it: nothing keeps such a check, so it is measured again each time it is asked. What the engine measured
`api.check` returns as `measured_in: "engine"` (`api.IN_ENGINE`; `IN_CALLER` is the caller's to say of its own).

**The interference check** (`cad <type> interference`, `cad.<type>.interference`: a model's, an xbf's, a STEP's)
is asked and answered the same way and is no manufacturing process's: the caller resolves its options
(`cad._internal.interference.options`: the poses, the mechanism states, the configuration sequences and their
samples, the named fits, its limits) and asks `api.check` with `process: "interference"`, which the runner takes
beside a process's (`checks_runner.INTERFERENCE`) and the checks process hands to its own measurer
(`registry.interference_check`, `cad.build123d._interference`, whose docstring is the mechanism). So it has a
check's whole life -- a slot of the pool, the limits, the kept result by the document's version and the options,
`superseded` when the model is built again. What it measures: each pose is every part's placement (as built,
or the mechanism's forward kinematics at a pose or at a sample of a sequence); the pairs whose boxes meet there
-- each part's tight box, turned with the part -- are answered once
for each way two parts stand to one another, so the copies of a part and the parts no pose moves cost one
answer. An answer is read from what was kept, else ruled out by the two parts' meshes, else measured. **Kept**:
each answer is written to the cache (`<cache>/interference`) under the two parts' geometry keys and the
placement of one in the other's frame, as it is made, with each geometry's tight box; so a model built again is
measured only where a part that changed is one of the two, a check stopped by its time goes on from what it had
measured, and a check that left a pair unmeasured is not kept whole (`partial`), so it is asked again. **Ruled
out**: the kernel takes seconds over a pair and minutes over a maker's drive beside a lofted cover, and most pairs
whose boxes meet have air between them, so the two parts are meshed (0.05 mm at most) and asked of the kernel's
own proximity test (`BRepExtrema_ShapeProximity`: a tree of each mesh's triangles); with no triangle of one
within the two meshes' deflections of the other's, and no shell of either inside a solid of the other, they share
nothing. **Measured**: every other pair, by `overlap_volume` on the parts' own solids, the pairs of the fewest
faces first. The pairs are measured in a few processes the checks process starts for the check (one a
core, four at most, each a kernel of its own, outside the memory the engine's rule counts, each ended by a small guard process
the moment the checks process is gone), because a
Boolean cannot be stopped from inside: a pair past its time (five minutes) has its process killed and is
answered **unmeasured** (`over_time`), as is one whose process exited (`process_lost`), one the kernel refused
(`error`) and every pair not reached
within the check's own time (twenty minutes, kept under `CAD_ENGINE_CHECK_SECONDS`, so a long check answers with
what it measured and goes on from there when asked again); neither limit is an option of the check. The result is a
`CheckResult`: `failed` with an `overlapping_parts` finding a pair, as a stress study names the same fact; `not_checked` (`unmeasured`) where none was found
but a pair went unmeasured; `ok` only with none of either. A caller of another release or code than the checks
processes' is not measured for (`Unanswered`): there is no measuring in the caller.

The checks processes are a small pool (`checks.Pool`): `CAD_ENGINE_CHECKS` of them (held to one to the machine's
cores, which `cad server status` says), else half the machine's cores, one at least and four at most, each a kernel
process of its own key (`checks`, `checks-2`, ...), with the daemon's environment, outside the count cap,
measuring one check at a time, so a file's check never retires a person's idle worker for its slot. A check
takes a free slot whose process last measured its document (what it read is still held there), else one whose
process is alive, else one whose process is to start, where the memory cap has room for one more beside those
being started, each of a checks process's size (`Pool.size_of`), and the system is not under memory pressure;
one that can take none says so to its caller on stderr at once ("waiting for another manufacturing check, started
21 s ago: the 4 checks processes are all busy"). An idle checks process is shed for memory with the render
processes; one over the memory cap after a check drops what it read (`worker.shed`) and, still over it, is
retired.

A checks process is asked one of two things of a document (`worker._check`), each in memory, nothing exported or
written. To **describe** it (`cad.build123d._dfm_check.described`): it reads the document and answers what a
measurement would read of it, its content record (`_dfm_brep.content`: each part's geometry key, names, how its
occurrences stand, the token of any mesh it was read with, its declared material's physics and process; never
its bytes, its path or its look), measuring nothing. To **measure** it (`held`): for the process the check
names and with the options that process's measurement reads alone (`cad._internal.dfm.kept.measuring`: each
process declares them, `MEASURES`, and is handed a table of those and no other), each part on a copy that shares
nothing with the document read. It answers the report (`checked`, with the release that measured it and whether
it read the document anew: `read`), the key of the record of the very parts it measured (`content_key`), and
`transient` beside a report the next measurement could make otherwise (`_dfm_check._transient`: molding's
release search out of its seconds; a family that failed for want of memory, by any of its names, and a print's
hull that took its other way for it; the kernel's validity check raising on a part, which leaves the report
silent on what it would have said; a table of the report that says of itself
`repeatable: false`, wherever it lies -- a CNC report's `holes.recognition`, where the holes' recognition fell
back for a reason the next check may not meet: its helper's environment not made yet, an answer that timed out
-- while one that says true, or nothing of it, is repeatable). The caller finishes the report into its result; every finding's
location is a ref `inspect` resolves, and the result equals the one the same document gets read from its file.
Neither entry point knows which process runs it, nor does a key: a checks process is where the runner sends
them today.

Each asked check is in one state (`checks_runner.State`): asked, waiting for a slot, starting its process,
measuring, answered -- or stopped by the engine, which stops only a check that has not ended and kills only the
process that check's own lease holds (signalled under the runner's lock, which the lease's end takes before it
lets the process go; a checks process holds nothing of anyone's). A check that does not complete is never a
result: it fails with one word for why (`reason`, `api.EngineError.reason`), for its caller to tell from a part
that fails its rules:

- `stopped`: the engine stopped under it -- an update's drain, which waits for no check, or `cad server stop` -- every
  check waiting or measuring at once, and one asked meanwhile (`api.Stopped`, from the engine's answer or its
  connection closing): run it again;
- `cancelled`: every caller of it had gone -- its own and each attached since, each connection watched for its
  end of file (`daemon._watched`) -- while a check whose caller is there could take no slot, so its process is
  that one's (`Runner.reap`: one for each such waiter, the oldest first). Otherwise a check outlives its caller,
  as a build does, and its measurement is kept; a check someone waits for is never cut short so; and a waiter
  whose own callers have gone leaves a free slot to one someone waits for;
- `over_time`, `over_memory`: past a check's own limits -- `CAD_ENGINE_CHECK_SECONDS` measuring (half an hour by
  default) or `CAD_ENGINE_CHECK_RSS_MB` resident in its process (by default the engine's memory cap), `0` for no
  limit -- which a watchdog reads every second from outside the process (`/proc`, `ps`, the system's count on
  Windows; where the system says no memory, the time limit alone), so a kernel call that never returns is stopped
  all the same, and the engine's memory rule counts what a measuring process holds now;
- `process_lost`: its checks process exited under it (one the system killed: usually for memory, and said so);
  the check is not run again, and the next starts a fresh process;
- `no_kernel`: no checks process could be started;
- `superseded`: its document changed under it -- a model built again, a file rewritten while it was read -- so
  nothing of it is kept or answered. The daemon tells the runner of each document a build registers, a hand-over
  replaces or a deletion removes (`Runner.built`): a check asked at a generation now gone stops there, its
  process killed and its slot free, never measured to its end for a result no one can use (the generation, read
  before its bytes and again after the check, catches a build the runner was not told of). While a caller of it
  is still there the check is asked again, of the document as it is now, three times at most (`READS`), and its
  callers -- the ones attached to it too -- get that result, saying once on stderr that the document changed;
  `superseded` is answered only past those tries, or where no caller is left to ask again for. A run that changes
  nothing keeps the generation and a build of another model is another document: neither disturbs a check;
- `error`: the measuring itself raised: its type and words, in one line.

A request that is no check -- a process the type has none of, options not resolved -- is refused in one line
before anything is read. The same check asked while it runs waits for it (`Runner.running`, by document, version
and check), says so ("waiting for the same manufacturing check, started 21 s ago") and answers with its answer
-- its result, or its failure -- so it is measured once. A manufacturing check of a file is the same only under
the name its alias is by: a hard link under another name is one file to the pool and, where the document's root
has no name and takes the file's, another document, so it is described and answered as itself. Two checks that read one measurement and differ beside
(another material, another path) are not the same check there: asked at once, each waits for a process of its
own, and each looks once more, as it gets its process, for what the other described and kept meanwhile -- so
with one process free they measure once, and with two they may measure twice, the second in the first's place.

**What is kept of a manufacturing check** ([measurements.py](../measurements.py), whose docstring is the store):
its measurement, by what was measured and not by which document it was measured of. The rules and the verdict
are never kept: the caller judges the report each time (`manufacturing.finish`). A check's try
(`Runner._content`) goes:

1. **The version.** A model's generation, read before its bytes and again after; the digest of a file's bytes.
2. **What the version holds**, its content record: the one kept for it (its *alias*), else the one a checks
   process says of it, asked to describe it under the check's lease, kept from then on. A model's alias is by
   its id, its revision (its build closure's key) and a digest of the build's facts as the engine holds them
   (`Daemon._check_built`; a build with no key, or none known of, by its generation, in memory alone);
   a file's by its bytes' digest with its name's stem and suffix, which are all of its path a read takes (an
   unnamed root is named by the stem), so the same bytes under the same name anywhere are known with no process
   asked. An alias is kept with the code and libraries that described it, and is served to a caller that process
   would describe for: after an edit to the library, or a release, a version is read once more. The facts are
   in a model's alias because a build is not always a function of its closure: one that reads its environment,
   an argument or a clock can make other parts at a revision the model had before (after an edit undone, or a
   deletion), and a check answered from what was kept asks no process to notice. By its facts -- its parts'
   geometry keys and counts, their looks and materials, its bounds and joints -- such a build is another
   version, and is read again; and a deleted document's aliases go with it. Two builds at one revision that
   agree in all of those are taken for one document: a part renamed, or moved within the same bounds, by what
   no closure holds is not seen until a process is asked.
3. **What the check asks**, from the record alone, in the daemon, with no kernel (`kept.asked`): the process
   named, or for a check given none the one the parts declare and its options resolved for it
   (`manufacturing.declared`, with the finding that says so); a record of no part is `document_empty`, and
   what `declared` refuses is the check's refusal, each answered from the record.
4. **The measurement** that check reads (`kept.measure_key`): the document's type, the process, whether it
   ranks candidates, the options its measurement reads as resolved, and the digest of the code that measures
   that process. The report kept under the record's key and that key is the answer (`reused`), with no process
   asked and none of the document's bytes read.
5. **Else it is measured**, in the process that described it where one did, for the process named, and kept --
   whole or with a family not measured, which its code makes of those parts each time; never one its measurer
   says is `transient` (out of its seconds or its memory, or holding a table that says it is not repeatable:
   answered, and measured again by the next check), a document that did not read, or one with no part a
   process makes.

Either way the answer is the asking check's own: its process, its options as resolved, and after the report's
findings the one that says a process was declared (`process_declared`), where one was -- byte for byte what a
measurement of that check answers. So none of these measures anything: another value of an option its rules
alone read (a CNC part's material; a sheet's material sets its K-factor, which its measurement reads, so there
it is measured again); the same bytes at another path; a process declared and the same one given; a model built
again with another colour (read once, to learn it holds the same); an edit made and undone; a restarted engine;
a release that changed none of that process's measuring code.

A result is kept with what measured it -- the digest of its process's measuring code and the libraries'
versions -- and is served to a caller whose own digest for that process and libraries are those
(`contract.measures_for` over the two): a caller of another library's version is measured again, the new result
in the old one's place. A caller with no kernel, the `cad` command's, names no library: it is answered by what
the checks processes measure with now, where the pool knows it (`Pool.known`), so after the base is made again
with another library an alias or a result of the one before is not served to it either; where the pool does
not know yet -- no checks process has started since the engine did -- whatever its code measured serves it.
The live handshake is unchanged: a process measures, and describes, only for a caller of its own
release, whole code and libraries. A report is kept under the key of the record its measurer says it measured;
where that is not the record the check was resolved from -- the alias told wrong, the file was rewritten between
its describing and its measuring -- nothing of it is answered, the alias is forgotten, the report is kept
under the key it said, and the check is asked again, as of a document that changed, where it finds it. A version
that differs after the check keeps nothing.

In memory the store holds 1024 aliases and 32 MB of them, 128 results and 64 MB, least recently used first. On
disk it is under `<cache>/checks/`: `checks/models/<id>/<revision's digest>.json`, a model's aliases, the 8 most
recently used, and the models' together 4096 and 32 MB at most; `checks/files/<xx>/<token's digest>.json`, the
files' aliases, 4096 and 32 MB at most; and
`checks/results/<xx>/<record's key>-<measurement's digest>.json`, 1024 and 256 MB at most, each written whole,
the least recently used (by its time on disk, set again by a read) going first. An entry that does not read as
what its name says -- not the JSON written, another format, another token's or measurement's under its name,
a record whose key is not its own -- is removed, never served. Each of the three is listed
once, at its first use, the half-written files a stopped engine left swept then; one gone since leaves
the list as it is asked for; and a cache folder that cannot be written keeps nothing there. Deleting a document
removes its own aliases: `checks/models/<id>/` goes with the document's other folders, removed by the registry
itself (`Registry.delete`), so by `cad delete` with no server running as by an engine; an engine that runs is
told (`FORGOTTEN`) and drops what it holds of them in memory. They are read and written under the registry's
lock of the document, so a check of it that began before neither names an alias nor takes one from disk into
memory. The results are no document's, and go by their bounds or with the cache (`cad cache clean`).

**What is kept of an interference check** (`checks.py`), which keeps each pair's answer by the two parts'
geometries itself: its result whole, by the document's version -- a model's generation, a file's bytes' digest
-- and the check (type, resolved options, the library's release and its code's digest), served to a caller the
process that measured it measures for, and only a result with no pair left unmeasured. A file is keyed by its
device and inode, so its hard links and the spellings of its case share one key in memory and while it runs
(`checks_runner.file_key`; by its real path, its case folded where the file system says it folds it, where the
system gives no inode). A document holds one version's results. In memory 128 results and 64 MB at most; on disk
under the version that outlives the engine (a model's revision; a build with no key keeps nothing there),
`<cache>/documents/<id>/checks/` (`checks.Disk`), so deleting a document removes them with it, 1024 results and
256 MB at most, least recently used first, an entry that does not read removed, never served, written under the
registry's lock of its document. A file there of the format before this one, which held a manufacturing check's
result too, is removed as the store is listed, which the first check asked of an engine does: none is read again.

`cad server status` lists each check asked and not ended: its process, its document or file, where it measures or that it
waits, for how long and whether its caller is gone; and `cad server status --json` counts both stores as one (`checks`: held,
bytes, measured, reused, restored: those reused from disk; described: the documents a process described; read: the
documents a process read for a check; aliases: the versions whose record is held in memory;
waited: those that waited for the same check; asked: those not ended; disk: held, bytes and the files' aliases on disk, once listed;
pool: its size, how many are busy, each checks process, and the line said where `CAD_ENGINE_CHECKS` was held to its
bounds; limits: a check's, in seconds and MB; running: each check asked and not ended -- type, process, document
or file, its `state`, `where` it measures (None, and `waiting`, while it has no process), since, seconds, whether
a caller is attached and how many are: `callers`, a caller gone never counted).

A part an edit left untouched is
measured again with its document: a measurement is of a document's parts together, as its record says them. A mesh is read as before (an STL as it is; a 3MF or a GLB written as one STL by
the library's readers), by its caller, in a process of its own the caller holds to a check's limits
(`cad._internal.manufacturing._watched`: the engine's, `worker.check_limits`). The process measures (`cad.build123d._dfm_<process>`, `cad.trimesh._<process>`),
the type side judges the report against the process's rules (`cad._internal.dfm.rules.evaluate`: general
practice, each rule cited, no shop's limits), and the result is
a `CheckResult` whose `measurements` is the report with every rule's outcome (`measurements["rules"]`). A
mesh's or a DXF's command runs it in its own process when its environment holds the type's integration
(`cad_server._internal.integration_env.carries`: a checkout's, one installed with the extras); else in that
integration's environment at the installation's release -- `cad[build123d]` is the base the engine's kernel
processes already run in, `cad[trimesh]` one the engine makes once, as `cad run` makes a program's
(`extras.ensure`) -- whose Python runs the library's runner of one operation (`cad._internal.operation`: the
call on stdin, the result on stdout), the result printed as it would be here. A refusal there -- an option
the declared process does not take, an id the engine does not hold -- comes back with its reason
(`invalid_argument`, `not_found`: `integration_env.Refused`), the command line's mistake, exit 2, as it is
here. The families, the JSON and
every rule are the library's `src/cad/_internal/dfm/README.md`.

**The stress study.** A B-rep type's `solve` (`model`, `xbf`, `step`: the registry's `solve` operation of the
`calculix` integration) is one function the library makes for each (`cad._internal.fea.operation.solve_for`, bound by
`DocumentType`): with no study, the study's setup, which writes nothing; with a study and `--out`, the solve.
The options of the other use (`--out` or `--deck` with no study, `--occurrence` beside one, an `--out` that is a
file) are refused there, the standard library alone, before anything is read. The study reads a file's B-rep with
the kernel in its own process (`cad._internal.fea.document`; a model's, from an `.xbf` the engine writes of it in a
temporary folder), meshes it with netgen in a process of netgen's own (`cad.netgen._mesher`) and solves it with
CalculiX (`cad.calculix`: the `calculix` integration's probe, `CAD_CCX`, else the cad-ccx package's `ccx`, run headless
in a private folder by `cad._internal.programs`; `--deck` keeps the input of the solve written). Its answer is a
`cad.results.FeaResult`, a check's: findings, `measurements` and the files `written` into the folder `--out` names
(`cad._internal.fea.run`): `result.json` (that answer), `result.glb` (the deformed surface coloured by a ramp
texture), `result.vtu` (the volume's fields) and `stress.png` and `displacement.png`, the stills of the GLB drawn
by this engine's snapshot in the study's own process (none, and a `solver_note`, where it cannot draw). The command runs the study in its own process when its environment holds the
kernel, netgen and ccx (`integration_env.carries("calculix")`, the kernel and netgen being calculix's
`alongside`: a checkout's with the extras, one installed with them); else in the environment of
`cad[build123d,calculix,netgen]` at the installation's release, made once by the engine, by the library's runner
of one operation, and the result is printed as it would be here (`FeaResult.from_data`).

**The KiCad board's DRC, the schematic's ERC and their exports.** `cad kicad_pcb drc` and `cad kicad_pcb export` are the library's
`cad.kicad_pcb.drc` and `export`, the `kicad` integration's (`cad.kicad._check`, `_export`), run the same
way: in the command's own process where it runs KiCad itself (`cad.kicad._program.carried`: `CAD_KICAD_CLI`
names a `kicad-cli`, or kicode is installed there), else in the environment of `cad[kicad]` at the
installation's release, made once by the engine (about 100 MB to download from PyPI, mostly kicode, and 340 MB on disk, the first time). kicad-cli
is found by the library's helper (`cad._internal.programs`: the override, then `kicode.executable()`; never
`PATH` or KiCad's installation folders) and run headless in a private folder, with `kicode.environment(root)`
for kicode's. An export's result is a `cad.results.ExportResult` (the files written, the warnings). A
board's `--to glb` holds its copper, mask and silkscreen too, each KiCad's own mesh named by its layer
(`<board>_copper`, `_pad`, `_via`, `_silkscreen`, `_soldermask`, `_PCB`); its `--to step` holds the board
and its parts alone. A
schematic's `cad kicad_sch erc` and `export` are `cad.kicad_sch.erc` and `export` (`cad.kicad._schematic`),
run the same way.

**A MuJoCo model's check.** An MJCF is MuJoCo's own file and no document type: the engine writes one
(`export/mjcf.py`) and reads none, the viewer lists none, and no still is drawn of one -- MuJoCo Studio shows
it (`cad run mujoco-studio --model FILE`). What cad does with one is the `mujoco` integration's operation,
`cad mujoco check FILE` (`cad.mujoco.check`, `cli/integrations.py`: the registry gives an integration
operations only on its tool's own files, with the suffixes they take). It is MuJoCo's compiler on the file
(`cad.mujoco._compile`: `MjModel.from_xml_path`, its warnings caught through `mju_user_warning`), what it
refuses an error and what it warns a warning, in its words; the model-health checks on the compiled model
(`_health`); and two facts as infos, each row of them in the result's `measurements` (`_report`): what the
model collides as (the geoms with a `contype` or `conaffinity` not 0, by kind and by body, and the moving
bodies that collide as nothing) and each contact exclude with how far apart its two bodies' collision geoms
stand at `qpos0` (`mj_geomDistance`). It runs in the command's own process where that holds mujoco, else
in the environment of `cad[mujoco]` at the installation's release, made once by the engine (`mujoco-core`
and `mujoco-studio`, about 20 MB: the compiler and the bindings, and Studio's web viewer, no GL). A
MuJoCo function's `save` says the same of the file it wrote.

**OrcaSlicer's presets (deprecated).** The `orcaslicer` integration is on its way out: a project saved from
OrcaSlicer's app carries its settings and slices on its command line as it is, and from OrcaSlicer 2.5 the
built-in presets are binary caches these commands cannot read. Its commands stay, unlisted, while skill text of
the last 30 days uses them, and say on stderr that they are deprecated (the registry entry's `deprecated`).
What they do until then:
OrcaSlicer keeps a preset as its differences from a parent (`inherits`), and its
command line neither fills the parent in nor reads compatibility conditions. The `orcaslicer` integration's two
operations take preset names, not a file (`cli/integrations.py`): `cad orcaslicer presets KIND` lists the
selectable presets of one kind, and `cad orcaslicer complete` writes a printer, a process and each filament
merged with every parent, the process and filaments naming the printer as compatible, as `printer.json`,
`process.json` and `filament-N.json` (`cad.orcaslicer._presets`: the folders given first, then the person's own,
the Flathub build's and the app's profiles; of several vendors' presets of one name, the one that lists the
printer, else the nearest). Every preset is resolved before a file is written. The integration has no extra:
its code is the standard library alone, so `integration_env.carries` holds it everywhere and the command runs
it in its own process, asking the engine nothing. OrcaSlicer itself is never run.

**A part's convex hulls.** `cad.mujoco.decompose(spec, part, max_hulls=16, threshold=None)` replaces a part's
collision in a MuJoCo function's spec with the convex hulls CoACD cuts its mesh into, the `coacd` integration's
(`cad.coacd._decomposer`), while its visual stays the part whole. It hands the mesh, with its options, to `hulls.py`,
which reads each mesh's hulls from the engine's cache (`places.cache_dir()/hulls/<digest>.npz`, the digest of the
recipe -- CoACD's release line, the weld, seed 0 --, the options and the mesh's bytes; never the model's folder),
and decomposes the misses in one child interpreter of the calling environment, or of the coacd integration's
environment (`python -m cad.coacd._decomposer`: CoACD's native library carries a TBB of its own beside OCCT's,
logs from native code to file descriptor 1 and can die on a mesh it cannot repair, so the process that holds the
kernel never loads it), keeping what it made. One decomposition is one mesh with one set of options. Each hull is a
mesh asset `<mesh>_hull<i>` (a file in the engine's cache) and a collision geom `<part>_hull<i>`. A decomposition
the cache does not hold needs coacd: where the calling environment does not hold it (a script `cad run` runs, whose
imports name `cad[mujoco]`, or a Python of its own), the device's engine makes `cad[coacd]`'s environment on first
need over its door (`{"op": "integration", "integration": "coacd"}`, `integration_env.made`) and the child runs
there, so no script names it in its header. It is refused by name, naming the part and the extra, only where CoACD
has no wheel, no engine answers, or the making fails; a hit needs no coacd at all. `cad[coacd]` is one wheel, about
3 MB, for macOS arm64, Linux x86-64 and aarch64 and Windows x86-64.

**A part's features.** `cad.quiddity.features(part)` (`features_of(parts)` for several) asks quiddity, a recogniser
of a STEP part's features, about one part of a document: its holes and its other features, each with its faces, and
where every face went (a feature, the body's own stock, a refusal, unexplained). The part's STEP is written in memory
(`engine/export/step.py`'s `shape_bytes`: geometry alone, where the part stands, the same bytes for the same shape)
and handed over a pipe to a child interpreter (`python -m cad.quiddity._recogniser`, the one module that imports
quiddity), one child for all the parts of a call, nothing written to disk. It is a process of its own because
quiddity has no time limit, no way to stop a run and no bound on its memory, and a fault in its native code would
end the process that holds the kernel: a part not answered in `timeout_s` (30 s unless the caller says) is given up
and the child stopped, a child that ends with a part says so, and the parts after either go to a new child. quiddity
numbers the faces of the file from 0 in its order; the kernel's writer puts a shape's faces there in the order it
numbers them (`TopExp.MapShapes`, a ref's ordinal), so quiddity's face `i` is `face i+1`. That is checked on every
call (`cad.quiddity._features`, the gate): quiddity counts the faces the kernel counts and accounts for each; the
point it proves on each face lies on the kernel's face of that ordinal; and where a record's family says what its
faces are, the kernel's own reading of them agrees (a hole's cylinders concave, about its axis and at its diameter or
a step's; a countersink's cone about that axis; a step level's faces planes). A part that fails any of it has no
features, never some. The result is plain data, JSON-safe and the same for the same part: `available`, and then
either the records, the holes in the words a check reads first and the accounting of every face, each face its
ordinal and every length in millimetres where the part stands; or the reason nothing was measured, one of a closed
set (`cad.quiddity.REASONS`), which no call raises for. An available result is not a complete one: quiddity leaves
faces unexplained and says which, so nothing found is never nothing there. Where the calling environment does not
hold quiddity -- the base, `cad[build123d]`, which the engine's kernel processes run in -- the device's engine makes
`cad[quiddity]`'s environment on first need over its door (`{"op": "integration", "integration": "quiddity"}`,
`integration_env.made`) and the child runs there, so the base is as it was: the code that asks
(`cad.quiddity.features`) reads the part through the kernel's modules (`cad.build123d._dfm_brep`, the engine's STEP
writer), so it runs only in a process whose environment holds the kernel, and quiddity's environment runs the
child alone, never that code (law 24). A check does not wait on that environment's first fetch (law 17): it waits
six seconds at most for it (one made from uv's cache is there in a second or two), reads its holes with its own
detector where it has not come, saying so, and asks for it again a minute later at the earliest
(`cad.quiddity._process`), so a computer offline with nothing cached pays those seconds once a minute at most, in
the checks processes that ask. `cad[quiddity]` is one wheel, about
9 MB, for macOS, Linux x86-64 and aarch64 (glibc 2.28 or newer) and Windows x86-64; anywhere else a part's features
are unavailable (`no_wheel`). No command runs it; the CNC check reads it, for what closes a part's holes
(`cad.build123d._dfm_cnc_recognised`).

**A GLB in Blender's scene.** `cad.blender.load` is the `blender` integration's one helper, for a script that
renders with bpy (Blender as a Python module, its extra `cad[blender]`), run by `cad run` in the environment
**Running a model** describes; no command of the server's runs it. It reads the GLB with the library's own
reader, hands Blender's glTF importer a copy whose JSON tags every node with its index (in the node's
`extras`, which the importer keeps on the object it makes, as a custom property) and names every animation by
its index, the binary chunk a file beside it in a temporary folder, and so knows each node's object and each
clip's action whatever Blender names them: a node with no name, two of one name, a name Blender cuts short.
The tags are taken off, each action is given its clip's name, every NLA track the import made is removed,
and each node a clip moves is put back where the file places it (the importer leaves it at its first clip's
start). `Model.play` assigns one clip's action to the objects it moves, the scene's frames 0 to its duration.
