# Running a model

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model runs where the CAD kernel is. The server (`cad_server`, in the `cad` distribution: the engine's daemon, the `cad`
command, the viewer's server, and the numpy, ezdxf and Pillow they read meshes, drawings and
pictures with) depends on the library (`cad`) without its kernel, and the CAD kernel (OCP,
build123d and the rest) is the library's `build123d` extra. The library's layer over it (the model
API, `kernel/`'s memo, naming and determinism settings) is the build123d integration, named for its
technology as its extra is; each of cad's integrations is an extra, listed with the modules, the
distributions and the decorators that are it in one table (`cad._internal.integrations`). So the
cad the install command installs (a uv tool) runs no
model itself: it makes environments with uv, and every process that loads the kernel starts from one.

**The base** is the environment of the build123d integration alone: `cad[build123d]` at the engine's
own release -- or the source tree, or the wheel, the installation was made from -- on the engine's own
Python, made by uv at `base/<key>` in the cache folder (`base.folder`), its files hard links into uv's cache; uv is
asked `--offline` first and goes to the network only for what its cache lacks, saying so first
(`cad_server._internal.base`). One per installation, keyed by it (the version it runs as, its release
and source), the Python line it is made on and the architecture, so an update has a base of its
own, and so has a cad on another Python line. Its marker, `cad-env.json`, written last, makes it complete, so a later use reads the marker and
resolves nothing; a lock beside it makes one process make it while another waits. An installation
whose own environment carries the kernel (installed with the extra, `pip install
'cad[build123d]==<release>'`) is its own base, and none is made. **Nothing is made ahead of need**:
not at install time, not by `cad doctor`, not after an update, and not at the engine's start (below).

**`cad run` is `uv run`, with cad pinned** (`cad_server.cli.run`). It takes `uv run`'s options and
behaves as it does: a script's PEP 723 header (a `# /// script` block's `dependencies` and
`requires-python`), `--with REQ` (repeated, or a comma-separated list), `--with-editable`,
`--with-requirements`, `-m MODULE`, `-c CODE`, `python ARGS` as `uv run python ARGS` takes it, a
command of the environment's, `--python`, the indexes and find-links, `--project`, `--no-project`,
`--directory`, `--env-file`. An option it does not read itself is handed, as given, to the uv the
server ships (`uv pip install`, where the engine makes the environment), which judges it, so `cad
run` never drifts from uv; those only the making reads (`--upgrade`, `--refresh`, `--offline`, the
verbosity) key nothing. What it adds is two things:

- **The pin.** The environment holds `cad[<integrations>]==<device release>` (or the installation's
  source tree or wheel), never PyPI's unrelated `cad` 1.x. Its integrations are chosen in one place
  (`extras.integrations`): a header that names `cad[...]` decides them outright (`"cad"` alone, the
  core); else a static scan of the program, with `ast`, and of the local modules it imports -- in its
  folder, its package, its project, following absolute and relative imports and the imports inside
  function bodies -- each module's top level looked up in the table (`build123d` and `OCP`: the
  build123d integration; `kicode`: the kicad integration), each of cad's names it imports or uses by the
  name it spells (`step.read`, `from cad.step import read`, 0.10's `read_step`: an alias read as the name
  it is now), which needs what the registry says (a type's reader its `reader_integration`, a STEP's
  build123d; an operation the calling process runs its integration, a mesh's `dfm` trimesh, a STEP's, an xbf's,
  a model's and a DXF's build123d; one the engine
  runs, an `export`, none; a type's edit its integration, `kicad_pcb.edit` kicad; a type alone, `from cad
  import step`, none) (`cad_server._internal.scan`); with what a
  project's requirement of cad names, and a requirement that is an integration's own distribution
  (`--with build123d`); and for a bare command, the integration that declares it (`kicad-cli`: the
  kicad integration's, the registry's `commands`). `--with cad[...]` adds to either. None found: the
  core alone. A header or
  project that pins cad to another release is refused before anything is made, in one line naming
  the device's release (`extras.pinned`: `plate.py's header pins cad to ==0.9.0, and this device runs
  cad 0.10.0: drop the pin, ...`); a pin of the device's own release is as none, and an unpinned
  `cad` gets the device's pin.
- **The environment.** The device's engine makes it, outside any sandbox, over its door (`{"op":
  "base", "key", "spec"}`: `extras.Making`), each line said as it comes, offline first from uv's
  cache, with the base's link mode, find-links and index settings; with no engine of its installation
  answering, `cad run` makes it itself. Then `cad run`, which may run in an agent's sandbox, runs the
  program with that environment's Python, in the caller's folder and environment, its folder last on
  its module search path (`cad._internal.program`). A command is the environment's own file, never
  one on PATH; one an integration declares runs through that integration's `_command` module in the
  environment's Python (`cad.kicad._command`): the environment's own `kicad-cli` (kicode's console
  script), headless in private homes
  (`cad.kicad._program.private_run`, a typed command's, KiCad's library variables naming KiCad's own
  libraries: the first 3D library a board's 3D view reads, the others an installation of KiCad's; none of
  the person's), its arguments, stdio and exit code kicad-cli's, and never the one
  `CAD_KICAD_CLI` names. The environment of the build123d integration
  alone, with nothing else, is the base.

**What an environment holds** (`extras.Spec`): the pin, and beside it the packages the program names.
A script with a header runs in an environment of its header's `dependencies`, and any project around
it is not read, as `uv run` reads none. Without one, inside a uv project -- a `pyproject.toml` with a
`[project]` table, found from the working folder up as uv finds one, or named by `--project` --
the project's dependencies are installed with it. Where the project has a `uv.lock`, exactly its
locked set: the engine exports it with uv (`uv export --format requirements-txt --no-hashes`, the
project's extras and groups as given), its path, git and other sources as uv writes them, and installs
that beside cad's pin, cad's own line taken out -- `--frozen` takes the lock as it is, `--locked`
refuses one out of date with its project in uv's words, and neither makes it current first, as `uv
run` does; a lock that pins cad to another release is refused in one line, as a header is
(`extras.locked_cad`). With no lock, the project itself, editable, when it is packaged (a
`[build-system]`, `--extra` naming its extras), else its dependencies (`-r pyproject.toml`), and
`--locked` or `--frozen` is refused, there being no lock to read. `--with`, `--with-editable` and
`--with-requirements` add on top in either case. Then uv's options; **uv's settings** as the caller's
shell has them, an allowlist of the variables that say how uv resolves (`base.UV_SETTINGS`: its
indexes and find-links, index strategy, keyring provider, TLS, pre-releases, HTTP timeout, build
settings, its configuration file), which the making is run with in place of the engine's own (the
settings the engine owns -- its cache, its link mode, where it installs Pythons -- stay its); the uv
configuration of the run's folder, read as uv reads it, uv running in the project's folder (else the
run's), so a project's `[tool.uv]` or `uv.toml` -- a private index -- is used (`extras.uv_config`);
and the Python: `--python` as uv reads it (a version, a path, an implementation; uv may fetch a
managed one), by default the engine's own. A run that differs from the base's only in how uv reaches
an index (TLS, a timeout, a keyring) still runs in the base (`extras.HOW`). **After uv installs it**, the distributions
it holds are read: one of an integration it was not given (`build123d`, `cadquery-ocp-novtk`,
pulled in by a package that depends on it) adds that integration's extra, and uv resolves again,
saying so (`build123d came in through another package: resolving again with cad[build123d] 0.10.0,
so cad's pins decide it`); its marker names the integrations it was made with (`integrations`).

**One per distinct set, never changed once made.** It lives beside the base (`base/<key>`, `base.folder`): its key digests the installation's base's inputs, the release among them, the spec
(`Spec.keyed`: the integrations, the requirements normalized, each once and sorted -- a local path
made absolute, against the working folder for `--with` and the script's folder for the header, a
name as PEP 503 spells it, its extras sorted, its specifier without spaces -- the editable folders,
the requirements files, uv's options and settings, the uv configuration, the lock and its export's
options, the Python), and what each local thing is now -- a lock, its project's `pyproject.toml` and
a uv configuration by their bytes --
(`extras.fingerprints`: a wheel's or a file's size and modification time; a folder's files' paths,
sizes and modification times, but for `.git`, `__pycache__`, `build`, `dist`, environments and
`*.egg-info`; an editable folder's metadata files alone, its code read as it is). An edit to a local
package is so another environment: the next run makes it, saying `making the environment of the
model's packages again, as <path> changed: ...`, and builds in a fresh worker of its Python. Its
marker, written last, names the installation, the requirements (`with`), the spec, the
integrations, its Python's version and the local fingerprints (`local`); a lock makes one maker. A
process there reaches the device's engine as one in the base does, and -- the environment not being
the base (`places.SEPARATE`) -- names its Python in its orders, with how `cad run` named its
environment (`places.RUN_WITH`: the options and requirements its command line was given, one word
an option, and the script whose header named the rest); the engine builds the script in a warm
worker of that Python, as for **a Python of the script's own** below, of one release with the
engine, so no notice of another release is said. A header's `requires-python` the Python does not meet is refused
in one line (read as PEP 440 reads it, `>=3.11.0rc1` too): before anything is made for the engine's
Python, once the environment is made for one `--python` named.

**Its releases.** Environments are tied to their release, cad being pinned in each. Making one
removes the environments of releases older than the one before the current -- the current
release's and the one before's stay (`extras.kept`: the newest older one) -- and the one an
edit to its local packages superseded, but one a process runs from (`releases.running`: named on a
process's command line, as written or by a link to it), which a later making removes
(`extras._collect`). The environments of other sets stay, one per set a program named; `cad cache prune` removes those made for
other releases and `cad cache clean` all of them (`cli/cache.py`); nothing else removes another release's. After an update,
a new release's environments are made as its runs ask for them, from uv's cache.

**An integration built for one Python** (`extras.on`). The registry says what only a tool decides of its
environment: the one Python line it is built for (`python`), its platforms and the folders its settings are
read from (`homes`). Blender's bpy has builds for CPython 3.13 alone, so an environment with the blender
integration -- a program that imports `bpy` or `cad.blender`, the scan finding either through local imports,
a header or `--with` too -- is made on that line where the engine's own Python is another (`uv venv --python
3.13 --managed-python`: a Python uv fetches into its own folder, never `uv python install`, which writes
`~/.local/bin/python3.13`), and on the engine's own where it is that line already. Nothing else differs: cad
is pinned in it with every integration the program uses (`cad[blender,build123d]==<release>`), it is keyed
and removed by its release as any other, the program runs through the library's runner, and the engine
builds its models in a warm worker of that Python. The tool's settings folders (`BLENDER_USER_CONFIG` and
the rest) are private ones in the cache folder (`homes/<name>`, the system's temporary folder where the cache
cannot be written) unless the caller named them, for the program and for that worker, so nothing of a
person's own Blender loads into a run. Refused in one line, before anything is made: a `--python` that names
another line (`render.py uses cad's blender integration, which runs on Python 3.13 alone: --python 3.14 is
another; drop --python`), a header's `requires-python` no release of 3.13 meets, and a platform the tool has
no build for (`cad's blender integration has no build for macOS x86-64: it runs on macOS arm64, Linux x86-64,
Windows x86-64 and Windows arm64`), where its extra installs nothing.

**What cannot be done is said in one line** (`base.failure`): requirements uv cannot resolve beside
cad's pins, with its reason -- `build123d<0.1 cannot be resolved beside cad[build123d] 0.10.0:
Because ...` -- and a package its cache lacks where the network cannot be reached, by name -- `the
environment of the model's packages needs the network once, for pandas, which uv's cache does not
hold: ...`. A program that stops importing a module of an integration its environment lacks -- one
the scan could not see, imported by name at run time -- is said as Python says it, then in one line
naming the extra (`cad._internal.program`, `integrations.missing`): `kicode comes with cad's kicad
integration: add `cad[kicad]` to the script's header`; nothing runs again. The record of a document a
`cad run` built names the options and requirements its command line was given (`with`), and the
command that builds it again gives them again (**The rebuild command**); a header's are its
script's, so `cad run` and the script build it again -- but the header of a program that calls a
model another script defines (a check script's), which the record names too, so its rebuild command
gives them with `--with` (`models._given`).

**A Python of the script's own.** A script run by any other Python that has the library -- a venv's
`python model.py`, `uv run`, a person's own interpreter with `cad[build123d]` -- names that Python in
each order that starts or reaches its worker (`contract.interpreter`: its executable, its
environment, the library's release and its worker contract); a process in a base (`places.HOME`)
names none, and one in an environment of a model's packages names its own (above). The engine builds such a script in a warm worker running that Python
(`Daemon.caller`, the worker service's `interpreter="lease"`), its import path that environment's own,
so the script's own packages import in its worker as they do in its run; one whose environment is the
base itself (an installation that carries the kernel) is built there as any other. The worker is
keyed by its script, that Python's environment as the system resolves its folder, and the release of
cad the build names: `python`, `python3` and `python3.14` of one environment share one warm worker,
which runs the first of them to ask; the same script run from two environments is two workers; and
another release of cad in one environment, under the same contract, gets a fresh worker, never the warm
one that holds the release before's code. It keeps its memo and the warm edits as any worker, and
adopts each run's environment the same way (`worker.adopt`, `places.RESTARTS`); it has no standby, so
its first build loads the kernel cold, and it never takes or waits for the standby. At the cap it makes
room by retiring an idle worker, as any build does; with none idle it waits for a busy worker to be free,
and holds up no build in the base meanwhile, which may take the standby. Where the standby is all that
holds the cap (`CAD_ENGINE_WORKERS=1`, or one core), it takes the standby's slot: the standby is retired
and stands again at the first slot free (`Supervisor._restand`), so no cap leaves a build waiting on
nothing. The rest of the engine's kernel processes stay in the base: the documents worker, the
meshing and reading pools, the render processes and the standby. A document such a worker holds is
asked of it alone (`via` and its environment's key): with that worker gone, an export or a shape of the
document is refused as not held, never asked of another worker of its script. Its record names that
Python (`python`), and the command that builds it again is that Python and the script (**The rebuild
command**).

What the two meet by is **the worker contract** (`cad.engine.contract.CONTRACT`), which the library
and the server both state: the worker protocol's number (`PROTOCOL`, bumped by any release that
changes what a worker and the server say to each other), the document format the worker writes
(`previous.FORMAT`) and the CAD kernel it builds with, OCP's major.minor as the library pins it
(`KERNEL`). An order whose contract is not the server's is refused before any worker starts, in one
line naming which package to update and to what release (`contract.refusal`): `cad here is 0.10.0,
worker contract 1 (xbf/9, OCP 8.0); cad-server 0.10.2 speaks contract 2 (xbf/9, OCP 8.0): update the
cad package in this environment to 0.10.2` -- the library's side, which names no installer -- or, for a
library newer than the server, `...: update cad-server to 0.10.3` (cad's messages still name the server
`cad-server`, its alias) -- updating the computer's cad: installing cad into a project's environment neither replaces nor
moves the computer's cad. One contract of two releases builds, and the build's answer carries the server's release
(`release`): the script's run then says once, on stderr after its report, which package to update for
the other's fixes (`contract.notice`, `api.say_notice`): `cad here is 0.10.0; cad-server is 0.10.2:
update the cad package in this environment to 0.10.2 for its fixes and features`, or `cad here is
0.10.3; cad-server is 0.10.2: update cad-server to 0.10.3`. A script in the base names
no Python and hears neither.

Every other process of the engine's that loads the kernel runs the base's Python (`places.kernel`,
which the distribution makes as `places.KERNEL`): a model's worker but one in its script's own Python,
the documents worker, the standby, the render processes, and the meshing and reading pools, whose spawned
processes start on the base's own import path, which the marker records (`serve._spawn_in`). **It is made on
first need**, by the server, for any cad of its release: a release just installed, or a base that was removed. The engine starts and
serves with none made -- pages, the home, documents held in the cache, `status` -- and `cad doctor` reports
one that is missing without making it. The first thing that needs it makes it: a `cad run` of a script whose
environment it is, or the start of one of the engine's kernel processes -- a build's worker, or a view or
an operation that opens or draws a STEP or an xbf, or meshes one (`places.kernel`, `base.kernel`) --, by
the engine's one making (`base.Making`, its lines in the engine's log and its state in `status`), and
every kernel process asked for meanwhile waits on it; those processes start only once it exists. The
standby stands only once the base exists -- at the engine's start where it is made already, else the
moment its making is done -- and until then none stands and nothing waits on one. An
engine a host's CAD app started runs outside any sandbox, where an agent's command may not write the
cache folder: a `cad run` that finds no base asks the device's engine over its door (`{"op": "base"}`,
its key naming the installation's base) and follows its making, each line said as it comes; it makes the
base itself only when no engine of its installation answers. A base that cannot be made fails the
request that needed it in one line (`serve.KernelProcessesUnavailable`) that says what to do next. The
engine remembers the failure in memory alone (`base.Making.remembered`): every kernel process asked for
after it is told it at once, as the earlier failure, rather than making the base again (uv run anew, every
call waiting on it). A failure that can clear by itself -- the network, uv killed, a file it could not
write or remove, a download its install failed for, a release or requirements uv cannot resolve (its cache
of an index lags a release by minutes) (`base.PASSING`) -- is made again on the first need five
minutes after it (`RETRY_SECONDS`); any other -- a denial, a Python uv cannot use, a base whose Python does
not run, no uv -- until something that could change it does: a
`cad run` that asks the engine for the base (`{"op": "base"}` always makes it again; the failure names
`cad run -c "import build123d"` for it), a base another process made, or the engine's restart (an update
among them). Its crash is reported once per making that failed, with its cause, however many calls it
answers (`base.Making.claim`, `mcp.server._first_report`).
