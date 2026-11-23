# The door

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A client reaches the daemon on POSIX through named pipes in the engine's folder, never a socket
(the library's `cad.engine.door`): agents run commands in sandboxes that refuse every socket, local ones too
(macOS Seatbelt, deny by default, answers `EPERM` to a Unix socket's connect and to a loopback
port's bind), while they let a command make and open files in its temporary folder, where the
engine's folder is, FIFOs among them. Windows keeps its loopback port and port file, the token
shown first, in the same hello (`daemon._admitted`, **The door's protocol** below). The engine's
folder (law 2; `places.default_engine_dir`) is one only the user can make: `cad-engine` in `$XDG_RUNTIME_DIR`, else in the user's own temporary folder (on macOS
the one the system names, `/var/folders/...`, whatever `$TMPDIR` a sandbox sets, so a sandboxed client
finds the engine started outside; elsewhere `$TMPDIR`), else `/tmp/cad-<uid>`; on Windows
`~\.local\state\cad-engine`, beside the state folder: the temporary folder is in the local application
data, which Windows virtualizes for every process an app package starts (the Claude desktop app's CAD
server, and the engine it starts), so a port file written there would reach no other app. 0.10.0's was
there, and for one release the engine writes its port file there too (`daemon._mirror`), for a 0.10.0
CAD app's server still running. 0.8 kept its engines in `cadgen-engine`, so no client of either release reaches the
other's door. Its door, lock and port file are directly in it (`places.engine_dir`, made this user's alone by
`places.make_engine_dir`), as in the layout of 0.11.11 and earlier, so every release's client finds the one
engine; its connections' pipes are in the `clients/` folder beside them. The 0.10.0 port file is written by whoever holds the flat one.

- **The door.** The daemon makes one FIFO beside its lock, `engine.door` (`places.door_path`), and
  holds it open for reading, and for writing too, so it never reads as closed. A door nobody reads
  refuses a writer's open (`ENXIO`): that is "no engine", and what `stop`, `status` and `wait_gone`
  ask (`door.answering`), opening and closing it with nothing written. No process is signalled
  or probed: the sandbox refuses `kill` on a process outside it.
- **A connection.** A client makes a pair of FIFOs in `clients/`, named by a random id (`<id>.up`,
  `<id>.down`), opens each for reading and writing (never blocking, never reading as closed before
  the daemon has opened it), and writes one hello into the door: its id, a space, the door protocol
  it speaks and a newline (`<id> 1\n`), far below `PIPE_BUF` (512 bytes on macOS), so hellos written
  at once never interleave. The daemon reads the door in one thread and answers each hello in a
  thread of its own: it opens the pair without blocking or following a link, refuses either end
  unless it is a FIFO of its own user's, and greets on `down` (`ok 1\n`). The client then opens
  each pipe again for its one direction, lets the read-write ends go and unlinks the pair's names. From there the connection is the request and
  answer lines a socket carried, through the same code (`daemon._serve`): every verb is untouched.
  Either side leaving is the other's end of file; the daemon ignores `SIGPIPE`, so a client gone
  mid-answer is a write's `BrokenPipeError`.
- **The door's protocol.** The hello and the greeting carry a number, `door.DOOR_PROTOCOL` (1), so
  that either can change without a cutover: an app keeps an older plugin's `cad-mcp` for long, and a
  release gone back to pairs a newer one with an older engine. Within one number, only additions --
  to the hello, the greeting and the operations -- each a field at the end of its line, which a
  reader of that number skips; a removal or a rename takes a new number. Each side reads the other's
  number first: the daemon greets with the number the connection speaks, the lower of its own and
  the hello's, and the client speaks that one or hangs up (`door.greeted`). Numbers start at 1: 0.8's door had none (a bare `<id>\n`
  and `ok\n`), which neither side reads, and 0.8's engines keep their own folder. On Windows the hello
  goes first on the loopback connection, the port file's token where a pair's id goes, and the
  greeting comes back on it; a connection that says no such hello is refused before its request is
  read.
- **Leftovers.** A client killed before its greeting leaves its pair: the daemon sweeps pairs no
  connection of its own holds once they are two minutes old, looking at their names and ages
  alone, never opening one, so a sweep never waits. A stopping daemon takes its door away first:
  a client waiting on a greeting it will never send sees the door go and stops waiting. Once its
  workers have stopped it removes the rest of its files -- its port file, its failure note (but a
  failure's, which its client reads) and last its lock, removed while still held (`daemon.let_go`)
  -- whether it stopped on `stop`, a terminate, a retirement or its door gone. An engine killed
  leaves its files: the next to start takes its lock and makes its door anew, and `cad server status` and
  `cad server stop` remove them, its lock free and nothing answering at its door (`client.sweep`). A lock is
  taken on the file its name names (`places.lock`), so a lock file removed under a daemon starting
  is never two daemons' lock.
- **Reads.** What a client used to ask of the loopback port, `inspect`'s document reads, goes
  through the door too (`{"op": "read"}`, `serve.Server.read`, answered in process), so a
  sandboxed shell needs no socket at all. A read of the parts' facts asked with `"progress": true`
  sends `{"progress": {done, total, key}}` lines as each part's comes in, before its answer. The
  HTTP listener serves pages, the CAD app and the stdio MCP peer, which run outside any shell's
  sandbox.
- **Trust.** The door changes no boundary: the engine's folder is the user's own and closed to
  everyone else (`places.folder_refusal`), `clients/` is made `0700`, and every pipe is `0600`, so
  the daemon serves whoever can make files in that folder: its owner, as the socket did. It
  carries the HTTP token to that owner (`{"op": "http"}`), and the HTTP side's token, cookie and
  app-capability rules are as they were.

**Starting the engine.** Outside a sandbox a client starts the daemon as before and waits for its
door. Inside one, a daemon could make its door but never bind its HTTP port, and every build
serves its document: so it starts none. A start that the system refuses a loopback port (`client._sandboxed`: one
bound and let go, never a variable, since an app hands a command it approved to run outside its sandbox the
sandbox's variables still) and finds no door is refused at once, in one line:
no engine runs and this shell's sandbox cannot start one; run the command again outside the sandbox,
or run `cad server start` outside it (`client.SANDBOXED`). A daemon
started where it may not bind a loopback port (`daemon._can_listen`, before it makes its door) or
take its lock writes why beside its lock (`engine.failed`, `places.failure_path`) and exits 1;
the client that started it says that reason at once, never after a timeout.

**A hold.** `cad mcp`, the stdio peer an agent host starts, connects to the engine as it starts
(starting it once, as `cad server start` does) and holds it (`client.hold`, `{"op": "hold"}`: a connection the
daemon answers and keeps until its client goes) for as long as the host runs it. While any hold
is open, the engine runs: an update's drain does not wait on a hold, and the host's next request
holds the new release's engine (**Starting and updating**). So a sandboxed shell an agent host runs
finds an engine whenever the host runs. An engine that goes while
held (`cad server stop`, a crash) is held again at the host's next request where one of its release
or a newer one runs, and never started again: a stop is obeyed. A hold names the host it serves (`{"op": "hold", "host": "codex"}`, as `cad_server.mcp.host.family`
names it), and `cad server status --json` says how many hold it (`holders`), per host (`hosts`), and the
environment it runs in (`prefix`): the current installation's, which `cad doctor` names.
