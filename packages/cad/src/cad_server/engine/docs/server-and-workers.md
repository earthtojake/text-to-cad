# The engine server and its workers

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

One engine server (`daemon.py`: a daemon) for the device (**Starting and updating**), started by `cad server
start` (or `cad mcp`). **No timer stops it**: a
person may be using a page or the CAD app for hours without a build. It stops in four ways: on
`cad server stop` (or a terminate); once it has drained, asked by the switch of 0.11.11 and earlier, a newer
release's start or cad's own update (**Starting and updating**); when
its door is gone -- its folder removed, a
temporary folder cleaned up, or another file put in the door's place -- so that no one can reach it
(`Daemon.tend` sees it within a round, and it stops as `stop` does, saving what it holds to the
cache); and with the machine. **No timer retires a worker either**: memory alone does. Idle
documents are saved to the cache, past the memory budget what no page watches leaves memory for it
(**Document lifetime**), and past the workers' memory cap, or under the system's memory pressure,
idle workers go (below). It holds a pool of warm workers, one per model script and Python (and one for
the documents no worker built), each a process whose memo lives as long as it does, and one standby.
Its rules are a standard pool's and one ceiling on a busy process (below): no admission guess, no
refusal; the operating system does the rest. (What the daemon itself holds, the documents and their
tessellations, is under one memory budget: **Document lifetime**.)

- **A cap.** At most `CAD_ENGINE_WORKERS` workers are alive (default: the machine's
  cores). A build for a script whose worker is alive goes to it, waiting while it builds
  something else: one build at a time per worker, builds of different scripts at once.
- **First come, first served.** A build for a script with no worker starts one under the cap.
  At the cap, the least recently used idle worker no page watches is retired first (drained of
  its documents, then its stdin closed, so it exits), and its slot is the new one's. With every worker busy, the build waits
  for the first to come free, and every build that needs a slot after it waits behind it. A
  build that waits for its own script's busy worker takes no slot.
- **The cap never retires a watched worker.** When every idle worker has a document a page
  watches, the new worker starts past the cap. The memory cap may still retire a watched one.
- **A standby.** One worker stands by with the kernel loaded and no script (`Supervisor.stand`): started
  once the base exists -- with the daemon where it is made already, else the moment its making on first
  need is done (`Daemon.made_base`); a start with none makes none, and no standby stands or is waited
  on before it (**Running a model**) -- and again each
  time a build takes it or starts a worker of its own, while the pool has a slot for it under the cap
  and room for it under the memory cap. A build for a script
  with no live worker takes it when the build's environment shapes the interpreter as the
  standby's does (`places.RESTARTS`), and starts a fresh worker otherwise -- after which the
  standby, of another interpreter, is replaced by one of the build's. A build in its script's own
  Python (**Running a model**) never takes it, nor waits for it, nor moves it, nor retires it for room
  at the cap: the standby is the base's, and stays for its builds. Taken, it is that script's
  worker (the standby's adoption, `Process.adopt`): its key, the environment it was asked in and the folder a fresh worker
  of it would start in, its run's environment adopted as every run's is (`worker.adopt`). A build
  arriving while the standby starts, of its interpreter, waits for it rather than start another.
  It counts toward the cap, is the first retired for room at the cap or for memory, and is never a
  script's worker in `status`. Measured on a 10-core Mac (one-box models, an installed bytecode
  cache): a new script's first build took 2.5-2.6 s in a fresh worker and 0.15-0.23 s in the
  standby; the standby holds 440 MB, a one-box model's worker 450-520 MB.
  `CAD_ENGINE_STANDBY=0` keeps none (`daemon.standby`): an operator's seam for CI and machines
  short of memory, not a setting a model's author touches; unset or any other value, the standby
  stands by. A test suite sets it for every daemon it starts but the standby's own.
