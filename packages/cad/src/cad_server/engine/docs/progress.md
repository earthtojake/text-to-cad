# Progress

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

Every job the engine runs says where it is in one **progress event** (`progress.py`), and nothing
in a model says it: the engine reports what it runs, by name. A job is a build, an import (a STEP a
page first opens), an export, a snapshot, or a measurement (`inspect`'s summary, a volume per part):

```json
{"kind": "build", "stage": "body", "job": "hand.py::hand", "outputs": ["/abs/XBF/hand.xbf"],
 "detail": "middle", "done": 2, "total": null, "elapsedMs": 4120}
```

- `kind`: `build`, `import`, `export`, `snapshot` or `inspect-measure` (`progress.KINDS`).
- `stage`: one of the kind's stages, a closed vocabulary (`progress.STAGES`, below; an unknown kind
  or stage is refused by name, naming the set).
- `job`: what the job is of, as the engine names it -- a build's model as its report does
  (`script::function`, the script alone while it loads); an import's, an export's or a snapshot's
  source file by its name, a held document by its id; a measurement's document by its name.
- `outputs`: the absolute paths of the files the job writes -- a build's declared files, an export's
  destinations, a snapshot's picture; an import and a measurement write none.
- `detail`: a name the engine gives of what is in flight within the stage -- a body's function, the
  file being written, an import's file and its size -- never a sentence, never a model's own words.
- `done` of `total`: the stage's units where it has any; `total` null where they cannot be counted (a
  build's bodies, whose `done` still counts: how many there will be is not known).
- `elapsedMs`: since the job began.

The stages, in the order a job passes them, with the words the engine gives them (`progress.words`,
what a terminal and `cad server status` print); a page says each in its own language by the key
`progress.<kind>.<stage>`:

| `kind` | `stage` | words | counted |
| --- | --- | --- | --- |
| `build` | `load` | Loading the script | -- |
| | `body` | Building geometry | bodies done, of no total; `detail` the innermost body running |
| | `names` | Naming elements | -- |
| | `document` | Making the document | -- |
| | `write` | Writing files | files written of the model's; `detail` the file |
| `import` | `read` | Importing model | -- ; `detail` the file and its size |
| | `collect` | Collecting parts | parts collected of the file's |
| `export` | `read` | Reading the document | -- ; `detail` the file (a held document reads nothing) |
| | `write` | Writing files | destinations written of them all; `detail` the file |
| `snapshot` | `scene` | Making the scene | -- ; a job's pictures of one document say it once |
| | `draw` | Drawing the picture | pictures drawn, where a job draws several |
| | `write` | Writing the picture | pictures written, where a job writes several; `detail` the file |
| `inspect-measure` | `measure` | Measuring parts | parts measured of the document's, as the engine has each (`Server.measure`); `detail` the last one in |

A stage opens with a frame of its own; the frames a stage says as its count moves (a body done, a part
collected or measured) come at least 100 ms apart (`progress.INTERVAL`), the latest held one sent when
the interval is up, so a job of a thousand small steps sends a frame an interval and a job's last
state is always its last frame. The end of a job is no stage: it is the job's answer on the same
channel -- a build's report, the page's `building` null, the verb's `wrote` line, an operation's
`succeeded`. No frame is a guess: a stage is said where the job reaches it, never on a timer, and a
stage with no countable units says its stage alone.

**A build's stages** are said where the build reaches them (`build.py`, through `progress.current`):
`load` (the script loads), `body` (a model's body runs), `names` (its result collected and its
elements named), `document` (its XCAF document made) and `write` (each file written, counted of the
model's files). Inside `body`, each `@memo` call and each child model the body calls is a body of its
own, said where it begins and where it ends by its function's name (`BuildContext.memo` and `child`,
through `Progress.entering` and `leaving`):

```python
@memo
def finger(name): ...                                     # "Building geometry  finger"

@xbf("XBF/hand.xbf")
def hand():
    fingers = [finger(name) for name in FINGERS]
    return bd.Compound(children=[palm(), *fingers], label="hand")
```

While a body runs the detail is its name, the innermost when they nest; when it ends the detail
goes back to the body around it and `done` counts it. A body the memo replays begins and ends too; a
placement of a result this build already made says nothing, and a body that raises says no end, so
the build's last frame names it. The worker sends each frame on its pipe (`{"id", "progress"}`), and
the daemon:

