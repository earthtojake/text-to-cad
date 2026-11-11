---
title: The engine
description: How a model script becomes a document, and how the CAD server builds, keeps, exports and draws it.
---

The engine turns a model script into a **document**, the thing you review in the CAD Viewer. This page explains what happens and why.

## A model is a Python function

A model is a function with no parameters that returns a build123d shape. A decorator says what it is: `@model` for a document with no file, or file decorators such as `@xbf("XBF/arm.xbf")` and `@step("arm.step")` for a document written to those files. Running the script (`cad run arm.py`) calls the function, and the call returns a handle to the document, with its id and its page's URL.

The engine holds the result as an XCAF document, OpenCASCADE's assembly format, with parts, placements, colours, materials and joints. An `.xbf` file is that document saved as it is; STEP, GLB, STL, 3MF and DXF are translations of it.

## The daemon and its workers

The daemon is started by the first command that needs it and runs until `cad stop` or an update. No timer stops it, since you may look at a page for hours.

The daemon never loads the CAD kernel itself. A model is built in a **worker**, a separate process that holds the kernel and its live objects, and the daemon keeps one warm worker per model script and Python:

- At most `CAD_ENGINE_WORKERS` workers run at once (by default, the machine's cores). A new script past that limit takes the standby's slot, else that of the least recently used idle worker no page watches.
- One **standby** worker waits with the kernel loaded: on a 10-core Mac, a new script's first build took about 2.5 seconds in a fresh worker and about 0.2 in the standby.
- Memory retires workers, never a timer. Past a memory cap (by default a quarter of the machine's memory, at least 2 GiB), or under the system's memory pressure, idle workers go, and one whose document a page shows goes last.

Workers run where the kernel is: the base environment, `cad[build123d]`, which uv makes the first time something needs it, the environment `cad run` made for a script's own packages, or the Python a script was run with. `cad status` lists them.

## The memo

Inside a worker, every kernel operation a model runs is keyed by its inputs. On the next build, an unchanged operation hands back the objects the first run made, and a changed one makes everything downstream of it run again. So an edit costs what it changed, and a face keeps its name across edits that leave it alone. A long stage, such as a whole sub-assembly, can be marked `@memo` (from `cad.build123d`) to be replayed whole while its inputs are unchanged.

The engine never watches your files. A document is what its model's last run made, and nothing reruns on its own: when to run the code again is the agent's call.

## Documents and their ids

Every document has one id, a UUID worked out from where it comes from: a model's script and function (or its folder and an explicit `name=`), or a file's path. Any process works out the same id without asking the engine, so a page address, `/<id>`, survives rebuilds.

## Document lifetime

A document outlives the worker that built it, the daemon's memory and the daemon itself. It lives until you delete it with `cad delete` or the Delete action on the viewer's home.

- After 10 seconds with no build or read, the engine saves a model's document to its **document cache**, `documents/<id>/document.xbf` in the cache folder. It also saves when a worker retires, and when the server stops.
- After a restart, a cached document is served from that file, with no run of the script.
- A fresh worker checks the cache before running a model, and takes the document whole when the model's key is unchanged.

The cache has no size cap and no expiry. `cad status` gives each document's state, and for one the cache does not hold, the command that builds it again.

## The build closure

Each model's document carries its **build closure**: paths and digests of what built it, never source. It names the script and function, the modules it imports, the files it read, the library versions (build123d, OCP and the material libraries), the operating system and architecture, and one key over them. That key decides whether a cached document is reused. `cad xbf inspect` prints the closure.

## Exports, the mesh and snapshots

One writer makes every file, whether a decorator declares it or `cad <type> export` asks for it, and a file is replaced only when its bytes change. GLB, STL and 3MF convert into one another, but a mesh has no B-rep (the exact surface description a CAD kernel works with), so no STEP, xbf or DXF is made from one.

The viewer, snapshots and exports share one tessellation, set from each part's own size (a quarter of a per cent of its bounding box's mean side) and an angle of 28.5 degrees. A mesh export can ask for finer, as in `cad model export <id> arm.3mf --tolerance 0.01`, for that file alone. The viewer's Export writes the document as its code built it, never the view's hidden parts or pose.

`cad <type> snapshot` writes a PNG drawn by OpenCASCADE (OCCT) from the engine's meshes, in the viewer's look. No browser draws it, and it is always light, whatever the viewer's theme.

## References and element names

Every face, edge and vertex gets a name from the feature history that made it, such as `f:plate.body.3;M:plate.relief` (face 3 of the body, modified by the relief cut). A dimension edit keeps every name; inserting a feature renames only what it touches.

A **ref** names a part, an assembly or one element: `hand/finger.2/face 7` is face 7 of the second `finger` under `hand`. The viewer copies refs of what you select, and `cad xbf inspect DOC REF` says what one names, including the line of code that made it while its worker lives. Refs resolve against the latest build, and one whose element is gone fails by name.

## The door

Commands and model scripts reach the daemon through its **door**: named pipes in a folder only your user can create. Pipes, because agents often run commands in sandboxes that refuse every socket but let a command open files in its temporary folder. On Windows the door is a loopback port and a port file. Pages and the CAD app use the server's HTTP listener instead ([Security and privacy](/docs/architecture/security)).

## Read more

- [The engine's README](repo:packages/cad-server/src/cad_server/engine/README.md) and [the design laws](repo:packages/cad/README.md) it follows.
- [Environments](repo:skills/cad/references/environments.md): how `cad run` chooses a model's environment.
- [What is installed where](/docs/architecture/installation-layout): where the cache and records live.