- **Memory retires, never a timer.** The workers' resident memory -- each one's as it measured it at
  its start and after each build, the standby's and the render processes' with it -- is held to one
  cap, `CAD_ENGINE_WORKER_RSS_MB` (default: a quarter of the machine's memory, at least 2 GiB;
  `0` for no cap; `Supervisor.shed`). After each build and picture, and each `Daemon.tend` round, past
  it idle processes are retired, least recently used first within each rank: the standby, render
  processes, the workers no page watches, then the watched ones, only when no other is left; a
  worker is drained first, so its documents stay held. Under the system's memory pressure (the server's
  `serve.Pressure`, polled every two seconds), the standby goes at once, none starts while it lasts, and
  the rest go down to half the cap (`CAD_ENGINE_PRESSURE`: `0` never under it, `1` always, unset
  measured; a test's seam, `Pressure.from_environment`). A busy process is never retired, and an idle worker under the cap lives as long as the
  engine. A worker alone over the cap after a build is retired at once: the report says so
  (`retired`), and once it has answered the daemon drains it and closes its stdin.
- **A busy process has a ceiling.** Retiring never takes a busy process, and a build in native code
  (an OCCT boolean that runs away, say) cannot stop itself, so a process past
  `CAD_ENGINE_WORKER_CEILING_MB` (default: half the machine's memory, at least 4 GiB; `0` for none;
  read when the engine starts) at two `Daemon.tend` rounds running, during one request, is killed
  (`Supervisor.overrun`). Two readings, so a peak that comes back down is never taken for a runaway: a
  runaway runs up to two rounds, a minute by default, past the ceiling. A reading under it, or another
  request, starts the count again, and a process whose request ended while it was measured is never
  killed: an idle worker is drained before it stops. Its memory is read from outside, as the system
  counts it (`worker.footprint_mb`: compressed and swapped pages too), since a busy worker says its own
  only when it answers; a platform that will not say has no ceiling. Its build fails as a build out of
  memory (`MemoryError`, `daemon._overran`): the error says the engine stopped it, at what size and
  past which setting; it is no crash of the engine's, and its page does not offer to report it.
- **Collected when idle.** A worker builds with Python's cyclic collector off and collects once
  no request has come for half a second, so a script's calls one after another never wait on
  it. A worker over its memory cap collects before it measures again.
- **One load per run.** The calls one `python model.py` process makes of its script are served
  from one load of it while every file the load read stands as it was, the call comes in the
  environment the load ran in (a run is its caller's environment, and a program that changes its
  own between two calls changes what an import of its script reads), the load made no kernel
  call and every call since took its models from their keys. Anything else loads the script
  again: another run, an edit, a body that ran.

**Services.** Every process the daemon starts and supervises is a service it declares, in one place
([services.py](../services.py)), and one supervisor runs them all ([supervisor.py](../supervisor.py), whose
docstring is the mechanism): a model script's worker (the documents worker among them), a served
document's render process (whose pictures [renders.py](../renders.py) asks for) and the checks processes (every
manufacturing check: **Document types and integrations**). A declaration says what
the process runs and in which environment, whether a lease may name the Python it runs instead, its
caller's (`interpreter`: the worker's), what one process serves (its key: a script's path, a
document's id; with a Python a lease named, that Python too), what binds a process to its caller's
interpreter (`places.RESTARTS`), whether it
counts toward the count cap, its rank when memory is shed (the standby 0, a render process 1, a
worker 2, a watched worker 3), whether the daemon drains it before it stops, whether its retirements
are listed in `status`, whether it keeps a standby and how long its start may take: a process that
has not said it is ready by then -- a worker in 300 s, the standby in 600, a render process in 120 --
is killed, and the request that waited for it refused in one line saying so, never asked again (a
standby is simply not there, and the daemon's log says why, once). The rules above
are the supervisor's, for every service alike: a new kind of process is a declaration, and no code of
the daemon's. A new service's large outputs go by path, a file on disk its caller reads, and its small
answers in frames; today's children keep their bulk in frames as they always have (a drained
document's xbf, a version's meshes sent to a render process, a picture). Not services: the build's
STEP reader (the worker's own child for one build), the meshing and reading pools (the library's,
which run with no daemon too) and the processes that outlive the engine (the telemetry sender, a new release's
setup an update runs). A known limit: the meshing and reading pools' memory, and the STEP reader's
and its helpers', count toward neither cap (12 processes and 3.2 GB measured with the meshing pool started on a 10-core
machine, below; 2.3 GB parsing a 354 MB STEP).

