# Architecture

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

One server per computer -- reached through one door, which clients of 0.11.11 and earlier find too
(**Starting and updating**) -- owns its processes, run by one supervisor (**Services**), served documents
and HTTP listener. `cad serve` and `cad viewer` reuse that server and return its URL; where none runs
they say so in one line.
The background process is implemented in `daemon.py`; warm workers remain separate.
Every successful build registers its document by id and gives it a URL, `/<id>`; registration does not mesh it.
A model's worker is a separate process, holding its memo and live kernel objects; the daemon holds
structures and buffers, never live kernel objects (law 19).
The daemon takes its HTTP application -- the viewer's and the CAD app's -- from the server's
composition root (`daemon.HTTP_FACTORY`, `cad_server._internal.engine_host`); the library's engine imports
no application module. Beside the library's own dependencies (numpy) it imports the `build123d`
extra's -- OCP, build123d, bd_materials, threejs_materials, Pillow (the renderer's rasteriser) and
ezdxf (build123d's own DXF library, which the DXF export writes and checks a drawing with, and the
viewer's DXF pane is flattened by in a drawing process) -- in the base its workers run in, and an integration's extra only in that integration's environment; a test
holds each extra's list (law 3). The application serves the built
viewer's one page on that listener, every document at `/<id>`. Document routes run in
process, with no network relay. Kernel reads, topology, poses and meshes run in
reader/mesh subprocesses; even an inline-mesh request stays outside the daemon. The daemon's own
process imports no kernel: its installation may have none (the wheel's core), and every process
of the engine's that loads the kernel -- a model's worker, the documents worker, the standby, the
meshing and reading pools, the DXF pane's drawing process, the render processes -- runs in an environment that has it (**Running a
model**): the base, or the Python a script was run with, for that script's worker. If Python cannot
start those processes (on Windows, a loader refusing `_multiprocessing.pyd`), or the environment they
run in cannot be made, the request fails with
`serve.KernelProcessesUnavailable`, which carries the loader's (or the environment's) words and a word
for which failure it was (`cause`). The engine has no fallback. A refused pool is tried again by the next
request; a failed making of the environment is remembered until something could change it (**Running a
model**).

Every document has one id (law 6), a lower-case UUID string (the library's `cad.engine.ids`), by one formula
(`derived_id`: uuid5 of a scope's canonical path, `::` and a name): a model's scope is its script
and its name its function's (`model_id`), worked out in the script's own process (`Model.id`) as in
the engine; a file's is its canonical path and no name (`file_id`), inside the engine only; a shape
handed over is its calling script's (or the working folder's) and its name. Identity is namespace
plus name: a model's namespace is its script's folder, with no project detection.
A model's name is its identity within its namespace, the function's name by default, `name=` gives
it another. `@model(name="arm")` and `@step("arm.step", name="arm")` use the folder and explicit
name in the same formula, independent of the declaring file. An explicit name is refused at
declaration while another declaration holds it -- another function in this process (`model.claim`),
or another file of the folder whose last run declared it, as the name's record says
(`identity.claimed`) -- naming both `file:line` locations. A function renamed keeps its name and its
document; so does a name moved to another file of its folder, once the file it left is gone or has
run again without it: each run records the explicit names its script declares (`declares`) and gives
up those it declares no more (`identity.released`), and no script but the run's own is read (law
22). The same explicit name in two folders is two documents, and there are no global names. Two unnamed functions in different files may share a name:
their ids still include their script paths. A name holding `::`, the formula's separator, is refused
at declaration. The canonical path (`ids.canonical`) is `realpath` and, on
macOS, the name as the file system spells it, so a symlink and a case variant of one file are one
document; the viewer's document reads (by id) and its Recents key by the same function, so it
serves one document and keeps one Recents entry for it too, while a page names a file by the path
it was given. The server keys everything by the id: its served documents and
the models registered to be served, their watchers and syncs, their builds, the documents a build
holds; its API takes it (`/api/v1/documents/<id>`, `/api/v1/documents/<kind>/<id>/...`: **Wire
format**), and a document served at a pose is `<id>~<digest>`. The
daemon keys by it the worker that built each model document (`builders`, from which `connected`
asks the server's watched ids; a file the build wrote is no key there) and the live models' book
(`models.py`); a worker keys by it what its builds named (`build._BUILT`, which `made_by` answers
from).
The workers alone are keyed otherwise: by the canonical path of the script a worker runs, and the
environment and cad release of the Python a build of it named where that is not the base's (**Running a
model**), a process's key, not a document's.