- passes it to the build's caller as it does the log's lines (`client.request(on_progress=)`):
  `python model.py` draws a bar on stderr when it is a terminal -- each
  stage finished a line with its time, the one in flight repainted in place -- and nothing when
  it is not (`progress.Bar`; `api.build_script(progress=)` takes the frames instead, `False` none);
- keeps a busy worker's last, which `cad server status` shows (**The engine server and its workers**);
- wakes the pages waiting on the model document it builds (below); a file among the frame's
  `outputs`, a declared xbf among them, is no document of the build's: its page hears nothing of
  the run and follows the file's bytes;
- sends it on to a build request queued behind it, one of the same script (`Daemon.behind`): a
  rerun after its client was killed (a shell's time limit) waits for the build that client left
  running, nothing cancelled. Its client says so on stderr at once ("waiting for the build of
  turbine.py started 21 s ago"), the frames follow as its own build's would, and its report's
  `waited` (`{"script", "ago", "seconds"}`) ends its line: "took the build of turbine.py it
  waited 206s for" when it takes the document that build made from its key, "replayed ..." when
  the memo replays it.

Each model's report holds its last frame (`progress`), so a failed build
says where it was; a worker that dies during a build fails it with where it was in the words.

**An export's, a snapshot's and a measurement's stages** reach their caller the same way. An export
runs in the worker that holds the document (or the documents worker, which reads a file), under a
job of kind `export` (`worker.job_progress`): `read` as it reads a file source, then `write` for each
destination. A snapshot's are three: `scene` while the document is served, meshed and its scene made,
`draw` while the frame is drawn, `write` as the PNG is written -- said by the worker that holds a
model's document, by the daemon as it draws a file through a render process (`Daemon.draw`,
`renders.Renders.draw`) and by the verb's own process for the write, or wholly in that process
with `daemon=False` (`render.service.draw_here_each`). A measurement's are `inspect`'s summary
measuring a volume per part, in the process that asks (`api._summary`). `cad <type> export`, `cad
snapshot` and `cad <type> inspect` draw them as `python model.py` draws a build's: the one bar, on a
terminal, nothing piped (`api.export(progress=)`, `api.snapshot(progress=)` and
`api.inspect(progress=)` take the frames instead, `False` none, as `build_script` does). A viewer
export's job (`cad_server.jobs`) keeps its worker's latest as its status's `progress` and the stage's
words as its `stage`, and a status asked `after` wakes with each. An export's or a snapshot's frames are the
request's, never its document's build: no page is woken by them (`Daemon.progressed`).

**The page's route.** `GET /api/v1/documents/<id>/version?after=V&progress=N&wait=S` answers
`{"version", "building", "failed", "progress"}` once the version is not `V`, or the
count `progress` is not `N`, or after `S` seconds (60 at most); without `progress=` it waits on
the version alone. `building` is the last frame of the build of the model's document now, null when
none is; `failed` is the last build of it that failed, `{"model", "error", "progress"}` -- its
error, and its last frame -- null once another begins or one succeeds; `progress` is a count that
moves whenever either does. A page sends back the last answer's `progress`, so each frame and the
build's end wake it, and nothing polls. The page says the frame's stage in its language by its key,
with its count (the bundled viewer's `kit/status`). A file names no model, so a run sends its page
nothing; what a file's `building` says is its own **import**: a STEP a page first opens is read in a
reader process (**The server**), and while that runs the server says where it is on the same channel
(`Server.importing`): frames of kind `import`, `read` while the reader parses the file (its detail
`<name> (<size>)`), then `collect` with `done` of `total` as the parts' shapes are collected (the
reader writes its counts to a file the server reads every quarter second while it waits),
`building` null once the document is in, or `failed` with the reader's error. The viewer's
open (`POST /api/v1/documents`) answers `202 {"id", "kind", "api", "state": "reading", "retryMs",
"building"}` with the last frame, and `Retry-After`, while the import
runs, held up to two seconds or until the frame moves, so the page's loading line says each stage as
it comes ("Collecting parts 120/628").
A file's version is its modification time and size: the server
looks at them each time the file is asked for and at least twice a second while a page waits on
it, and reads the file again when they changed -- whatever program wrote it, a model's run writing
the xbf it declares among them: no run sends a file's page anything (**Document lifetime**).