**The protocol** (`cad.engine.frames`), every service's: requests are one JSON object per line on the
child's stdin, a request's payload that many `bytes` after its line, each carrying the memory cap the
daemon holds its processes to (`rssCapMb`), which a child over it after a request retires itself by
-- never its caller's environment's, which a worker adopts; the child answers on a handle of
its own -- its original stdout -- in frames, a JSON object on one line and that many `bytes` after it,
and says what it prints on its stderr, its log. Its first frame is `{"ready": pid, "rssMb"}`; then,
for each request, its `log`, `notice` and `progress` frames, which go to whoever asked, and one
answer, which may say `rssMb` and `retire`. A line before a frame that is no JSON object is skipped
(a banner). A child that answers side requests while a request runs (a worker's `where`) reads its
stdin on a thread of its own. It exits when its stdin closes. The supervisor holds it from its spawn:
`cad server stop` kills one still being started, which reads nothing until it is ready (the standby loading
the kernel), so none outlives the engine. Its memory is what it says (`rssMb`):
a child that cannot measure itself is never retired for memory.

The meshing pool starts with the first page, view or inspection, never with a build. A build
serves its document, so the daemon's server starts with the first `python model.py`; its meshing
pool waits. Every process starts on the first mesh a page asks for, or on `Server.warm`: sent by
`cad viewer` at launch (`CAD_VIEWER_WARM=0` skips it), called when an app launches a view the kernel
reads (a model, an xbf, a STEP, a robot: never a mesh the page parses itself, a DXF or a KiCad file, whose
view must not wait for, or fail on, a pool it never uses) and when a build's `view:` link lands -- there on a
thread of its own, one at a time (`EngineApp._warm`), so the page is answered at once even where the pool's start
waits for the base to be made (a model built in an environment of its own leaves it unmade): the page shows its
loading state while its document's requests wait on that making, and a base that cannot be made is its
document's error. An inspection's measurements, picked elements and poses start
only the processes their jobs need (`Mesher.processes`, `warm=False`; a
document's measurements take two at most while no page has warmed the pool, **Mesh**). With no page
and no inspection, the daemon's only children are the worker and the standby. Measured (before the
standby) on a 24-part model (5 shapes) on a 10-core machine: 1 child and 0.5 GB with no page,
against 12 and 3.2 GB when the pool started with the server. The pool's start costs a first page
about 0.8 s, less the time the page takes to load after the warm.

The pool takes its jobs from two queues and is handed one job per process at a time
(`Mesher.run`): facts (an inspection's measurements, picked elements, poses, and an inspected
document's measurement after its next build), then tessellations. A fact waits for a running job
at most, never queued meshes.

A retired script's next build is a fresh worker's: a restart, which takes each model's document
whole from the cache when its key is unchanged (**Build closure**, **The cache**), and else builds
the model cold. A render
process (**The viewer and the snapshot**) is no worker and does not count toward the count cap; its
memory counts toward the workers' memory cap, which retires an idle one before any worker, and one
alone over it after a picture is retired at once.

On Windows every process the engine starts -- each worker, STEP reader and render process --
has a console of its own and no window (`places.windowless`: `CREATE_NO_WINDOW`), and the daemon
a process group of its own too (`places.detached`), never no console at all: a console program
started with none gets a new console, with a window (#597). What they start in turn (the
meshing and reading pools) shares their windowless console.

Workers start with Python's fault handler enabled, so a native fault writes its Python stack
to stderr. A worker that fails to start or exits during a request includes its last 16,384
stderr characters in the local error, including startup diagnostics before a client can receive
logs, after the line saying where its build was. This tail is held only in memory and reset for
each request; a build whose log showed the model's stderr as it came says the error without it, as
its log said it already. Telemetry still reports the worker's exit status alone, never its stderr.

Telemetry counts each model build the daemon answers, where it answers it (`Daemon._counted`,
`_internal/engine_telemetry.answered`), never in the model's own process, where only the library is: one
line kept in the spool after the answer is sent, never on the network, for the person who asked it -- the
environment its request carries (`DO_NOT_TRACK`, `CAD_TELEMETRY`), then the settings, as a command's count
decides. Every build it answered is in the row's `count`; it `failed` only for a reason the system or the
machine caused (`analytics.SYSTEM_FAILURES`: a mistake in our code, no kernel process, a file it could not
write, the memory), never for a script that raised or a fillet the kernel refused; a worker that died under it
is `crashed`, with its exit status; the workers it started, lost and retired are its `health`. A kernel
environment whose making failed is reported once per failed making, whichever meets it first, a build or a CAD
tool's call (`base.Making.claim`). A build's features (an assembly, declared meshes, a drawing) are usage, and
not counted. The daemon hands the spool to a sender once it has waited a window (`tend`), so the builds of a
person who only ever runs `python model.py` are sent too. A Python caller that imports the server sees its own
`Model.build()` and counts it no second time; a build in the caller's own process (`daemon=False`) is
counted nowhere.

A worker runs each request in that request's folder (its script's, or the caller's), so a model's
relative reads resolve as they would under `python SCRIPT`, and stands in the temporary folder
between requests: an idle worker holds no project folder (on Windows, one a process stands in
cannot be renamed or deleted). A meshing or reading pool's processes exit with the process that
started them, however it ends.

A worker is an interpreter -- the base's Python, the one `cad run` ran the script with (the base's, or
an environment of the model's packages'), or the Python a script was run with directly where that is not
the base's (**Running a model**) --; a run is the
script in its caller's environment. A build goes to its script's live worker of its Python whatever
the caller's environment but for what shapes the interpreter's import system (`places.RESTARTS`): `PYTHONPATH`, `PYTHONHOME`, `PYTHONSAFEPATH`,
`PYTHONNOUSERSITE`, `PYTHONUSERBASE` and `PYTHONPLATLIBDIR`. A relative `PYTHONPATH` entry is the
caller's, as Python reads it for `python SCRIPT`: made absolute against the caller's working folder
before the engine is handed it (`client.environment`), since a worker stands in the script's folder.
A build with another value of any of them replaces the worker (retired `environment`), and its
memo goes with it. Everything else the
run adopts (`worker.adopt`): before the body runs, the caller's environment replaces the worker's
`os.environ`, keeping only those variables and what the worker set for itself
(`CAD_ENGINE_WORKER`, and the daemon's bytecode setting, `places.BYTECODE`). `PATH` and `VIRTUAL_ENV` are adopted, not
restarts: neither changes a running interpreter's `sys.path` (the worker is started with `-P`,
and `site` finds a virtual environment by the interpreter's own
`pyvenv.cfg`, never by `VIRTUAL_ENV`, which only activation scripts and installers read), and
the kernel reads neither; a model that starts a program finds it on its caller's `PATH`. An
agent's shell may give each turn its own `PATH` (Codex puts a temporary folder of its own on it,
`~/.codex/tmp/arg0/codex-arg0…`, new with each Codex process): one warm worker serves every turn.