The daemon maps each built document to its worker. HTTP watcher accounting has its
own lock, independent of document reads and the supervisor's leases. A page watches a document (law 18)
while it has a version wait outstanding or completed a sync within `serve.LIVE` seconds; its heartbeats
name the document by its id (`ids`): a file's `file_id`, a model's `model_id`, never turning
a model into a file path. To admit a new script at the worker-count cap, the
standby goes first, then the least recently used unwatched idle worker. When every idle worker is
watched, the new worker starts past the cap instead: a build never waits on an open page, and never
costs one its warm worker. The workers' memory cap retires a watched worker only when no unwatched one
is left to retire. A retired worker's documents stay served: the daemon takes them from it first, and
holds them under one memory budget that never evicts a watched one (**Document lifetime**).

The installation's door (**The door**) supplies its HTTP token, which programmatic clients send as a
Bearer header; no URL carries it. A page URL the engine prints or opens carries a link instead, good
until the token is rotated and the same text every time it is printed (its expiry one fixed instant,
`LINK_EXPIRES`, the first second of the year 3000), for which a browser is given a SameSite=Strict session cookie (the link
stays in the page's address, which the page gives one where it has none: `GET /api/v1/local/link`), one name on every port of
the host, that lasts 30 days from its last use (a page load renews it, as any request does once it
is a day old): both are the token's signatures of an expiry, checked by signing again, so no engine
keeps a session (`viewer.engine_app`: `EngineApp.link`, `sign`, `standing`). A request whose
`Authorization` Bearer is a link -- a CAD card reading the engine from its host's sandbox -- is the
one cross-origin read answered, for the origin that sent it and with no credentials, as is its
preflight (`EngineApp.preflight`); the cookie, a link in a URL, the token and `/mcp` never are. All routes
retain the application's Host and cross-site mutation checks. Explicit host/port
requests must match an existing listener. Every client reaches the one engine of the device, in the engine
folder (`places.engine_dir`; **Starting and updating**): its door, lock and port file are named `engine`
(`places.NAME`). What outlives an engine -- the port it rolled to -- is the engine's record in the state folder,
`engines/engine.json`, beside the page token, which every release reads.

**A link outlives its engine.** The port is the device's and the page token the user's, not one
engine's (`daemon.bind`). A port named -- `--port` (`cad server --port`, or a `serve`/`viewer`
request's), else `CAD_ENGINE_PORT` (0: any free port), read from the engine's own environment --
is taken or refused. Else the engine's own port: 3245 (`daemon.DEFAULT_PORT`, 0xCAD) when it can, as
Vite, Jupyter and Next.js take theirs; when another program holds it, the next free port
(`daemon.PORTS_TRIED` above it, then any), which the engine remembers in its record and takes at
every later start, whatever release it runs, so its links stay what they were. The start that rolls says so once, on the
stderr of the client whose request bound the port (a build's, when its page bound it; or `cad
server start`'s) and in `cad server status`, as a fact with nothing to act on (the engine works on the port it
took, and whatever holds 3245 -- another installation's server, a test's -- is left running):
`the engine serves on port 3246 and keeps it for its links: 3245 is in use by <name> (pid N)`. A remembered port
that is free is used, and one held is rolled from the same way. When 3245 is free again at a start,
the engine takes it back and forgets the port it rolled to: `back on the default port 3245: links
made on 3246 no longer work` -- the one time a link changes. Who holds a port is named as the
system says it (`daemon.port_holder`: `lsof` on macOS, `/proc` on Linux, `netstat` on Windows), or
`another process` where it does not say, and another cad server, by its command line (another
engine folder's, 0.8's), `another cad-server (<name>, pid N)` (the words the code prints, `cad.engine.said.SERVER`).

**Starting and updating.** One server a device, in one engine folder, whatever release runs it: the layout of 0.11.11
and earlier, kept as it was, with one state folder and one cache folder (`cad.engine.places`). Only `cad server start`
starts it (and `cad mcp`, which starts it so, then serves the CAD app over stdio): a newer release's start replaces an
older release's server, an older one joins a newer server that runs (`client.start`, `cad_mcp.shim.start_server`). A
`cad mcp` that is not the global `cad` installed on the computer (Codex's plugin line runs it from uvx's cache) starts
none of its own: it runs the installed cad's `cad server start` and joins the server that leaves, whatever the two
releases are, so the server is always the one that updates itself. Where no global cad is installed, one run from uv's
cache installs it first (`cad_server._internal.tool_install`: `uv tool install "cad<N>"`, PyPI's newest of its own
major, never `--force`, and never over a `cad` tool of a higher major).
Every other command, `cad run` and a model run directly among them, attaches to the one that runs, and says so in one
line where none does (`not_running`). A model's own process -- the library, which never starts a server of its own
environment -- starts none. No client starts another release's engine beside the device's: an engine runs on until
`cad server stop`, an update, or its door going. Each installation's bytecode is its own (`places.bytecode_tag`).

The clients of 0.11.11 and earlier -- their CAD app's line, their `cad` command, the library in a person's own
Python -- find the same door, and where none answers start the installation `<state>/installations/current` names
(`cad_server._internal.installations`), by its Python, with `-m cad_server._internal.engine_daemon`: this release's
server where the bridge pointed it there (below). Such a client's builds are refused only for another worker contract
(`contract.refusal`).

The version feed (`cad_server.updates`): the server reads it in the background at most once an hour as it tends
itself (`updates.refresh`), never waited on, for cad's automatic update alone; `cad update` asks PyPI instead
(`updates.pypi`), at once; nothing says a newer release to a person or an agent unasked (`cad update` and `cad
doctor` name a release of a higher major, which never installs itself).

A global install of cad (`uv tool install cad`; `cad_server._internal.auto_update.global_install`) updates itself
to newer releases of its own major unless the person turned it off (`cad update auto off`), or when asked (`cad
update`: `Daemon.update`, the update begun once nothing is in flight, whatever the switch says; `cad update --major`
to the newest of all): first thing as a server starts, before its door opens, and as it tends itself once nothing
has run for a minute (or nothing since it started), where the version feed as last read names a newer release of
its major, a detached helper that is not cad (`auto_update_helper`, run by the Python cad's environment was made
from) stops the server, runs the installer's upgrade bounded to that major (`uv tool install --upgrade
"cad>=<installed>,<<next major>"`), tried again on failure, and starts the server with whatever cad is there. A server that hands its start over exits
`UPDATING`, and its starter waits for the next one; a `cad server start` that fails asks for the update before it
gives up; a start never replaces a newer server, it joins it (`client.start`, `cad_mcp.shim.start_server`). With
`cad plugin update auto` on, the server, at its start and at each quiet tending, runs `cad plugin install` (which
updates the plugin in each agent app with that app's own command, with 15 minutes at most) once where its cad is
newer than the release that command last went well in every app for, however it got newer (`_internal/plugin_catch_up.py`), then counts the last update attempt once (`auto_update.report`); the
helper and `cad update` run none, and no update of cad begins while a run of it is going. Where no server runs, a typed `cad update` begins the update itself
(`cli/update.py`), and its helper starts no server after it.

The updaters of 0.10.0 to 0.11.11 are frozen on computers, though, and update by running a newer release's hidden
`cad setup --engine-update` from a flat release folder they made (`<state>/releases/X`). The bridge
(`cad_server.cli.setup`, all of it to be deleted together once those releases are gone) answers: that run writes the
installation record their switch starts the server by, naming that folder's environment, owes install mode, and
changes nothing else; the switch points `installations/current` at X and starts X's server from that folder, and goes
back where it does not answer. Five minutes after it started with `current` naming X, that server runs the hosted
install command in install mode (cad as a uv tool, our plugin in every agent app), once, retried as it failed (hourly
at a start, then daily, 30 attempts or 30 days at most; `cad_server._internal.install_script`); once a report says
cad was installed and nothing is in flight, the records point at the global cad's environment and a helper that is
not cad stops this server and starts the global cad's. Every server of a global install points `current` and its
record at itself, so a client of 0.11.11 or earlier that finds no server starts it. On a computer whose agent apps got
text-to-cad from a store alone (no receipt or plugin folder of our earlier setup) nothing is owed: after the same five
minutes the server installs cad globally itself (`tool_install`), as it does where install mode's run installed no
cad, and hands over the same way. A global install's server on a computer our setup set up before, whose `cad plugin
update auto` was never set (the new cad arrived by the uv line), turns that switch on and runs the install command
once. 0.10.0's updater on
Windows keeps its state in the local application data, so its switch could only go back: there the run stops 0.10.0's
server by its own stop command first, moves its data once, points the records in both state folders at X, and starts
X's server on the port and with the token it took in. Plain `cad setup`, which `cad update` typed on those releases
runs, is the install command in install mode. Nothing of a past release is deleted by cad: the release folders stay
until `cad cache prune`. A server asked for `{"op": "http",
"port": P}` while it serves pages on another port Q -- an updater handing the pages' port on, 0.11.10's switch helper
among them, to a server that started while 0.11.10 still held P -- takes P too, a second listener of the same
application and token, and P is its own from then on (what `status` says, what its record keeps for the next start,
the port a later update hands on), Q kept as well; where P cannot be taken it answers with where it serves, never
`failed`. Any other request naming another port (`cad viewer --port`) is refused as before. Every page keeps its link
through it, and reloads once its server answers with another release or start (`release`, `instance`).

An engine asks no other process anything, another engine no more than any program: 0.8's server on
the port is rolled from as above, or refused where the port is named, as below.

A named port another process holds is refused in one line naming the holder (`daemon.PortHeld`).
`cad server` binds at its start, so the command fails at once with that line on stderr and exits
1, no engine left. An engine a client starts binds on the first request that serves, but for one that replaces
a server that served pages: a client that stops a server (`client.sweep`: `cad server stop`, which cad's own update
and the bridge's move run before they start the next, and a start that replaces an older server) first asks it where
it serves pages, any release's server alike, and notes the port (`places.pages_path`); the next server to start takes
the note and serves pages there at once with the user's token (`daemon.resumed`, `Daemon.resume`), so a page open in a
browser reconnects with nobody doing anything. A port named (`--port`, `CAD_ENGINE_PORT`) comes first; where the port noted is taken,
that server runs as one with no pages before, and its log says so. A port that
request names (`cad viewer --port`) refuses that request alone, with the line: the engine runs
on, unbound, for its other clients' builds and the next request that serves. Its own port held
(`CAD_ENGINE_PORT` in the environment it started in) fails that request with the line, and the
engine, which can never serve, leaves its note (`places.failure_path`) and exits 1: `port 3245 is
held by <name> (pid N): stop it, or start the server with another CAD_ENGINE_PORT` (`…or pass another
--port` for a port `--port` named).

The token is made at the first engine's start and every start serves with it: the engine's record,
`engines/engine.json` in the state folder (`places.state_dir`), keeps the port it rolled to (`registry.Registry.engine`,
its own `registry.ENGINE_SCHEMA`), and the token is the user's one file beside it, `engines/token`,
which every release's engine serves with (`registry.Registry.token`; both this user's alone, 0600), so a link
outlives an update too. So a page link
-- the `cad viewer` output, a model's `view:` line, the CAD app's card -- works across `cad
server stop`, a crash, a reboot and an update until the token is rotated, the session it left in a browser for 30 days past that
browser's last use of it, on any port, and a page that lost its engine keeps asking the same address
and reloads itself when the engine answers again. Whoever holds a live link or session reaches the
user's folders whenever the engine runs. `cad server --rotate-token` replaces the token, once the person says yes
(**Consent**, `--yes`), in the state folder every release reads, and tells every running server to take it at once (`{"op": "token"}`, `Daemon.retoken`): every link and session made
before stops working now, in every server. One that cannot be told (a server of 0.11.11 or earlier) is said, and
takes the new token as it starts again. `cad server status` says the
port and where it came from: the default, `--port`, `CAD_ENGINE_PORT`, or `rolled from 3245
because <name> (pid N) holds it`.

The injected application also serves `/mcp`, the Streamable HTTP MCP transport
(2025-11-25 and the previously supported protocol revisions). Initialization returns
an opaque `Mcp-Session-Id`. Every subsequent request identifies that session;
DELETE releases it, and a missing/expired session must initialize again (the stdio shim
does so for its host). JSON replies
are used; GET returns 405 because this server has no unsolicited SSE events.
Each session owns its tool server, view registry and immutable UI resource. `cad_http`,
the page's requests of the viewer's routes, dispatches into the same application in
process. It is app-only, as `cad_sync` and `cad_capture_reply` are, and absent where
no page is drawn: no agent reaches a viewer route. Launch results carry the app
capability (the stdio peer's, one for its host, which every session it opens is given) in UI-only `_meta["dev.texttocad/httpToken"]`, never content, structured
content or the resource. The page sends it in `x-cad-app`; the server checks it
before dispatch and strips it, and refuses a call without it. Authorization precedes
the range cache. This is an MCP host/model boundary, not a sandbox against the
local authenticated host, which already has the installation's file authority.
Page protocol 9 requires the capability, on `cad_http` and on the page's own `cad_sync` and
`cad_capture_reply`; older pages must reopen. Sidebar views alone are shared through
an in-memory registry; thread views remain session-local. The host's stdio process
proxies JSON-RPC and owns no page, tool implementation, catalog or view state.
Its one act of its own is a text host's browser open: the engine runs in the environment of
whatever started it (another agent's shell, another `BROWSER`, no display), so it never opens a
browser for a `cad_show`. The stdio process says at initialize that it opens one, and whether its
environment can (`_meta["dev.texttocad/transport"].browser`, `{"refusal": null | "<why not>"}`);
the engine's `cad_show` answer then carries the page in `_meta["dev.texttocad/open"]`
(`{"url", "said", "failed"}`), which the stdio process opens through an owner-only redirect file
with `webbrowser` (its own `BROWSER`) and strips, saying why not in place of `said` where no
browser opens. Before it answers the host, it tells the engine on its session whether the page
opened: the notification `notifications/dev.texttocad/opened`, `{"url", "opened"}`, which the
transport hands the session's tool server (`cad_server.mcp.server.Server.notify`). The engine records
nothing as it asks; the page counts as open in the person's browser (`serve.Server.in_page`'s 30
seconds) only from the peer's word that it opened. The first word on a page that session's peer
was asked to open settles the ask, so a failed open records nothing and the next `cad_show` opens
the page again, and a word on any other page, from any client, is ignored. A client that declared
no such peer is given the URL in words, and nothing opens.
Host differences stay at the boundary (law 19): the stdio process translates host capabilities, the app
page keeps its version reads short enough for the host's tool-call slots, and the engine's request
handlers act on declared capabilities, never on a host's identity.
Active HTTP calls keep the daemon alive; quiet MCP sessions expire after an hour. The host's
stdio process holds the engine from its start while the host runs (**The door**), under a name it
opens its sessions with: it ends them itself at its input's end and on SIGTERM, and when its hold's
connection drops -- the process gone, killed before it could say so -- the engine ends every session
opened under that name, or once its running operations finish (`Sessions.release`).
A card's `cad_sync` renews its served document's warm-worker lease.

The viewer launcher owns no server, reload watcher or process-reuse probe. It
asks the existing engine for its page: each file it names, a relative one read from the launch's
folder, is registered by its id (the id of its canonical path) and printed as its page, `/<id>`.
Development client reload remains a browser concern; Python changes take effect when the engine is
explicitly restarted. What the page knows by id is memory
only, and a file's id is derived again from its path after a restart.