`cad server status` says what the server holds (`--json`: the same as data, `api.status()`):

```
engine server 98307, up 2h10m · workers 3/10 with the standby · held by 1 app server · RSS 4.7 GB of 16.0 GB
  busy  tom.py         98310   12 builds   3.7 GB  building tom.py::tom · Building geometry · 3/7 stages · 41s
  idle  motorbike.py   98410    3 builds   0.6 GB  4m
  standby              98512               0.4 GB  kernel loaded · 4m
  waiting  2 builds, first come first served
retired: finger_01.py (LRU) 3m ago · qdd_actuator.py (pressure) 41m ago · tom.py (RSS) 2h ago
serving http://127.0.0.1:52811: 3 documents · 2.1 GB of 16.0 GB held
cache /Users/me/.cache/cad: 14 documents · 212.4 MB, kept until deleted
documents:
  live      tom      8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12
  held      bracket  3e9b7c21-55aa-5f0e-8d11-6c2a9b4e7d30  memory and disk
  held      lid      0a6f2d94-7c1e-5b38-9e40-1d5c7a2b8f63  disk
  unsaved   arm      71d0c4e8-9b2a-5c13-a6f4-0e8d2b5c9a17  run `cad run /work/assemble.py`
```

A worker's memory is as it measured it after its last build; a busy one's build is where its
last progress frame says (**Progress**); the time is how long it has been busy, or idle; a worker in
its script's own Python ends its line with that Python (`--json`: `python`). The
standby's line has no script: its process, its memory and how long it has stood by (`starting`
while it loads the kernel); it counts toward the workers' count (`with the standby`) and the RSS
the header gives against the cap (`--json`: `standby`, `rssMb`, `rssCapMb`). A retirement's reason is
`LRU` (room at the cap), `RSS` (over the workers' memory cap), `pressure` (the system's memory pressure),
`environment` (a build asked for the script with another `PYTHONPATH`, or another of the variables
that shape the interpreter's import system: its worker is replaced in its slot) or `exited` (it died).
A render process's retirement is listed too, by its document (`--json`: `document` where a worker's
row says `script`; `retired: part.xbf's renderer (RSS) 2m ago`). The `documents:` lines are each model
document, its state and, for one not held, the command that builds it again (**Document
lifetime**), and a held one where it is held: in memory, on disk (the cache), or both. The
`cache` line is the cache folder, the documents and bytes in it -- no cap: they stay until a person
deletes them -- and the last save that failed. `--json` lists the documents as `models`, the cache as
`cache`, and `serving.documents` the files served, each `held` or `evicted` (out of memory for its
budget: read again from its file when asked), with the bytes it holds. It
also says its `version` (its release), its `installation` (the version it runs as) and what uses it -- `holders`, `watched` (the documents pages watch), `busy`
(builds and draws running) and `active` (HTTP work underway) -- what a later release's engine asks of
an earlier one before it takes its port (**Starting and updating**).
